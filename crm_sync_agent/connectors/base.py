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


class BaseCRMConnector(ABC):
    """
    Minimal interface every CRM connector must implement.

    All methods raise `CRMError` on failure. Callers should catch it and
    inspect `.retriable` to decide whether to re-queue.
    """

    @abstractmethod
    def ping(self) -> bool:
        """Return True if credentials are valid and the API is reachable."""

    @abstractmethod
    def find_contact_by_email(self, email: str) -> Optional[dict]:
        """Return a dict with at least {"id": "..."} or None if not found."""

    @abstractmethod
    def upsert_contact(self, email: str, properties: dict) -> str:
        """
        Create or update a contact by email.

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
