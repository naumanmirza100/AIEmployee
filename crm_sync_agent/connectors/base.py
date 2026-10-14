"""Abstract base for all CRM connectors."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class CRMError(Exception):
    """Normalized CRM error. `retriable=False` means do not retry (bad token, bad payload)."""

    def __init__(self, message: str, retriable: bool = True, status_code: Optional[int] = None):
        super().__init__(message)
        self.retriable = retriable
        self.status_code = status_code


def is_blank(value) -> bool:
    """Nothing in this CRM field: missing, empty, or only spaces."""
    return value is None or not str(value).strip()


class BaseCRMConnector(ABC):
    """
    Minimal interface every CRM connector must implement.

    All methods raise `CRMError` on failure. Callers should catch it and
    inspect `.retriable` to decide whether to re-queue.

    The rule for a record the customer already has in their CRM: it is theirs.
    We fill in a field that is empty there and leave every field that has a
    value, whatever ours says. `upsert_contact` used to send our names, phone,
    company, job title and lead status over whatever the CRM held, on every
    save of a lead; and an email, meeting or note for a contact we had no link
    to went through the same call with no names in hand, which renamed people
    to the first half of their email address.
    """

    def find_or_create_contact(self, email: str, properties: dict, create: bool = True) -> Optional[str]:
        """For an email, meeting or note: the id of the contact to file it under.

        An existing contact is returned as it is, never changed. A missing one
        is created from `properties` (the lead's own details), unless `create`
        is False, when None is returned."""
        existing = self.find_contact(email, properties)
        if existing and existing.get('id'):
            return str(existing['id'])
        if not create:
            return None
        return self.create_contact(email, properties)

    def find_contact(self, email: str, properties: dict) -> Optional[dict]:
        """The existing contact for this person, or None. By email unless a connector knows more."""
        return self.find_contact_by_email(email) if email else None

    @abstractmethod
    def create_contact(self, email: str, properties: dict) -> str:
        """Create a new contact and return its id. Never called for one that exists."""

    @abstractmethod
    def ping(self) -> bool:
        """Return True if credentials are valid and the API is reachable."""

    @abstractmethod
    def find_contact_by_email(self, email: str) -> Optional[dict]:
        """Return a dict with at least {"id": "..."} or None if not found."""

    @abstractmethod
    def upsert_contact(self, email: str, properties: dict) -> str:
        """
        Create the contact, or, if the CRM already has it, fill in only the
        fields that are empty there.

        `properties` may include:
            first_name, last_name, phone, company, job_title,
            linkedin_url, lead_score, lead_status, source
        Returns the CRM contact ID string.
        """

    @abstractmethod
    def log_email_activity(
        self,
        crm_contact_id: str,
        subject: str,
        body: str,
        sent_at,
        direction: str = 'OUTBOUND',
    ) -> Optional[str]:
        """
        Log an email send or receive as an activity/engagement.
        Returns the CRM activity ID or None if not supported.
        """

    @abstractmethod
    def log_meeting(
        self,
        crm_contact_id: str,
        title: str,
        start_time,
        end_time=None,
        notes: str = '',
    ) -> Optional[str]:
        """
        Log a meeting. Returns the CRM meeting ID or None.
        `start_time` / `end_time` are timezone-aware datetime objects.
        """

    @abstractmethod
    def log_note(self, crm_contact_id: str, body: str) -> Optional[str]:
        """Attach a plain-text note to a contact. Returns the CRM note ID or None."""
