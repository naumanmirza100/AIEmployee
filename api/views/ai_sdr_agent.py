"""
AI SDR Agent — REST API views
=================================
Endpoints for Lead Research & Enrichment, Lead Qualification, and ICP management.

Auth: CompanyUserTokenAuthentication + IsCompanyUserOnly  (same as every other agent)
"""

import csv
import io
import json
import logging

from django.db.models import Q
from django.utils import timezone
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response

from api.authentication import CompanyUserTokenAuthentication
from api.permissions import IsCompanyUserOnly
from ai_sdr_agent.models import (
    SDRIcpProfile, SDRLead, SDRLeadResearchJob,
    SDRCampaign, SDRCampaignStep, SDRCampaignEnrollment, SDROutreachLog, SDRMeeting,
)
from ai_sdr_agent.agents.lead_research_agent import LeadResearchAgent
from ai_sdr_agent.agents.lead_qualification_agent import LeadQualificationAgent
from ai_sdr_agent.agents.outreach_agent import OutreachAgent

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Singletons — initialised once, reused across requests
# --------------------------------------------------------------------------
_research_agent: LeadResearchAgent | None = None
_qualification_agent: LeadQualificationAgent | None = None
_outreach_agent: OutreachAgent | None = None


def _get_research_agent() -> LeadResearchAgent:
    global _research_agent
    if _research_agent is None:
        _research_agent = LeadResearchAgent()
    return _research_agent


def _get_qualification_agent() -> LeadQualificationAgent:
    global _qualification_agent
    if _qualification_agent is None:
        _qualification_agent = LeadQualificationAgent()
    return _qualification_agent


def _get_outreach_agent() -> OutreachAgent:
    global _outreach_agent
    if _outreach_agent is None:
        _outreach_agent = OutreachAgent()
    return _outreach_agent


# --------------------------------------------------------------------------
# Serialisers
# --------------------------------------------------------------------------

def _serialize_lead(lead: SDRLead) -> dict:
    return {
        'id': lead.id,
        'full_name': lead.display_name,
        'first_name': lead.first_name,
        'last_name': lead.last_name,
        'email': lead.email,
        'phone': lead.phone,
        'job_title': lead.job_title,
        'seniority_level': lead.seniority_level,
        'department': lead.department,
        'company_name': lead.company_name,
        'company_domain': lead.company_domain,
        'company_industry': lead.company_industry,
        'company_size': lead.company_size,
        'company_size_range': lead.company_size_range,
        'company_location': lead.company_location,
        'company_technologies': lead.company_technologies,
        'linkedin_url': lead.linkedin_url,
        'company_linkedin_url': lead.company_linkedin_url,
        'company_website': lead.company_website,
        'recent_news': lead.recent_news,
        'buying_signals': lead.buying_signals,
        'score': lead.score,
        'temperature': lead.temperature,
        'score_breakdown': lead.score_breakdown,
        'qualification_reasoning': lead.qualification_reasoning,
        'status': lead.status,
        'source': lead.source,
        'qualified_at': lead.qualified_at.isoformat() if lead.qualified_at else None,
        'created_at': lead.created_at.isoformat(),
        'updated_at': lead.updated_at.isoformat(),
    }


def _serialize_icp(icp: SDRIcpProfile) -> dict:
    return {
        'id': icp.id,
        'name': icp.name,
        'industries': icp.industries,
        'job_titles': icp.job_titles,
        'company_size_min': icp.company_size_min,
        'company_size_max': icp.company_size_max,
        'locations': icp.locations,
        'keywords': icp.keywords,
        'hot_threshold': icp.hot_threshold,
        'warm_threshold': icp.warm_threshold,
        'is_active': icp.is_active,
    }


def _lead_stats(company_user) -> dict:
    qs = SDRLead.objects.filter(company_user=company_user)
    return {
        'total': qs.count(),
        'hot': qs.filter(temperature='hot').count(),
        'warm': qs.filter(temperature='warm').count(),
        'cold': qs.filter(temperature='cold').count(),
        'unscored': qs.filter(score__isnull=True).count(),
    }


# ==========================================================================
# ICP Profile
# ==========================================================================

