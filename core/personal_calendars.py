"""A person's own Google or Outlook calendar (24 Nov 2026).

The agents checked only the meetings they had booked themselves. A person's real diary (a dentist at 11, a client
call made outside the product) never counted, and nothing the agents booked reached that diary. A person may now
connect their own calendar:

  * Its busy times come in as `CalendarBlock` rows with source 'personal': the times only, private, titled "Busy".
    Every agent's clash check reads that table, so they count everywhere at once. Free (transparent) events,
    cancelled ones, ones the person declined and the events this module wrote itself are left out.
  * The meetings the agents booked for the person go out into it, and are moved or removed with the booking. A
    private booking's title stays in PayPerProject.

It runs every 15 minutes (core.tasks.sync_personal_calendars), once straight after connecting, and on "Sync now".
The identity is the employee login (auth.User), as for the rest of the shared calendar. A dashboard login connects
through the employee login it maps to (core/scheduling/identity.py).

Google uses the platform's Google OAuth app and its redirect URI, the same one the company calendar uses (the
signed state says which flow it is). Outlook needs its own app registration: MICROSOFT_CLIENT_ID,
MICROSOFT_CLIENT_SECRET and MICROSOFT_OAUTH_REDIRECT_URI.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import threading
import urllib.parse
from datetime import date, datetime, time, timedelta, timezone as dt_timezone

from django.conf import settings
from django.core import signing
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger(__name__)

#: How far ahead busy times are read.
WINDOW_DAYS = 60
#: The agents' bookings that go into a personal calendar. Leave is not a meeting; 'personal' is the calendar itself.
PUSHED_SOURCES = ('pm', 'hr', 'frontline', 'recruitment', 'sdr', 'exec')
#: Most events read or written in one sync.
MAX_EVENTS = 1000
#: A sync that started longer ago than this is taken to have died.
SYNC_STALE = timedelta(minutes=10)
TIMEOUT = 20

GOOGLE_AUTH_URI = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_TOKEN_URI = 'https://oauth2.googleapis.com/token'
GOOGLE_USERINFO_URI = 'https://openidconnect.googleapis.com/v1/userinfo'
GOOGLE_EVENTS = 'https://www.googleapis.com/calendar/v3/calendars/primary/events'
# The scope the company calendar already asks for, so the platform's Google app needs no new consent setup.
GOOGLE_SCOPE = 'openid email https://www.googleapis.com/auth/calendar'
#: Marks the events written here (a private extended property), so they are not read back as busy time.
GOOGLE_MARK = 'payperproject_booking'

MS_AUTHORITY = 'https://login.microsoftonline.com/common/oauth2/v2.0'
MS_SCOPE = 'offline_access openid email User.Read Calendars.ReadWrite'
GRAPH = 'https://graph.microsoft.com/v1.0'
MS_MARK = 'payperproject-'          # start of the transactionId on events written here

STATE_SALT = 'personal-calendar.oauth.v1'
STATE_MAX_AGE_SECONDS = 600

PROVIDER_LABELS = {'google': 'Google Calendar', 'microsoft': 'Outlook'}
REVOKED = '{provider} ended the connection. Connect it again to keep using it.'
NOT_LINKED = ("Your dashboard login isn't matched to one employee login, so the agents can't tell which calendar is "
              "yours. Ask HR to link your login to your employee record, or use the same email for both.")


class CalendarError(Exception):
    """Something the person is told, as it is."""


class _Revoked(CalendarError):
    """The provider no longer accepts the refresh token."""


# ---------------------------------------------------------------------------
# Who, and what is offered
# ---------------------------------------------------------------------------

def offered() -> dict:
    return {
        'google': bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET
                       and settings.GOOGLE_OAUTH_REDIRECT_URI),
        'microsoft': bool(getattr(settings, 'MICROSOFT_CLIENT_ID', '') and getattr(settings, 'MICROSOFT_CLIENT_SECRET', '')
                          and getattr(settings, 'MICROSOFT_OAUTH_REDIRECT_URI', '')),
    }


def calendar_user_id(company_user) -> int | None:
    """The employee login whose calendar a dashboard login connects, or None when it maps to nobody (or two)."""
    from core.scheduling.identity import login_user_id_for_company_user
    return login_user_id_for_company_user(company_user)


def _token_of(cal) -> str:
    from core.google_calendar import refresh_token_of
    return refresh_token_of({'refresh_token': cal.refresh_token})


def _seal(token: str) -> str:
    from core.google_calendar import seal_refresh_token
    return seal_refresh_token(token)


# ---------------------------------------------------------------------------
# Connecting
# ---------------------------------------------------------------------------

def make_state(*, user_id, company_id, provider, return_to) -> str:
    signed = signing.dumps({'user_id': user_id, 'company_id': company_id, 'provider': provider,
                            'return_to': return_to}, salt=STATE_SALT)
    return base64.urlsafe_b64encode(signed.encode()).decode().rstrip('=')


def read_state(state) -> dict | None:
    """The connect request a state carries, or None when it isn't one of ours (or was tampered with).
    Raises CalendarError when it is ours but too old."""
    if not state:
        return None
    try:
        padded = state + '=' * (-len(state) % 4)
        signed = base64.urlsafe_b64decode(padded.encode()).decode()
        return signing.loads(signed, salt=STATE_SALT, max_age=STATE_MAX_AGE_SECONDS)
    except signing.SignatureExpired:
        raise CalendarError('The connection request expired. Please try again.')
    except Exception:
        return None


def auth_url(provider, state) -> str:
    if provider == 'google':
        params = {'client_id': settings.GOOGLE_CLIENT_ID, 'redirect_uri': settings.GOOGLE_OAUTH_REDIRECT_URI,
                  'response_type': 'code', 'scope': GOOGLE_SCOPE, 'access_type': 'offline', 'prompt': 'consent',
                  'include_granted_scopes': 'true', 'state': state}
        return f'{GOOGLE_AUTH_URI}?{urllib.parse.urlencode(params)}'
    params = {'client_id': settings.MICROSOFT_CLIENT_ID, 'redirect_uri': settings.MICROSOFT_OAUTH_REDIRECT_URI,
              'response_type': 'code', 'response_mode': 'query', 'scope': MS_SCOPE, 'prompt': 'select_account',
              'state': state}
    return f'{MS_AUTHORITY}/authorize?{urllib.parse.urlencode(params)}'


def redirect_after(return_to, *, connected=False, error=None):
    from django.http import HttpResponseRedirect
    base = (settings.FRONTEND_URL or '').rstrip('/')
    path = return_to if (isinstance(return_to, str) and return_to.startswith('/') and not return_to.startswith('//')) \
        else '/me/meetings'
    sep = '&' if '?' in path else '?'
    url = f'{base}{path}'
    if connected:
        url += f'{sep}mycal=connected'
    elif error:
        url += f'{sep}mycal_error={urllib.parse.quote(str(error)[:200])}'
    return HttpResponseRedirect(url)


def _exchange(provider, code) -> tuple[str, str, str]:
    """(refresh token, access token, account email) for an authorization code."""
    import requests
    if provider == 'google':
        resp = requests.post(GOOGLE_TOKEN_URI, data={
            'code': code, 'client_id': settings.GOOGLE_CLIENT_ID, 'client_secret': settings.GOOGLE_CLIENT_SECRET,
            'redirect_uri': settings.GOOGLE_OAUTH_REDIRECT_URI, 'grant_type': 'authorization_code'}, timeout=TIMEOUT)
    else:
        resp = requests.post(f'{MS_AUTHORITY}/token', data={
            'code': code, 'client_id': settings.MICROSOFT_CLIENT_ID,
            'client_secret': settings.MICROSOFT_CLIENT_SECRET, 'redirect_uri': settings.MICROSOFT_OAUTH_REDIRECT_URI,
            'grant_type': 'authorization_code', 'scope': MS_SCOPE}, timeout=TIMEOUT)
    body = _json(resp)
    if resp.status_code != 200 or not body.get('refresh_token'):
        logger.warning('Personal calendar token exchange failed (%s): %s', provider, body.get('error'))
        raise CalendarError(body.get('error_description') or body.get('error') or 'The sign-in could not be finished.')
    access = body.get('access_token') or ''
    email = ''
    try:
        if provider == 'google':
            me = requests.get(GOOGLE_USERINFO_URI, headers=_bearer(access), timeout=TIMEOUT)
            email = _json(me).get('email', '') if me.status_code == 200 else ''
        else:
            me = requests.get(f'{GRAPH}/me?$select=mail,userPrincipalName', headers=_bearer(access), timeout=TIMEOUT)
            data = _json(me) if me.status_code == 200 else {}
            email = data.get('mail') or data.get('userPrincipalName') or ''
    except Exception:
        pass
    return body['refresh_token'], access, email


def finish_connect(state_data, code):
    """Save the connection a sign-in made, then sync it in the background. Returns the PersonalCalendar."""
    from core.models import PersonalCalendar
    from core.scheduling.identity import member_ids
    provider = state_data.get('provider')
    user_id, company_id = state_data.get('user_id'), state_data.get('company_id')
    if provider not in PROVIDER_LABELS or not offered().get(provider):
        raise CalendarError('That calendar is not set up on this server.')
    if not member_ids(company_id, [user_id]):
        raise CalendarError('This login is no longer part of the company.')
    refresh, _access, email = _exchange(provider, code)

    old = PersonalCalendar.objects.filter(user_id=user_id).first()
    if old is not None and (old.provider != provider or (old.account_email or '').lower() != (email or '').lower()):
        disconnect(old)                       # another calendar: take the agents' meetings out of the old one
        old = None
    if old is None:
        cal = PersonalCalendar.objects.create(user_id=user_id, company_id=company_id, provider=provider,
                                              account_email=email[:254], refresh_token=_seal(refresh))
    else:                                     # the same calendar again: keep what was written to it
        old.company_id, old.refresh_token, old.last_error, old.sync_started_at = company_id, _seal(refresh), '', None
        old.save(update_fields=['company', 'refresh_token', 'last_error', 'sync_started_at'])
        cal = old
    sync_soon(cal.pk)
    return cal


def sync_soon(cal_id):
    """Sync after this request: in place under the test settings, otherwise on a thread of its own."""
    if getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', False):
        sync_id(cal_id)
        return

    def on_its_own_thread():
        try:
            sync_id(cal_id)
        except Exception:
            logger.exception('Personal calendar %s: first sync failed', cal_id)
        finally:
            connection.close()

    transaction.on_commit(lambda: threading.Thread(target=on_its_own_thread, name=f'personal-cal-{cal_id}',
                                                   daemon=True).start())


def disconnect(cal) -> None:
    """Stop using a calendar: its busy times go, and the agents' upcoming meetings are taken out of it (as far as the
    provider still lets us)."""
    from core.models import CalendarBlock
    now = timezone.now()
    try:
        client = _client(cal)
        for event in cal.events.all():
            if _stored_end(event.state) > now:
                client.delete(event.external_id)
    except Exception as exc:                  # a revoked token: the events stay, nothing else to do
        logger.info('Personal calendar %s: events not removed on disconnect (%s)', cal.pk, type(exc).__name__)
    CalendarBlock.objects.filter(source='personal', user_id=cal.user_id).delete()
    cal.delete()


# ---------------------------------------------------------------------------
# The two providers
# ---------------------------------------------------------------------------

def _json(resp) -> dict:
    try:
        body = resp.json()
        return body if isinstance(body, dict) else {}
    except Exception:
        return {}


def _bearer(token):
    return {'Authorization': f'Bearer {token}'}


def _utc(dt) -> datetime:
    return dt.astimezone(dt_timezone.utc)


def _rfc3339(dt) -> str:
    return _utc(dt).strftime('%Y-%m-%dT%H:%M:%SZ')


def _parse(value, zone_name='UTC') -> datetime | None:
    """An event's start or end: Google's {'dateTime'} / {'date'}, Graph's {'dateTime', 'timeZone'} in UTC."""
    from core.scheduling.conflicts import zone_info
    if not isinstance(value, dict):
        return None
    if value.get('dateTime'):
        text = str(value['dateTime']).strip()
        if text.endswith('Z'):
            text = text[:-1] + '+00:00'
        head, rest = text[:19], text[19:]
        if rest.startswith('.'):                       # Graph sends seven digits of a second
            rest = rest[1:].lstrip('0123456789')
        try:
            moment = datetime.fromisoformat(head + rest)
        except ValueError:
            return None
        # Google always says its offset; Graph, asked for UTC, says none.
        return moment if moment.tzinfo else moment.replace(tzinfo=dt_timezone.utc)
    if value.get('date'):                     # a whole day, on the calendar's own clock
        try:
            day = date.fromisoformat(str(value['date']))
        except ValueError:
            return None
        return datetime.combine(day, time(0), tzinfo=zone_info(zone_name))
    return None


