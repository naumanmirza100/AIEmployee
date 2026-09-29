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


import re as _re

# A length of time in the user's own words: "30 min", "1.5 hours", "2h",
# "30-minute", "half an hour", "an hour", "hour-long". Clock times ("3pm",
# "10:30") say when, not how long, and deliberately don't match.
_DURATION_RE = _re.compile(
    r"\b\d+(?:\.\d+)?\s*-?\s*(?:m|min|mins|minute|minutes|h|hr|hrs|hour|hours)\b"
    r"|\b(?:half|quarter)\s+(?:of\s+)?(?:an\s+)?hour\b"
    r"|\b(?:an|one|two|three)\s+hours?\b"
    r"|\bhour[-\s]long\b",
    _re.IGNORECASE,
)


def duration_mentioned(text) -> bool:
    """Did the user say how long the meeting is?

    The schedulers' prompts have the model default a length when none is
    given, so the parsed number can't tell "30, as I said" from "I never said".
    The raw words can — and a meeting scheduler should ask rather than assume.
    """
    return bool(text and _DURATION_RE.search(str(text)))


def in_zone(value, tz_name):
    """`value` as an aware datetime, reading a naive one in `tz_name`.

    The schedulers ask the model for wall-clock time in the user's own zone,
    because it cannot reliably convert "3 PM" to UTC — it isn't told, and isn't
    good at, the offset. A naive result is therefore the user's local time,
    not UTC. Returns None for anything unparseable.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).strip().replace('Z', '+00:00'))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(zone_name(tz_name)))
    return dt


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
