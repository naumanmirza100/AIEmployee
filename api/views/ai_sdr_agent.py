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
from ai_sdr_agent.models import SDRIcpProfile, SDRLead, SDRLeadResearchJob
from ai_sdr_agent.agents.lead_research_agent import LeadResearchAgent
from ai_sdr_agent.agents.lead_qualification_agent import LeadQualificationAgent

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Singletons — initialised once, reused across requests
# --------------------------------------------------------------------------
_research_agent: LeadResearchAgent | None = None
_qualification_agent: LeadQualificationAgent | None = None


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