class _Client:
    provider = ''

    def __init__(self, cal):
        import requests
        self.cal, self.http, self._access = cal, requests.Session(), None

    def _call(self, method, url, **kwargs):
        resp = self.http.request(method, url, headers={**_bearer(self.access()), **kwargs.pop('headers', {})},
                                 timeout=TIMEOUT, **kwargs)
        if resp.status_code == 401:
            raise _Revoked(REVOKED.format(provider=PROVIDER_LABELS[self.provider]))
        return resp

    def _refresh(self, url, data):
        resp = self.http.post(url, data=data, timeout=TIMEOUT)
        body = _json(resp)
        if resp.status_code != 200 or not body.get('access_token'):
            if body.get('error') in ('invalid_grant', 'unauthorized_client', 'invalid_client', 'interaction_required'):
                raise _Revoked(REVOKED.format(provider=PROVIDER_LABELS[self.provider]))
            raise CalendarError(f'{PROVIDER_LABELS[self.provider]} did not answer ({resp.status_code}).')
        if body.get('refresh_token') and body['refresh_token'] != _token_of(self.cal):   # Microsoft rolls them
            self.cal.refresh_token = _seal(body['refresh_token'])
            type(self.cal).objects.filter(pk=self.cal.pk).update(refresh_token=self.cal.refresh_token)
        return body['access_token']