@api_view(['GET', 'POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def icp_profile(request):
    """GET → return active ICP. POST → upsert ICP."""
    company_user = request.user

    if request.method == 'GET':
        try:
            icp = SDRIcpProfile.objects.filter(company_user=company_user, is_active=True).first()
            return Response({'status': 'success', 'data': _serialize_icp(icp) if icp else None})
        except Exception as exc:
            logger.error("Get ICP error: %s", exc)
            return Response({'status': 'error', 'message': str(exc)}, status=500)

    # POST — save / update
    try:
        data = request.data
        icp, _ = SDRIcpProfile.objects.update_or_create(
            company_user=company_user,
            is_active=True,
            defaults={
                'name': data.get('name', 'Default ICP'),
                'industries': data.get('industries', []),
                'job_titles': data.get('job_titles', []),
                'company_size_min': data.get('company_size_min') or None,
                'company_size_max': data.get('company_size_max') or None,
                'locations': data.get('locations', []),
                'keywords': data.get('keywords', []),
                'hot_threshold': int(data.get('hot_threshold', 70)),
                'warm_threshold': int(data.get('warm_threshold', 40)),
            },
        )
        return Response({'status': 'success', 'message': 'ICP saved.', 'data': _serialize_icp(icp)})
    except Exception as exc:
        logger.error("Save ICP error: %s", exc)
        return Response({'status': 'error', 'message': str(exc)}, status=500)


# ==========================================================================
# Leads — list / create
# ==========================================================================

@api_view(['GET', 'POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def leads_list(request):
    company_user = request.user

    if request.method == 'GET':
        try:
            qs = SDRLead.objects.filter(company_user=company_user)

            search = request.GET.get('search', '').strip()
            if search:
                qs = qs.filter(
                    Q(full_name__icontains=search)
                    | Q(company_name__icontains=search)
                    | Q(email__icontains=search)
                    | Q(job_title__icontains=search)
                )

            temp = request.GET.get('temperature', '')
            if temp:
                qs = qs.filter(temperature=temp)

            status_f = request.GET.get('status', '')
            if status_f:
                qs = qs.filter(status=status_f)

            leads = [_serialize_lead(l) for l in qs.select_related()[:200]]
            return Response({'status': 'success', 'data': leads, 'stats': _lead_stats(company_user)})
        except Exception as exc:
            logger.error("List leads error: %s", exc)
            return Response({'status': 'error', 'message': str(exc)}, status=500)

    # POST — manual create
    try:
        d = request.data
        full_name = d.get('full_name') or f"{d.get('first_name', '')} {d.get('last_name', '')}".strip()
        lead = SDRLead.objects.create(
            company_user=company_user,
            first_name=d.get('first_name', ''),
            last_name=d.get('last_name', ''),
            full_name=full_name,
            email=d.get('email', ''),
            phone=d.get('phone', ''),
            job_title=d.get('job_title', ''),
            company_name=d.get('company_name', ''),
            company_industry=d.get('company_industry', ''),
            company_size=d.get('company_size') or None,
            company_location=d.get('company_location', ''),
            linkedin_url=d.get('linkedin_url', ''),
            company_website=d.get('company_website', ''),
            source='manual',
            status='new',
        )
        return Response({'status': 'success', 'data': _serialize_lead(lead)}, status=201)
    except Exception as exc:
        logger.error("Create lead error: %s", exc)
        return Response({'status': 'error', 'message': str(exc)}, status=500)


# ==========================================================================
# Lead detail — get / update / delete
# ==========================================================================

@api_view(['GET', 'PUT', 'DELETE'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def lead_detail(request, lead_id):
    company_user = request.user
    try:
        lead = SDRLead.objects.get(id=lead_id, company_user=company_user)
    except SDRLead.DoesNotExist:
        return Response({'status': 'error', 'message': 'Lead not found.'}, status=404)

    if request.method == 'GET':
        return Response({'status': 'success', 'data': _serialize_lead(lead)})

    if request.method == 'PUT':
        try:
            d = request.data
            for field in [
                'first_name', 'last_name', 'full_name', 'email', 'phone',
                'job_title', 'company_name', 'company_industry',
                'company_size', 'company_location', 'linkedin_url',
                'company_website', 'status',
            ]:
                if field in d:
                    setattr(lead, field, d[field])
            lead.save()
            return Response({'status': 'success', 'data': _serialize_lead(lead)})
        except Exception as exc:
            return Response({'status': 'error', 'message': str(exc)}, status=500)

    # DELETE
    lead.delete()
    return Response({'status': 'success', 'message': 'Lead deleted.'})


# ==========================================================================
# Qualify single lead
# ==========================================================================

@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def qualify_lead(request, lead_id):
    """Run AI qualification on a single lead."""
    company_user = request.user
    try:
        lead = SDRLead.objects.get(id=lead_id, company_user=company_user)
        icp = SDRIcpProfile.objects.filter(company_user=company_user, is_active=True).first()
        if not icp:
            return Response({'status': 'error', 'message': 'Set up your ICP profile first.'}, status=400)

        result = _get_qualification_agent().qualify_lead(lead, icp)
        lead.score = result['score']
        lead.temperature = result['temperature']
        lead.score_breakdown = result.get('score_breakdown', {})
        lead.qualification_reasoning = result.get('qualification_reasoning', '')
        lead.qualified_at = timezone.now()
        lead.status = 'qualified'
        lead.save()
        return Response({'status': 'success', 'data': _serialize_lead(lead)})
    except SDRLead.DoesNotExist:
        return Response({'status': 'error', 'message': 'Lead not found.'}, status=404)
    except Exception as exc:
        logger.error("Qualify lead error: %s", exc)
        return Response({'status': 'error', 'message': str(exc)}, status=500)


# ==========================================================================
# Qualify ALL unscored leads
# ==========================================================================

@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def qualify_all_leads(request):
    """Batch-qualify up to 50 unscored leads."""
    company_user = request.user
    try:
        icp = SDRIcpProfile.objects.filter(company_user=company_user, is_active=True).first()
        if not icp:
            return Response({'status': 'error', 'message': 'Set up your ICP profile first.'}, status=400)

        unscored = SDRLead.objects.filter(company_user=company_user, score__isnull=True)[:50]
        agent = _get_qualification_agent()
        qualified = errors = 0

        for lead in unscored:
            try:
                result = agent.qualify_lead(lead, icp)
                lead.score = result['score']
                lead.temperature = result['temperature']
                lead.score_breakdown = result.get('score_breakdown', {})
                lead.qualification_reasoning = result.get('qualification_reasoning', '')
                lead.qualified_at = timezone.now()
                lead.status = 'qualified'
                lead.save()
                qualified += 1
            except Exception as exc:
                logger.error("Qualify lead %s error: %s", lead.id, exc)
                errors += 1

        return Response({
            'status': 'success',
            'message': f'Qualified {qualified} leads. {errors} errors.',
            'qualified': qualified,
            'errors': errors,
            'stats': _lead_stats(company_user),
        })
    except Exception as exc:
        logger.error("Qualify-all error: %s", exc)
        return Response({'status': 'error', 'message': str(exc)}, status=500)


# ==========================================================================
# Research (find new leads)
# ==========================================================================

@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def research_leads(request):
    """
    Find new leads from Apollo.io (if key configured) or generate via Groq AI.
    Auto-qualifies found leads immediately.
    """
    company_user = request.user
    try:
        count = min(int(request.data.get('count', 20)), 50)
        icp = SDRIcpProfile.objects.filter(company_user=company_user, is_active=True).first()
        if not icp:
            return Response({'status': 'error', 'message': 'Set up your ICP profile first.'}, status=400)

        job = SDRLeadResearchJob.objects.create(
            company_user=company_user,
            icp_profile=icp,
            status='running',
            search_params={'industries': icp.industries, 'job_titles': icp.job_titles, 'count': count},
            started_at=timezone.now(),
        )

        try:
            researcher = _get_research_agent()
            raw_leads = researcher.search_leads(icp, count=count)

            created = 0
            for ld in raw_leads:
                full_name = ld.get('full_name') or f"{ld.get('first_name','')} {ld.get('last_name','')}".strip()
                SDRLead.objects.create(
                    company_user=company_user,
                    icp_profile=icp,
                    first_name=ld.get('first_name', ''),
                    last_name=ld.get('last_name', ''),
                    full_name=full_name,
                    email=ld.get('email', ''),
                    phone=ld.get('phone', ''),
                    job_title=ld.get('job_title', ''),
                    seniority_level=ld.get('seniority_level', ''),
                    department=ld.get('department', ''),
                    company_name=ld.get('company_name', ''),
                    company_domain=ld.get('company_domain', ''),
                    company_industry=ld.get('company_industry', ''),
                    company_size=ld.get('company_size') or None,
                    company_size_range=ld.get('company_size_range', ''),
                    company_location=ld.get('company_location', ''),
                    company_technologies=ld.get('company_technologies', []),
                    linkedin_url=ld.get('linkedin_url', ''),
                    company_linkedin_url=ld.get('company_linkedin_url', ''),
                    company_website=ld.get('company_website', ''),
                    recent_news=ld.get('recent_news', []),
                    buying_signals=ld.get('buying_signals', []),
                    apollo_id=ld.get('apollo_id', ''),
                    raw_data=ld.get('raw_data', {}),
                    source=ld.get('source', 'ai_generated'),
                    status='new',
                )
                created += 1

            # Auto-qualify newly created leads
            new_leads = SDRLead.objects.filter(
                company_user=company_user, score__isnull=True
            ).order_by('-created_at')[:created]

            qualifier = _get_qualification_agent()
            qualified = 0
            for lead in new_leads:
                try:
                    result = qualifier.qualify_lead(lead, icp)
                    lead.score = result['score']
                    lead.temperature = result['temperature']
                    lead.score_breakdown = result.get('score_breakdown', {})
                    lead.qualification_reasoning = result.get('qualification_reasoning', '')
                    lead.qualified_at = timezone.now()
                    lead.status = 'qualified'
                    lead.save()
                    qualified += 1
                except Exception as exc:
                    logger.error("Auto-qualify lead %s: %s", lead.id, exc)

            job.status = 'completed'
            job.total_found = len(raw_leads)
            job.leads_created = created
            job.leads_qualified = qualified
            job.source = researcher.source_label
            job.completed_at = timezone.now()
            job.save()

            return Response({
                'status': 'success',
                'message': f'Found {created} leads, qualified {qualified}.',
                'leads_created': created,
                'leads_qualified': qualified,
                'source': job.source,
                'stats': _lead_stats(company_user),
            })

        except Exception as exc:
            job.status = 'failed'
            job.error_message = str(exc)
            job.completed_at = timezone.now()
            job.save()
            raise

    except Exception as exc:
        logger.error("Research leads error: %s", exc)
        return Response({'status': 'error', 'message': str(exc)}, status=500)


# ==========================================================================
# CSV Import
# ==========================================================================

@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def import_leads_csv(request):
    """Import leads from a CSV file. Accepts multipart/form-data with key 'file'."""
    company_user = request.user
    try:
        csv_file = request.FILES.get('file')
        if not csv_file:
            return Response({'status': 'error', 'message': 'No file provided.'}, status=400)

        decoded = csv_file.read().decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(decoded))

        created = 0
        errors = []
        for i, row in enumerate(reader, start=2):
            try:
                full_name = (
                    row.get('full_name')
                    or row.get('name')
                    or f"{row.get('first_name', '')} {row.get('last_name', '')}".strip()
                )
                raw_size = row.get('company_size', '').strip()
                company_size = int(raw_size) if raw_size.isdigit() else None

                SDRLead.objects.create(
                    company_user=company_user,
                    first_name=row.get('first_name', ''),
                    last_name=row.get('last_name', ''),
                    full_name=full_name,
                    email=row.get('email', ''),
                    phone=row.get('phone', ''),
                    job_title=row.get('job_title') or row.get('title', ''),
                    company_name=row.get('company_name') or row.get('company', ''),
                    company_industry=row.get('company_industry') or row.get('industry', ''),
                    company_size=company_size,
                    company_location=row.get('company_location') or row.get('location', ''),
                    linkedin_url=row.get('linkedin_url') or row.get('linkedin', ''),
                    company_website=row.get('company_website') or row.get('website', ''),
                    source='csv_import',
                    status='new',
                )
                created += 1
            except Exception as exc:
                errors.append(f"Row {i}: {exc}")

        return Response({
            'status': 'success',
            'message': f'Imported {created} leads.',
            'created': created,
            'errors': errors[:5],
        })
    except Exception as exc:
        logger.error("CSV import error: %s", exc)
        return Response({'status': 'error', 'message': str(exc)}, status=500)


# ==========================================================================
# Dashboard overview stats
# ==========================================================================

@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def sdr_dashboard(request):
    company_user = request.user
    try:
        stats = _lead_stats(company_user)
        hot_leads = [
            _serialize_lead(l)
            for l in SDRLead.objects.filter(
                company_user=company_user, temperature='hot'
            ).order_by('-score', '-created_at')[:5]
        ]
        return Response({'status': 'success', 'data': {'stats': stats, 'recent_hot_leads': hot_leads}})
    except Exception as exc:
        logger.error("SDR dashboard error: %s", exc)
        return Response({'status': 'error', 'message': str(exc)}, status=500)


# ==========================================================================
# Campaign serialiser helpers
# ==========================================================================

def _serialize_campaign(c: SDRCampaign) -> dict:
    return {
        'id': c.id,
        'name': c.name,
        'description': c.description,
        'status': c.status,
        'sender_name': c.sender_name,
        'sender_title': c.sender_title,
        'sender_company': c.sender_company,
        'from_email': c.from_email,
        'smtp_host': c.smtp_host,
        'smtp_port': c.smtp_port,
        'smtp_username': c.smtp_username,
        'smtp_use_tls': c.smtp_use_tls,
        'total_leads': c.total_leads,
        'emails_sent': c.emails_sent,
        'replies_received': c.replies_received,
        'created_at': c.created_at.isoformat(),
        'updated_at': c.updated_at.isoformat(),
    }


def _serialize_step(s: SDRCampaignStep) -> dict:
    return {
        'id': s.id,
        'campaign_id': s.campaign_id,
        'step_order': s.step_order,
        'step_type': s.step_type,
        'delay_days': s.delay_days,
        'name': s.name,
        'subject_template': s.subject_template,
        'body_template': s.body_template,
        'ai_personalize': s.ai_personalize,
        'is_active': s.is_active,
    }


def _serialize_enrollment(e: SDRCampaignEnrollment) -> dict:
    lead = e.lead
    total_steps = e.campaign.steps.filter(is_active=True).count()
    logs = list(e.logs.order_by('-created_at').values(
        'id', 'step_order', 'action_type', 'status', 'subject_sent', 'body_sent', 'error_message', 'sent_at'
    )[:20])
    meeting = e.meetings.order_by('-created_at').first() if hasattr(e, 'meetings') else None
    return {
        'id': e.id,
        'campaign_id': e.campaign_id,
        'lead_id': lead.id,
        'lead_name': lead.display_name,
        'lead_email': lead.email,
        'lead_company': lead.company_name,
        'lead_job_title': lead.job_title,
        'lead_temperature': lead.temperature,
        'lead_score': lead.score,
        'status': e.status,
        'current_step': e.current_step,
        'total_steps': total_steps,
        'next_action_at': e.next_action_at.isoformat() if e.next_action_at else None,
        'replied_at': e.replied_at.isoformat() if e.replied_at else None,
        'reply_content': e.reply_content or '',
        'reply_sentiment': e.reply_sentiment or '',
        'meeting_id': meeting.id if meeting else None,
        'meeting_status': meeting.status if meeting else None,
        'enrolled_at': e.enrolled_at.isoformat(),
        'completed_at': e.completed_at.isoformat() if e.completed_at else None,
        'logs': logs,
    }


def _serialize_meeting(m: SDRMeeting) -> dict:
    return {
        'id': m.id,
        'lead_id': m.lead_id,
        'lead_name': m.lead.display_name,
        'lead_email': m.lead.email,
        'lead_company': m.lead.company_name,
        'enrollment_id': m.enrollment_id,
        'title': m.title,
        'notes': m.notes,
        'reply_snippet': m.reply_snippet,
        'scheduled_at': m.scheduled_at.isoformat() if m.scheduled_at else None,
        'duration_minutes': m.duration_minutes,
        'status': m.status,
        'calendar_link': m.calendar_link,
        'created_at': m.created_at.isoformat(),
    }


# ==========================================================================
# Campaigns list / create
# ==========================================================================

@api_view(['GET', 'POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def sdr_campaigns_list(request):
    company_user = request.user

    if request.method == 'GET':
        try:
            campaigns = SDRCampaign.objects.filter(company_user=company_user)
            return Response({
                'status': 'success',
                'data': [_serialize_campaign(c) for c in campaigns],
            })
        except Exception as exc:
            logger.error("List campaigns error: %s", exc)
            return Response({'status': 'error', 'message': str(exc)}, status=500)

    # POST — create campaign
    try:
        d = request.data
        campaign = SDRCampaign.objects.create(
            company_user=company_user,
            name=d.get('name', 'New Campaign'),
            description=d.get('description', ''),
            sender_name=d.get('sender_name', ''),
            sender_title=d.get('sender_title', ''),
            sender_company=d.get('sender_company', ''),
            from_email=d.get('from_email', ''),
            smtp_host=d.get('smtp_host', ''),
            smtp_port=int(d.get('smtp_port', 587)),
            smtp_username=d.get('smtp_username', ''),
            smtp_password=d.get('smtp_password', ''),
            smtp_use_tls=bool(d.get('smtp_use_tls', True)),
            status='draft',
        )

        # Auto-generate steps if requested
        if d.get('generate_steps', True):
            icp = SDRIcpProfile.objects.filter(company_user=company_user, is_active=True).first()
            steps_data = _get_outreach_agent().generate_campaign_steps(campaign, icp)
            for sd in steps_data:
                SDRCampaignStep.objects.create(
                    campaign=campaign,
                    step_order=sd.get('step_order', 1),
                    step_type=sd.get('step_type', 'email'),
                    delay_days=sd.get('delay_days', 1),
                    name=sd.get('name', ''),
                    subject_template=sd.get('subject_template', ''),
                    body_template=sd.get('body_template', ''),
                )

        return Response({'status': 'success', 'data': _serialize_campaign(campaign)}, status=201)
    except Exception as exc:
        logger.error("Create campaign error: %s", exc)
        return Response({'status': 'error', 'message': str(exc)}, status=500)


# ==========================================================================
# Campaign detail — get / update / delete
# ==========================================================================

@api_view(['GET', 'PUT', 'DELETE'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def sdr_campaign_detail(request, campaign_id):
    company_user = request.user
    try:
        campaign = SDRCampaign.objects.get(id=campaign_id, company_user=company_user)
    except SDRCampaign.DoesNotExist:
        return Response({'status': 'error', 'message': 'Campaign not found.'}, status=404)

    if request.method == 'GET':
        data = _serialize_campaign(campaign)
        data['steps'] = [_serialize_step(s) for s in campaign.steps.filter(is_active=True)]
        return Response({'status': 'success', 'data': data})

    if request.method == 'PUT':
        try:
            d = request.data
            for field in ['name', 'description', 'status', 'sender_name', 'sender_title',
                          'sender_company', 'from_email', 'smtp_host', 'smtp_username',
                          'smtp_use_tls']:
                if field in d:
                    setattr(campaign, field, d[field])
            if 'smtp_port' in d:
                campaign.smtp_port = int(d['smtp_port'])
            if 'smtp_password' in d and d['smtp_password']:
                campaign.smtp_password = d['smtp_password']
            campaign.save()
            return Response({'status': 'success', 'data': _serialize_campaign(campaign)})
        except Exception as exc:
            return Response({'status': 'error', 'message': str(exc)}, status=500)

    # DELETE
    campaign.delete()
    return Response({'status': 'success', 'message': 'Campaign deleted.'})


# ==========================================================================
# Campaign steps — list / add
# ==========================================================================

@api_view(['GET', 'POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def sdr_campaign_steps(request, campaign_id):
    company_user = request.user
    try:
        campaign = SDRCampaign.objects.get(id=campaign_id, company_user=company_user)
    except SDRCampaign.DoesNotExist:
        return Response({'status': 'error', 'message': 'Campaign not found.'}, status=404)

    if request.method == 'GET':
        steps = [_serialize_step(s) for s in campaign.steps.all()]
        return Response({'status': 'success', 'data': steps})

    # POST — add a step
    try:
        d = request.data
        step = SDRCampaignStep.objects.create(
            campaign=campaign,
            step_order=d.get('step_order', campaign.steps.count() + 1),
            step_type=d.get('step_type', 'email'),
            delay_days=int(d.get('delay_days', 1)),
            name=d.get('name', ''),
            subject_template=d.get('subject_template', ''),
            body_template=d.get('body_template', ''),
            ai_personalize=bool(d.get('ai_personalize', True)),
        )
        return Response({'status': 'success', 'data': _serialize_step(step)}, status=201)
    except Exception as exc:
        return Response({'status': 'error', 'message': str(exc)}, status=500)


# ==========================================================================
# Campaign step detail — update / delete
# ==========================================================================

@api_view(['PUT', 'DELETE'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def sdr_campaign_step_detail(request, campaign_id, step_id):
    company_user = request.user
    try:
        step = SDRCampaignStep.objects.get(
            id=step_id, campaign__id=campaign_id, campaign__company_user=company_user
        )
    except SDRCampaignStep.DoesNotExist:
        return Response({'status': 'error', 'message': 'Step not found.'}, status=404)

    if request.method == 'DELETE':
        step.delete()
        return Response({'status': 'success', 'message': 'Step deleted.'})

    # PUT
    try:
        d = request.data
        for field in ['step_type', 'name', 'subject_template', 'body_template']:
            if field in d:
                setattr(step, field, d[field])
        if 'step_order' in d:
            step.step_order = int(d['step_order'])
        if 'delay_days' in d:
            step.delay_days = int(d['delay_days'])
        if 'ai_personalize' in d:
            step.ai_personalize = bool(d['ai_personalize'])
        step.save()
        return Response({'status': 'success', 'data': _serialize_step(step)})
    except Exception as exc:
        return Response({'status': 'error', 'message': str(exc)}, status=500)


# ==========================================================================
# Generate steps with AI
# ==========================================================================

@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def sdr_generate_steps(request, campaign_id):
    company_user = request.user
    try:
        campaign = SDRCampaign.objects.get(id=campaign_id, company_user=company_user)
    except SDRCampaign.DoesNotExist:
        return Response({'status': 'error', 'message': 'Campaign not found.'}, status=404)

    try:
        # Delete existing steps first
        campaign.steps.all().delete()

        icp = SDRIcpProfile.objects.filter(company_user=company_user, is_active=True).first()
        steps_data = _get_outreach_agent().generate_campaign_steps(campaign, icp)

        created_steps = []
        for sd in steps_data:
            step = SDRCampaignStep.objects.create(
                campaign=campaign,
                step_order=sd.get('step_order', 1),
                step_type=sd.get('step_type', 'email'),
                delay_days=sd.get('delay_days', 1),
                name=sd.get('name', ''),
                subject_template=sd.get('subject_template', ''),
                body_template=sd.get('body_template', ''),
            )
            created_steps.append(_serialize_step(step))

        return Response({'status': 'success', 'data': created_steps})
    except Exception as exc:
        logger.error("Generate steps error: %s", exc)
        return Response({'status': 'error', 'message': str(exc)}, status=500)


# ==========================================================================
# Enroll leads into campaign
# ==========================================================================

@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def sdr_enroll_leads(request, campaign_id):
    company_user = request.user
    try:
        campaign = SDRCampaign.objects.get(id=campaign_id, company_user=company_user)
    except SDRCampaign.DoesNotExist:
        return Response({'status': 'error', 'message': 'Campaign not found.'}, status=404)

    try:
        lead_ids = request.data.get('lead_ids', [])
        if not lead_ids:
            return Response({'status': 'error', 'message': 'No lead_ids provided.'}, status=400)

        leads = SDRLead.objects.filter(id__in=lead_ids, company_user=company_user)
        first_step = campaign.steps.filter(is_active=True).order_by('step_order').first()

        enrolled = skipped = 0
        for lead in leads:
            already = SDRCampaignEnrollment.objects.filter(campaign=campaign, lead=lead).exists()
            if already:
                skipped += 1
                continue

            next_action = None
            if first_step:
                next_action = timezone.now() + timezone.timedelta(days=first_step.delay_days)

            SDRCampaignEnrollment.objects.create(
                campaign=campaign,
                lead=lead,
                status='active',
                current_step=0,
                next_action_at=next_action,
            )
            enrolled += 1

        campaign.total_leads = campaign.enrollments.count()
        campaign.status = 'active'
        campaign.save(update_fields=['total_leads', 'status'])

        return Response({
            'status': 'success',
            'enrolled': enrolled,
            'skipped': skipped,
            'total_leads': campaign.total_leads,
        })
    except Exception as exc:
        logger.error("Enroll leads error: %s", exc)
        return Response({'status': 'error', 'message': str(exc)}, status=500)


# ==========================================================================
# Campaign enrollments list
# ==========================================================================

@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def sdr_campaign_enrollments(request, campaign_id):
    company_user = request.user
    try:
        campaign = SDRCampaign.objects.get(id=campaign_id, company_user=company_user)
    except SDRCampaign.DoesNotExist:
        return Response({'status': 'error', 'message': 'Campaign not found.'}, status=404)

    try:
        enrollments = campaign.enrollments.select_related('lead').order_by('-enrolled_at')
        return Response({
            'status': 'success',
            'data': [_serialize_enrollment(e) for e in enrollments],
        })
    except Exception as exc:
        logger.error("List enrollments error: %s", exc)
        return Response({'status': 'error', 'message': str(exc)}, status=500)


# ==========================================================================
# Mark enrollment as replied
# ==========================================================================

@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def sdr_mark_replied(request, campaign_id, enrollment_id):
    company_user = request.user
    try:
        enrollment = SDRCampaignEnrollment.objects.get(
            id=enrollment_id, campaign__id=campaign_id, campaign__company_user=company_user
        )
    except SDRCampaignEnrollment.DoesNotExist:
        return Response({'status': 'error', 'message': 'Enrollment not found.'}, status=404)

    try:
        d = request.data
        reply_content = d.get('reply_content', '')

        # AI sentiment analysis
        agent = _get_outreach_agent()
        if reply_content:
            sentiment_result = agent.analyze_reply_sentiment(reply_content)
            sentiment = sentiment_result['sentiment']
            is_interested = sentiment_result['is_interested']
        else:
            # Manual override — trust the frontend value
            sentiment = d.get('reply_sentiment', 'positive')
            is_interested = sentiment == 'positive'

        enrollment.status = 'replied'
        enrollment.replied_at = timezone.now()
        enrollment.reply_content = reply_content
        enrollment.reply_sentiment = sentiment
        enrollment.save()

        campaign = enrollment.campaign
        lead = enrollment.lead

        if is_interested:
            lead.status = 'replied'
            lead.save(update_fields=['status'])
            campaign.replies_received = (campaign.replies_received or 0) + 1
            campaign.save(update_fields=['replies_received'])

            # Create meeting record (scheduling agent handoff)
            meeting, created = SDRMeeting.objects.get_or_create(
                enrollment=enrollment,
                defaults={
                    'company_user': company_user,
                    'lead': lead,
                    'title': f'Discovery Call with {lead.display_name}',
                    'reply_snippet': reply_content[:500],
                    'calendar_link': campaign.calendar_link or '',
                    'status': 'pending',
                }
            )
            if created:
                campaign.meetings_booked = (campaign.meetings_booked or 0) + 1
                campaign.save(update_fields=['meetings_booked'])
                # Send scheduling email
                try:
                    agent.send_scheduling_email(campaign, lead, campaign.calendar_link or '')
                except Exception as exc:
                    logger.warning("Scheduling email failed for lead %s: %s", lead.id, exc)

        return Response({
            'status': 'success',
            'sentiment': sentiment,
            'is_interested': is_interested,
            'meeting_created': is_interested,
            'data': _serialize_enrollment(enrollment),
        })
    except Exception as exc:
        logger.error("Mark replied error: %s", exc)
        return Response({'status': 'error', 'message': str(exc)}, status=500)


# ==========================================================================
# Process outreach — send due steps for campaign
# ==========================================================================

@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def sdr_process_outreach(request, campaign_id):
    """Send the next due outreach step for all active enrollments in the campaign."""
    company_user = request.user
    try:
        campaign = SDRCampaign.objects.get(id=campaign_id, company_user=company_user)
    except SDRCampaign.DoesNotExist:
        return Response({'status': 'error', 'message': 'Campaign not found.'}, status=404)

    try:
        now = timezone.now()
        force = request.data.get('force', True)  # default: force-send regardless of timing

        qs = campaign.enrollments.filter(status='active')
        if not force:
            qs = qs.filter(
                Q(next_action_at__lte=now) | Q(next_action_at__isnull=True)
            )
        due = qs.select_related('lead')

        if not due.exists():
            return Response({
                'status': 'success',
                'message': 'No active enrollments to process.',
                'processed': 0,
                'sent': 0,
                'failed': 0,
                'skipped': 0,
                'results': [],
            })

        agent = _get_outreach_agent()
        results = []
        for enrollment in due:
            result = agent.process_enrollment(enrollment)
            results.append(result)

        sent = sum(1 for r in results if r['status'] == 'sent')
        failed = sum(1 for r in results if r['status'] == 'failed')
        skipped = sum(1 for r in results if r['status'] == 'skipped')
        errors = [r['error'] for r in results if r.get('error')]

        return Response({
            'status': 'success',
            'processed': len(results),
            'sent': sent,
            'failed': failed,
            'skipped': skipped,
            'errors': errors,
            'results': results,
        })
    except Exception as exc:
        logger.error("Process outreach error: %s", exc)
        return Response({'status': 'error', 'message': str(exc)}, status=500)


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def sdr_reset_enrollment(request, campaign_id, enrollment_id):
    """Reset an enrollment back to active so it can be re-processed."""
    company_user = request.user
    try:
        campaign = SDRCampaign.objects.get(id=campaign_id, company_user=company_user)
    except SDRCampaign.DoesNotExist:
        return Response({'status': 'error', 'message': 'Campaign not found.'}, status=404)

    try:
        enrollment = SDRCampaignEnrollment.objects.get(id=enrollment_id, campaign=campaign)
    except SDRCampaignEnrollment.DoesNotExist:
        return Response({'status': 'error', 'message': 'Enrollment not found.'}, status=404)

    enrollment.status = 'active'
    enrollment.current_step = 0
    enrollment.next_action_at = None
    enrollment.replied_at = None
    enrollment.reply_content = ''
    enrollment.reply_sentiment = ''
    enrollment.completed_at = None
    enrollment.save()

    return Response({'status': 'success', 'message': f'Enrollment for {enrollment.lead.display_name} reset to active.'})


# ==========================================================================
# Check inbox for replies — IMAP polling
# ==========================================================================

@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def sdr_check_replies(request, campaign_id):
    """
    Poll IMAP inbox for replies from enrolled leads.
    For each reply found: runs AI sentiment, marks enrollment replied, creates meeting if positive.
    """
    company_user = request.user
    try:
        campaign = SDRCampaign.objects.get(id=campaign_id, company_user=company_user)
    except SDRCampaign.DoesNotExist:
        return Response({'status': 'error', 'message': 'Campaign not found.'}, status=404)

    try:
        # Check active enrollments that have been contacted (current_step > 0)
        enrollments = list(
            campaign.enrollments
            .filter(status__in=['active', 'completed'])
            .filter(current_step__gt=0)
            .select_related('lead')
        )

        agent = _get_outreach_agent()
        replies_found = agent.check_inbox_for_replies(campaign, enrollments)

        new_replies = 0
        meetings_created = 0
        details = []

        for r in replies_found:
            enrollment = r['enrollment']
            reply_text = r['reply_text']

            # Skip if already marked replied
            if enrollment.status == 'replied':
                continue

            sentiment_result = agent.analyze_reply_sentiment(reply_text)
            sentiment = sentiment_result['sentiment']
            is_interested = sentiment_result['is_interested']

            enrollment.status = 'replied'
            enrollment.replied_at = timezone.now()
            enrollment.reply_content = reply_text[:2000]
            enrollment.reply_sentiment = sentiment
            enrollment.save()

            campaign.replies_received = (campaign.replies_received or 0) + 1
            new_replies += 1

            if is_interested:
                enrollment.lead.status = 'replied'
                enrollment.lead.save(update_fields=['status'])

                meeting, created = SDRMeeting.objects.get_or_create(
                    enrollment=enrollment,
                    defaults={
                        'company_user': company_user,
                        'lead': enrollment.lead,
                        'title': f'Discovery Call with {enrollment.lead.display_name}',
                        'reply_snippet': reply_text[:500],
                        'calendar_link': campaign.calendar_link or '',
                        'status': 'pending',
                    }
                )
                if created:
                    meetings_created += 1
                    campaign.meetings_booked = (campaign.meetings_booked or 0) + 1
                    try:
                        agent.send_scheduling_email(campaign, enrollment.lead, campaign.calendar_link or '')
                    except Exception as exc:
                        logger.warning("Scheduling email failed: %s", exc)

            details.append({
                'lead': enrollment.lead.display_name,
                'email': r['sender_email'],
                'sentiment': sentiment,
                'is_interested': is_interested,
                'subject': r.get('subject', ''),
            })

        campaign.save(update_fields=['replies_received', 'meetings_booked'])

        return Response({
            'status': 'success',
            'checked': len(enrollments),
            'new_replies': new_replies,
            'meetings_created': meetings_created,
            'details': details,
        })
    except Exception as exc:
        logger.error("Check replies error for campaign %s: %s", campaign_id, exc)
        return Response({'status': 'error', 'message': str(exc)}, status=500)


# ==========================================================================
# Meetings — scheduling agent output
# ==========================================================================

@api_view(['GET', 'POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def sdr_meetings_list(request):
    company_user = request.user

    if request.method == 'GET':
        try:
            status_filter = request.GET.get('status', '')
            qs = SDRMeeting.objects.filter(company_user=company_user).select_related('lead', 'enrollment')
            if status_filter:
                qs = qs.filter(status=status_filter)
            return Response([_serialize_meeting(m) for m in qs])
        except Exception as exc:
            return Response({'status': 'error', 'message': str(exc)}, status=500)

    # POST — create manual meeting
    try:
        d = request.data
        lead_id = d.get('lead_id')
        if not lead_id:
            return Response({'status': 'error', 'message': 'lead_id required'}, status=400)
        lead = SDRLead.objects.get(id=lead_id, company_user=company_user)
        meeting = SDRMeeting.objects.create(
            company_user=company_user,
            lead=lead,
            title=d.get('title', f'Discovery Call with {lead.display_name}'),
            notes=d.get('notes', ''),
            scheduled_at=d.get('scheduled_at') or None,
            duration_minutes=d.get('duration_minutes', 30),
            calendar_link=d.get('calendar_link', ''),
            status=d.get('status', 'pending'),
        )
        return Response({'status': 'success', 'data': _serialize_meeting(meeting)}, status=201)
    except SDRLead.DoesNotExist:
        return Response({'status': 'error', 'message': 'Lead not found.'}, status=404)
    except Exception as exc:
        return Response({'status': 'error', 'message': str(exc)}, status=500)


@api_view(['GET', 'PUT', 'DELETE'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def sdr_meeting_detail(request, meeting_id):
    company_user = request.user
    try:
        meeting = SDRMeeting.objects.get(id=meeting_id, company_user=company_user)
    except SDRMeeting.DoesNotExist:
        return Response({'status': 'error', 'message': 'Meeting not found.'}, status=404)

    if request.method == 'GET':
        return Response(_serialize_meeting(meeting))

    if request.method == 'PUT':
        try:
            d = request.data
            for field in ('title', 'notes', 'status', 'calendar_link', 'duration_minutes'):
                if field in d:
                    setattr(meeting, field, d[field])
            if 'scheduled_at' in d:
                meeting.scheduled_at = d['scheduled_at'] or None
            meeting.save()
            return Response({'status': 'success', 'data': _serialize_meeting(meeting)})
        except Exception as exc:
            return Response({'status': 'error', 'message': str(exc)}, status=500)

    # DELETE
    meeting.delete()
    return Response({'status': 'success'})
