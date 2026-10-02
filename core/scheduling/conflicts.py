"""The clash check every scheduler runs before it books or moves a meeting.

Policy (agreed 2026-09-17): a clash is shown as a warning and the booking is
refused — there is no override. Pending invitations count as busy.

Usage, from any agent:

    with booking_guard(user_ids):
        ensure_free(user_ids, start, duration, viewer_source='hr', tz_name=tz)
        meeting = HRMeeting.objects.create(...)   # blocks are written by signal

`ensure_free` raises `ScheduleConflict`, whose `.response()` is the HTTP 409
the API returns and whose `.markdown()` is what the chat schedulers reply.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from datetime import timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from core.scheduling.sources import SOURCES

WORK_START_HOUR = 9
WORK_END_HOUR = 18
SLOT_STEP_MINUTES = 30

_RESPONSE_LABELS = {
    'pending': 'invitation pending',
    'accepted': 'accepted',
    'counter_proposed': 'new time proposed',
    'organizer': 'organizing',
    'scheduled': 'scheduled',
    'on_leave': 'on leave',
}

# Busy time that isn't a meeting reads differently: "Ali is on leave 6–8 Oct",
# "Mon Oct 06 is a company holiday (Eid)".
_OFF_LABELS = {'leave': 'Leave', 'holiday': 'Company holiday'}


def zone_info(tz_name):
    """ZoneInfo for a timezone name, falling back to UTC for anything invalid."""
    from zoneinfo import ZoneInfo
    try:
        return ZoneInfo((tz_name or 'UTC').strip() or 'UTC')
    except Exception:
        return ZoneInfo('UTC')


def clock_label(dt):
    """'3:00 PM' — strftime's %-I isn't available on Windows."""
    return f"{dt:%I:%M %p}".lstrip('0')


def zone_caption(tz_name, at=None) -> str:
    """'Asia/Karachi (UTC+05:00)'. The offset is the one in force at `at`."""
    moment = (at or timezone.now()).astimezone(zone_info(tz_name))
    offset = moment.strftime('%z')
    offset = f"UTC{offset[:3]}:{offset[3:]}" if offset else 'UTC'
    return tz_name if tz_name == 'UTC' else f"{tz_name} ({offset})"


def when_label(dt, tz_name) -> str:
    """'Monday, October 06, 2026 at 10:00 AM (Asia/Karachi, UTC+05:00)' — an
    instant on `tz_name`'s clock, saying which zone that is."""
    moment = _aware(dt).astimezone(zone_info(tz_name))
    zone = zone_caption(tz_name, dt).replace(' (', ', ').rstrip(')')
    return f"{moment:%A, %B %d, %Y} at {clock_label(moment)} ({zone})"


def _aware(dt):
    return timezone.make_aware(dt, dt_timezone.utc) if timezone.is_naive(dt) else dt


def _exclude_q(exclude) -> Q:
    """`exclude` is an iterable of (source, meeting_id) pairs — the meeting(s)
    being edited, which must not clash with themselves."""
    by_source: dict[str, set] = {}
    for source, meeting_id in exclude or ():
        if meeting_id:
            by_source.setdefault(source, set()).add(meeting_id)
    q = Q()
    for source, ids in by_source.items():
        q |= Q(source=source, source_id__in=ids)
    return q


def _busy_blocks(user_ids, start, end, exclude=()):
    from core.models import CalendarBlock
    ids = {int(u) for u in user_ids if u}
    if not ids:
        return CalendarBlock.objects.none()
    qs = CalendarBlock.objects.filter(user_id__in=ids, ends_at__gt=start, starts_at__lt=end)
    skip = _exclude_q(exclude)
    if skip:
        qs = qs.exclude(skip)
    return qs


@dataclass
class Clash:
    user_id: int
    user_name: str
    source: str
    source_id: int
    title: str | None          # None when the meeting is private to another agent
    starts_at: datetime
    ends_at: datetime
    response: str

    @property
    def source_label(self):
        if self.source in _OFF_LABELS:
            return _OFF_LABELS[self.source]
        return SOURCES[self.source].label if self.source in SOURCES else 'meeting'

    def describe(self, tz_name='UTC') -> str:
        zone = zone_info(tz_name)
        s, e = self.starts_at.astimezone(zone), self.ends_at.astimezone(zone)
        if self.source == 'holiday':
            return f'{s:%a %b %d} is a company holiday' + (f' ({self.title})' if self.title else '')
        if self.source == 'leave':
            last = (e - timedelta(microseconds=1))
            days = f'{s:%a %b %d}' if last.date() == s.date() else f'{s:%a %b %d}–{last:%a %b %d}'
            half = ' (half day)' if (e - s) < timedelta(hours=20) else ''
            return f'{self.user_name} is on leave {days}{half}'
        span = f"{s:%a %b %d}, {clock_label(s)}–{clock_label(e)}"
        what = self.source_label
        state = _RESPONSE_LABELS.get(self.response)
        detail = f"{what}, {state}" if state else what
        if self.title:
            return f'{self.user_name} is busy {span} — "{self.title}" ({detail})'
        return f'{self.user_name} is busy {span} ({detail})'

    def as_dict(self):
        return {
            'user_id': self.user_id,
            'user_name': self.user_name,
            'source': self.source,
            'source_label': self.source_label,
            'meeting_id': self.source_id,
            'title': self.title,
            'starts_at': self.starts_at.isoformat(),
            'ends_at': self.ends_at.isoformat(),
            'response': self.response,
        }