class _Google(_Client):
    provider = 'google'

    def access(self):
        if self._access is None:
            self._access = self._refresh(GOOGLE_TOKEN_URI, {
                'client_id': settings.GOOGLE_CLIENT_ID, 'client_secret': settings.GOOGLE_CLIENT_SECRET,
                'refresh_token': _token_of(self.cal), 'grant_type': 'refresh_token'})
        return self._access

    def busy(self, start, end) -> list[tuple[str, datetime, datetime]]:
        out, page = [], None
        while len(out) < MAX_EVENTS:
            params = {'timeMin': _rfc3339(start), 'timeMax': _rfc3339(end), 'singleEvents': 'true',
                      'orderBy': 'startTime', 'maxResults': 250, 'showDeleted': 'false'}
            if page:
                params['pageToken'] = page
            resp = self._call('GET', GOOGLE_EVENTS, params=params)
            if resp.status_code != 200:
                raise CalendarError(f'Google Calendar did not answer ({resp.status_code}).')
            body = _json(resp)
            zone = body.get('timeZone') or 'UTC'
            for item in body.get('items') or []:
                if item.get('status') == 'cancelled' or item.get('transparency') == 'transparent':
                    continue
                if GOOGLE_MARK in ((item.get('extendedProperties') or {}).get('private') or {}):
                    continue
                if item.get('eventType') in ('workingLocation', 'focusTime') and item.get('transparency') != 'opaque':
                    continue
                me = next((a for a in item.get('attendees') or [] if a.get('self')), None)
                if me and me.get('responseStatus') == 'declined':
                    continue
                s, e = _parse(item.get('start'), zone), _parse(item.get('end'), zone)
                if s and e and e > s and item.get('id'):
                    out.append((str(item['id']), s, e))
            page = body.get('nextPageToken')
            if not page:
                break
        return out[:MAX_EVENTS]

    def _body(self, booking):
        return {'summary': booking['title'], 'description': booking['description'],
                'start': {'dateTime': _rfc3339(booking['starts_at'])}, 'end': {'dateTime': _rfc3339(booking['ends_at'])},
                'extendedProperties': {'private': {GOOGLE_MARK: booking['key']}}}

    def create(self, booking) -> str:
        resp = self._call('POST', GOOGLE_EVENTS, json=self._body(booking))
        if resp.status_code not in (200, 201) or not _json(resp).get('id'):
            raise CalendarError(f'Google Calendar refused the event ({resp.status_code}).')
        return str(_json(resp)['id'])

    def update(self, external_id, booking) -> bool:
        resp = self._call('PATCH', f'{GOOGLE_EVENTS}/{urllib.parse.quote(external_id, safe="")}', json=self._body(booking))
        if resp.status_code in (404, 410):
            return False
        if resp.status_code != 200:
            raise CalendarError(f'Google Calendar refused the change ({resp.status_code}).')
        return _json(resp).get('status') != 'cancelled'

    def delete(self, external_id) -> None:
        resp = self._call('DELETE', f'{GOOGLE_EVENTS}/{urllib.parse.quote(external_id, safe="")}')
        if resp.status_code not in (200, 204, 404, 410):
            raise CalendarError(f'Google Calendar refused to remove the event ({resp.status_code}).')


