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

The agent's own reminders and its "this meeting is over" sweep still compare
the stored time with the clock, and so run late or early by the company's
offset. That is a fault of its own, older than this module.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo

from django.utils import timezone


def company_zone(company) -> str:
    """The company's time zone, or UTC when it has none set."""
    from core.scheduling import zone_name
    return zone_name(getattr(company, 'timezone_name', ''))


def real_instant(stored: datetime | None, company) -> datetime | None:
    """The instant meant by a time kept the agent's way, for this company."""
    if stored is None:
        return None
    if timezone.is_naive(stored):
        typed = stored
    else:
        typed = stored.astimezone(dt_timezone.utc).replace(tzinfo=None)
    return typed.replace(tzinfo=ZoneInfo(company_zone(company)))


def real_start(meeting) -> datetime | None:
    """When this executive meeting really starts."""
    return real_instant(meeting.scheduled_at, meeting.organizer.company)


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