def _company_ids_for(user_ids) -> set[int]:
    from core.models import UserProfile
    ids = {int(u) for u in user_ids if u}
    if not ids:
        return set()
    rows = UserProfile.objects.filter(user_id__in=ids).values_list(
        'company_id', 'created_by_company_user__company_id')
    return {c for pair in rows for c in pair if c}


def holiday_intervals(user_ids, start, end, tz_name='UTC') -> list[tuple[datetime, datetime, str]]:
    """(starts, ends, name) of each company-wide day off that overlaps
    [start, end) for these people's companies. A holiday is a date, so it is
    read in `tz_name` — the zone the booking is being made in. Regional
    holidays and working "bridge" days don't count."""
    try:
        from hr_agent.models import Holiday
    except ImportError:  # pragma: no cover — HR app not installed
        return []
    companies = _company_ids_for(user_ids)
    if not companies:
        return []
    zone = zone_info(tz_name)
    first = _aware(start).astimezone(zone).date()
    last = (_aware(end) - timedelta(microseconds=1)).astimezone(zone).date()
    out = []
    for day, name in (Holiday.objects.filter(company_id__in=companies, region='', is_working_day=False,
                                             date__range=(first, last))
                      .order_by('date').values_list('date', 'name').distinct()):
        begins = datetime.combine(day, time(0), tzinfo=zone)
        out.append((begins, begins + timedelta(days=1), name))
    return out


def find_conflicts(user_ids, start, end, *, exclude=(), viewer_source=None,
                   reveal_private=False, hide_titles=False, tz_name=None) -> list[Clash]:
    """Every busy block that overlaps [start, end) for any of `user_ids`,
    and, when `tz_name` says which day it is, any company holiday.

    A private meeting's title is shown only to its own agent, and only when
    the caller says the viewer may see it (`reveal_private`); everyone else
    sees just "busy (HR meeting)". `hide_titles` hides every title — for
    employees, who may learn that a colleague is busy but not with what.
    """
    start, end = _aware(start), _aware(end)
    clashes = []
    for block in _busy_blocks(user_ids, start, end, exclude).select_related('user').order_by('starts_at', 'user_id'):
        visible = not hide_titles and (
            not block.is_private or (reveal_private and block.source == viewer_source))
        user = block.user
        clashes.append(Clash(
            user_id=block.user_id,
            user_name=(user.get_full_name() or user.username or f'User {block.user_id}').strip(),
            source=block.source,
            source_id=block.source_id,
            title=(block.title or None) if visible else None,
            starts_at=block.starts_at,
            ends_at=block.ends_at,
            response=block.response,
        ))
    if tz_name is not None:
        for begins, ends, name in holiday_intervals(user_ids, start, end, tz_name):
            clashes.append(Clash(user_id=0, user_name='Everyone', source='holiday', source_id=0,
                                 title=name, starts_at=begins, ends_at=ends, response='holiday'))
    return clashes


def busy_intervals(user_ids, start, end, *, exclude=(), tz_name=None) -> list[tuple[datetime, datetime]]:
    """(starts_at, ends_at) of every busy block for `user_ids` overlapping
    [start, end) — for checking many candidate times with one query. With
    `tz_name`, company holidays are included."""
    busy = list(_busy_blocks(user_ids, _aware(start), _aware(end), exclude)
                .values_list('starts_at', 'ends_at'))
    if tz_name is not None:
        busy += [(s, e) for s, e, _ in holiday_intervals(user_ids, start, end, tz_name)]
    return busy


def overlaps(intervals, start, end) -> bool:
    return any(s < end and e > start for s, e in intervals)


def free_slots(user_ids, day: date, duration_minutes, tz_name='UTC', *, exclude=(),
               limit=6, not_before=None) -> list[datetime]:
    """Start times on `day` (working hours in `tz_name`) when everyone is free."""
    zone = zone_info(tz_name)
    duration = timedelta(minutes=max(1, int(duration_minutes or 30)))
    day_start = datetime.combine(day, time(WORK_START_HOUR), tzinfo=zone)
    day_end = datetime.combine(day, time(WORK_END_HOUR), tzinfo=zone)
    if holiday_intervals(user_ids, day_start, day_end, tz_name):
        return []   # a company holiday: nobody is offered a time that day
    busy = list(_busy_blocks(user_ids, day_start, day_end, exclude).values_list('starts_at', 'ends_at'))
    earliest = max(timezone.now(), _aware(not_before)) if not_before else timezone.now()

    slots, cursor = [], day_start
    while cursor + duration <= day_end and len(slots) < limit:
        end = cursor + duration
        if cursor >= earliest and not any(s < end and e > cursor for s, e in busy):
            slots.append(cursor)
        cursor += timedelta(minutes=SLOT_STEP_MINUTES)
    return slots


