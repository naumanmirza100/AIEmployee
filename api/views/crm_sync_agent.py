"""REST API views for the CRM Sync Agent."""
from __future__ import annotations

import logging

from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response

from api.authentication import CompanyUserTokenAuthentication
from api.permissions import IsCompanyUserOnly
from crm_sync_agent.models import CRMIntegration, CRMSyncLog, CRMSyncQueue

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ #
# Serialization helpers
# ------------------------------------------------------------------ #

def _serialize_integration(integration: CRMIntegration) -> dict:
    creds = dict(integration.credentials or {})
    # Mask secrets — never return raw tokens to the client
    for key in ('access_token', 'api_token', 'client_secret', 'password', 'security_token'):
        if key in creds and creds[key]:
            creds[key] = '***' + str(creds[key])[-4:]

    return {
        'id': integration.pk,
        'provider': integration.provider,
        'provider_label': integration.get_provider_display(),
        'credentials_preview': creds,
        'field_mappings': integration.field_mappings,
        'sync_contacts': integration.sync_contacts,
        'sync_emails': integration.sync_emails,
        'sync_meetings': integration.sync_meetings,
        'sync_notes': integration.sync_notes,
        'is_active': integration.is_active,
        'last_ping_at': integration.last_ping_at,
        'last_ping_ok': integration.last_ping_ok,
        'created_at': integration.created_at,
        'updated_at': integration.updated_at,
    }


def _serialize_log(log: CRMSyncLog) -> dict:
    return {
        'id': log.pk,
        'provider': log.integration.provider if log.integration else None,
        'object_type': log.object_type,
        'object_id': log.object_id,
        'crm_object_id': log.crm_object_id,
        'operation': log.operation,
        'status': log.status,
        'error_message': log.error_message,
        'attempted_at': log.attempted_at,
    }


# ------------------------------------------------------------------ #
# Integrations — list / create
# ------------------------------------------------------------------ #

