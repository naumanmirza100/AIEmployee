"""
Shared per-company Google Calendar / Google Meet helper.

A company connects its own Google account once (Company Profile → Integrations),
which stores a refresh token on ``Company.google_calendar_config``. Any agent
(recruitment interviews, SDR meetings, …) can then create a Calendar event with
a Google Meet link on that company's calendar through the functions here —
so the OAuth wiring lives in exactly one place and both agents behave the same.

There is no global-env refresh-token fallback: a company that hasn't connected
simply gets ``None`` back and the caller falls back to Jitsi.

An event used to be created once and then forgotten: its id was not kept and
nothing ever updated or deleted one, so an interview that moved or was called
off stayed in Google at its old time. A meeting row now keeps its event's id
and the time the event stands at (``google_event_id``, ``google_event_state``),
and ``follow`` brings the event back in step after any change.

Nothing here raises. A failure at Google must never stop a meeting being
booked, moved or cancelled in the product.
"""
import logging
import uuid
from datetime import timedelta
from typing import Optional

from django.conf import settings

logger = logging.getLogger(__name__)


def is_google_connected(company) -> bool:
    """True when this company has a usable Google Calendar connection.

    Mirrors the ``connected`` flag the status endpoint reports: both the
    ``connected`` marker and a stored ``refresh_token`` must be present.
    """
    cfg = (getattr(company, 'google_calendar_config', None) or {}) if company else {}
    return bool(cfg.get('connected') and cfg.get('refresh_token'))


def _calendar(company):
    """(service, calendar id) for the company's connected calendar, or None
    when it has not connected, the platform OAuth app is not configured, or the
    google client libraries are missing. May raise on a network or auth error;
    every caller below catches."""
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:
        logger.warning("google-auth / google-api-python-client not installed — skipping Google Calendar.")
        return None

    client_id = getattr(settings, 'GOOGLE_CLIENT_ID', '')
    client_secret = getattr(settings, 'GOOGLE_CLIENT_SECRET', '')
    cfg = (getattr(company, 'google_calendar_config', None) or {}) if company else {}
    refresh_token = cfg.get('refresh_token', '')
    if not cfg.get('connected') or not refresh_token:
        logger.info("Company has not connected Google Calendar — skipping.")
        return None
    if not all([client_id, client_secret]):
        logger.warning("Google OAuth app not configured on server — skipping Google Calendar.")
        return None

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
        token_uri='https://oauth2.googleapis.com/token',
        scopes=['https://www.googleapis.com/auth/calendar'],
    )
    # Explicitly mint an access token from the refresh token before calling.
    creds.refresh(Request())
    service = build('calendar', 'v3', credentials=creds, cache_discovery=False)
    return service, (cfg.get('calendar_id') or 'primary')


def _times(start_dt, duration_minutes):
    end_dt = start_dt + timedelta(minutes=duration_minutes or 30)
    return {'start': {'dateTime': start_dt.isoformat(), 'timeZone': 'UTC'},
            'end': {'dateTime': end_dt.isoformat(), 'timeZone': 'UTC'}}


def event_state(start_dt, duration_minutes) -> str:
    """What an event stands at, as kept in ``google_event_state``: when it
    starts and how long it runs. Two states differ when the event must move."""
    return f"{start_dt.isoformat() if start_dt else ''}|{int(duration_minutes or 30)}"