class _Microsoft(_Client):
    provider = 'microsoft'

    def access(self):
        if self._access is None:
            self._access = self._refresh(f'{MS_AUTHORITY}/token', {
                'client_id': settings.MICROSOFT_CLIENT_ID, 'client_secret': settings.MICROSOFT_CLIENT_SECRET,
                'refresh_token': _token_of(self.cal), 'grant_type': 'refresh_token', 'scope': MS_SCOPE})
        return self._access

    def busy(self, start, end) -> list[tuple[str, datetime, datetime]]:
        out = []
        url = f'{GRAPH}/me/calendarView'
        params = {'startDateTime': _rfc3339(start), 'endDateTime': _rfc3339(end), '$top': 100,
                  '$select': 'id,start,end,showAs,isCancelled,responseStatus,transactionId'}
        while url and len(out) < MAX_EVENTS:
            resp = self._call('GET', url, params=params, headers={'Prefer': 'outlook.timezone="UTC"'})
            if resp.status_code != 200:
                raise CalendarError(f'Outlook did not answer ({resp.status_code}).')
            body = _json(resp)
            for item in body.get('value') or []:
                if item.get('isCancelled') or item.get('showAs') in ('free', 'workingElsewhere'):
                    continue
                if str(item.get('transactionId') or '').startswith(MS_MARK):
                    continue
                if ((item.get('responseStatus') or {}).get('response')) == 'declined':
                    continue
                s, e = _parse(item.get('start')), _parse(item.get('end'))
                if s and e and e > s and item.get('id'):
                    out.append((str(item['id']), s, e))
            url, params = body.get('@odata.nextLink'), None
        return out[:MAX_EVENTS]

    def _body(self, booking):
        def when(dt):
            return {'dateTime': _utc(dt).strftime('%Y-%m-%dT%H:%M:%S'), 'timeZone': 'UTC'}
        return {'subject': booking['title'], 'body': {'contentType': 'text', 'content': booking['description']},
                'start': when(booking['starts_at']), 'end': when(booking['ends_at']), 'showAs': 'busy'}

    def create(self, booking) -> str:
        stamp = hashlib.sha256(f"{booking['key']}|{timezone.now().isoformat()}".encode()).hexdigest()[:16]
        resp = self._call('POST', f'{GRAPH}/me/events', json={**self._body(booking), 'transactionId': MS_MARK + stamp})
        if resp.status_code not in (200, 201) or not _json(resp).get('id'):
            raise CalendarError(f'Outlook refused the event ({resp.status_code}).')
        return str(_json(resp)['id'])

    def update(self, external_id, booking) -> bool:
        resp = self._call('PATCH', f'{GRAPH}/me/events/{urllib.parse.quote(external_id, safe="")}', json=self._body(booking))
        if resp.status_code == 404:
            return False
        if resp.status_code != 200:
            raise CalendarError(f'Outlook refused the change ({resp.status_code}).')
        return True

    def delete(self, external_id) -> None:
        resp = self._call('DELETE', f'{GRAPH}/me/events/{urllib.parse.quote(external_id, safe="")}')
        if resp.status_code not in (200, 204, 404):
            raise CalendarError(f'Outlook refused to remove the event ({resp.status_code}).')


