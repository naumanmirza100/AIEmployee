"""Per-agent rules: for one meeting, who is busy and when.

Each source turns one meeting row into a `Booking` — the time window plus the
people it occupies — or None when the meeting no longer occupies anyone
(declined, withdrawn, cancelled, completed). `sync` writes the result to
`CalendarBlock`; `people_for` uses the same rules to decide whom to check
before a meeting moves to a new time.

Pending invitations count as busy on purpose (product decision 2026-09-17): a
slot someone has been invited to is not free for a second booking until they
decline it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from core.scheduling.identity import login_user_id_for_company_user, login_user_ids_for_employees

# Participant states that keep a seat busy. Declined ('rejected') frees it.
BUSY_RESPONSES = ('pending', 'accepted', 'counter_proposed')

ORGANIZER = 'organizer'
PARTICIPANT = 'participant'


@dataclass(frozen=True)
class Seat:
    user_id: int
    role: str
    response: str


@dataclass
class Booking:
    company_id: int | None
    starts_at: datetime
    ends_at: datetime
    title: str = ''
    is_private: bool = False
    seats: list[Seat] = field(default_factory=list)

    def add(self, user_id, role, response):
        if user_id:
            self.seats.append(Seat(int(user_id), role, response))

    def unique_seats(self) -> list[Seat]:
        """One seat per person. Someone who organizes and also sits in the
        participant list is recorded once, as the organizer."""
        by_user: dict[int, Seat] = {}
        for seat in self.seats:
            current = by_user.get(seat.user_id)
            if current is None or (seat.role == ORGANIZER and current.role != ORGANIZER):
                by_user[seat.user_id] = seat
        return list(by_user.values())


def _window(start, minutes):
    return start, start + timedelta(minutes=max(1, int(minutes or 30)))


class Source:
    key = ''
    label = ''
    model_label = ''
    # Saves limited to other fields (notes, reminder flags, …) can't change who
    # is busy, so they skip the resync. Background reminder jobs save that way.
    relevant_fields: frozenset = frozenset()
    participant_model_label = ''

    @property
    def model(self):
        from django.apps import apps
        return apps.get_model(self.model_label)

    @property
    def participant_model(self):
        from django.apps import apps
        return apps.get_model(self.participant_model_label)

    def booking(self, meeting, *, assume_active=False, include_declined=False) -> Booking | None:
        """`assume_active` ignores the meeting-level status (cancelled,
        withdrawn, …) and `include_declined` keeps seats that were declined.
        Both answer "who would this meeting occupy at a new time?" before a
        change that revives or moves it."""
        raise NotImplementedError

    def upcoming(self, since, company_id=None):
        """Meetings whose blocks the nightly rebuild should recompute."""
        raise NotImplementedError


class ProjectManagerSource(Source):
    key = 'pm'
    label = 'Project Manager meeting'
    model_label = 'project_manager_agent.ScheduledMeeting'
    participant_model_label = 'project_manager_agent.MeetingParticipant'
    relevant_fields = frozenset({'proposed_time', 'duration_minutes', 'status', 'title',
                                 'invitee', 'invitee_id', 'organizer', 'organizer_id'})

    def booking(self, m, *, assume_active=False, include_declined=False):
        if m.proposed_time is None or (not assume_active and m.status in ('rejected', 'withdrawn')):
            return None
        organizer = m.organizer
        starts, ends = _window(m.proposed_time, m.duration_minutes)
        b = Booking(company_id=organizer.company_id, starts_at=starts, ends_at=ends,
                    title=m.title or '')
        rows = list(self.participant_model.objects
                    .filter(meeting_id=m.pk).values_list('user_id', 'status'))
        if rows:
            for user_id, response in rows:
                if include_declined or response in BUSY_RESPONSES:
                    b.add(user_id, PARTICIPANT, response)
        elif m.invitee_id:
            # Single-invitee meetings from before MeetingParticipant existed.
            b.add(m.invitee_id, PARTICIPANT, 'accepted' if m.status == 'accepted' else 'pending')
        b.add(login_user_id_for_company_user(organizer), ORGANIZER, ORGANIZER)
        return b

    def upcoming(self, since, company_id=None):
        # A meeting can run up to a day, so start the window a day early.
        qs = self.model.objects.filter(proposed_time__gte=since - timedelta(days=1))
        if company_id:
            qs = qs.filter(organizer__company_id=company_id)
        return qs.select_related('organizer')


class HRSource(Source):
    key = 'hr'
    label = 'HR meeting'
    model_label = 'hr_agent.HRMeeting'
    participant_model_label = 'hr_agent.HRMeetingParticipant'
    relevant_fields = frozenset({'scheduled_at', 'duration_minutes', 'status', 'response_status',
                                 'title', 'visibility', 'organizer', 'organizer_id',
                                 'company', 'company_id'})

    def booking(self, m, *, assume_active=False, include_declined=False):
        if m.scheduled_at is None:
            return None
        if not assume_active and (m.status in ('cancelled', 'completed')
                                  or m.response_status in ('withdrawn', 'rejected')):
            return None
        starts, ends = _window(m.scheduled_at, m.duration_minutes)
        b = Booking(company_id=m.company_id, starts_at=starts, ends_at=ends,
                    title=m.title or '', is_private=(m.visibility == 'private'))
        rows = [(emp_id, response) for emp_id, response in
                self.participant_model.objects.filter(meeting_id=m.pk)
                    .values_list('employee_id', 'status')
                if include_declined or response in BUSY_RESPONSES]
        logins = login_user_ids_for_employees([e for e, _ in rows] + [m.organizer_id])
        for emp_id, response in rows:
            b.add(logins.get(emp_id), PARTICIPANT, response)
        if m.organizer_id:
            b.add(logins.get(m.organizer_id), ORGANIZER, ORGANIZER)
        return b

    def upcoming(self, since, company_id=None):
        qs = self.model.objects.filter(scheduled_at__gte=since - timedelta(days=1))
        if company_id:
            qs = qs.filter(company_id=company_id)
        return qs


class FrontlineSource(Source):
    key = 'frontline'
    label = 'Frontline meeting'
    model_label = 'Frontline_agent.FrontlineMeeting'
    relevant_fields = frozenset({'scheduled_at', 'duration_minutes', 'status', 'title',
                                 'organizer', 'organizer_id', 'company', 'company_id'})

    def booking(self, m, *, assume_active=False, include_declined=False):
        if not m.company_id or m.scheduled_at is None:
            return None
        if not assume_active and m.status not in ('scheduled', 'rescheduled'):
            return None
        starts, ends = _window(m.scheduled_at, m.duration_minutes)
        b = Booking(company_id=m.company_id, starts_at=starts, ends_at=ends, title=m.title or '')
        # Frontline has no accept/decline step: an attendee is booked from creation.
        for user_id in m.participants.values_list('id', flat=True):
            b.add(user_id, PARTICIPANT, 'scheduled')
        # The organizer is stored as an auth.User. For dashboard logins without an
        # employee account that is a password-less stand-in, which `sync` drops
        # because it isn't a company member.
        b.add(m.organizer_id, ORGANIZER, ORGANIZER)
        return b

    def upcoming(self, since, company_id=None):
        qs = self.model.objects.filter(scheduled_at__gte=since - timedelta(days=1))
        if company_id:
            qs = qs.filter(company_id=company_id)
        return qs


SOURCES: dict[str, Source] = {s.key: s for s in (ProjectManagerSource(), HRSource(), FrontlineSource())}


def people_for(source_key: str, meeting, *, include_declined=False) -> list[int]:
    """Employee logins a meeting occupies (or would, if it were active) —
    the people to check before moving it to a new time.

    Pass `include_declined=True` when the move resets everyone's answer to
    pending (HR does), since the people who declined become busy again.
    """
    from core.scheduling.identity import member_ids
    booking = SOURCES[source_key].booking(meeting, assume_active=True,
                                          include_declined=include_declined)
    if booking is None or not booking.company_id:
        return []
    ids = {seat.user_id for seat in booking.seats}
    return sorted(member_ids(booking.company_id, ids))
