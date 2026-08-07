"""
Shared per-company Google Calendar / Google Meet helper.

A company connects its own Google account once (Company Profile → Integrations),
which stores a refresh token on ``Company.google_calendar_config``. Any agent
(recruitment interviews, SDR meetings, …) can then create a Calendar event with
a Google Meet link on that company's calendar through the two functions here —
so the OAuth wiring lives in exactly one place and both agents behave the same.

There is no global-env refresh-token fallback: a company that hasn't connected
simply gets ``None`` back and the caller falls back to Jitsi.
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


def create_google_meet_link(
    company,
    *,
    start_dt,
    duration_minutes: int = 30,
    summary: str = 'Meeting',
    description: str = '',
    attendee_email: str = '',
) -> Optional[str]:
    """Create a Google Calendar event with a Meet link on ``company``'s calendar.

    Returns the Google Meet URL, or ``None`` when the company hasn't connected
    Google Calendar, the platform OAuth app isn't configured, the google client
    libraries are missing, or the API call fails — so callers can fall back to
    Jitsi. Never raises.

    The load-bearing bits are ``conferenceData.createRequest`` with
    ``conferenceSolutionKey.type == 'hangoutsMeet'`` plus ``conferenceDataVersion=1``
    on the insert — without both, Google creates the event but no Meet link.
    """
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        client_id     = getattr(settings, 'GOOGLE_CLIENT_ID', '')
        client_secret = getattr(settings, 'GOOGLE_CLIENT_SECRET', '')

        cfg = (getattr(company, 'google_calendar_config', None) or {}) if company else {}
        refresh_token = cfg.get('refresh_token', '')
        calendar_id   = cfg.get('calendar_id') or 'primary'

        if not cfg.get('connected') or not refresh_token:
            logger.info("Company has not connected Google Calendar — skipping Meet link.")
            return None
        if not all([client_id, client_secret]):
            logger.warning("Google OAuth app not configured on server — skipping Meet link creation.")
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

        end_dt = start_dt + timedelta(minutes=duration_minutes or 30)

        event = {
            'summary': summary or 'Meeting',
            'description': description or '',
            'start': {'dateTime': start_dt.isoformat(), 'timeZone': 'UTC'},
            'end':   {'dateTime': end_dt.isoformat(),   'timeZone': 'UTC'},
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
        return meet_url or None

    except ImportError:
        logger.warning("google-auth / google-api-python-client not installed — skipping Meet link.")
        return None
    except Exception as exc:
        logger.error("Failed to create Google Meet link: %s", exc, exc_info=True)
        logger.error("The company may need to reconnect Google Calendar, or the Calendar API may be disabled.")
        return None