def _client(cal) -> _Client:
    return (_Google if cal.provider == 'google' else _Microsoft)(cal)


# ---------------------------------------------------------------------------
# Syncing
# ---------------------------------------------------------------------------

def block_id(external_id) -> int:
    """A personal block's source_id: the event's id there, hashed into 60 bits."""
    return int(hashlib.sha256(str(external_id).encode()).hexdigest()[:15], 16)


def _stored_end(state) -> datetime:
    try:
        return datetime.fromisoformat((state or '').split('|')[1])
    except (IndexError, ValueError):
        return timezone.now() + timedelta(days=1)     # unknown: treat as still to come


def _booking(block) -> dict:
    from core.scheduling.sources import SOURCES
    label = SOURCES[block.source].label if block.source in SOURCES else 'Meeting'
    title = (f'{label} (details in PayPerProject)' if block.is_private or not block.title
             else block.title)[:200]
    if block.response == 'pending':
        title = f'Invited: {title}'[:200]
    return {'key': f'{block.source}:{block.source_id}', 'title': title, 'starts_at': block.starts_at,
            'ends_at': block.ends_at,
            'description': (f'Booked by the {label} agent in PayPerProject. Changes made here are not read back: '
                            'move or cancel it there.')}


def _state(booking) -> str:
    return f"{_utc(booking['starts_at']).isoformat()}|{_utc(booking['ends_at']).isoformat()}|{booking['title']}"[:300]


