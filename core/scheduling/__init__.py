"""One calendar across the PM, HR and Frontline agents.

Each agent keeps its own meeting table; `core.models.CalendarBlock` holds every
employee's busy time from all three, so any agent can refuse a booking that
would double-book someone, whichever agent made the other booking.

    sync       keeps CalendarBlock in step with the meeting tables (signals)
    conflicts  the clash check, free-time suggestions and booking lock
    sources    per-agent rules for who is busy
    identity   maps each agent's attendees onto employee logins

Design: MDS/MEETING_CONFLICTS_ACROSS_AGENTS.md
"""
from core.scheduling.conflicts import (  # noqa: F401
    Clash,
    ScheduleConflict,
    booking_guard,
    ensure_free,
    find_conflicts,
    free_slots,
    lock_people,
    suggest_slots,
)
from core.scheduling.identity import login_user_id_for_company_user  # noqa: F401
from core.scheduling.sources import people_for  # noqa: F401
from core.scheduling.sync import rebuild, sync_meeting  # noqa: F401


def zone_name(raw, default='UTC') -> str:
    """A valid IANA timezone name from untrusted input, else `default`."""
    from zoneinfo import ZoneInfo
    name = str(raw or '').strip()[:64]
    if not name:
        return default
    try:
        ZoneInfo(name)
    except Exception:
        return default
    return name
