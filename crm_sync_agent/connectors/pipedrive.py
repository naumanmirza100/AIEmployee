"""Pipedrive CRM connector — Persons, Activities (emails/calls), Notes.

Credentials required in CRMIntegration.credentials:
    {"api_token": "..."}
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone as dt_timezone
from typing import Optional

import requests

from .base import BaseCRMConnector, CRMError

logger = logging.getLogger(__name__)

PIPEDRIVE_BASE = 'https://api.pipedrive.com/v1'
DEFAULT_TIMEOUT = 12


def _pd_date(dt) -> str:
    """Format datetime as YYYY-MM-DD for Pipedrive date fields."""
    if dt is None:
        return datetime.now(dt_timezone.utc).strftime('%Y-%m-%d')
    if hasattr(dt, 'strftime'):
        return dt.strftime('%Y-%m-%d')
    return datetime.now(dt_timezone.utc).strftime('%Y-%m-%d')


def _pd_time(dt) -> str:
    """Format datetime as HH:MM for Pipedrive time fields."""
    if dt is None:
        return datetime.now(dt_timezone.utc).strftime('%H:%M')
    if hasattr(dt, 'strftime'):
        return dt.strftime('%H:%M')
    return datetime.now(dt_timezone.utc).strftime('%H:%M')


class PipedriveConnector(BaseCRMConnector):
    """Pipedrive REST API v1 connector."""

    def __init__(self, api_token: str, timeout: int = DEFAULT_TIMEOUT):
        if not api_token:
            raise CRMError('Pipedrive api_token is required', retriable=False)
        self._token = api_token
        self._timeout = timeout

    # ------------------------------------------------------------------ #
    # BaseCRMConnector interface
    # ------------------------------------------------------------------ #

    def ping(self) -> bool:
        try:
            resp = self._get('/users/me')
            data = resp.json() or {}
            return data.get('success') is True
        except CRMError:
            return False

    def find_contact_by_email(self, email: str) -> Optional[dict]:
        resp = self._get('/persons/search', params={
            'term': email.lower().strip(),
            'fields': 'email',
            'exact_match': 'true',
            'limit': 1,
        })
        items = ((resp.json() or {}).get('data') or {}).get('items') or []
        if items:
            person = items[0].get('item') or {}
            return {'id': str(person.get('id', '')), 'properties': person}
        return None

    def upsert_contact(self, email: str, properties: dict) -> str:
        existing = self.find_contact_by_email(email)
        pd_data = self._build_person_payload(email, properties)

        if existing:
            pid = existing['id']
            self._put(f'/persons/{pid}', json=pd_data)
            return pid

        resp = self._post('/persons', json=pd_data)
        return str(((resp.json() or {}).get('data') or {}).get('id', ''))

    def log_email_activity(
        self,
        crm_contact_id: str,
        subject: str,
        body: str,
        sent_at,
        direction: str = 'OUTBOUND',
    ) -> Optional[str]:
        activity = {
            'subject': (subject or '(no subject)')[:255],
            'note': (body or '')[:5000],
            'type': 'email',
            'person_id': int(crm_contact_id),
            'done': 1,
            'due_date': _pd_date(sent_at),
            'due_time': _pd_time(sent_at),
        }
        resp = self._post('/activities', json=activity)
        return str(((resp.json() or {}).get('data') or {}).get('id', '')) or None

    def log_meeting(
        self,
        crm_contact_id: str,
        title: str,
        start_time,
        end_time=None,
        notes: str = '',
    ) -> Optional[str]:
        activity = {
            'subject': (title or 'Meeting')[:255],
            'note': (notes or '')[:5000],
            'type': 'meeting',
            'person_id': int(crm_contact_id),
            'done': 1,
            'due_date': _pd_date(start_time),
            'due_time': _pd_time(start_time),
        }
        resp = self._post('/activities', json=activity)
        return str(((resp.json() or {}).get('data') or {}).get('id', '')) or None

    def log_note(self, crm_contact_id: str, body: str) -> Optional[str]:
        note = {
            'content': (body or '')[:10000],
            'person_id': int(crm_contact_id),
        }
        resp = self._post('/notes', json=note)
        return str(((resp.json() or {}).get('data') or {}).get('id', '')) or None

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _build_person_payload(email: str, props: dict) -> dict:
        first = props.get('first_name', '') or ''
        last = props.get('last_name', '') or ''
        if not first and not last:
            full = props.get('name', '') or email.split('@')[0]
            parts = full.strip().split()
            first = parts[0] if parts else ''
            last = ' '.join(parts[1:]) if len(parts) > 1 else ''
        name = f'{first} {last}'.strip() or email.split('@')[0]
        out: dict = {
            'name': name[:255],
            'email': [{'value': email.lower().strip(), 'primary': True}],
        }
        if props.get('phone'):
            out['phone'] = [{'value': str(props['phone']), 'primary': True}]
        if props.get('job_title'):
            out['job_title'] = str(props['job_title'])[:255]
        return out

    def _params(self, extra: dict | None = None) -> dict:
        p = {'api_token': self._token}
        if extra:
            p.update(extra)
        return p

    def _get(self, path: str, params=None):
        return self._request('GET', path, params=params)

    def _post(self, path: str, json=None):
        return self._request('POST', path, json=json)

    def _put(self, path: str, json=None):
        return self._request('PUT', path, json=json)

    def _request(self, method: str, path: str, params=None, json=None):
        url = f'{PIPEDRIVE_BASE}{path}'
        qp = self._params(params)
        try:
            resp = requests.request(
                method, url,
                params=qp,
                json=json,
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            raise CRMError(f'Pipedrive network error: {exc}', retriable=True) from exc

        if 200 <= resp.status_code < 300:
            return resp
        if resp.status_code in (401, 403):
            raise CRMError(
                f'Pipedrive auth failed ({resp.status_code}): {resp.text[:200]}',
                retriable=False,
                status_code=resp.status_code,
            )
        if resp.status_code == 429 or resp.status_code >= 500:
            raise CRMError(
                f'Pipedrive transient error ({resp.status_code}): {resp.text[:200]}',
                retriable=True,
                status_code=resp.status_code,
            )
        raise CRMError(
            f'Pipedrive client error ({resp.status_code}): {resp.text[:300]}',
            retriable=False,
            status_code=resp.status_code,
        )