def _push(cal, client, now) -> dict:
    """Put the agents' upcoming bookings for this person into the calendar; move or remove the ones that changed."""
    from core.models import CalendarBlock, PersonalCalendarEvent
    wanted = {}
    for block in (CalendarBlock.objects.filter(user_id=cal.user_id, company_id=cal.company_id,
                                               source__in=PUSHED_SOURCES, ends_at__gt=now)
                  .order_by('starts_at')[:MAX_EVENTS]):
        wanted[(block.source, block.source_id)] = _booking(block)
    written = {(e.block_source, e.block_source_id): e for e in cal.events.all()}
    stats = {'added': 0, 'moved': 0, 'removed': 0}
    for key, booking in wanted.items():
        state = _state(booking)
        event = written.get(key)
        if event is None:
            PersonalCalendarEvent.objects.create(calendar=cal, block_source=key[0], block_source_id=key[1],
                                                 external_id=client.create(booking)[:255], state=state)
            stats['added'] += 1
        elif event.state != state:
            if not client.update(event.external_id, booking):       # removed there: put it back, it has moved
                event.external_id = client.create(booking)[:255]
            event.state = state
            event.save(update_fields=['external_id', 'state'])
            stats['moved'] += 1
    for key, event in written.items():
        if key in wanted:
            continue
        if _stored_end(event.state) > now:     # cancelled, declined or the person taken off it
            client.delete(event.external_id)
            stats['removed'] += 1
        event.delete()                         # an ended one is just forgotten; it stays in their calendar
    return stats


def _pull(cal, client, now) -> int:
    """Replace this person's 'personal' busy blocks with what the calendar holds now."""
    from core.models import CalendarBlock
    mine = set(cal.events.values_list('external_id', flat=True))
    rows, seen = [], set()
    for external_id, starts, ends in client.busy(now, now + timedelta(days=WINDOW_DAYS)):
        key = block_id(external_id)
        if external_id in mine or key in seen:
            continue
        seen.add(key)
        rows.append(CalendarBlock(company_id=cal.company_id, user_id=cal.user_id, starts_at=starts, ends_at=ends,
                                  source='personal', source_id=key, role='participant', response='busy',
                                  title='Busy', is_private=True))
    with transaction.atomic():
        CalendarBlock.objects.filter(source='personal', user_id=cal.user_id).delete()
        CalendarBlock.objects.bulk_create(rows)
    return len(rows)


