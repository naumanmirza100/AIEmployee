"""Salesforce CRM connector — Contacts, Tasks (emails), Events (meetings), Notes.

Credentials in CRMIntegration.credentials, from an External Client App with the client credentials flow on:
    {
        "instance_url":   "yourcompany.my.salesforce.com",   # the org's My Domain
        "client_id":      "3MVG...",                         # Consumer Key
        "client_secret":  "...",                             # Consumer Secret
    }
Saved before 2 Nov 2026 (the username-password flow, which Salesforce is retiring):
    {"client_id", "client_secret", "username", "password", "security_token", "domain": "login" | "test"}
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Optional

import requests

from .base import BaseCRMConnector, CRMError, is_blank, network_error

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 15
SF_API_VERSION = 'v58.0'


def _sf_datetime(dt) -> str:
    """Format a datetime as Salesforce ISO-8601 string (UTC)."""
    if dt is None:
        dt = datetime.now(dt_timezone.utc)
    if not hasattr(dt, 'isoformat'):
        return datetime.now(dt_timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=dt_timezone.utc)
    return dt.astimezone(dt_timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


def _host(value: str) -> str:
    """The org's sign-in host from what was typed: 'https://acme.my.salesforce.com/', the Lightning address people
    copy from the browser ('acme.lightning.force.com'), or the old 'login' / 'test'."""
    host = str(value or '').strip().lower()
    host = host.split('://', 1)[-1].split('/', 1)[0]
    if host.endswith('.lightning.force.com'):
        host = host[:-len('.lightning.force.com')] + '.my.salesforce.com'
    if '.' not in host:
        host = f'{host or "login"}.salesforce.com'
    return host


def _sign_in_reason(resp, with_password: bool) -> str:
    """Salesforce's sign-in refusal in words for the person connecting, from its error code. Never its raw text."""
    try:
        body = resp.json() or {}
    except ValueError:
        body = {}
    error = str(body.get('error') or '')
    detail = str(body.get('error_description') or '').lower()
    if with_password:
        return ('Salesforce refused the username and password. New Salesforce accounts no longer allow this way '
                "of signing in: connect with an app's key and secret and your My Domain instead.")
    if error in ('invalid_client_id', 'invalid_client'):
        return "Salesforce doesn't know this key and secret. Copy both again from the app (Consumer Key and Secret)."
    if error == 'unsupported_grant_type' or 'client credentials' in detail or 'run-as' in detail or 'user' in detail:
        return ("Salesforce took the key but the app can't sign in by itself. In the app: tick Enable Client "
                'Credentials Flow, and on its Policies tab set Run As to a user.')
    if 'domain' in detail or resp.status_code == 404:
        return 'Salesforce did not answer at this address. Use your My Domain, e.g. yourcompany.my.salesforce.com.'
    return 'Salesforce refused the sign-in. Check the My Domain, key and secret, and try again.'