def suggest_slots(user_ids, around: datetime, duration_minutes, tz_name='UTC', *,
                  exclude=(), limit=6, days_ahead=7) -> list[datetime]:
    """Free start times on the requested day, then on following weekdays,
    until `limit` are found."""
    zone = zone_info(tz_name)
    first_day = _aware(around).astimezone(zone).date()
    found = []
    for offset in range(days_ahead + 1):
        day = first_day + timedelta(days=offset)
        if offset and day.weekday() >= 5:
            continue
        found += free_slots(user_ids, day, duration_minutes, tz_name, exclude=exclude,
                            limit=limit - len(found))
        if len(found) >= limit:
            break
    return found


class ScheduleConflict(Exception):
    """Raised when a booking would double-book someone. The booking must not
    be saved."""

    code = 'schedule_conflict'

    def __init__(self, clashes, suggestions=(), tz_name='UTC'):
        self.clashes = list(clashes)
        self.suggestions = list(suggestions)
        self.tz_name = tz_name or 'UTC'
        super().__init__(self.text())

    def _slot_label(self, dt, previous_day):
        local = dt.astimezone(zone_info(self.tz_name))
        return clock_label(local) if local.date() == previous_day else f"{local:%a %b %d} {clock_label(local)}"

    def _slots_text(self):
        labels, day = [], None
        for dt in self.suggestions:
            labels.append(self._slot_label(dt, day))
            day = dt.astimezone(zone_info(self.tz_name)).date()
        return ', '.join(labels)

    def _unique_lines(self):
        seen, lines = set(), []
        for clash in self.clashes:
            line = clash.describe(self.tz_name)
            if line not in seen:
                seen.add(line)
                lines.append(line)
        return lines

    def text(self) -> str:
        lines = self._unique_lines()
        msg = "Can't schedule: " + '; '.join(lines[:5])
        if len(lines) > 5:
            msg += f'; and {len(lines) - 5} more'
        msg += '.'
        if self.suggestions:
            msg += f' Times when everyone is free ({self.tz_name}): {self._slots_text()}.'
        else:
            msg += ' Please pick a different time.'
        return msg

    def markdown(self) -> str:
        lines = self._unique_lines()
        out = ["⚠️ **Can't schedule this meeting — someone is already busy.**", '']
        out += [f'- {line}' for line in lines[:10]]
        if len(lines) > 10:
            out.append(f'- …and {len(lines) - 10} more')
        if self.suggestions:
            out += ['', f'**Times when everyone is free** ({self.tz_name}):']
            out += [f'- {self._slot_label(dt, None)}' for dt in self.suggestions]
        else:
            out += ['', 'Please pick a different time.']
        return '\n'.join(out)

    def payload(self) -> dict:
        return {
            'status': 'error',
            'code': self.code,
            'message': self.text(),
            'data': {
                'conflicts': [c.as_dict() for c in self.clashes],
                'suggested_slots': [dt.isoformat() for dt in self.suggestions],
                'timezone': self.tz_name,
            },
        }

    def response(self):
        from rest_framework import status
        from rest_framework.response import Response
        return Response(self.payload(), status=status.HTTP_409_CONFLICT)


def ensure_free(user_ids, starts, duration_minutes, *, tz_name='UTC', exclude=(),
                viewer_source=None, reveal_private=False, hide_titles=False,
                suggest=True) -> None:
    """Raise ScheduleConflict if any of `user_ids` is busy.

    `starts` is one datetime, or a list of them for a recurring series — every
    occurrence is checked and the whole series is refused if any one clashes.
    """
    if isinstance(starts, datetime):
        starts = [starts]
    starts = [_aware(s) for s in starts if s is not None]
    duration = timedelta(minutes=max(1, int(duration_minutes or 30)))
    clashes, clashing_starts = [], []
    for start in starts:
        found = find_conflicts(user_ids, start, start + duration, exclude=exclude,
                               viewer_source=viewer_source, reveal_private=reveal_private,
                               hide_titles=hide_titles, tz_name=tz_name)
        if found:
            clashes += found
            clashing_starts.append(start)
    if not clashes:
        return
    suggestions = []
    if suggest:
        # Offer times on the day of the earliest occurrence that clashed.
        suggestions = suggest_slots(user_ids, min(clashing_starts), duration_minutes, tz_name,
                                    exclude=exclude)
    raise ScheduleConflict(clashes, suggestions, tz_name)


def lock_people(user_ids) -> None:
    """Serialize bookings that involve the same people.

    Row locks on the users, always taken in id order so two bookings can't
    deadlock each other. Must run inside a transaction; the locks are released
    at commit, by which point the new meeting's blocks are written.
    """
    ids = sorted({int(u) for u in user_ids if u})
    if ids:
        list(get_user_model().objects.select_for_update()
             .filter(pk__in=ids).order_by('pk').values_list('pk', flat=True))


@contextmanager
def booking_guard(user_ids):
    """Transaction + people locks around a check-then-book sequence."""
    with transaction.atomic():
        lock_people(user_ids)
        yield
