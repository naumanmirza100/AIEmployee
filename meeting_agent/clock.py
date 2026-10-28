"""When an executive meeting really is.

The Executive Meeting agent keeps a meeting's time as it was typed. Its
screens send "11:00" with no zone, the server files that as 11:00 UTC, and the
screens print the same digits back. Inside the agent that is consistent. It is
not the instant the meeting happens for anyone whose clock is not UTC: booked
for 11:00 in Karachi, it is stored as 11:00 UTC, which is 4 pm there.

Anything that compares an executive meeting with something outside the agent
needs the real instant: the calendar every agent shares, the employee's
Meetings page. It is read here on the company's clock (Company profile, time
zone): the digits stored are taken as a time of day there. A company with no
time zone set is read as UTC, which is the instant that was stored.

A company with no time zone set is read on the meeting's own zone instead: the
organiser's browser sends it with the meeting since 28 Oct 2026 (CO-210). Read
as UTC, a new company's 11:00 in Karachi was reminded five hours late.

The agent's reminders, its "this meeting is over" sweep, its emails and its AI
helpers' "today" all go through here (CO-210). They compared the stored time
with the clock, and ran late or early by the company's offset.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo

from django.utils import timezone


def company_zone(company, fallback='') -> str:
    """The company's time zone; when it has none set, `fallback` (a zone sent by the browser), else UTC."""
    from core.scheduling import zone_name
    return zone_name(getattr(company, 'timezone_name', ''), default='') or zone_name(fallback)


def meeting_zone(meeting) -> str:
    """The zone this meeting's typed time is on: the company's, else the one sent with the meeting."""
    return company_zone(meeting.organizer.company, getattr(meeting, 'timezone_name', ''))


def real_instant(stored: datetime | None, company, fallback='') -> datetime | None:
    """The instant meant by a time kept the agent's way, for this company."""
    if stored is None:
        return None
    if timezone.is_naive(stored):
        typed = stored
    else:
        typed = stored.astimezone(dt_timezone.utc).replace(tzinfo=None)
    return typed.replace(tzinfo=ZoneInfo(company_zone(company, fallback)))


def real_start(meeting) -> datetime | None:
    """When this executive meeting really starts."""
    return real_instant(meeting.scheduled_at, meeting.organizer.company, getattr(meeting, 'timezone_name', ''))


def real_end(meeting) -> datetime | None:
    """When it really ends."""
    start = real_start(meeting)
    return start + timedelta(minutes=meeting.duration_minutes or 0) if start else None


def today(company, fallback='') -> date:
    """Today's date on the company's clock: what "today" means to the agent's AI helpers and defaults."""
    return timezone.now().astimezone(ZoneInfo(company_zone(company, fallback))).date()


def today_for(company_id, fallback='') -> date:
    """`today` for the AI helpers, which know only the company's id. They used the server's (UTC) date: after
    7 pm in New York, or before 5 am in Karachi, "tomorrow" was a day off (CO-210)."""
    from core.models import Company
    company = Company.objects.filter(id=company_id).first() if company_id else None
    return today(company, fallback)


def typed_now(company, fallback='') -> datetime:
    """Now, kept the agent's way (the wall-clock digits filed as UTC), to compare with stored times in a query."""
    wall = timezone.now().astimezone(ZoneInfo(company_zone(company, fallback))).replace(tzinfo=None)
    return wall.replace(tzinfo=dt_timezone.utc)


def when_text(meeting) -> str:
    """The meeting's time for an email or alert, with its zone named ("... at 11:00 AM Asia/Karachi").
    The emails printed the typed digits with "UTC" after them."""
    from core.scheduling import when_text as shared_when_text
    zone = meeting_zone(meeting)
    return shared_when_text(real_start(meeting), zone)


def held_on(meeting) -> date:
    """The day a meeting was held, on the company's clock: the day typed for it.

    The note-taker works out "by Friday" from this day. A meeting with no time,
    or one whose notes are written before its day comes, counts as held today."""
    day = timezone.now().astimezone(ZoneInfo(meeting_zone(meeting))).date()
    start = real_start(meeting)
    return min(start.date(), day) if start else day


def resync_company(company) -> int:
    """Rewrite the calendar rows of the company's executive meetings that have
    not ended, at the hours its time zone now gives. Called when that zone
    changes: every one of them moves with it. Returns how many meetings."""
    from core.scheduling.sync import safe_sync
    from meeting_agent.models import ExecutiveMeeting

    # A day of margin either side of now covers any offset between the two readings.
    recent = timezone.now() - timedelta(days=2)
    meetings = (ExecutiveMeeting.objects.filter(organizer__company=company, scheduled_at__gte=recent)
                .select_related('organizer__company'))
    count = 0
    for meeting in meetings.iterator(chunk_size=200):
        safe_sync('exec', meeting)
        count += 1
    return count