class SalesforceConnector(BaseCRMConnector):
    """Salesforce REST API connector using the Username-Password OAuth2 flow."""

    def __init__(self, credentials: dict, timeout: int = DEFAULT_TIMEOUT):
        if credentials.get('username') and credentials.get('password') and not credentials.get('instance_url'):
            required = ('client_id', 'client_secret', 'username', 'password', 'security_token')    # saved before 2 Nov 2026
        else:
            required = ('instance_url', 'client_id', 'client_secret')
        missing = [k for k in required if not credentials.get(k)]
        if missing:
            raise CRMError(
                f'Salesforce credentials missing: {missing}',
                retriable=False,
            )
        self._creds = credentials
        self._timeout = timeout
        self._access_token: Optional[str] = None
        self._instance_url: Optional[str] = None

    # ------------------------------------------------------------------ #
    # BaseCRMConnector interface
    # ------------------------------------------------------------------ #

    label = 'Salesforce'

    def _ping(self) -> bool:
        self._ensure_token()
        resp = self._get(f'/services/data/{SF_API_VERSION}/limits')
        return resp.status_code == 200

    def find_contact_by_email(self, email: str) -> Optional[dict]:
        self._ensure_token()
        q = f"SELECT Id, FirstName, LastName, Email, Phone, Title FROM Contact WHERE Email = '{email.replace(chr(39), '')}' LIMIT 1"
        resp = self._get(f'/services/data/{SF_API_VERSION}/query', params={'q': q})
        records = (resp.json() or {}).get('records') or []
        if records:
            r = records[0]
            return {'id': r['Id'], 'properties': r}
        return None

    def create_contact(self, email: str, properties: dict) -> str:
        self._ensure_token()
        resp = self._post(f'/services/data/{SF_API_VERSION}/sobjects/Contact/',
                          json=self._build_contact_payload(email, properties))
        return str((resp.json() or {}).get('id', ''))

    def upsert_contact(self, email: str, properties: dict) -> str:
        self._ensure_token()
        existing = self.find_contact_by_email(email)
        if not existing:
            return self.create_contact(email, properties)

        sf_id = existing['id']
        blanks = self._blanks_to_fill(existing.get('properties') or {}, properties)
        if blanks:
            self._patch(f'/services/data/{SF_API_VERSION}/sobjects/Contact/{sf_id}', json=blanks)
        return sf_id

    def log_email_activity(
        self,
        crm_contact_id: str,
        subject: str,
        body: str,
        sent_at,
        direction: str = 'OUTBOUND',
    ) -> Optional[str]:
        self._ensure_token()
        task = {
            'WhoId': crm_contact_id,
            'Subject': (subject or '(no subject)')[:255],
            'Description': (body or '')[:32000],
            'Status': 'Completed',
            'TaskSubtype': 'Email',
            'ActivityDate': _sf_datetime(sent_at)[:10],
            'Type': 'Email',
        }
        resp = self._post(f'/services/data/{SF_API_VERSION}/sobjects/Task/', json=task)
        return str((resp.json() or {}).get('id', '')) or None

    def log_meeting(
        self,
        crm_contact_id: str,
        title: str,
        start_time,
        end_time=None,
        notes: str = '',
    ) -> Optional[str]:
        self._ensure_token()
        if end_time is None:
            if hasattr(start_time, 'timestamp'):
                end_time = start_time + timedelta(hours=1)
            else:
                end_time = start_time
        # Start and end only. 'DurationInMinutes': 60 went with them, so every half-hour meeting disagreed with itself
        # and Salesforce refuses that (CO-161).
        event = {
            'WhoId': crm_contact_id,
            'Subject': (title or 'Meeting')[:255],
            'Description': (notes or '')[:32000],
            'StartDateTime': _sf_datetime(start_time),
            'EndDateTime': _sf_datetime(end_time),
        }
        resp = self._post(f'/services/data/{SF_API_VERSION}/sobjects/Event/', json=event)
        return str((resp.json() or {}).get('id', '')) or None

    def update_meeting(self, crm_meeting_id: str, title: str, start_time, end_time=None, notes: str = '',
                       cancelled: bool = False) -> None:
        """Moved: the Event's start and end. Cancelled: the Event is deleted (CO-275)."""
        self._ensure_token()
        path = f'/services/data/{SF_API_VERSION}/sobjects/Event/{crm_meeting_id}'
        if cancelled:
            self._request('DELETE', path)
            return
        if end_time is None and hasattr(start_time, 'timestamp'):
            end_time = start_time + timedelta(minutes=30)
        fields = {'Subject': (title or 'Meeting')[:255], 'StartDateTime': _sf_datetime(start_time),
                  'EndDateTime': _sf_datetime(end_time)}
        if notes:
            fields['Description'] = notes[:32000]
        self._patch(path, json=fields)

    def log_note(self, crm_contact_id: str, body: str) -> Optional[str]:
        self._ensure_token()
        note = {
            'ParentId': crm_contact_id,
            'Title': 'Agent Note',
            'Body': (body or '')[:32000],
        }
        resp = self._post(f'/services/data/{SF_API_VERSION}/sobjects/Note/', json=note)
        return str((resp.json() or {}).get('id', '')) or None

    # ------------------------------------------------------------------ #
    # Deals: Salesforce opportunities, whose "pipeline" is the Stage picklist
    # ------------------------------------------------------------------ #

    #: Days ahead an opportunity's Close Date is set; Salesforce requires one.
    CLOSE_IN_DAYS = 30

    def list_pipelines(self) -> list:
        self._ensure_token()
        fields = (self._get(f'/services/data/{SF_API_VERSION}/sobjects/Opportunity/describe').json() or {}).get('fields') or []
        stage = next((f for f in fields if f.get('name') == 'StageName'), {})
        stages = [{'id': v.get('value'), 'label': v.get('label') or v.get('value')}
                  for v in stage.get('picklistValues') or [] if v.get('active', True)]
        return [{'id': 'opportunity', 'label': 'Opportunities', 'stages': stages}]

    def create_deal(self, crm_contact_id: str, name: str, pipeline_id: str, stage_id: str) -> Optional[str]:
        self._ensure_token()
        from datetime import date
        close = (date.today() + timedelta(days=self.CLOSE_IN_DAYS)).isoformat()
        resp = self._post(f'/services/data/{SF_API_VERSION}/sobjects/Opportunity/',
                          json={'Name': (name or 'New deal')[:120], 'StageName': stage_id, 'CloseDate': close})
        opp = str((resp.json() or {}).get('id', ''))
        if opp:
            self._post(f'/services/data/{SF_API_VERSION}/sobjects/OpportunityContactRole/',
                       json={'OpportunityId': opp, 'ContactId': crm_contact_id, 'IsPrimary': True})
        return opp or None

    # ------------------------------------------------------------------ #
    # Auth
    # ------------------------------------------------------------------ #

    def _uses_password(self) -> bool:
        """The old way, only when no My Domain was given: a connection changed to the new way keeps its old
        fields in the merged credentials."""
        return bool(self._creds.get('username') and self._creds.get('password') and not self._creds.get('instance_url'))

    def _ensure_token(self):
        """Sign in. With an External Client App's key and secret and the org's My Domain (the client credentials
        flow), as Salesforce now asks. Salesforce has switched the username-password flow off in new orgs and is
        retiring it (2026); a connection saved that way still signs in that way while its org allows it."""
        if self._access_token:
            return
        if self._uses_password():
            token_url = f"https://{_host(self._creds.get('domain') or 'login')}/services/oauth2/token"
            data = {
                'grant_type': 'password',
                'client_id': self._creds['client_id'],
                'client_secret': self._creds['client_secret'],
                'username': self._creds['username'],
                'password': self._creds['password'] + self._creds.get('security_token', ''),
            }
        else:
            token_url = f"https://{_host(self._creds['instance_url'])}/services/oauth2/token"
            data = {
                'grant_type': 'client_credentials',
                'client_id': self._creds['client_id'],
                'client_secret': self._creds['client_secret'],
            }
        try:
            resp = requests.post(token_url, data=data, timeout=self._timeout)
        except requests.RequestException as exc:
            raise network_error('Salesforce', exc) from exc

        if resp.status_code != 200:
            raise CRMError(
                f'Salesforce auth failed ({resp.status_code}): {resp.text[:300]}',
                retriable=resp.status_code >= 500,
                status_code=401 if resp.status_code in (400, 401, 403) else resp.status_code,
                reason=_sign_in_reason(resp, self._uses_password()),
            )
        body = resp.json()
        self._access_token = body['access_token']
        self._instance_url = body['instance_url']

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _build_contact_payload(email: str, props: dict) -> dict:
        out: dict = {'Email': email}
        if props.get('first_name'):
            out['FirstName'] = str(props['first_name'])[:40]
        if props.get('last_name'):
            out['LastName'] = str(props['last_name'])[:80]
        elif not props.get('first_name'):
            # Salesforce requires LastName
            full = props.get('name', '') or email.split('@')[0]
            parts = full.strip().split()
            out['FirstName'] = parts[0][:40] if len(parts) > 1 else ''
            out['LastName'] = (parts[-1] if parts else 'Unknown')[:80]
        if props.get('phone'):
            out['Phone'] = str(props['phone'])[:40]
        # The company name is not sent. A Contact has no 'Company' field, and the
        # 'AccountId': None that used to go with it would, on an update, have cut an
        # existing contact loose from its account.
        if props.get('job_title'):
            out['Title'] = str(props['job_title'])[:128]
        if props.get('lead_score') is not None:
            out['Description'] = f"Lead score: {props['lead_score']}"
        return out

    @staticmethod
    def _blanks_to_fill(existing: dict, props: dict) -> dict:
        """Of the lead's details, the ones for fields the Salesforce contact has empty.

        Names, phone and title only. Description is the customer's own notes
        field: it is written on a contact we create and never on one that exists."""
        ours = {
            'FirstName': str(props.get('first_name') or '')[:40],
            'LastName': str(props.get('last_name') or '')[:80],
            'Phone': str(props.get('phone') or '')[:40],
            'Title': str(props.get('job_title') or '')[:128],
        }
        return {field: value for field, value in ours.items()
                if not is_blank(value) and is_blank(existing.get(field))}

    def _headers(self) -> dict:
        return {
            'Authorization': f'Bearer {self._access_token}',
            'Content-Type': 'application/json',
        }

    def _get(self, path: str, params=None):
        return self._request('GET', path, params=params)

    def _post(self, path: str, json=None):
        return self._request('POST', path, json=json)

    def _patch(self, path: str, json=None):
        return self._request('PATCH', path, json=json)

    def _request(self, method: str, path: str, params=None, json=None):
        url = f'{self._instance_url}{path}'
        try:
            resp = requests.request(
                method, url,
                headers=self._headers(),
                params=params,
                json=json,
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            raise network_error('Salesforce', exc) from exc

        # 204 No Content is success for PATCH
        if resp.status_code in (200, 201, 204):
            return resp
        if resp.status_code == 401:
            # Token expired — clear so next call re-authenticates
            self._access_token = None
            self._instance_url = None
            raise CRMError(
                f'Salesforce token expired ({resp.status_code})',
                retriable=True,
                status_code=resp.status_code,
            )
        if resp.status_code in (403,):
            api_off = 'API_DISABLED_FOR_ORG' in resp.text
            raise CRMError(
                f'Salesforce permission denied ({resp.status_code}): {resp.text[:200]}',
                retriable=False,
                status_code=resp.status_code,
                reason=("This Salesforce plan doesn't let outside tools in (no API access). Enterprise and higher "
                        'include it; smaller plans need the API add-on from Salesforce.') if api_off else None,
            )
        if resp.status_code == 429 or resp.status_code >= 500:
            raise CRMError(
                f'Salesforce transient error ({resp.status_code}): {resp.text[:200]}',
                retriable=True,
                status_code=resp.status_code,
            )
        raise CRMError(
            f'Salesforce client error ({resp.status_code}): {resp.text[:300]}',
            retriable=False,
            status_code=resp.status_code,
        )