@api_view(['GET', 'POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def integrations_list(request):
    company_user = request.user
    company = company_user.company

    if request.method == 'GET':
        qs = CRMIntegration.objects.filter(company=company).order_by('provider')
        return Response([_serialize_integration(i) for i in qs])

    # POST — create
    data = request.data
    provider = (data.get('provider') or '').strip()
    valid_providers = [p[0] for p in CRMIntegration.PROVIDERS]

    if provider not in valid_providers:
        return Response(
            {'error': f'provider must be one of: {valid_providers}'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not data.get('credentials'):
        return Response(
            {'error': 'credentials are required'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if CRMIntegration.objects.filter(company=company, provider=provider).exists():
        return Response(
            {'error': f'Integration with provider "{provider}" already exists.'},
            status=status.HTTP_409_CONFLICT,
        )

    integration = CRMIntegration.objects.create(
        company=company,
        provider=provider,
        credentials=data.get('credentials', {}),
        field_mappings=data.get('field_mappings', {}),
        sync_contacts=data.get('sync_contacts', True),
        sync_emails=data.get('sync_emails', True),
        sync_meetings=data.get('sync_meetings', True),
        sync_notes=data.get('sync_notes', True),
        is_active=data.get('is_active', True),
    )
    logger.info('CRM integration created: company=%d provider=%s', company.pk, provider)
    return Response(_serialize_integration(integration), status=status.HTTP_201_CREATED)


# ------------------------------------------------------------------ #
# Integrations — detail / update / delete
# ------------------------------------------------------------------ #

@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def integration_detail(request, integration_id: int):
    company_user = request.user
    company = company_user.company

    try:
        integration = CRMIntegration.objects.get(pk=integration_id, company=company)
    except CRMIntegration.DoesNotExist:
        return Response({'error': 'Integration not found.'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        return Response(_serialize_integration(integration))

    if request.method == 'DELETE':
        integration.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    # PUT / PATCH
    data = request.data
    if 'credentials' in data:
        integration.credentials = data['credentials']
    if 'field_mappings' in data:
        integration.field_mappings = data['field_mappings']
    for flag in ('sync_contacts', 'sync_emails', 'sync_meetings', 'sync_notes', 'is_active'):
        if flag in data:
            setattr(integration, flag, bool(data[flag]))
    integration.save()
    return Response(_serialize_integration(integration))


# ------------------------------------------------------------------ #
# Ping — test credentials
# ------------------------------------------------------------------ #

@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def integration_ping(request, integration_id: int):
    company_user = request.user
    company = company_user.company

    try:
        integration = CRMIntegration.objects.get(pk=integration_id, company=company)
    except CRMIntegration.DoesNotExist:
        return Response({'error': 'Integration not found.'}, status=status.HTTP_404_NOT_FOUND)

    from crm_sync_agent.agents.crm_sync_agent import CRMSyncAgent
    from crm_sync_agent.connectors.base import CRMError

    try:
        agent = CRMSyncAgent(company)
        connector = agent._get_connector(integration)
        ok = connector.ping()
    except CRMError as exc:
        ok = False
        logger.warning('CRM ping failed: %s', exc)
    except Exception as exc:
        ok = False
        logger.exception('CRM ping unexpected error: %s', exc)

    integration.last_ping_at = timezone.now()
    integration.last_ping_ok = ok
    integration.save(update_fields=['last_ping_at', 'last_ping_ok'])

    if ok:
        return Response({'status': 'ok', 'message': 'Connection successful.'})
    return Response(
        {'status': 'failed', 'message': 'Could not connect. Check credentials.'},
        status=status.HTTP_502_BAD_GATEWAY,
    )


# ------------------------------------------------------------------ #
# Trigger full lead re-sync
# ------------------------------------------------------------------ #

@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def integration_sync_leads(request, integration_id: int):
    company_user = request.user
    company = company_user.company

    try:
        CRMIntegration.objects.get(pk=integration_id, company=company)
    except CRMIntegration.DoesNotExist:
        return Response({'error': 'Integration not found.'}, status=status.HTTP_404_NOT_FOUND)

    try:
        from crm_sync_agent.tasks import sync_sdr_leads_to_crm
        sync_sdr_leads_to_crm.delay(company_id=company.pk)
        return Response({'status': 'queued', 'message': 'Full lead sync has been queued.'})
    except Exception:
        # Redis/Celery not available — run synchronously
        from crm_sync_agent.agents.crm_sync_agent import CRMSyncAgent
        from ai_sdr_agent.models import SDRLead, SDROutreachLog, SDRMeeting
        agent = CRMSyncAgent(company)

        # Sync leads (contacts)
        leads = SDRLead.objects.filter(company_user__company=company)
        for lead in leads:
            agent.enqueue_sdr_lead(lead)

        # Backfill past sent emails
        emails = SDROutreachLog.objects.filter(
            status='sent',
            enrollment__lead__company_user__company=company,
        ).select_related('enrollment__lead')
        for email in emails:
            agent.enqueue_email_sent(email)

        # Backfill past meetings
        meetings = SDRMeeting.objects.filter(
            lead__company_user__company=company,
        ).select_related('lead')
        for meeting in meetings:
            agent.enqueue_meeting(meeting)

        result = agent.process_pending(limit=500)
        return Response({
            'status': 'done',
            'message': f'Synced {leads.count()} leads, {emails.count()} emails, {meetings.count()} meetings.',
            'result': result,
        })


# ------------------------------------------------------------------ #
# Sync Logs
# ------------------------------------------------------------------ #

@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def sync_logs(request):
    company_user = request.user
    company = company_user.company

    provider = request.query_params.get('provider')
    obj_type = request.query_params.get('object_type')
    log_status = request.query_params.get('status')

    qs = CRMSyncLog.objects.filter(company=company).select_related('integration')
    if provider:
        qs = qs.filter(integration__provider=provider)
    if obj_type:
        qs = qs.filter(object_type=obj_type)
    if log_status:
        qs = qs.filter(status=log_status)

    return Response([_serialize_log(lg) for lg in qs[:200]])


# ------------------------------------------------------------------ #
# Queue Status
# ------------------------------------------------------------------ #

@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def queue_status(request):
    company_user = request.user
    company = company_user.company

    from django.db.models import Count
    breakdown = list(
        CRMSyncQueue.objects
        .filter(company=company)
        .values('status', 'object_type')
        .annotate(count=Count('id'))
        .order_by('status', 'object_type')
    )

    return Response({
        'total': CRMSyncQueue.objects.filter(company=company).count(),
        'pending': CRMSyncQueue.objects.filter(company=company, status=CRMSyncQueue.STATUS_PENDING).count(),
        'failed': CRMSyncQueue.objects.filter(company=company, status=CRMSyncQueue.STATUS_FAILED).count(),
        'done': CRMSyncQueue.objects.filter(company=company, status=CRMSyncQueue.STATUS_DONE).count(),
        'breakdown': breakdown,
    })


# ------------------------------------------------------------------ #
# Retry failed items
# ------------------------------------------------------------------ #

@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def retry_failed(request):
    company_user = request.user
    company = company_user.company

    count = CRMSyncQueue.objects.filter(
        company=company,
        status=CRMSyncQueue.STATUS_FAILED,
        attempts__lt=3,
    ).update(
        status=CRMSyncQueue.STATUS_PENDING,
        scheduled_at=timezone.now(),
        error_message='',
    )
    return Response({'requeued': count})