def create_google_event(
    company,
    *,
    start_dt,
    duration_minutes: int = 30,
    summary: str = 'Meeting',
    description: str = '',
    attendee_email: str = '',
) -> Optional[dict]:
    """Create a Google Calendar event with a Meet link on ``company``'s calendar.

    Returns ``{'event_id', 'meet_url'}``, or ``None`` when the company hasn't
    connected Google Calendar, the platform OAuth app isn't configured, the
    google client libraries are missing, or the API call fails — so callers can
    fall back to Jitsi. Never raises.

    The load-bearing bits are ``conferenceData.createRequest`` with
    ``conferenceSolutionKey.type == 'hangoutsMeet'`` plus ``conferenceDataVersion=1``
    on the insert — without both, Google creates the event but no Meet link.
    """
    try:
        calendar = _calendar(company)
        if calendar is None:
            return None
        service, calendar_id = calendar
        event = {
            'summary': summary or 'Meeting',
            'description': description or '',
            **_times(start_dt, duration_minutes),
            'conferenceData': {
                'createRequest': {
                    'requestId': str(uuid.uuid4()),
                    'conferenceSolutionKey': {'type': 'hangoutsMeet'},
                }
            },
        }
        if attendee_email:
            event['attendees'] = [{'email': attendee_email}]

        created = service.events().insert(
            calendarId=calendar_id,
            body=event,
            conferenceDataVersion=1,
            sendUpdates='none',
        ).execute()

        meet_url = created.get('hangoutLink') or ''
        logger.info("Google Meet link created: %s", meet_url)
        return {'event_id': created.get('id') or '', 'meet_url': meet_url}
    except Exception as exc:
        logger.error("Failed to create Google Meet link: %s", exc, exc_info=True)
        logger.error("The company may need to reconnect Google Calendar, or the Calendar API may be disabled.")
        return None


def create_google_meet_link(company, **kwargs) -> Optional[str]:
    """The Meet URL of a new event, or ``None``. For a caller that does not
    keep the event; one that does should use ``create_google_event``."""
    created = create_google_event(company, **kwargs)
    return (created or {}).get('meet_url') or None


def _gone(exc) -> bool:
    """Did Google say the event no longer exists? Then there is nothing left
    to move or delete, which is as good as done."""
    status = getattr(getattr(exc, 'resp', None), 'status', None)
    return str(status) in ('404', '410')


def update_google_event(company, event_id, *, start_dt, duration_minutes: int = 30) -> bool:
    """Move an event to a new time or length. True when Google has it at that
    time now. Never raises."""
    if not event_id:
        return False
    try:
        calendar = _calendar(company)
        if calendar is None:
            return False
        service, calendar_id = calendar
        service.events().patch(calendarId=calendar_id, eventId=event_id,
                               body=_times(start_dt, duration_minutes), sendUpdates='none').execute()
        return True
    except Exception as exc:
        logger.warning("Could not move Google event %s: %s", event_id, exc)
        return False


def delete_google_event(company, event_id) -> bool:
    """Remove an event. True when it is gone from Google, including when it
    already was. Never raises."""
    if not event_id:
        return False
    try:
        calendar = _calendar(company)
        if calendar is None:
            return False
        service, calendar_id = calendar
        service.events().delete(calendarId=calendar_id, eventId=event_id, sendUpdates='none').execute()
        return True
    except Exception as exc:
        if _gone(exc):
            return True
        logger.warning("Could not delete Google event %s: %s", event_id, exc)
        return False


def follow(meeting, *, company, start_dt, duration_minutes, active) -> str:
    """Bring a meeting's Google event back in step with the meeting.

    ``meeting`` is any row with ``google_event_id`` and ``google_event_state``.
    If the meeting is off (``active`` false, or it has no time) the event is
    deleted and forgotten. If its time or length differs from what the event
    stands at, the event is moved. Otherwise nothing is asked of Google.

    Safe to call after every save: it does nothing for a meeting with no
    event, or one whose event is already right. If Google cannot be reached
    the row is left as it was, so the next call tries again.

    Returns what it did: '' (nothing to do), 'moved', 'removed' or 'failed'.
    """
    event_id = getattr(meeting, 'google_event_id', '') or ''
    if not event_id:
        return ''
    rows = type(meeting).objects.filter(pk=meeting.pk)
    if not active or start_dt is None:
        if not delete_google_event(company, event_id):
            return 'failed'
        rows.update(google_event_id='', google_event_state='')
        meeting.google_event_id = meeting.google_event_state = ''
        return 'removed'
    state = event_state(start_dt, duration_minutes)
    if meeting.google_event_state == state:
        return ''
    if not update_google_event(company, event_id, start_dt=start_dt, duration_minutes=duration_minutes):
        return 'failed'
    rows.update(google_event_state=state)
    meeting.google_event_state = state
    return 'moved'
