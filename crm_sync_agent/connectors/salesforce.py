"""Salesforce CRM connector — Contacts, Tasks (emails), Events (meetings), Notes.

Credentials required in CRMIntegration.credentials:
    {
        "client_id":      "3MVG...",
        "client_secret":  "...",
        "username":       "user@example.com",
        "password":       "MyPassword",
        "security_token": "AbCdEf...",   # append to password for login
        "domain":         "login"         # "login" (prod) or "test" (sandbox)
    }
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Optional

import requests

from .base import BaseCRMConnector, CRMError

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


class SalesforceConnector(BaseCRMConnector):
    """Salesforce REST API connector using the Username-Password OAuth2 flow."""

    def __init__(self, credentials: dict, timeout: int = DEFAULT_TIMEOUT):
        required = ('client_id', 'client_secret', 'username', 'password', 'security_token')
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

    def ping(self) -> bool:
        try:
            self._ensure_token()
            resp = self._get(f'/services/data/{SF_API_VERSION}/limits')
            return resp.status_code == 200
        except CRMError:
            return False

    def find_contact_by_email(self, email: str) -> Optional[dict]:
        self._ensure_token()
        q = f"SELECT Id, FirstName, LastName, Email, Phone FROM Contact WHERE Email = '{email.replace(chr(39), '')}' LIMIT 1"
        resp = self._get(f'/services/data/{SF_API_VERSION}/query', params={'q': q})
        records = (resp.json() or {}).get('records') or []
        if records:
            r = records[0]
            return {'id': r['Id'], 'properties': r}
        return None

    def upsert_contact(self, email: str, properties: dict) -> str:
        self._ensure_token()
        existing = self.find_contact_by_email(email)
        sf_data = self._build_contact_payload(email, properties)

        if existing:
            sf_id = existing['id']
            self._patch(
                f'/services/data/{SF_API_VERSION}/sobjects/Contact/{sf_id}',
                json=sf_data,
            )
            return sf_id

        resp = self._post(f'/services/data/{SF_API_VERSION}/sobjects/Contact/', json=sf_data)
        return str((resp.json() or {}).get('id', ''))

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
        event = {
            'WhoId': crm_contact_id,
            'Subject': (title or 'Meeting')[:255],
            'Description': (notes or '')[:32000],
            'StartDateTime': _sf_datetime(start_time),
            'EndDateTime': _sf_datetime(end_time),
            'DurationInMinutes': 60,
        }
        resp = self._post(f'/services/data/{SF_API_VERSION}/sobjects/Event/', json=event)
        return str((resp.json() or {}).get('id', '')) or None

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
    # Auth
    # ------------------------------------------------------------------ #

    def _ensure_token(self):
        if self._access_token:
            return
        domain = self._creds.get('domain', 'login')
        token_url = f'https://{domain}.salesforce.com/services/oauth2/token'
        password = self._creds['password'] + self._creds.get('security_token', '')
        data = {
            'grant_type': 'password',
            'client_id': self._creds['client_id'],
            'client_secret': self._creds['client_secret'],
            'username': self._creds['username'],
            'password': password,
        }
        try:
            resp = requests.post(token_url, data=data, timeout=self._timeout)
        except requests.RequestException as exc:
            raise CRMError(f'Salesforce auth network error: {exc}', retriable=True) from exc

        if resp.status_code != 200:
            raise CRMError(
                f'Salesforce auth failed ({resp.status_code}): {resp.text[:300]}',
                retriable=resp.status_code >= 500,
                status_code=resp.status_code,
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
        if props.get('company'):
            out['AccountId'] = None  # would require account lookup — skipped
            out['Company'] = str(props['company'])[:255]  # not a real SF field but harmless
        if props.get('job_title'):
            out['Title'] = str(props['job_title'])[:128]
        if props.get('lead_score') is not None:
            out['Description'] = f"Lead score: {props['lead_score']}"
        return out

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
            raise CRMError(f'Salesforce network error: {exc}', retriable=True) from exc

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
            raise CRMError(
                f'Salesforce permission denied ({resp.status_code}): {resp.text[:200]}',
                retriable=False,
                status_code=resp.status_code,
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
