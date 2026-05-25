"""CRM Sync Agent — orchestrates contact, email, meeting, and note syncing
across all active CRM integrations for a given company.

Usage:
    agent = CRMSyncAgent(company)
    agent.enqueue_sdr_lead(lead)
    agent.enqueue_email_sent(outreach_log)
    agent.enqueue_meeting(meeting)
    stats = agent.process_pending(limit=100)
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Optional

from django.utils import timezone

from crm_sync_agent.connectors.base import BaseCRMConnector, CRMError
from crm_sync_agent.connectors.hubspot import HubSpotConnector
from crm_sync_agent.connectors.salesforce import SalesforceConnector
from crm_sync_agent.connectors.pipedrive import PipedriveConnector
from crm_sync_agent.models import (
    CRMIntegration,
    CRMContactMapping,
    CRMSyncLog,
    CRMSyncQueue,
)

logger = logging.getLogger(__name__)

# Exponential back-off delays (seconds) indexed by attempt number (0-based)
_BACKOFF_SECONDS = [0, 120, 600, 3600]


def _backoff_delay(attempts: int) -> int:
    idx = min(attempts, len(_BACKOFF_SECONDS) - 1)
    return _BACKOFF_SECONDS[idx]


class CRMSyncAgent:
    """
    Company-scoped CRM sync orchestrator.

    One instance per company. Loads all active integrations on construction
    and builds connector instances on-demand (cached per-call).
    """

    def __init__(self, company):
        self.company = company
        self._integrations = list(
            CRMIntegration.objects.filter(company=company, is_active=True)
        )
        self._connector_cache: dict[int, BaseCRMConnector] = {}

    # ------------------------------------------------------------------ #
    # Public enqueue helpers — called by signals
    # ------------------------------------------------------------------ #

    def enqueue_sdr_lead(self, lead) -> None:
        """Enqueue contact upsert when a SDR lead is created or updated."""
        if not self._integrations:
            return
        payload = self._lead_to_contact_payload(lead)
        for integration in self._integrations:
            if not integration.sync_contacts:
                continue
            self._enqueue(
                integration=integration,
                object_type=CRMSyncQueue.TYPE_CONTACT,
                operation=CRMSyncQueue.OP_CREATE,
                source_type=CRMSyncQueue.SOURCE_SDR_LEAD,
                source_id=lead.pk,
                payload=payload,
                priority=3,
            )

    def enqueue_email_sent(self, outreach_log) -> None:
        """Enqueue email activity when an SDR outreach email is sent."""
        if not self._integrations:
            return
        try:
            enrollment = outreach_log.enrollment
            lead = enrollment.lead
        except Exception:
            return

        payload = {
            'email': lead.email,
            'subject': outreach_log.subject_sent or '',
            'body': outreach_log.body_sent or '',
            'sent_at': outreach_log.sent_at.isoformat() if outreach_log.sent_at else None,
            'direction': 'OUTBOUND',
            'lead_first_name': lead.first_name or '',
            'lead_last_name': lead.last_name or '',
        }
        for integration in self._integrations:
            if not integration.sync_emails:
                continue
            self._enqueue(
                integration=integration,
                object_type=CRMSyncQueue.TYPE_EMAIL,
                operation=CRMSyncQueue.OP_CREATE,
                source_type=CRMSyncQueue.SOURCE_SDR_EMAIL,
                source_id=outreach_log.pk,
                payload=payload,
                priority=5,
            )

    def enqueue_reply_note(self, enrollment) -> None:
        """Enqueue a note when a lead replies to an outreach email."""
        if not self._integrations:
            return
        try:
            lead = enrollment.lead
        except Exception:
            return

        sentiment = getattr(enrollment, 'reply_sentiment', 'unknown') or 'unknown'
        body = (
            f"Lead replied to SDR outreach.\n"
            f"Sentiment: {sentiment}\n"
            f"Reply snippet: {(getattr(enrollment, 'reply_snippet', '') or '')[:500]}"
        )
        payload = {
            'email': lead.email,
            'note_body': body,
        }
        for integration in self._integrations:
            if not integration.sync_notes:
                continue
            self._enqueue(
                integration=integration,
                object_type=CRMSyncQueue.TYPE_NOTE,
                operation=CRMSyncQueue.OP_CREATE,
                source_type=CRMSyncQueue.SOURCE_SDR_NOTE,
                source_id=enrollment.pk,
                payload=payload,
                priority=5,
            )

    def enqueue_meeting(self, meeting) -> None:
        """Enqueue meeting sync when a SDR meeting is booked."""
        if not self._integrations:
            return
        try:
            lead = meeting.lead
        except Exception:
            return

        payload = {
            'email': lead.email,
            'title': meeting.title or f'Meeting with {lead.full_name or lead.email}',
            'start_time': meeting.scheduled_at.isoformat() if meeting.scheduled_at else None,
            'end_time': None,
            'notes': (
                f"Booked via AI SDR Agent.\n"
                f"Lead: {lead.full_name} <{lead.email}>\n"
                f"Company: {lead.company_name or 'N/A'}\n"
                f"Title: {lead.job_title or 'N/A'}"
            ),
        }
        for integration in self._integrations:
            if not integration.sync_meetings:
                continue
            self._enqueue(
                integration=integration,
                object_type=CRMSyncQueue.TYPE_MEETING,
                operation=CRMSyncQueue.OP_CREATE,
                source_type=CRMSyncQueue.SOURCE_SDR_MEETING,
                source_id=meeting.pk,
                payload=payload,
                priority=2,
            )

    # ------------------------------------------------------------------ #
    # Queue processing
    # ------------------------------------------------------------------ #

    def process_pending(self, limit: int = 50) -> dict:
        """
        Fetch and process up to `limit` pending/retryable items.
        Returns stats: {processed, succeeded, failed, skipped}.
        """
        now = timezone.now()
        items = (
            CRMSyncQueue.objects
            .filter(
                company=self.company,
                status__in=[CRMSyncQueue.STATUS_PENDING, CRMSyncQueue.STATUS_FAILED],
                scheduled_at__lte=now,
                attempts__lt=models_max_attempts(),
            )
            .select_related('integration')
            .order_by('priority', 'scheduled_at')[:limit]
        )

        stats = {'processed': 0, 'succeeded': 0, 'failed': 0, 'skipped': 0}
        for item in items:
            if item.attempts >= item.max_attempts:
                stats['skipped'] += 1
                continue
            stats['processed'] += 1
            ok = self._process_item(item)
            if ok:
                stats['succeeded'] += 1
            else:
                stats['failed'] += 1
        return stats

    def _process_item(self, item: CRMSyncQueue) -> bool:
        """Process one queue item. Returns True on success."""
        item.status = CRMSyncQueue.STATUS_PROCESSING
        item.attempts += 1
        item.last_attempted_at = timezone.now()
        item.save(update_fields=['status', 'attempts', 'last_attempted_at'])

        try:
            connector = self._get_connector(item.integration)
        except CRMError as exc:
            return self._fail_item(item, str(exc), retriable=exc.retriable)
        except Exception as exc:
            return self._fail_item(item, f'Connector init error: {exc}', retriable=False)

        try:
            crm_id = self._dispatch(connector, item)
        except CRMError as exc:
            return self._fail_item(item, str(exc), retriable=exc.retriable)
        except Exception as exc:
            logger.exception('Unexpected error processing CRM queue item %d', item.pk)
            return self._fail_item(item, f'Unexpected: {exc}', retriable=True)

        # Success
        item.status = CRMSyncQueue.STATUS_DONE
        item.error_message = ''
        item.save(update_fields=['status', 'error_message'])
        self._write_log(item, status=CRMSyncLog.STATUS_SUCCESS, crm_object_id=crm_id or '')
        return True

    def _dispatch(self, connector: BaseCRMConnector, item: CRMSyncQueue) -> Optional[str]:
        """Route the item to the correct connector method."""
        p = item.payload

        if item.object_type == CRMSyncQueue.TYPE_CONTACT:
            return self._sync_contact(connector, item, p)

        if item.object_type == CRMSyncQueue.TYPE_EMAIL:
            return self._sync_email(connector, item, p)

        if item.object_type == CRMSyncQueue.TYPE_MEETING:
            return self._sync_meeting(connector, item, p)

        if item.object_type == CRMSyncQueue.TYPE_NOTE:
            return self._sync_note(connector, item, p)

        raise CRMError(f'Unknown object_type: {item.object_type}', retriable=False)

    def _sync_contact(
        self, connector: BaseCRMConnector, item: CRMSyncQueue, p: dict
    ) -> Optional[str]:
        email = p.get('email', '')
        linkedin_url = p.get('linkedin_url', '')
        name = p.get('name') or f"{p.get('first_name','')} {p.get('last_name','')}".strip()
        if not email and not linkedin_url and not name:
            raise CRMError('Contact has no email, linkedin_url, or name — cannot sync', retriable=False)

        crm_id = connector.upsert_contact(email, p)

        # Persist mapping so downstream email/meeting syncs can look it up
        if crm_id:
            CRMContactMapping.objects.update_or_create(
                integration=item.integration,
                source_type=item.source_type,
                source_id=item.source_id,
                defaults={'crm_contact_id': crm_id, 'company': self.company},
            )
        return crm_id

    def _sync_email(
        self, connector: BaseCRMConnector, item: CRMSyncQueue, p: dict
    ) -> Optional[str]:
        email = p.get('email', '')
        crm_contact_id = self._resolve_crm_contact_id(
            item.integration, CRMContactMapping.SOURCE_SDR_LEAD,
            email, connector, p
        )
        if not crm_contact_id:
            raise CRMError(f'Cannot resolve CRM contact for email {email}', retriable=True)

        from datetime import datetime
        sent_at_str = p.get('sent_at')
        sent_at = None
        if sent_at_str:
            try:
                from django.utils.dateparse import parse_datetime
                sent_at = parse_datetime(sent_at_str)
            except Exception:
                pass

        return connector.log_email_activity(
            crm_contact_id=crm_contact_id,
            subject=p.get('subject', ''),
            body=p.get('body', ''),
            sent_at=sent_at,
            direction=p.get('direction', 'OUTBOUND'),
        )

    def _sync_meeting(
        self, connector: BaseCRMConnector, item: CRMSyncQueue, p: dict
    ) -> Optional[str]:
        email = p.get('email', '')
        crm_contact_id = self._resolve_crm_contact_id(
            item.integration, CRMContactMapping.SOURCE_SDR_LEAD,
            email, connector, p
        )
        if not crm_contact_id:
            raise CRMError(f'Cannot resolve CRM contact for meeting {email}', retriable=True)

        from django.utils.dateparse import parse_datetime
        start_time = None
        end_time = None
        if p.get('start_time'):
            try:
                start_time = parse_datetime(p['start_time'])
            except Exception:
                pass
        if p.get('end_time'):
            try:
                end_time = parse_datetime(p['end_time'])
            except Exception:
                pass

        return connector.log_meeting(
            crm_contact_id=crm_contact_id,
            title=p.get('title', 'Meeting'),
            start_time=start_time or timezone.now(),
            end_time=end_time,
            notes=p.get('notes', ''),
        )

    def _sync_note(
        self, connector: BaseCRMConnector, item: CRMSyncQueue, p: dict
    ) -> Optional[str]:
        email = p.get('email', '')
        crm_contact_id = self._resolve_crm_contact_id(
            item.integration, CRMContactMapping.SOURCE_SDR_LEAD,
            email, connector, p
        )
        if not crm_contact_id:
            raise CRMError(f'Cannot resolve CRM contact for note {email}', retriable=True)

        return connector.log_note(
            crm_contact_id=crm_contact_id,
            body=p.get('note_body', ''),
        )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _resolve_crm_contact_id(
        self,
        integration: CRMIntegration,
        source_type: str,
        email: str,
        connector: BaseCRMConnector,
        props: dict,
    ) -> Optional[str]:
        """
        Look up the CRM contact ID from the mapping table.
        If not found, attempt a just-in-time upsert and persist the mapping.
        Works for leads with email OR linkedin_url (Apify leads often have no email).
        """
        from ai_sdr_agent.models import SDRLead

        # Try mapping table first (fast path — no API call)
        try:
            lead = None
            if email:
                lead = SDRLead.objects.filter(
                    company_user__company=self.company, email__iexact=email
                ).first()
            if not lead and props.get('linkedin_url'):
                lead = SDRLead.objects.filter(
                    company_user__company=self.company,
                    linkedin_url=props['linkedin_url'],
                ).first()
            if lead:
                mapping = CRMContactMapping.objects.filter(
                    integration=integration,
                    source_type=source_type,
                    source_id=lead.pk,
                ).first()
                if mapping:
                    return mapping.crm_contact_id
        except Exception:
            pass

        # Fall back: upsert in CRM (handles email or linkedin_url as identifier)
        crm_id = connector.upsert_contact(email, props)
        if crm_id:
            try:
                lead = None
                if email:
                    lead = SDRLead.objects.filter(
                        company_user__company=self.company, email__iexact=email
                    ).first()
                if not lead and props.get('linkedin_url'):
                    lead = SDRLead.objects.filter(
                        company_user__company=self.company,
                        linkedin_url=props['linkedin_url'],
                    ).first()
                if lead:
                    CRMContactMapping.objects.update_or_create(
                        integration=integration,
                        source_type=source_type,
                        source_id=lead.pk,
                        defaults={'crm_contact_id': crm_id, 'company': self.company},
                    )
            except Exception:
                pass
        return crm_id

    def _get_connector(self, integration: CRMIntegration) -> BaseCRMConnector:
        if integration.pk in self._connector_cache:
            return self._connector_cache[integration.pk]

        creds = integration.credentials or {}
        provider = integration.provider

        if provider == CRMIntegration.PROVIDER_HUBSPOT:
            connector: BaseCRMConnector = HubSpotConnector(
                access_token=creds.get('access_token', ''),
            )
        elif provider == CRMIntegration.PROVIDER_SALESFORCE:
            connector = SalesforceConnector(credentials=creds)
        elif provider == CRMIntegration.PROVIDER_PIPEDRIVE:
            connector = PipedriveConnector(
                api_token=creds.get('api_token', ''),
            )
        else:
            raise CRMError(f'Unknown CRM provider: {provider}', retriable=False)

        self._connector_cache[integration.pk] = connector
        return connector

    def _enqueue(
        self,
        integration: CRMIntegration,
        object_type: str,
        operation: str,
        source_type: str,
        source_id: int,
        payload: dict,
        priority: int = 5,
    ) -> None:
        # Deduplicate: if a pending item already exists for the same
        # integration + source, update its payload rather than double-queue.
        existing = CRMSyncQueue.objects.filter(
            integration=integration,
            object_type=object_type,
            source_type=source_type,
            source_id=source_id,
            status__in=[CRMSyncQueue.STATUS_PENDING, CRMSyncQueue.STATUS_FAILED],
        ).first()

        if existing:
            existing.payload = payload
            existing.scheduled_at = timezone.now()
            existing.save(update_fields=['payload', 'scheduled_at'])
            return

        CRMSyncQueue.objects.create(
            company=self.company,
            integration=integration,
            object_type=object_type,
            operation=operation,
            source_type=source_type,
            source_id=source_id,
            priority=priority,
            payload=payload,
        )

    def _fail_item(self, item: CRMSyncQueue, error: str, retriable: bool) -> bool:
        if retriable and item.attempts < item.max_attempts:
            delay = _backoff_delay(item.attempts)
            item.status = CRMSyncQueue.STATUS_FAILED
            item.error_message = error[:2000]
            item.scheduled_at = timezone.now() + timedelta(seconds=delay)
        else:
            item.status = CRMSyncQueue.STATUS_FAILED
            item.error_message = error[:2000]
        item.save(update_fields=['status', 'error_message', 'scheduled_at'])
        self._write_log(item, status=CRMSyncLog.STATUS_FAILED, error=error)
        logger.warning(
            'CRM sync failed [%s] item=%d attempt=%d retriable=%s: %s',
            item.integration.provider, item.pk, item.attempts, retriable, error[:200],
        )
        return False

    @staticmethod
    def _write_log(
        item: CRMSyncQueue,
        status: str,
        crm_object_id: str = '',
        error: str = '',
    ) -> None:
        try:
            CRMSyncLog.objects.create(
                company=item.company,
                integration=item.integration,
                object_type=item.object_type,
                object_id=f'{item.source_type}:{item.source_id}',
                crm_object_id=crm_object_id,
                operation=item.operation,
                status=status,
                error_message=error[:2000],
                payload=item.payload,
            )
        except Exception:
            logger.exception('Failed to write CRMSyncLog for item %d', item.pk)

    @staticmethod
    def _lead_to_contact_payload(lead) -> dict:
        return {
            'email': lead.email or '',
            'first_name': lead.first_name or '',
            'last_name': lead.last_name or '',
            'name': lead.full_name or f'{lead.first_name} {lead.last_name}'.strip(),
            'phone': lead.phone or '',
            'company': lead.company_name or '',
            'job_title': lead.job_title or '',
            'linkedin_url': lead.linkedin_url or '',
            'lead_score': getattr(lead, 'score', None),
            'lead_status': getattr(lead, 'temperature', ''),
            'source': 'ai_sdr_agent',
        }


def models_max_attempts() -> int:
    """Default max attempts ceiling for queue queries."""
    return 3
