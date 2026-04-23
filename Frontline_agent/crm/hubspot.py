"""HubSpot CRM client.

Authenticates with a per-tenant **Private App access token** (not OAuth) —
tenants create a private app in their HubSpot settings → Integrations → Private Apps,
grant it `crm.objects.contacts.read` + `crm.objects.contacts.write` scopes, and
paste the token into our UI. This avoids the OAuth-redirect + callback infra
and is the recommended path for server-to-server integrations HubSpot itself
documents for multi-tenant tools.

All calls include a short timeout and surface concrete errors; retries are the
caller's responsibility (the Celery task wraps them with exponential backoff).
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

HUBSPOT_BASE = 'https://api.hubapi.com'
DEFAULT_TIMEOUT = 10  # seconds


class HubSpotError(Exception):
    """Normalized error so the Celery retry path can distinguish by attr."""
    def __init__(self, message: str, status_code: Optional[int] = None, retriable: bool = True):
        super().__init__(message)
        self.status_code = status_code
        # 4xx that are the caller's fault (bad token, bad payload) should not retry.
        self.retriable = retriable


class HubSpotClient:
    """Thin wrapper over the five calls we need today.

    Example:
        client = HubSpotClient(access_token='pat-...')
        if client.ping():
            hs_id = client.upsert_contact(email='a@b.com', name='Alice')
    """

    def __init__(self, access_token: str, base_url: str = HUBSPOT_BASE,
                 timeout: int = DEFAULT_TIMEOUT):
        if not access_token:
            raise HubSpotError("HubSpot access_token is required", retriable=False)
        self.access_token = access_token
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def ping(self) -> bool:
        """Authenticated probe — returns True when the token is live.
        Uses the 'contacts' endpoint with limit=1 which is cheap and requires
        the same scope we'll need for writes anyway."""
        try:
            resp = self._get('/crm/v3/objects/contacts', params={'limit': 1})
            return resp.status_code == 200
        except HubSpotError:
            return False

    def find_contact_by_email(self, email: str) -> Optional[dict]:
        """Search the contacts index for an exact email match. Returns the
        full contact dict (with id + properties) or None."""
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

    def create_contact(self, email: str, name: str = '', phone: str = '',
                       extra_properties: Optional[dict] = None) -> dict:
        """Create a new contact. Returns the full HubSpot contact dict."""
        props = self._build_properties(email, name, phone, extra_properties)
        resp = self._post('/crm/v3/objects/contacts', json={'properties': props})
        return resp.json() or {}

    def update_contact(self, hubspot_contact_id: str, email: str = '',
                       name: str = '', phone: str = '',
                       extra_properties: Optional[dict] = None) -> dict:
        """Patch an existing contact."""
        props = self._build_properties(email, name, phone, extra_properties,
                                       require_email=False)
        if not props:
            return {}
        resp = self._patch(f'/crm/v3/objects/contacts/{hubspot_contact_id}',
                           json={'properties': props})
        return resp.json() or {}

    def upsert_contact(self, email: str, name: str = '', phone: str = '',
                       extra_properties: Optional[dict] = None) -> str:
        """Get-or-create by email. Returns the HubSpot contact id.

        Strategy: search by email first (costs one API call but saves a conflict
        retry on duplicate email — HubSpot returns 409 with the existing id,
        but parsing that is more fragile than a search)."""
        if not email:
            raise HubSpotError("email is required for upsert", retriable=False)
        existing = self.find_contact_by_email(email)
        if existing:
            hs_id = existing.get('id')
            # Only update when the fields we're pushing differ — saves an API call on idle syncs.
            existing_props = existing.get('properties') or {}
            if self._diff_requires_update(existing_props, name, phone, extra_properties):
                self.update_contact(hs_id, email=email, name=name, phone=phone,
                                    extra_properties=extra_properties)
            return str(hs_id)
        created = self.create_contact(email, name=name, phone=phone,
                                      extra_properties=extra_properties)
        return str(created.get('id') or '')

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _headers(self) -> dict:
        return {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json',
        }

    def _get(self, path: str, params: Optional[dict] = None):
        return self._request('GET', path, params=params)

    def _post(self, path: str, json: Optional[dict] = None):
        return self._request('POST', path, json=json)

    def _patch(self, path: str, json: Optional[dict] = None):
        return self._request('PATCH', path, json=json)

    def _request(self, method: str, path: str, params=None, json=None):
        url = f"{self.base_url}{path}"
        try:
            resp = requests.request(
                method, url, headers=self._headers(), params=params, json=json,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise HubSpotError(f"HubSpot network error: {exc}", retriable=True) from exc

        if 200 <= resp.status_code < 300:
            return resp
        # 401/403 → bad token → non-retriable, disable sync at caller
        if resp.status_code in (401, 403):
            raise HubSpotError(
                f"HubSpot auth failed (status={resp.status_code}): "
                f"{(resp.text or '')[:200]}",
                status_code=resp.status_code, retriable=False,
            )
        # 429/5xx → retriable
        if resp.status_code == 429 or resp.status_code >= 500:
            raise HubSpotError(
                f"HubSpot transient error (status={resp.status_code}): "
                f"{(resp.text or '')[:200]}",
                status_code=resp.status_code, retriable=True,
            )
        # Other 4xx → caller's payload is wrong → non-retriable
        raise HubSpotError(
            f"HubSpot client error (status={resp.status_code}): "
            f"{(resp.text or '')[:200]}",
            status_code=resp.status_code, retriable=False,
        )

    @staticmethod
    def _build_properties(email: str, name: str, phone: str,
                          extra: Optional[dict], require_email: bool = True) -> dict:
        """Build HubSpot's `properties` dict from our flat Contact fields.
        Splits `name` into firstname/lastname naively on the first space."""
        props: dict = {}
        if email:
            props['email'] = email.lower().strip()
        elif require_email:
            raise HubSpotError("email is required to build properties", retriable=False)
        if name:
            name = name.strip()
            if ' ' in name:
                first, _, last = name.partition(' ')
                props['firstname'] = first[:100]
                props['lastname'] = last[:100]
            else:
                props['firstname'] = name[:100]
        if phone:
            props['phone'] = phone.strip()[:50]
        if extra:
            for k, v in extra.items():
                # Only string-ish values; drop None.
                if v is None:
                    continue
                props[str(k)[:60]] = str(v)[:500]
        return props

    @staticmethod
    def _diff_requires_update(existing: dict, name: str, phone: str,
                              extra: Optional[dict]) -> bool:
        """Return True if any of the fields we'd push differ from HubSpot's
        current value. Avoids unnecessary PATCHes on idle syncs."""
        if name:
            want_first, _, want_last = name.strip().partition(' ')
            if (existing.get('firstname') or '').strip() != want_first.strip():
                return True
            if want_last and (existing.get('lastname') or '').strip() != want_last.strip():
                return True
        if phone and (existing.get('phone') or '').strip() != phone.strip():
            return True
        if extra:
            for k, v in extra.items():
                if v is None:
                    continue
                if (existing.get(str(k)) or '') != str(v):
                    return True
        return False