def sync(cal, *, now=None) -> dict:
    """One calendar, both ways. Never raises: what went wrong is kept on the calendar for its card."""
    from core.models import CalendarBlock, PersonalCalendar
    from core.scheduling.identity import member_ids
    now = now or timezone.now()
    claimed = (PersonalCalendar.objects.filter(pk=cal.pk)
               .filter(Q(sync_started_at__isnull=True) | Q(sync_started_at__lt=now - SYNC_STALE))
               .update(sync_started_at=now))
    if not claimed:
        return {'skipped': 'already syncing'}
    stats = {}
    try:
        if not member_ids(cal.company_id, [cal.user_id]):           # left the company: their busy time goes
            CalendarBlock.objects.filter(source='personal', user_id=cal.user_id).delete()
            return {'skipped': 'not a member'}
        client = _client(cal)
        if cal.push_events:
            stats.update(_push(cal, client, now))
        if cal.read_busy:
            stats['busy'] = _pull(cal, client, now)
        else:
            CalendarBlock.objects.filter(source='personal', user_id=cal.user_id).delete()
        cal.last_synced_at, cal.last_error = now, ''
    except _Revoked as exc:
        # Stale busy times would block bookings for nothing: they go until it is connected again.
        CalendarBlock.objects.filter(source='personal', user_id=cal.user_id).delete()
        cal.last_error, stats = str(exc)[:500], {'error': 'revoked'}
    except CalendarError as exc:
        cal.last_error, stats = str(exc)[:500], {'error': str(exc)[:200]}
    except Exception as exc:
        logger.exception('Personal calendar %s sync failed', cal.pk)
        cal.last_error = f'{PROVIDER_LABELS.get(cal.provider, "The calendar")} could not be reached just now.'
        stats = {'error': type(exc).__name__}
    finally:
        PersonalCalendar.objects.filter(pk=cal.pk).update(
            sync_started_at=None, last_synced_at=cal.last_synced_at, last_error=cal.last_error)
    return stats


def sync_id(cal_id) -> dict:
    from core.models import PersonalCalendar
    cal = PersonalCalendar.objects.filter(pk=cal_id).first()
    return sync(cal) if cal is not None else {'skipped': 'gone'}


def sync_all() -> dict:
    from core.models import PersonalCalendar
    done = failed = 0
    for cal in PersonalCalendar.objects.filter(Q(read_busy=True) | Q(push_events=True)).iterator():
        result = sync(cal)
        failed += 1 if 'error' in result else 0
        done += 1
    return {'calendars': done, 'failed': failed}


# ---------------------------------------------------------------------------
# What the card shows
# ---------------------------------------------------------------------------

def status_for(user_id, *, linked=True) -> dict:
    from core.models import CalendarBlock, PersonalCalendar
    cal = PersonalCalendar.objects.filter(user_id=user_id).first() if user_id else None
    out = {'offered': offered(), 'linked': bool(linked and user_id), 'connected': cal is not None,
           'notLinkedReason': '' if (linked and user_id) else NOT_LINKED}
    if cal is not None:
        now = timezone.now()
        out.update({
            'provider': cal.provider, 'providerLabel': PROVIDER_LABELS.get(cal.provider, cal.provider),
            'accountEmail': cal.account_email, 'readBusy': cal.read_busy, 'pushEvents': cal.push_events,
            'connectedAt': cal.connected_at.isoformat() if cal.connected_at else None,
            'lastSyncedAt': cal.last_synced_at.isoformat() if cal.last_synced_at else None,
            'lastError': cal.last_error,
            'busyCount': CalendarBlock.objects.filter(source='personal', user_id=user_id, ends_at__gt=now).count(),
            'pushedCount': cal.events.count(),
        })
    return out
