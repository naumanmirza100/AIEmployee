"""HubSpot CRM connector — contacts + CRM v3 engagements (emails, meetings, notes).

Credentials required in CRMIntegration.credentials:
    {"access_token": "pat-na1-..."}

Required HubSpot private-app scopes:
    crm.objects.contacts.read
    crm.objects.contacts.write
    crm.objects.notes.read
    crm.objects.notes.write
    crm.objects.meetings.read
    crm.objects.meetings.write
    crm.objects.emails.read
    crm.objects.emails.write
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone as dt_timezone
from typing import Optional

import requests

from .base import BaseCRMConnector, CRMError

logger = logging.getLogger(__name__)

HUBSPOT_BASE = 'https://api.hubapi.com'
DEFAULT_TIMEOUT = 12


def _to_hs_timestamp(dt) -> int:
    """Convert a datetime to HubSpot's Unix-millisecond timestamp."""
    if dt is None:
        return int(datetime.now(dt_timezone.utc).timestamp() * 1000)
    if isinstance(dt, (int, float)):
        return int(dt)
    if hasattr(dt, 'timestamp'):
        return int(dt.timestamp() * 1000)
    return int(datetime.now(dt_timezone.utc).timestamp() * 1000)


class HubSpotConnector(BaseCRMConnector):
    """Full HubSpot connector: contacts + engagements via CRM v3 API."""

    def __init__(self, access_token: str, timeout: int = DEFAULT_TIMEOUT):
        if not access_token:
            raise CRMError('HubSpot access_token is required', retriable=False)
        self._token = access_token
        self._timeout = timeout

    # ------------------------------------------------------------------ #
    # BaseCRMConnector interface
    # ------------------------------------------------------------------ #

    def ping(self) -> bool:
        try:
            resp = self._get('/crm/v3/objects/contacts', params={'limit': 1})
            return resp.status_code == 200
        except CRMError:
            return False

    def find_contact_by_email(self, email: str) -> Optional[dict]:
        if not email:
            return None
        body = {
            'filterGroups': [{
                'filters': [{
                    'propertyName': 'email',
                    'operator': 'EQ',
                    'value': email.lower().strip(),
                }],
            }],
            'properties': ['email', 'firstname', 'lastname', 'phone', 'hs_object_id'],
            'limit': 1,
        }
        resp = self._post('/crm/v3/objects/contacts/search', json=body)
        results = (resp.json() or {}).get('results') or []
        return results[0] if results else None

    def upsert_contact(self, email: str, properties: dict) -> str:
        if not email:
            raise CRMError('email required for HubSpot upsert', retriable=False)

        existing = self.find_contact_by_email(email)
        hs_props = self._build_contact_props(email, properties)

        if existing:
            hs_id = str(existing.get('id', ''))
            if hs_id and self._contact_needs_update(existing.get('properties', {}), hs_props):
                self._patch(f'/crm/v3/objects/contacts/{hs_id}', json={'properties': hs_props})
            return hs_id

        resp = self._post('/crm/v3/objects/contacts', json={'properties': hs_props})
        return str((resp.json() or {}).get('id', ''))

    def log_email_activity(
        self,
        crm_contact_id: str,
        subject: str,
        body: str,
        sent_at,
        direction: str = 'OUTBOUND',
    ) -> Optional[str]:
        return self._log_engagement(
            eng_type='EMAIL',
            contact_id=crm_contact_id,
            timestamp=_to_hs_timestamp(sent_at),
            metadata={
                'subject': subject[:500] if subject else '(no subject)',
                'text': body[:10000] if body else '',
                'status': 'SENT' if direction.upper() == 'OUTBOUND' else 'RECEIVED',
            },
        )

    def log_meeting(
        self,
        crm_contact_id: str,
        title: str,
        start_time,
        end_time=None,
        notes: str = '',
    ) -> Optional[str]:
        start_ms = _to_hs_timestamp(start_time)
        end_ms = _to_hs_timestamp(end_time) if end_time else start_ms + 3_600_000
        return self._log_engagement(
            eng_type='MEETING',
            contact_id=crm_contact_id,
            timestamp=start_ms,
            metadata={
                'title': title[:500] if title else 'Meeting',
                'startTime': start_ms,
                'endTime': end_ms,
                'body': notes[:5000] if notes else '',
            },
        )

    def log_note(self, crm_contact_id: str, body: str) -> Optional[str]:
        return self._log_engagement(
            eng_type='NOTE',
            contact_id=crm_contact_id,
            timestamp=_to_hs_timestamp(None),
            metadata={'body': body[:10000] if body else ''},
        )

    def _log_engagement(self, eng_type: str, contact_id: str, timestamp: int, metadata: dict) -> Optional[str]:
        """Use legacy Engagements v1 API — works on free HubSpot accounts."""
        payload = {
            'engagement': {'active': True, 'type': eng_type, 'timestamp': timestamp},
            'associations': {'contactIds': [int(contact_id)]},
            'metadata': metadata,
        }
        try:
            resp = self._post('/engagements/v1/engagements', json=payload)
            return str(((resp.json() or {}).get('engagement') or {}).get('id', '')) or None
        except CRMError as e:
            if e.status_code == 403:
                logger.warning('HubSpot: engagement scope missing for type=%s (free plan limitation)', eng_type)
                return None
            raise

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _contact_association(contact_id: str, type_id: int) -> list:
        return [{
            'to': {'id': contact_id},
            'types': [{
                'associationCategory': 'HUBSPOT_DEFINED',
                'associationTypeId': type_id,
            }],
        }]

    @staticmethod
    def _build_contact_props(email: str, props: dict) -> dict:
        out: dict = {'email': email.lower().strip()}
        first = props.get('first_name', '') or ''
        last = props.get('last_name', '') or ''
        if not first and not last:
            full = props.get('name', '') or ''
            if full:
                first, _, last = full.strip().partition(' ')
        if first:
            out['firstname'] = str(first)[:100]
        if last:
            out['lastname'] = str(last)[:100]
        if props.get('phone'):
            out['phone'] = str(props['phone'])[:50]
        if props.get('company'):
            out['company'] = str(props['company'])[:255]
        if props.get('job_title'):
            out['jobtitle'] = str(props['job_title'])[:255]
        if props.get('linkedin_url'):
            out['hs_linkedin_url'] = str(props['linkedin_url'])[:500]
        if props.get('lead_status'):
            _status_map = {'hot': 'IN_PROGRESS', 'warm': 'OPEN', 'cold': 'NEW'}
            out['hs_lead_status'] = _status_map.get(str(props['lead_status']).lower(), 'NEW')
        # hubspotscore is read-only in HubSpot — skip it
        return out

    @staticmethod
    def _contact_needs_update(existing: dict, new_props: dict) -> bool:
        for key, value in new_props.items():
            if key == 'email':
                continue
            if str(existing.get(key) or '').strip() != str(value or '').strip():
                return True
        return False

    def _headers(self) -> dict:
        return {
            'Authorization': f'Bearer {self._token}',
            'Content-Type': 'application/json',
        }

    def _get(self, path: str, params=None):
        return self._request('GET', path, params=params)

    def _post(self, path: str, json=None):
        return self._request('POST', path, json=json)

    def _patch(self, path: str, json=None):
        return self._request('PATCH', path, json=json)

    def _request(self, method: str, path: str, params=None, json=None):
        url = f'{HUBSPOT_BASE}{path}'
        try:
            resp = requests.request(
                method, url,
                headers=self._headers(),
                params=params,
                json=json,
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            raise CRMError(f'HubSpot network error: {exc}', retriable=True) from exc

        if 200 <= resp.status_code < 300:
            return resp

        if resp.status_code in (401, 403):
            raise CRMError(
                f'HubSpot auth failed ({resp.status_code}): {resp.text[:200]}',
                retriable=False,
                status_code=resp.status_code,
            )
        if resp.status_code == 429 or resp.status_code >= 500:
            raise CRMError(
                f'HubSpot transient error ({resp.status_code}): {resp.text[:200]}',
                retriable=True,
                status_code=resp.status_code,
            )
        raise CRMError(
            f'HubSpot client error ({resp.status_code}): {resp.text[:200]}',
            retriable=False,
            status_code=resp.status_code,
        )
