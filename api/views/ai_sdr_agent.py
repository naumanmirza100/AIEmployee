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
import os
import re
from datetime import timedelta
from typing import Optional

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response

from api.authentication import CompanyUserTokenAuthentication
from api.permissions import IsCompanyUserOnly
from ai_sdr_agent.models import (
    SDRIcpProfile, SDRLead, SDRLeadResearchJob,
    SDRCampaign, SDRCampaignStep, SDRCampaignEnrollment, SDROutreachLog, SDRMeeting,
    SDRAgentSettings, SDRReplyDraft,
)
from ai_sdr_agent.agents.lead_research_agent import (
    ApifyApprovalRequired, LeadResearchAgent, NoLeadSource, apify_actor_page_url,
)
from ai_sdr_agent.agents.lead_qualification_agent import LeadQualificationAgent
from ai_sdr_agent.reply_actions import apply_reply_action as _apply_reply_action, handle_inbox_reply, read_inbox
from ai_sdr_agent.agents.outreach_agent import OutreachAgent

from contextlib import contextmanager

from core.api_key_service import KeyServiceError
from core.scheduling import ScheduleConflict

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Per-request agent factories — pass company so keys resolve per-company
# --------------------------------------------------------------------------

def _ensure_https(url: str) -> str:
    """Add https:// prefix if a URL has no protocol."""
    if not url:
        return url
    url = url.strip()
    if url and not url.startswith(('http://', 'https://')):
        return f'https://{url}'
    return url


_EMAIL_RE = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')


def _validate_lead_input(full_name, email, linkedin_url, company_size) -> Optional[str]:
    """Server-side validation for a manually-created lead. Mirrors the frontend
    checks so invalid data can't be saved by bypassing the UI. Returns an error
    message string, or None when the input is valid.
    """
    name = (full_name or '').strip()
    email = (email or '').strip()
    linkedin = (linkedin_url or '').strip()

    if not name and not email:
        return 'Enter at least a name or a business email.'
    if email and not _EMAIL_RE.match(email):
        return 'Enter a valid business email like jane@company.com.'
    if linkedin:
        url = linkedin if re.match(r'^https?://', linkedin, re.I) else f'https://{linkedin}'
        host = re.sub(r'^https?://', '', url, flags=re.I).split('/')[0].lower()
        if not (host == 'linkedin.com' or host.endswith('.linkedin.com')):
            return 'Enter a valid LinkedIn URL like https://linkedin.com/in/jane.'
    if company_size not in (None, '') and not str(company_size).strip().isdigit():
        return 'Employees must be a whole number.'
    return None


def _validate_url_optional(value, error_message) -> Optional[str]:
    """Validate an optional URL field. Empty is allowed. Returns error_message
    when the value is present but not a plausible http(s) URL, else None."""
    v = (value or '').strip()
    if not v:
        return None
    url = v if re.match(r'^https?://', v, re.I) else f'https://{v}'
    host = re.sub(r'^https?://', '', url, flags=re.I).split('/')[0]
    if not host or '.' not in host or ' ' in host:
        return error_message
    return None


def _get_research_agent(company, company_user=None) -> LeadResearchAgent:
    """Create a LeadResearchAgent with the correct company key context."""
    if company_user is not None:
        sdr_settings = SDRAgentSettings.objects.filter(company_user=company_user).first()
        if sdr_settings:
            return LeadResearchAgent(
                company=company,
                apollo_api_key=sdr_settings.apollo_api_key or None,
                apify_token=sdr_settings.apify_api_token or None,
                apify_actor=sdr_settings.apify_actor_id or None,
            )
    return LeadResearchAgent(company=company)


def _get_qualification_agent(company) -> LeadQualificationAgent:
    """Create a LeadQualificationAgent with the correct company key context."""
    return LeadQualificationAgent(company=company)


def _get_outreach_agent(company) -> OutreachAgent:
    """Create an OutreachAgent with the correct company key context."""
    return OutreachAgent(company=company)


def _get_research_agent_legacy(company_user=None) -> LeadResearchAgent:
    """Legacy factory kept for compatibility — redirects to company-based resolver."""
    if company_user is not None:
        sdr_settings = SDRAgentSettings.objects.filter(company_user=company_user).first()
        if sdr_settings:
            return LeadResearchAgent(
                apollo_api_key=sdr_settings.apollo_api_key or None,
                apify_token=sdr_settings.apify_api_token or None,
                apify_actor=sdr_settings.apify_actor_id or None,
            )
    return LeadResearchAgent()


def _mask_key(key: str) -> str:
    """Return a masked version of an API key for display (e.g. abc...xyz)."""
    if not key:
        return ''
    if len(key) <= 8:
        return '***'
    return key[:4] + '***' + key[-4:]


def _parse_aware_datetime(value):
    """Parse an ISO 8601 string (or datetime) into an aware datetime; ValueError if invalid."""
    import datetime as _dtm
    import dateutil.parser
    if isinstance(value, _dtm.datetime):
        parsed = value
    else:
        try:
            parsed = dateutil.parser.isoparse(str(value))
        except (ValueError, OverflowError) as exc:
            raise ValueError('Invalid date format. Use ISO 8601.') from exc
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)
    return parsed


def _validate_mail_settings(d, campaign=None):
    """Error message if the SMTP/IMAP host or port in ``d`` is unsafe, else None."""
    from ai_sdr_agent.agents.outreach_agent import validate_mail_server

    def _val(key, default=None):
        if key in d:
            return d[key]
        return getattr(campaign, key, default) if campaign else default

    try:
        smtp_err = validate_mail_server(_val('smtp_host'), _val('smtp_port') or 587, 'smtp')
        imap_err = validate_mail_server(_val('imap_host'), _val('imap_port') or 993, 'imap')
    except (TypeError, ValueError):
        return 'SMTP/IMAP port must be a number.'
    if smtp_err or imap_err:
        return smtp_err or imap_err
    # Changed mailbox settings are tried before they are saved (CO-197, CO-198). A saved password is used when
    # none was typed.
    mailbox_fields = ('smtp_host', 'smtp_port', 'smtp_username', 'smtp_password', 'smtp_use_tls', 'imap_host',
                      'imap_port')
    if any(f in d for f in mailbox_fields):
        from ai_sdr_agent.agents.outreach_agent import try_mailbox_logins
        return try_mailbox_logins(
            _val('smtp_host'), _val('smtp_port') or 587, _val('smtp_use_tls', True), _val('smtp_username'),
            d.get('smtp_password') or getattr(campaign, 'smtp_password', ''),
            _val('imap_host'), _val('imap_port') or 993) or None
    return None


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
        'key_strengths': lead.key_strengths if hasattr(lead, 'key_strengths') else [],
        'concerns': lead.concerns if hasattr(lead, 'concerns') else [],
        'outreach_strategy': lead.outreach_strategy if hasattr(lead, 'outreach_strategy') else '',
        'confidence_score': lead.confidence_score if hasattr(lead, 'confidence_score') else None,
        'data_quality_flags': lead.data_quality_flags if hasattr(lead, 'data_quality_flags') else [],
        'email_bounced': lead.email_bounced,
        'status': lead.status,
        'qualification_status': lead.qualification_status,
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
        # Leads waiting in / running through the background qualification queue.
        'qualifying': qs.filter(qualification_status__in=['pending', 'processing']).count(),
    }


# ==========================================================================
# ICP Profile
# ==========================================================================

@api_view(['GET', 'POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def icp_profile(request):
    """GET → return all ICPs (list). POST → upsert ICP."""
    company_user = request.user

    if request.method == 'GET':
        try:
            icps = SDRIcpProfile.objects.filter(company_user=company_user).order_by('-is_active', '-updated_at')
            if not icps.exists():
                return Response({'status': 'success', 'data': None, 'all': []})
            return Response({
                'status': 'success',
                'data': _serialize_icp(icps.filter(is_active=True).first()),
                'all': [_serialize_icp(i) for i in icps],
            })
        except KeyServiceError:
            raise
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
                # Defaults must match SDRICPProfile model defaults (75 / 60) so
                # hot/warm bucketing is consistent regardless of code path.
                'hot_threshold': int(data.get('hot_threshold', 75)),
                'warm_threshold': int(data.get('warm_threshold', 60)),
            },
        )
        return Response({'status': 'success', 'message': 'ICP saved.', 'data': _serialize_icp(icp)})
    except KeyServiceError:
        raise
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

            # ── Filters ───────────────────────────────────────────────
            search = request.GET.get('search', '').strip()
            if search:
                qs = qs.filter(
                    Q(full_name__icontains=search)
                    | Q(first_name__icontains=search)
                    | Q(last_name__icontains=search)
                    | Q(company_name__icontains=search)
                    | Q(email__icontains=search)
                    | Q(job_title__icontains=search)
                    | Q(company_location__icontains=search)
                    | Q(company_industry__icontains=search)
                )

            temp = request.GET.get('temperature', '').strip()
            if temp:
                qs = qs.filter(temperature=temp)

            status_f = request.GET.get('status', '').strip()
            if status_f:
                qs = qs.filter(status=status_f)

            # The Enroll dialog leaves out leads already in that campaign (CO-146).
            not_in = request.GET.get('not_in_campaign', '').strip()
            if not_in.isdigit():
                qs = qs.exclude(campaign_enrollments__campaign_id=int(not_in))
            source_f = request.GET.get('source', '').strip()
            if source_f:
                qs = qs.filter(source=source_f)

            SORT_MAP = {
                'score_desc':   ['-score', '-created_at'],
                'score_asc':    ['score',  '-created_at'],
                'name_asc':     ['full_name'],
                'name_desc':    ['-full_name'],
                'created_desc': ['-created_at'],
                'created_asc':  ['created_at'],
                'company_asc':  ['company_name'],
            }
            sort_by = request.GET.get('sort', 'score_desc')
            qs = qs.order_by(*SORT_MAP.get(sort_by, ['-score', '-created_at']))

            try:
                page      = max(1, int(request.GET.get('page', 1)))
                page_size = min(100, max(5, int(request.GET.get('page_size', 25))))
            except (ValueError, TypeError):
                page, page_size = 1, 25

            from django.core.paginator import Paginator
            total_count = qs.count()
            paginator   = Paginator(qs, page_size)
            page_obj    = paginator.get_page(page)

            leads = [_serialize_lead(l) for l in page_obj.object_list]
            return Response({
                'status':     'success',
                'data':       leads,
                'stats':      _lead_stats(company_user),
                'pagination': {
                    'page':        page_obj.number,
                    'page_size':   page_size,
                    'total_count': total_count,
                    'total_pages': paginator.num_pages,
                    'has_next':    page_obj.has_next(),
                    'has_prev':    page_obj.has_previous(),
                },
            })
        except KeyServiceError:
            raise
        except Exception as exc:
            logger.error("List leads error: %s", exc)
            return Response({'status': 'error', 'message': str(exc)}, status=500)

    # POST — manual create
    try:
        d = request.data
        full_name = d.get('full_name') or f"{d.get('first_name', '')} {d.get('last_name', '')}".strip()

        # ── Validation (mirrors the frontend; never trust the client) ─────────
        email_input = (d.get('email') or '').strip().lower()
        linkedin_input = (d.get('linkedin_url') or '').strip()
        size_input = d.get('company_size')

        err = _validate_lead_input(full_name, email_input, linkedin_input, size_input)
        if err:
            return Response({'status': 'error', 'message': err}, status=400)
        # ─────────────────────────────────────────────────────────────────────

        # ── Duplicate guard ──────────────────────────────────────────────────
        if email_input:
            existing = SDRLead.objects.filter(
                company_user=company_user, email__iexact=email_input
            ).first()
            if existing:
                logger.info("Create lead DUPLICATE blocked — email=%s lead_id=%s", email_input, existing.id)
                return Response({
                    'status': 'duplicate',
                    'message': f'A lead with email "{email_input}" already exists.',
                    'data': _serialize_lead(existing),
                }, status=200)
        # ────────────────────────────────────────────────────────────────────

        lead = SDRLead.objects.create(
            company_user=company_user,
            first_name=d.get('first_name', ''),
            last_name=d.get('last_name', ''),
            full_name=full_name,
            email=email_input or d.get('email', ''),
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
            # Queue for background qualification so manually-added leads get
            # scored automatically like research/CSV leads.
            qualification_status='pending',
            qualification_queued_at=timezone.now(),
        )
        return Response({'status': 'success', 'data': _serialize_lead(lead)}, status=201)
    except KeyServiceError:
        raise
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
        except KeyServiceError:
            raise
        except Exception as exc:
            return Response({'status': 'error', 'message': str(exc)}, status=500)

    # DELETE — soft delete so the client can offer an Undo (restore).
    lead.soft_delete()
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

        result = _get_qualification_agent(company_user.company).qualify_lead(lead, icp)
        lead.score = result['score']
        lead.temperature = result['temperature']
        lead.score_breakdown = result.get('score_breakdown', {})
        lead.qualification_reasoning = result.get('qualification_reasoning', '')
        lead.key_strengths = result.get('key_strengths', [])
        lead.concerns = result.get('concerns', [])
        lead.outreach_strategy = result.get('outreach_strategy', '')
        lead.qualified_at = timezone.now()
        if lead.status in ('new', 'qualified'):   # never regress contacted/replied/etc.
            lead.status = 'qualified'
        lead.save()
        return Response({'status': 'success', 'data': _serialize_lead(lead)})
    except SDRLead.DoesNotExist:
        return Response({'status': 'error', 'message': 'Lead not found.'}, status=404)
    except KeyServiceError:
        raise
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
    """Queue all unscored leads for background qualification (token-safe)."""
    company_user = request.user
    try:
        icp = SDRIcpProfile.objects.filter(company_user=company_user, is_active=True).first()
        if not icp:
            return Response({'status': 'error', 'message': 'Set up your ICP profile first.'}, status=400)

        # Put every unscored lead (that isn't already qualifying) into the queue.
        # The scheduler drains it in small batches, retrying failures — so this
        # never blocks or exhausts tokens in one shot.
        queued = SDRLead.objects.filter(
            company_user=company_user, score__isnull=True,
        ).exclude(qualification_status__in=['pending', 'processing']).update(
            qualification_status='pending', qualification_queued_at=timezone.now(),
            qualification_attempts=0, qualification_error='',
        )

        return Response({
            'status': 'success',
            'message': f'Queued {queued} leads — they’ll be qualified in the background shortly.',
            'qualified': 0,
            'queued': queued,
            'stats': _lead_stats(company_user),
        })
    except KeyServiceError:
        raise
    except Exception as exc:
        logger.error("Qualify-all error: %s", exc)
        return Response({'status': 'error', 'message': str(exc)}, status=500)


# ==========================================================================
# Research (find new leads)
# ==========================================================================

@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def research_sources(request):
    """Return available lead research sources based on configured API keys."""
    company_user = request.user
    # The person's own keys count too: the list ignored them and said no source was set.
    researcher = _get_research_agent(company_user.company, company_user=company_user)
    return Response({
        'sources': researcher.available_sources,
        'default': researcher.source_label,
        'apify_actor': researcher.apify_actor if researcher.apify_token else None,
    })


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def research_leads(request):
    """
    Find new leads from Apollo.io or Apify, whichever key is configured. With neither, nothing is searched (the AI
    no longer makes leads up). Found leads are queued for qualification.
    """
    company_user = request.user
    try:
        count = min(int(request.data.get('count', 20)), 50)
        source = request.data.get('source', 'auto')
        icp_id = request.data.get('icp_id')
        if icp_id:
            icp = SDRIcpProfile.objects.filter(company_user=company_user, pk=icp_id).first()
        else:
            icp = SDRIcpProfile.objects.filter(company_user=company_user, is_active=True).first()
        if not icp:
            return Response({'status': 'error', 'message': 'Set up your ICP profile first.'}, status=400)

        job = SDRLeadResearchJob.objects.create(
            company_user=company_user,
            icp_profile=icp,
            status='running',
            search_params={'industries': icp.industries, 'job_titles': icp.job_titles, 'count': count, 'source': source},
            started_at=timezone.now(),
        )

        try:
            researcher = _get_research_agent(company_user.company, company_user=company_user)
            raw_leads = researcher.search_leads(icp, count=count, source=source)

            created = 0
            created_ids = []
            skipped_dupes = 0

            # Pre-load existing keys to catch dupes. LinkedIn URL is the most
            # reliable (unique per profile) — essential for no-email sources like
            # the Google scraper, where company often doesn't parse and name+company
            # dedup misses. Also track email, name+company, and name-only.
            existing_leads_qs = SDRLead.objects.filter(company_user=company_user).values_list(
                'email', 'full_name', 'company_name', 'linkedin_url'
            )
            existing_emails_lower = set()
            existing_name_company = set()
            existing_linkedin = set()
            existing_names = set()

            def _norm_li(url):
                u = (url or '').strip().lower().rstrip('/')
                return u.split('?')[0] if u else ''

            for em, fn, cn, li in existing_leads_qs:
                if em:
                    existing_emails_lower.add(em.lower())
                if fn and cn:
                    existing_name_company.add((fn.lower().strip(), cn.lower().strip()))
                if fn:
                    existing_names.add(fn.lower().strip())
                nli = _norm_li(li)
                if nli:
                    existing_linkedin.add(nli)

            from ai_sdr_agent.agents.lead_validator import validate_lead
            for ld in raw_leads:
                full_name = ld.get('full_name') or f"{ld.get('first_name','')} {ld.get('last_name','')}".strip()
                lead_email = (ld.get('email') or '').strip().lower()
                company_name = (ld.get('company_name') or '').strip()
                linkedin = _norm_li(ld.get('linkedin_url'))

                # ── Reject leads with no name and no company (totally empty) ──
                if not full_name.strip() and not company_name:
                    logger.info("SDR [research] SKIPPING empty lead (no name, no company)")
                    skipped_dupes += 1
                    continue

                # ── Duplicate guard — linkedin > email > name+company > name ──
                if linkedin and linkedin in existing_linkedin:
                    logger.info("SDR [research] SKIPPING duplicate linkedin=%s", linkedin)
                    skipped_dupes += 1
                    continue
                if lead_email and lead_email in existing_emails_lower:
                    logger.info("SDR [research] SKIPPING duplicate email=%s", lead_email)
                    skipped_dupes += 1
                    continue
                name_company_key = (full_name.lower().strip(), company_name.lower().strip())
                if full_name and company_name and name_company_key in existing_name_company:
                    logger.info("SDR [research] SKIPPING duplicate name+company: %s @ %s", full_name, company_name)
                    skipped_dupes += 1
                    continue
                # No email/company (Google scraper) → fall back to name-only so
                # the same profile scraped twice isn't inserted again.
                name_key = full_name.lower().strip()
                if not lead_email and not company_name and not linkedin and name_key and name_key in existing_names:
                    logger.info("SDR [research] SKIPPING duplicate name-only: %s", full_name)
                    skipped_dupes += 1
                    continue

                # Track all keys for intra-batch dedup
                if linkedin:
                    existing_linkedin.add(linkedin)
                if lead_email:
                    existing_emails_lower.add(lead_email)
                if full_name and company_name:
                    existing_name_company.add(name_company_key)
                if name_key:
                    existing_names.add(name_key)
                # ─────────────────────────────────────────────────────────────

                validation = validate_lead({**ld, 'full_name': full_name})

                new_lead = SDRLead.objects.create(
                    company_user=company_user,
                    icp_profile=icp,
                    first_name=ld.get('first_name', ''),
                    last_name=ld.get('last_name', ''),
                    full_name=full_name,
                    email=lead_email or ld.get('email', ''),
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
                    linkedin_url=_ensure_https(ld.get('linkedin_url', '')),
                    company_linkedin_url=_ensure_https(ld.get('company_linkedin_url', '')),
                    company_website=_ensure_https(ld.get('company_website', '')),
                    recent_news=ld.get('recent_news', []),
                    buying_signals=ld.get('buying_signals', []),
                    apollo_id=ld.get('apollo_id', ''),
                    raw_data=ld.get('raw_data', {}),
                    source=ld.get('source') or researcher.source_label,
                    status='new',
                    confidence_score=validation['confidence_score'],
                    data_quality_flags=validation['data_quality_flags'],
                )
                created += 1
                created_ids.append(new_lead.pk)

            # Queue ONLY the leads created by this run for background
            # qualification — the scheduler drains the queue in small batches so
            # AI tokens aren't exhausted in one burst, and retries failures
            # automatically. Scoping to created_ids avoids sweeping up unrelated
            # pre-existing unscored leads (e.g. CSV/manual imports).
            queued = SDRLead.objects.filter(
                pk__in=created_ids, score__isnull=True, qualification_status='none',
            ).update(qualification_status='pending', qualification_queued_at=timezone.now())

            job.status = 'completed'
            job.total_found = len(raw_leads)
            job.leads_created = created
            job.leads_qualified = 0
            job.source = researcher.source_label
            job.completed_at = timezone.now()
            job.save()

            if queued:
                message = (
                    f'Found {created} leads. Qualifying {queued} in the background — '
                    f'scores will appear shortly. Skipped {skipped_dupes} duplicates.'
                )
            else:
                message = f'Found {created} leads. Skipped {skipped_dupes} duplicates.'

            return Response({
                'status': 'success',
                'message': message,
                'leads_created': created,
                'leads_queued': queued,
                'skipped_duplicates': skipped_dupes,
                'source': job.source,
                'stats': _lead_stats(company_user),
            })

        except KeyServiceError:
            raise
        except Exception as exc:
            job.status = 'failed'
            job.error_message = str(exc)
            job.completed_at = timezone.now()
            job.save()
            raise

    except KeyServiceError:
        raise
    except ApifyApprovalRequired as exc:
        # Not a server error: the user has to approve the actor once on Apify.
        return Response({
            'status': 'error',
            'code': 'apify_approval_required',
            'message': str(exc),
            'approval_url': exc.approval_url,
            'actor': exc.actor,
        }, status=400)
    except NoLeadSource as exc:
        return Response({'status': 'error', 'code': 'no_lead_source', 'message': str(exc)}, status=400)
    except Exception as exc:
        logger.error("Research leads error: %s", exc)
        return Response({'status': 'error', 'message': str(exc)}, status=500)


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def fetch_apify_leads(request):
    """Import leads from the user's EXISTING Apify runs (generated in the Apify
    Console). Works on the free Apify plan, which can't RUN paid actors via the
    API but CAN read finished runs' datasets. No ICP filtering — pulls whatever
    the user already generated. Auto-qualify is best-effort (skipped silently if
    platform AI tokens are exhausted, so the import never fails on that)."""
    company_user = request.user
    try:
        max_leads = min(int(request.data.get('count', 200)), 500)
        actor = request.data.get('actor')  # optional override
        icp = SDRIcpProfile.objects.filter(company_user=company_user, is_active=True).first()

        # The person's own Apify account only: on the platform's key it imported whatever that account ran last,
        # including searches run for other companies (CO-142).
        own = SDRAgentSettings.objects.filter(company_user=company_user).first()
        if not (own and (own.apify_api_token or '').strip()):
            return Response({'status': 'error', 'code': 'no_lead_source',
                             'message': 'Add your own Apify API token in SDR Agent → Settings to fetch your runs.'},
                            status=400)
        researcher = _get_research_agent(company_user.company, company_user=company_user)
        raw_leads = researcher.fetch_apify_runs(max_leads=max_leads, actor=actor)
        if not raw_leads:
            return Response({'status': 'error', 'message': 'No leads found in your Apify runs.'}, status=400)

        # ── Dedup against existing leads (linkedin > email > name+company > name) ──
        existing_qs = SDRLead.objects.filter(company_user=company_user).values_list(
            'email', 'full_name', 'company_name', 'linkedin_url'
        )

        def _norm_li(url):
            u = (url or '').strip().lower().rstrip('/')
            return u.split('?')[0] if u else ''

        seen_email, seen_nc, seen_li, seen_name = set(), set(), set(), set()
        for em, fn, cn, li in existing_qs:
            if em:
                seen_email.add(em.lower())
            if fn and cn:
                seen_nc.add((fn.lower().strip(), cn.lower().strip()))
            if fn:
                seen_name.add(fn.lower().strip())
            nli = _norm_li(li)
            if nli:
                seen_li.add(nli)

        from ai_sdr_agent.agents.lead_validator import validate_lead
        created = 0
        skipped = 0
        for ld in raw_leads:
            full_name = ld.get('full_name') or f"{ld.get('first_name','')} {ld.get('last_name','')}".strip()
            email = (ld.get('email') or '').strip().lower()
            company_name = (ld.get('company_name') or '').strip()
            linkedin = _norm_li(ld.get('linkedin_url'))
            name_key = full_name.lower().strip()

            if not full_name.strip() and not company_name:
                skipped += 1
                continue
            if linkedin and linkedin in seen_li:
                skipped += 1; continue
            if email and email in seen_email:
                skipped += 1; continue
            nc = (name_key, company_name.lower().strip())
            if full_name and company_name and nc in seen_nc:
                skipped += 1; continue
            if not email and not company_name and not linkedin and name_key and name_key in seen_name:
                skipped += 1; continue

            if linkedin: seen_li.add(linkedin)
            if email: seen_email.add(email)
            if full_name and company_name: seen_nc.add(nc)
            if name_key: seen_name.add(name_key)

            validation = validate_lead({**ld, 'full_name': full_name})
            SDRLead.objects.create(
                company_user=company_user,
                icp_profile=icp,
                first_name=ld.get('first_name', ''),
                last_name=ld.get('last_name', ''),
                full_name=full_name,
                email=email or ld.get('email', ''),
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
                linkedin_url=_ensure_https(ld.get('linkedin_url', '')),
                company_linkedin_url=_ensure_https(ld.get('company_linkedin_url', '')),
                company_website=_ensure_https(ld.get('company_website', '')),
                recent_news=ld.get('recent_news', []),
                buying_signals=ld.get('buying_signals', []),
                apollo_id=ld.get('apollo_id', ''),
                raw_data=ld.get('raw_data', {}),
                source='apify',
                status='new',
                confidence_score=validation['confidence_score'],
                data_quality_flags=validation['data_quality_flags'],
                # Queue for background qualification instead of scoring inline —
                # a synchronous loop here blocked the request for minutes and hit
                # AI token limits. The scheduler drains the queue in small batches.
                qualification_status='pending',
                qualification_queued_at=timezone.now(),
            )
            created += 1

        queued = created  # every imported lead is queued for qualification

        msg = f'Imported {created} leads from Apify'
        if queued:
            msg += '. Qualifying them in the background — scores will appear shortly'
        if skipped:
            msg += f'. Skipped {skipped} duplicates'
        return Response({
            'status': 'success',
            'message': msg + '.',
            'leads_created': created,
            'leads_queued': queued,
            'skipped_duplicates': skipped,
            'stats': _lead_stats(company_user),
        })

    except KeyServiceError:
        raise
    except Exception as exc:
        logger.error("Fetch-from-Apify error: %s", exc)
        return Response({'status': 'error', 'message': str(exc)}, status=500)


# ==========================================================================
# CSV Import
# ==========================================================================

CSV_IMPORT_MAX_ROWS = 2000


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
        skipped_dupes = 0
        skipped_empty = 0
        errors = []
        refused = []

        # Pre-load existing emails once to avoid per-row DB hits
        existing_emails_lower = set(
            e.lower()
            for e in SDRLead.objects.filter(company_user=company_user)
            .values_list('email', flat=True) if e
        )

        def _norm_key(k):
            # "Full Name" / "FULL_NAME" / "full-name" → "fullname"
            return re.sub(r'[^a-z0-9]', '', (k or '').strip().lower())

        # Map each CSV field to the header variations that should feed it.
        FIELD_ALIASES = {
            'full_name':        ['fullname', 'name', 'contactname', 'leadname'],
            'first_name':       ['firstname', 'fname', 'givenname'],
            'last_name':        ['lastname', 'lname', 'surname', 'familyname'],
            'email':            ['email', 'emailaddress', 'workemail', 'businessemail', 'mail'],
            'phone':            ['phone', 'phonenumber', 'mobile', 'mobilenumber', 'tel', 'telephone'],
            'job_title':        ['jobtitle', 'title', 'position', 'role', 'designation'],
            'company_name':     ['companyname', 'company', 'organization', 'organisation', 'employer', 'account'],
            'company_industry': ['companyindustry', 'industry', 'sector', 'vertical'],
            'company_size':     ['companysize', 'size', 'employees', 'employeecount', 'headcount'],
            'company_location': ['companylocation', 'location', 'city', 'country', 'region', 'address'],
            'linkedin_url':     ['linkedinurl', 'linkedin', 'linkedinprofile', 'profileurl'],
            'company_website':  ['companywebsite', 'website', 'url', 'domain', 'web'],
        }

        rows = list(reader)
        if len(rows) > CSV_IMPORT_MAX_ROWS:
            # Every row is queued for AI scoring; a 5,000-row file held the queue for a day and a half (CO-202).
            return Response({'status': 'error', 'code': 'too_many_rows',
                             'message': f'The file has {len(rows)} rows. Please import at most '
                                        f'{CSV_IMPORT_MAX_ROWS} leads at a time.'}, status=400)
        for i, raw_row in enumerate(rows, start=2):
            try:
                # Normalise this row's keys once, then pick fields by alias.
                norm = {_norm_key(k): (v or '').strip() for k, v in raw_row.items() if k}

                def pick(field):
                    for alias in FIELD_ALIASES.get(field, []):
                        if norm.get(alias):
                            return norm[alias]
                    return ''

                first_name = pick('first_name')
                last_name = pick('last_name')
                full_name = pick('full_name') or f"{first_name} {last_name}".strip()
                company_name = pick('company_name')
                row_email = pick('email').lower()

                # Skip completely blank rows (no name, no company, no email).
                if not full_name and not company_name and not row_email:
                    skipped_empty += 1
                    continue

                # An email that is not one is refused with the reason: 'sana.malik@' and 'n/a' were taken as leads
                # (found in the live run of 29 Oct). No email at all is allowed, as when a lead is added by hand
                # (LinkedIn steps).
                who = full_name or company_name or f'row {i}'
                if row_email:
                    try:
                        validate_email(row_email)
                    except ValidationError:
                        refused.append(f'row {i} ({who}): "{row_email}" is not an email address')
                        continue

                raw_size = pick('company_size')
                digits = re.sub(r'[^\d]', '', raw_size)
                company_size = int(digits) if digits else None

                # ── Duplicate guard ──────────────────────────────────────────
                if row_email and row_email in existing_emails_lower:
                    skipped_dupes += 1
                    logger.info("CSV import SKIPPING duplicate email=%s (row %d)", row_email, i)
                    continue
                if row_email:
                    existing_emails_lower.add(row_email)   # prevent intra-file dupes
                # ─────────────────────────────────────────────────────────────

                SDRLead.objects.create(
                    company_user=company_user,
                    first_name=first_name,
                    last_name=last_name,
                    full_name=full_name,
                    email=row_email,
                    phone=pick('phone'),
                    job_title=pick('job_title'),
                    company_name=company_name,
                    company_industry=pick('company_industry'),
                    company_size=company_size,
                    company_location=pick('company_location'),
                    linkedin_url=pick('linkedin_url'),
                    company_website=pick('company_website'),
                    source='csv_import',
                    status='new',
                    # Queue for background qualification so imported leads get
                    # scored automatically instead of sitting permanently unscored.
                    qualification_status='pending',
                    qualification_queued_at=timezone.now(),
                )
                created += 1
            except KeyServiceError:
                raise
            except Exception as exc:
                errors.append(f"Row {i}: {exc}")

        msg = f'Imported {created} leads. Skipped {skipped_dupes} duplicates'
        if skipped_empty:
            msg += f', {skipped_empty} empty rows'
        msg += '.'
        if refused:
            msg += f' Not imported: {"; ".join(refused[:5])}' + (f'; and {len(refused) - 5} more' if len(refused) > 5 else '') + '.'
        if created:
            msg += ' Qualifying them in the background — scores will appear shortly.'
        if created == 0 and not errors and not refused:
            msg = ('No leads imported — check the CSV has a header row with columns like '
                   'full_name / email / company_name (any capitalisation).')
        return Response({
            'status': 'success',
            'message': msg,
            'created': created,
            'skipped_duplicates': skipped_dupes,
            'skipped_empty': skipped_empty,
            'refused': refused,
            'errors': errors[:5],
        })
    except KeyServiceError:
        raise
    except Exception as exc:
        logger.error("CSV import error: %s", exc)
        return Response({'status': 'error', 'message': str(exc)}, status=500)


# ==========================================================================
# Bulk lead operations
# ==========================================================================

@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def sdr_bulk_delete_leads(request):
    """
    Bulk-delete leads by ID list.
    Body: { "ids": [1, 2, 3, ...] }
    Only deletes leads that belong to the authenticated company_user.
    """
    company_user = request.user
    try:
        ids = request.data.get('ids', [])
        if not isinstance(ids, list) or not ids:
            return Response({'status': 'error', 'message': 'Provide a non-empty "ids" list.'}, status=400)

        # Safety: only delete leads that belong to this company_user.
        # Soft delete (mark hidden) so the client can offer an Undo. Capture the
        # ids that were actually affected so the restore call targets exactly
        # those rows.
        qs = SDRLead.objects.filter(company_user=company_user, id__in=ids)
        affected_ids = list(qs.values_list('id', flat=True))
        deleted_count = qs.update(is_deleted=True, deleted_at=timezone.now())

        return Response({
            'status': 'success',
            'message': f'Deleted {deleted_count} lead(s).',
            'deleted': deleted_count,
            'deleted_ids': affected_ids,
        })
    except Exception as exc:
        logger.error("SDR bulk delete error: %s", exc)
        return Response({'status': 'error', 'message': str(exc)}, status=500)


# ==========================================================================
# Restore soft-deleted leads (Undo)
# ==========================================================================

@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def restore_lead(request, lead_id):
    """Undo a single soft-deleted lead. Uses all_objects since the default
    manager hides deleted rows."""
    company_user = request.user
    try:
        lead = SDRLead.all_objects.get(id=lead_id, company_user=company_user)
    except SDRLead.DoesNotExist:
        return Response({'status': 'error', 'message': 'Lead not found.'}, status=404)

    lead.restore()
    return Response({'status': 'success', 'message': 'Lead restored.', 'data': _serialize_lead(lead)})


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def sdr_bulk_restore_leads(request):
    """Undo a bulk soft-delete. Body: { "ids": [1, 2, 3, ...] }.
    Only restores leads belonging to the authenticated company_user."""
    company_user = request.user
    try:
        ids = request.data.get('ids', [])
        if not isinstance(ids, list) or not ids:
            return Response({'status': 'error', 'message': 'Provide a non-empty "ids" list.'}, status=400)

        qs = SDRLead.all_objects.filter(company_user=company_user, id__in=ids, is_deleted=True)
        restored_count = qs.update(is_deleted=False, deleted_at=None)

        return Response({
            'status': 'success',
            'message': f'Restored {restored_count} lead(s).',
            'restored': restored_count,
        })
    except Exception as exc:
        logger.error("SDR bulk restore error: %s", exc)
        return Response({'status': 'error', 'message': str(exc)}, status=500)


# ==========================================================================
# Scheduler health check
# ==========================================================================

@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def sdr_scheduler_status(request):
    """
    Health-check endpoint — returns whether the embedded APScheduler is running
    and when each job is next scheduled.

    GET /api/sdr/scheduler-status/
    Response:
      { "running": true, "jobs": [{"id": "...", "name": "...", "next_run": "..."}, ...] }
    """
    try:
        from ai_sdr_agent.scheduler import scheduler_status
        return Response({'status': 'success', 'data': scheduler_status()})
    except Exception as exc:
        logger.error("SDR scheduler status error: %s", exc)
        return Response({'status': 'error', 'message': str(exc)}, status=500)


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
    except KeyServiceError:
        raise
    except Exception as exc:
        logger.error("SDR dashboard error: %s", exc)
        return Response({'status': 'error', 'message': str(exc)}, status=500)


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def sdr_analytics(request):
    """Full analytics metrics for the Analytics tab dashboard."""
    company_user = request.user
    try:
        from ai_sdr_agent.agents.analytics_agent import AnalyticsAgent
        metrics = AnalyticsAgent().compute_metrics(company_user)
        return Response({'status': 'success', 'data': metrics})
    except KeyServiceError:
        raise
    except Exception as exc:
        logger.error('SDR analytics error: %s', exc)
        return Response({'status': 'error', 'message': str(exc)}, status=500)


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def sdr_send_daily_summary(request):
    """Manually trigger the daily summary email (for testing)."""
    company_user = request.user
    try:
        from ai_sdr_agent.agents.analytics_agent import AnalyticsAgent
        agent = AnalyticsAgent()
        sent = agent.send_daily_summary(company_user)
        return Response({'status': 'success', 'sent': sent})
    except KeyServiceError:
        raise
    except Exception as exc:
        logger.error('SDR send_daily_summary error: %s', exc)
        return Response({'status': 'error', 'message': str(exc)}, status=500)


# ==========================================================================
# Campaign serialiser helpers
# ==========================================================================

def _serialize_campaign(c: SDRCampaign, viewer=None) -> dict:
    from ai_sdr_agent.leavers import owner_of
    return {
        'id': c.id,
        # Whose campaign it is. An owner or admin is shown colleagues' campaigns
        # too, and may pause, resume or delete them; the rest is the owner's.
        'owner': owner_of(c, viewer) if viewer is not None else None,
        'name': c.name,
        'description': c.description,
        'status': c.status,
        'paused_reason': c.paused_reason if c.status == 'paused' else '',
        'sender_name': c.sender_name,
        'sender_title': c.sender_title,
        'sender_company': c.sender_company,
        'postal_address': c.postal_address,
        'from_email': c.from_email,
        'smtp_host': c.smtp_host,
        'smtp_port': c.smtp_port,
        'smtp_username': c.smtp_username,
        'smtp_use_tls': c.smtp_use_tls,
        'imap_host': c.imap_host,
        'imap_port': c.imap_port,
        'calendar_link': c.calendar_link,
        'start_date': c.start_date if isinstance(c.start_date, str) else (c.start_date.isoformat() if c.start_date else None),
        'end_date': c.end_date if isinstance(c.end_date, str) else (c.end_date.isoformat() if c.end_date else None),
        'auto_check_replies': c.auto_check_replies,
        'review_ai_replies': c.review_ai_replies,
        'answers_waiting': SDRReplyDraft.objects.filter(enrollment__campaign=c, status='pending').count(),
        'last_replies_checked_at': c.last_replies_checked_at.isoformat() if c.last_replies_checked_at else None,
        'inbox_error': c.inbox_error or '',
        'inbox_error_at': c.inbox_error_at.isoformat() if c.inbox_error_at else None,
        'activated_at': c.activated_at.isoformat() if c.activated_at else None,
        'total_leads': c.total_leads,
        'emails_sent': c.emails_sent,
        'replies_received': c.replies_received,
        'meetings_booked': c.meetings_booked,
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
        'reply_category_label': {
            'out_of_office': '🏖️ Out of Office',
            'not_interested': '🚫 Not Interested',
            'wants_more_info': '💬 Wants More Info',
            'positive': '✅ Interested',
            'positive_interest': '✅ Interested',
            'neutral': '💭 Neutral',
            'unsubscribe': '✋ Unsubscribed',
            'send_failed': '⚠️ Sending failed',
        }.get(e.reply_sentiment or '', ''),
        # Why a lead was parked after failed sends: the screen did not say (CO-198).
        'send_error': next((l['error_message'] for l in logs if l['status'] == 'failed'), '')
        if e.status == 'paused' and e.reply_sentiment == 'send_failed' else '',
        'resume_at': e.next_action_at.isoformat() if e.status == 'paused' and e.next_action_at else None,
        'meeting_id': meeting.id if meeting else None,
        'meeting_status': meeting.status if meeting else None,
        'enrolled_at': e.enrolled_at.isoformat(),
        'completed_at': e.completed_at.isoformat() if e.completed_at else None,
        'logs': logs,
    }


def _serialize_meeting(m: SDRMeeting) -> dict:
    campaign = m.enrollment.campaign if m.enrollment_id and m.enrollment else None
    return {
        'id': m.id,
        'lead_id': m.lead_id,
        'lead_name': m.lead.display_name,
        'lead_email': m.lead.email,
        'lead_company': m.lead.company_name,
        'lead_job_title': m.lead.job_title,
        'lead_temperature': m.lead.temperature,
        'lead_score': m.lead.score,
        'enrollment_id': m.enrollment_id,
        'campaign_id': campaign.id if campaign else None,
        'campaign_name': campaign.name if campaign else None,
        'campaign_status': campaign.status if campaign else None,   # active/completed/paused
        'campaign_removed': not m.is_manual and campaign is None,
        'title': m.title,
        'notes': m.notes,
        'reply_snippet': m.reply_snippet,
        'scheduled_at': m.scheduled_at.isoformat() if m.scheduled_at else None,
        'duration_minutes': m.duration_minutes,
        'status': m.status,
        'calendar_link': m.calendar_link,
        'prep_notes': m.prep_notes or {},
        'lead_timezone': m.lead_timezone or 'UTC',
        'scheduling_email_sent_at': m.scheduling_email_sent_at.isoformat() if m.scheduling_email_sent_at else None,
        'reminder_sent_at': m.reminder_sent_at.isoformat() if m.reminder_sent_at else None,
        'confirmed_at': m.confirmed_at.isoformat() if m.confirmed_at else None,
        'approval_proposed_at': m.approval_proposed_at.isoformat() if m.approval_proposed_at else None,
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
            # Its own; and for an owner or admin, everybody's in the company, so that a
            # campaign is never something only the person who made it can see or stop.
            from ai_sdr_agent.leavers import campaigns_for
            campaigns = campaigns_for(company_user).select_related('company_user')
            return Response({
                'status': 'success',
                'data': [_serialize_campaign(c, company_user) for c in campaigns],
            })
        except KeyServiceError:
            raise
        except Exception as exc:
            logger.error("List campaigns error: %s", exc)
            return Response({'status': 'error', 'message': str(exc)}, status=500)

    # POST — create campaign
    try:
        d = request.data
        start_date = d.get('start_date') or None  # ISO date string or None

        # ── Validation (mirrors the frontend; never trust the client) ─────────
        if not (d.get('name') or '').strip():
            return Response({'status': 'error', 'message': 'Campaign name is required.'}, status=400)
        mail_err = _validate_mail_settings(d)
        if mail_err:
            return Response({'status': 'error', 'message': mail_err}, status=400)
        cal_err = _validate_url_optional(
            d.get('calendar_link'),
            'Enter a valid calendar link like https://calendly.com/you/30min.',
        )
        if cal_err:
            return Response({'status': 'error', 'message': cal_err}, status=400)
        # ─────────────────────────────────────────────────────────────────────

        # If start_date provided → status='scheduled' (Celery will auto-activate)
        initial_status = 'scheduled' if start_date else 'draft'

        campaign = SDRCampaign.objects.create(
            company_user=company_user,
            name=d.get('name', 'New Campaign'),
            description=d.get('description', ''),
            sender_name=d.get('sender_name', ''),
            sender_title=d.get('sender_title', ''),
            sender_company=d.get('sender_company', ''),
            postal_address=str(d.get('postal_address', ''))[:500],
            from_email=d.get('from_email', ''),
            smtp_host=d.get('smtp_host', ''),
            smtp_port=int(d.get('smtp_port', 587)),
            smtp_username=d.get('smtp_username', ''),
            smtp_password=d.get('smtp_password', ''),
            smtp_use_tls=bool(d.get('smtp_use_tls', True)),
            imap_host=d.get('imap_host') or '',
            imap_port=int(d.get('imap_port') or 993),
            calendar_link=d.get('calendar_link', ''),
            start_date=start_date,
            auto_check_replies=bool(d.get('auto_check_replies', True)),
            review_ai_replies=bool(d.get('review_ai_replies', True)),
            status=initial_status,
        )

        # Auto-generate steps — on KeyServiceError rollback the campaign so no orphan is left
        if d.get('generate_steps', True):
            icp = SDRIcpProfile.objects.filter(company_user=company_user, is_active=True).first()
            try:
                steps_data = _get_outreach_agent(company_user.company).generate_campaign_steps(campaign, icp)
            except KeyServiceError:
                campaign.delete()
                raise
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

        if start_date:
            campaign.end_date = campaign.derive_end_date()
            campaign.save()

        return Response({'status': 'success', 'data': _serialize_campaign(campaign, company_user)}, status=201)
    except KeyServiceError:
        raise
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
    from ai_sdr_agent.leavers import campaigns_for
    campaign = campaigns_for(company_user).select_related('company_user').filter(id=campaign_id).first()
    if campaign is None:
        return Response({'status': 'error', 'message': 'Campaign not found.'}, status=404)
    mine = campaign.company_user_id == company_user.id

    if request.method == 'GET':
        data = _serialize_campaign(campaign, company_user)
        data['steps'] = [_serialize_step(s) for s in campaign.steps.filter(is_active=True)]
        return Response({'status': 'success', 'data': data})

    if request.method == 'PUT' and not mine:
        # A colleague's campaign: an owner or admin may pause it or start it again,
        # and nothing else. Its mailbox, its sender and its wording stay its owner's.
        sent = set((request.data or {}).keys()) if hasattr(request.data, 'keys') else set()
        if sent != {'status'} or request.data.get('status') not in ('paused', 'active'):
            return Response({'status': 'error', 'message': (
                "This is a colleague's campaign. You can pause it, start it again or delete it; "
                'only they can change it.')}, status=403)
        if request.data['status'] == 'active' and not campaign.company_user.is_active:
            return Response({'status': 'error', 'message': (
                'This campaign belongs to a login that is switched off, so it cannot be started again. '
                'Switch the login back on first, or delete the campaign.')}, status=400)

    if request.method == 'PUT':
        try:
            d = request.data
            mail_err = _validate_mail_settings(d, campaign)
            if mail_err:
                return Response({'status': 'error', 'message': mail_err}, status=400)
            # Leads are enrolled: the campaign's mailbox can be changed but not taken away.
            # It is what sends to them and what their replies are read from.
            emptied = [label for field, label in (('smtp_host', 'SMTP host'), ('smtp_username', 'SMTP username'))
                       if field in d and not str(d[field] or '').strip() and getattr(campaign, field)]
            if emptied and campaign.enrollments.exists():
                return Response({'status': 'error', 'message': (
                    'This campaign has leads enrolled, so its mailbox settings can be changed but not '
                    'removed (%s). Remove the leads first, or enter the new mailbox.' % ', '.join(emptied))},
                    status=400)
            if 'status' in d:
                new_status = d['status']
                if new_status not in dict(SDRCampaign.STATUS_CHOICES):
                    return Response({'status': 'error', 'message': 'Invalid campaign status.'}, status=400)
                if new_status == 'active' and campaign.status != 'active':
                    smtp_ok = all([
                        d.get('smtp_host', campaign.smtp_host),
                        d.get('smtp_username', campaign.smtp_username),
                        d.get('smtp_password') or campaign.smtp_password,
                    ])
                    if not smtp_ok:
                        return Response({'status': 'error', 'message': 'Add SMTP settings before activating the campaign.'}, status=400)
                    if not campaign.steps.filter(is_active=True).exists():
                        return Response({'status': 'error', 'message': 'Add at least one step before activating the campaign.'}, status=400)
            status_before = campaign.status
            for field in ['name', 'description', 'status', 'sender_name', 'sender_title',
                          'sender_company', 'postal_address', 'from_email', 'smtp_host', 'smtp_username',
                          'smtp_use_tls', 'imap_host', 'calendar_link', 'auto_check_replies',
                          'review_ai_replies']:
                if field in d:
                    setattr(campaign, field, d[field])
            if campaign.status != status_before:
                campaign.paused_reason = ''        # a person changed it: the product's own reason is history
            if campaign.status == 'active' and status_before in ('draft', 'completed', 'scheduled'):
                # Start campaign: a later start date makes it Scheduled (CO-149).
                start = campaign.start_date
                if isinstance(start, str):
                    from datetime import date as _d
                    start = _d.fromisoformat(start)
                if start and start > timezone.now().date():
                    campaign.status = 'scheduled'
                else:
                    campaign.activated_at = timezone.now()
            if 'smtp_port' in d:
                campaign.smtp_port = int(d['smtp_port'])
            if 'imap_port' in d:
                campaign.imap_port = int(d['imap_port'])
            if 'smtp_password' in d and d['smtp_password']:
                campaign.smtp_password = d['smtp_password']
            if 'start_date' in d:
                campaign.start_date = d['start_date'] or None
                if campaign.start_date and campaign.status == 'draft':
                    campaign.status = 'scheduled'
            campaign.save()
            return Response({'status': 'success', 'data': _serialize_campaign(campaign, company_user)})
        except KeyServiceError:
            raise
        except Exception as exc:
            return Response({'status': 'error', 'message': str(exc)}, status=500)

    # DELETE: its open calls are cancelled first; they stayed booked, blocking the calendar, but hidden (CO-148).
    from django.db import transaction
    from ai_sdr_agent.reply_actions import cancel_meetings_of
    with transaction.atomic():
        cancel_meetings_of(campaign.enrollments.all())
        campaign.delete()
    return Response({'status': 'success', 'message': 'Campaign deleted.'})


# ==========================================================================
# Clear all enrollments / leads from a campaign
# ==========================================================================

@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def sdr_clear_campaign_leads(request, campaign_id):
    """Delete every enrollment (and related logs/meetings) for a campaign and reset counters."""
    company_user = request.user
    try:
        campaign = SDRCampaign.objects.get(id=campaign_id, company_user=company_user)
    except SDRCampaign.DoesNotExist:
        return Response({'status': 'error', 'message': 'Campaign not found.'}, status=404)

    try:
        # Selective: if enrollment_ids provided, only delete those
        enrollment_ids = request.data.get('enrollment_ids', [])
        if enrollment_ids:
            qs = campaign.enrollments.filter(id__in=enrollment_ids)
        else:
            qs = campaign.enrollments.all()
        # Open calls cancelled, then the recount. The recount used relations a campaign does not have, so every
        # Clear Leads ended in an error after the delete, with the old figures left (CO-147, CO-148).
        from django.db import transaction
        from ai_sdr_agent.reply_actions import cancel_meetings_of
        with transaction.atomic():
            cancel_meetings_of(qs)
            deleted_count = qs.count()
            qs.delete()
            campaign.total_leads = campaign.enrollments.count()
            campaign.emails_sent = SDROutreachLog.objects.filter(
                enrollment__campaign=campaign, status='sent', action_type='email').count()
            campaign.replies_received = campaign.enrollments.filter(replied_at__isnull=False).count()
            campaign.meetings_booked = SDRMeeting.objects.filter(enrollment__campaign=campaign).count()
            campaign.save(update_fields=['emails_sent', 'replies_received', 'meetings_booked', 'total_leads'])
        logger.info("SDR: cleared %d enrollments from campaign %s", deleted_count, campaign_id)
        return Response({
            'status': 'success',
            'message': f'Cleared {deleted_count} enrollment records.',
            'data': _serialize_campaign(campaign, company_user),
        })
    except KeyServiceError:
        raise
    except Exception as exc:
        logger.error("SDR clear leads error: %s", exc)
        return Response({'status': 'error', 'message': str(exc)}, status=500)


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def sdr_retry_failed(request, campaign_id):
    """Put the leads parked after failed sends back in the sequence, once the mailbox is fixed (CO-198)."""
    company_user = request.user
    campaign = SDRCampaign.objects.filter(id=campaign_id, company_user=company_user).first()
    if campaign is None:
        return Response({'status': 'error', 'message': 'Campaign not found.'}, status=404)
    retried = campaign.enrollments.filter(status='paused', reply_sentiment='send_failed').update(
        status='active', reply_sentiment='', next_action_at=timezone.now())
    if retried and campaign.status == 'completed':
        campaign.status = 'active'
        campaign.save(update_fields=['status'])
    return Response({'status': 'success', 'retried': retried, 'data': _serialize_campaign(campaign, company_user)})


# ==========================================================================
# Email Assistant: write an outreach email, or read a lead's reply
# (it was a "Coming soon" page; the client's list, part 6)
# ==========================================================================

def _assistant_context(company_user, data):
    """The sender and the offer: typed on the page, or taken from one of the person's campaigns."""
    campaign = None
    if str(data.get('campaign_id') or '').isdigit():
        campaign = SDRCampaign.objects.filter(id=int(data['campaign_id']), company_user=company_user).first()
    sender = {
        'name': (data.get('sender_name') or (campaign.sender_name if campaign else '') or company_user.full_name or '').strip(),
        'title': (data.get('sender_title') or (campaign.sender_title if campaign else '') or '').strip(),
        'company': (data.get('sender_company') or (campaign.sender_company if campaign else '')
                    or company_user.company.name or '').strip(),
    }
    offer = (data.get('offer') or (campaign.description if campaign else '') or '').strip()
    return sender, offer


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def sdr_assistant_write(request):
    from ai_sdr_agent.agents.email_assistant_agent import EmailAssistantAgent
    company_user, d = request.user, request.data
    prospect = {k: str(d.get(k) or '')[:300] for k in ('name', 'title', 'company', 'industry')}
    prospect['notes'] = str(d.get('notes') or '')[:800]
    if not (prospect['name'] or prospect['company']):
        return Response({'status': 'error', 'message': "Type at least the prospect's name or company."}, status=400)
    sender, offer = _assistant_context(company_user, d)
    try:
        email_text = EmailAssistantAgent(company=company_user.company).write_email(
            d.get('kind'), d.get('tone'), prospect, sender, offer)
    except KeyServiceError:
        raise
    except ValueError as exc:
        return Response({'status': 'error', 'message': str(exc)}, status=400)
    except Exception as exc:
        logger.warning("Email assistant write failed: %s", exc)
        return Response({'status': 'error', 'message': 'The AI could not write the email. Please try again.'},
                        status=502)
    return Response({'status': 'success', 'data': email_text})


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def sdr_assistant_read(request):
    from ai_sdr_agent.agents.email_assistant_agent import EmailAssistantAgent
    company_user, d = request.user, request.data
    reply_text = str(d.get('reply') or '').strip()
    if not reply_text:
        return Response({'status': 'error', 'message': "Paste the lead's reply first."}, status=400)
    sender, offer = _assistant_context(company_user, d)
    try:
        reading = EmailAssistantAgent(company=company_user.company).read_reply(reply_text[:5000], sender, offer)
    except KeyServiceError:
        raise
    except ValueError as exc:
        return Response({'status': 'error', 'message': str(exc)}, status=400)
    except Exception as exc:
        logger.warning("Email assistant read failed: %s", exc)
        return Response({'status': 'error', 'message': 'The AI could not read the reply. Please try again.'},
                        status=502)
    return Response({'status': 'success', 'data': reading})


# ==========================================================================
# Answers the AI wrote to leads' replies, waiting for a person to check them
# (ai_sdr_agent/reply_answers.py)
# ==========================================================================

def _serialize_reply_draft(draft: SDRReplyDraft) -> dict:
    lead = draft.enrollment.lead
    return {
        'id': draft.id,
        'campaign_id': draft.enrollment.campaign_id,
        'enrollment_id': draft.enrollment_id,
        'lead_name': lead.display_name,
        'lead_email': lead.email,
        'lead_reply': draft.lead_reply,
        'subject': draft.subject,
        'body': draft.body,
        'status': draft.status,
        'error': draft.error,
        'created_at': draft.created_at.isoformat(),
    }


def _own_reply_draft(company_user, draft_id):
    return (SDRReplyDraft.objects.select_related('enrollment__lead', 'enrollment__campaign__company_user')
            .filter(id=draft_id, enrollment__campaign__company_user=company_user).first())


@api_view(['GET'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def sdr_reply_drafts(request, campaign_id):
    """The answers waiting to be checked in one of the caller's campaigns."""
    company_user = request.user
    if not SDRCampaign.objects.filter(id=campaign_id, company_user=company_user).exists():
        return Response({'status': 'error', 'message': 'Campaign not found.'}, status=404)
    drafts = (SDRReplyDraft.objects.select_related('enrollment__lead')
              .filter(enrollment__campaign_id=campaign_id, status='pending').order_by('created_at'))
    return Response({'status': 'success', 'data': [_serialize_reply_draft(d) for d in drafts]})


@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def sdr_reply_draft_decide(request, draft_id, decision):
    """Send a waiting answer (as written, or with the subject and text sent here), or discard it."""
    from ai_sdr_agent import reply_answers

    company_user = request.user
    draft = _own_reply_draft(company_user, draft_id)
    if draft is None:
        return Response({'status': 'error', 'message': 'Answer not found.'}, status=404)
    try:
        if decision == 'send':
            d = request.data if isinstance(request.data, dict) else {}
            # The answer is already written, so this needs the mailbox and no AI key.
            draft = reply_answers.send_draft(
                draft, company_user, outreach_agent=OutreachAgent(company=company_user.company, needs_ai=False),
                subject=d.get('subject'), body=d.get('body'))
        else:
            draft = reply_answers.discard_draft(draft, company_user)
    except reply_answers.NotSendable as refused:
        return Response({'status': 'error', 'message': str(refused)}, status=400)
    return Response({'status': 'success', 'data': _serialize_reply_draft(draft)})


# ==========================================================================
# Campaign steps — list / add
# ==========================================================================

@api_view(['GET', 'POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def sdr_campaign_steps(request, campaign_id):
    company_user = request.user
    from ai_sdr_agent.leavers import campaigns_for
    campaign = campaigns_for(company_user).filter(id=campaign_id).first()
    if campaign is None or (request.method != 'GET' and campaign.company_user_id != company_user.id):
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
    except KeyServiceError:
        raise
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
    except KeyServiceError:
        raise
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

    # Not while it is sending: leads part-way through would carry on from the same place with new text, hand edits
    # gone (CO-245). The screen asks before it replaces the steps.
    mid_sequence = campaign.enrollments.filter(status='active').count()
    if campaign.status == 'active' and mid_sequence:
        return Response({'status': 'error', 'code': 'campaign_sending',
                         'message': f'Pause the campaign first: {mid_sequence} lead(s) are part-way through these '
                                    f'emails.'}, status=409)

    try:
        icp = SDRIcpProfile.objects.filter(company_user=company_user, is_active=True).first()
        # Generate BEFORE deleting existing steps — so quota error leaves steps intact
        steps_data = _get_outreach_agent(company_user.company).generate_campaign_steps(campaign, icp)

        campaign.steps.all().delete()
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
    except KeyServiceError:
        raise
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

        # Require explicit SMTP credentials — never fall back to global Django email settings
        if not (campaign.smtp_host and campaign.smtp_username and campaign.smtp_password):
            return Response({
                'status': 'error',
                'message': 'Campaign SMTP not configured. Open Settings → Email/SMTP and add your email credentials before enrolling leads.',
            }, status=400)

        leads = SDRLead.objects.filter(id__in=lead_ids, company_user=company_user)
        first_step = campaign.steps.filter(is_active=True).order_by('step_order').first()

        enrolled = skipped = 0
        skipped_reasons = []
        cross_campaign_warnings = []

        for lead in leads:
            # Dedup by lead ID (same object re-enrolled)
            if SDRCampaignEnrollment.objects.filter(campaign=campaign, lead=lead).exists():
                skipped += 1
                skipped_reasons.append(f"{lead.display_name}: already enrolled in this campaign")
                continue

            # Never enroll an address that unsubscribed or hard-bounced anywhere
            # in this company.
            from ai_sdr_agent.agents.outreach_agent import is_email_suppressed
            if is_email_suppressed(company_user, lead.email):
                skipped += 1
                skipped_reasons.append(f"{lead.display_name}: unsubscribed or bounced address")
                continue

            # Leads the AI made up before 29 Oct 2026 are not real people: their addresses could belong to strangers.
            if lead.source == 'ai_generated':
                skipped += 1
                skipped_reasons.append(f"{lead.display_name}: made up by the AI, not a real person")
                continue

            # Dedup by email address — prevents two different lead records with the
            # same email from both receiving outreach in the same campaign.
            lead_email = (lead.email or '').strip().lower()
            if lead_email and SDRCampaignEnrollment.objects.filter(
                campaign=campaign,
                lead__email__iexact=lead_email,
                status__in=['active', 'replied'],
            ).exclude(lead=lead).exists():
                skipped += 1
                skipped_reasons.append(f"{lead.display_name}: email already enrolled in this campaign")
                logger.warning(
                    "SDR [ENROLL-DEDUP] skipping lead=%d (%s) email=%s — "
                    "another lead with the same email is already active in campaign=%d",
                    lead.id, lead.display_name, lead_email, campaign.id,
                )
                continue

            # ── Cross-campaign warning ───────────────────────────────────────
            # Don't block enrollment, but warn if lead is active in other campaigns.
            # The scheduler's daily guard will prevent them receiving more than
            # 1 email per day across all campaigns.
            if lead_email:
                other_active = SDRCampaignEnrollment.objects.filter(
                    lead__email__iexact=lead_email,
                    status__in=['active', 'replied'],
                    campaign__company_user=company_user,
                ).exclude(campaign=campaign).select_related('campaign')
                if other_active.exists():
                    other_names = ', '.join(
                        e.campaign.name for e in other_active[:3]
                    )
                    cross_campaign_warnings.append(
                        f"{lead.display_name} is also active in: {other_names} "
                        f"— will receive max 1 email/day total"
                    )
            # ─────────────────────────────────────────────────────────────────

            next_action = None
            if first_step:
                # delay_days=1 means "Day 1" = send immediately on enrollment day
                next_action = timezone.now() + timedelta(days=max(0, first_step.delay_days - 1))

            SDRCampaignEnrollment.objects.create(
                campaign=campaign,
                lead=lead,
                status='active',
                current_step=0,
                next_action_at=next_action,
            )
            enrolled += 1

        # Adding leads no longer starts the campaign: a draft's first email went out within five minutes of
        # "Enroll Selected", with no warning (CO-149). Start campaign does it.
        campaign.total_leads = campaign.enrollments.count()
        campaign.save(update_fields=['total_leads'])

        resp = {
            'status': 'success',
            'enrolled': enrolled,
            'skipped': skipped,
            'total_leads': campaign.total_leads,
            'campaign_status': campaign.status,
        }
        if skipped_reasons:
            resp['skipped_reasons'] = skipped_reasons
        if cross_campaign_warnings:
            resp['warnings'] = cross_campaign_warnings
        return Response(resp)
    except KeyServiceError:
        raise
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
    from ai_sdr_agent.leavers import campaigns_for
    campaign = campaigns_for(company_user).filter(id=campaign_id).first()
    if campaign is None:
        return Response({'status': 'error', 'message': 'Campaign not found.'}, status=404)

    try:
        enrollments = campaign.enrollments.select_related('lead').order_by('-enrolled_at')
        return Response({
            'status': 'success',
            'data': [_serialize_enrollment(e) for e in enrollments],
        })
    except KeyServiceError:
        raise
    except Exception as exc:
        logger.error("List enrollments error: %s", exc)
        return Response({'status': 'error', 'message': str(exc)}, status=500)


# ==========================================================================
# Mark enrollment as replied
# ==========================================================================

# ==========================================================================
# Marking a reply by hand (the reply rules themselves are in ai_sdr_agent/reply_actions.py)
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
        campaign = enrollment.campaign
        lead = enrollment.lead

        # Classify with EmailAssistantAgent
        from ai_sdr_agent.agents.email_assistant_agent import EmailAssistantAgent
        if reply_content:
            classification = EmailAssistantAgent(company=company_user.company).classify_reply(reply_content)
        else:
            # Manual override: no text → treat as positive
            classification = {
                'category': 'positive_interest', 'action': 'book_meeting',
                'label': 'Positive', 'is_interested': True, 'reason': 'Manual',
                'resume_date': None,
            }

        result = _apply_reply_action(
            company_user, campaign, enrollment, lead, classification, reply_content
        )

        return Response({
            'status': 'success',
            'category': classification['category'],
            'label': classification.get('label', ''),
            'action_taken': result['action'],
            'meeting_created': result.get('meeting_created', False),
            'is_interested': classification['is_interested'],
            'data': _serialize_enrollment(enrollment),
        })
    except KeyServiceError:
        raise
    except Exception as exc:
        logger.error("Mark replied error: %s", exc)
        return Response({'status': 'error', 'message': str(exc)}, status=500)


# ==========================================================================
# Process outreach — send due steps for campaign
# ==========================================================================

PROCESS_BATCH_LIMIT = 50   # max enrollments sent per manual "Process" click


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

        if campaign.status != 'active':
            return Response({
                'status': 'error',
                'message': f'Campaign is {campaign.status}. Activate it before processing outreach.',
            }, status=400)

        qs = campaign.enrollments.filter(status='active', lead__is_deleted=False)
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

        agent = _get_outreach_agent(company_user.company)
        results = []
        batch = list(due[:PROCESS_BATCH_LIMIT + 1])
        remaining = max(0, len(batch) - PROCESS_BATCH_LIMIT)
        for enrollment in batch[:PROCESS_BATCH_LIMIT]:
            try:
                result = agent.process_enrollment(enrollment)
            except KeyServiceError:
                raise
            except Exception as exc:
                # One bad enrollment must not abort the whole run with a 500.
                logger.error("Process outreach: enrollment %s failed: %s", enrollment.id, exc, exc_info=True)
                result = {'status': 'failed', 'lead': enrollment.lead.display_name, 'error': str(exc)}
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
            'remaining': remaining,
        })
    except KeyServiceError:
        raise
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
        enrollments = list(
            campaign.enrollments
            .filter(status__in=['active', 'paused', 'completed', 'replied'])
            .exclude(lead__email='')
            .select_related('lead')
            .prefetch_related('logs')
        )

        from ai_sdr_agent.agents.email_assistant_agent import EmailAssistantAgent
        email_agent = EmailAssistantAgent(company=company_user.company)
        outreach_agent = _get_outreach_agent(company_user.company)
        replies_found = read_inbox(campaign, enrollments, outreach_agent)
        if replies_found is None:
            return Response({'status': 'error', 'code': 'inbox_unreadable', 'message': campaign.inbox_error},
                            status=400)

        new_replies = 0
        meetings_created = 0
        details = []

        for r in replies_found:
            result = handle_inbox_reply(campaign, r, email_agent=email_agent, outreach_agent=outreach_agent)
            if not result or result['action'] == 'bounced':
                continue
            classification = result['classification']
            lead = r['enrollment'].lead

            if result['action'] not in ('wait',):
                new_replies += 1
            if result.get('meeting_created'):
                meetings_created += 1

            details.append({
                'lead': lead.display_name,
                'email': r['sender_email'],
                'subject': r.get('subject', ''),
                'category': classification['category'],
                'label': classification['label'],
                'action_taken': result['action'],
            })

        campaign.save(update_fields=['replies_received', 'meetings_booked'])

        return Response({
            'status': 'success',
            'checked': len(enrollments),
            'new_replies': new_replies,
            'meetings_created': meetings_created,
            'details': details,
        })
    except KeyServiceError:
        raise
    except Exception as exc:
        logger.error("Check replies error for campaign %s: %s", campaign_id, exc)
        return Response({'status': 'error', 'message': str(exc)}, status=500)


# ==========================================================================
# Meetings — scheduling agent output
# ==========================================================================

@contextmanager
def _host_booking(company_user, scheduled_at, duration_minutes, *, exclude_id=None, public=False):
    """The salesperson must be free then, on the calendar every agent shares:
    no interview, no other agent's meeting, no leave, no company holiday.

    Use as ``with _host_booking(...): save the call``. It holds the booking
    lock while the call is saved, and raises ``ScheduleConflict`` before
    anything is saved if they are busy. Sales calls used to be checked only
    against the same person's other sales calls, or against nothing at all.

    ``public`` is for the page a lead books on: the reason is kept back, so a
    stranger learns only that the time is not available. A salesperson whose
    dashboard login is nobody's employee login has no calendar to check.
    """
    from core.scheduling import booking_guard, ensure_free, login_user_id_for_company_user, zone_name
    host = login_user_id_for_company_user(company_user)
    people = [host] if host else []
    with booking_guard(people):
        if people and scheduled_at is not None:
            ensure_free(people, scheduled_at, duration_minutes or 30,
                        tz_name=zone_name(company_user.company.timezone_name),
                        exclude=[('sdr', exclude_id)] if exclude_id else (),
                        viewer_source='sdr', hide_titles=public, suggest=not public)
        elif scheduled_at is not None:
            # No employee login, so no shared calendar: their own sales calls are checked still. Nothing was, and
            # two calls could overlap (CO-151).
            _ensure_own_calls_free(company_user, scheduled_at, duration_minutes or 30, exclude_id, public)
        yield


def _ensure_own_calls_free(company_user, start, minutes, exclude_id, public):
    """Raise ScheduleConflict if another of this salesperson's booked or proposed calls overlaps."""
    from core.scheduling import Clash, zone_name
    from core.scheduling.sources import SOURCES
    end = start + timedelta(minutes=minutes)
    clashes = []
    others = SDRMeeting.objects.filter(company_user=company_user, status__in=SOURCES['sdr'].BOOKED,
                                       scheduled_at__lt=end, scheduled_at__gt=start - timedelta(hours=8))
    for other in others.exclude(id=exclude_id):
        other_end = other.scheduled_at + timedelta(minutes=other.duration_minutes or 30)
        if other_end > start:
            clashes.append(Clash(user_id=0, user_name=company_user.full_name or company_user.email,
                                 source='sdr', source_id=other.id, title=None if public else other.title,
                                 starts_at=other.scheduled_at, ends_at=other_end, response=''))
    if clashes:
        raise ScheduleConflict(clashes, tz_name=zone_name(company_user.company.timezone_name))


def _takes_time(status, scheduled_at) -> bool:
    """Does a call in this state occupy the salesperson's calendar?"""
    from core.scheduling.sources import SOURCES
    return scheduled_at is not None and status in SOURCES['sdr'].BOOKED


def _clean_meeting_fields(d):
    """Validate the editable meeting fields in ``d``.

    Returns (fields, None) with only the keys that were sent, or (None, message).
    Bad input used to reach the ORM and come back as a 500.
    """
    fields = {}
    if 'title' in d:
        fields['title'] = str(d['title'] or '')[:255]
    if 'notes' in d:
        fields['notes'] = str(d['notes'] or '')
    if 'calendar_link' in d:
        fields['calendar_link'] = str(d['calendar_link'] or '')[:500]
    if 'status' in d:
        if d['status'] not in dict(SDRMeeting.STATUS_CHOICES):
            return None, 'Invalid meeting status.'
        fields['status'] = d['status']
    if 'duration_minutes' in d:
        try:
            minutes = int(d['duration_minutes'])
        except (TypeError, ValueError):
            return None, 'duration_minutes must be a number.'
        if not 5 <= minutes <= 480:
            return None, 'duration_minutes must be between 5 and 480.'
        fields['duration_minutes'] = minutes
    if 'scheduled_at' in d:
        if d['scheduled_at']:
            try:
                fields['scheduled_at'] = _parse_aware_datetime(d['scheduled_at'])
            except ValueError as exc:
                return None, str(exc)
        else:
            fields['scheduled_at'] = None
    return fields, None


@api_view(['GET', 'POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def sdr_meetings_list(request):
    company_user = request.user

    if request.method == 'GET':
        try:
            status_filter    = request.GET.get('status', '').strip()
            campaign_id      = request.GET.get('campaign_id', '').strip()
            campaign_status  = request.GET.get('campaign_status', '').strip()
            search           = request.GET.get('search', '').strip()
            search_field     = request.GET.get('search_field', 'all').strip()
            temperature_f    = request.GET.get('temperature', '').strip()
            # active_only=true → strictly active campaigns only; default false = show all
            active_only    = request.GET.get('active_only', 'false').lower() == 'true'
            try:
                page      = max(1, int(request.GET.get('page', 1)))
                page_size = min(100, max(5, int(request.GET.get('page_size', 20))))
            except (ValueError, TypeError):
                page, page_size = 1, 20

            # Sorting
            MEET_SORT_MAP = {
                'created_desc':   ['-created_at'],
                'created_asc':    ['created_at'],
                'scheduled_asc':  ['scheduled_at'],
                'scheduled_desc': ['-scheduled_at'],
                'score_desc':     ['-lead__score', '-created_at'],
                'name_asc':       ['lead__full_name'],
            }
            sort_by  = request.GET.get('sort', 'created_desc')
            ordering = MEET_SORT_MAP.get(sort_by, ['-created_at'])

            qs = SDRMeeting.objects.filter(company_user=company_user).select_related(
                'lead', 'enrollment', 'enrollment__campaign'
            ).order_by(*ordering)

            # A call whose campaign was removed is shown ("campaign removed"), no longer hidden: it could not be
            # opened or cancelled (CO-148).

            # campaign_status filter overrides active_only when provided
            if campaign_status:
                qs = qs.filter(enrollment__campaign__status=campaign_status)
            elif active_only:
                qs = qs.filter(enrollment__campaign__status='active')

            if status_filter:
                qs = qs.filter(status=status_filter)

            if campaign_id:
                qs = qs.filter(enrollment__campaign_id=campaign_id)

            if temperature_f:
                qs = qs.filter(lead__temperature=temperature_f)

            if search:
                field_map = {
                    'name':     Q(lead__full_name__icontains=search) | Q(lead__first_name__icontains=search) | Q(lead__last_name__icontains=search),
                    'email':    Q(lead__email__icontains=search),
                    'company':  Q(lead__company_name__icontains=search),
                    'title':    Q(lead__job_title__icontains=search),
                    'campaign': Q(enrollment__campaign__name__icontains=search),
                }
                if search_field in field_map:
                    qs = qs.filter(field_map[search_field])
                else:
                    qs = qs.filter(
                        Q(lead__full_name__icontains=search)
                        | Q(lead__first_name__icontains=search)
                        | Q(lead__last_name__icontains=search)
                        | Q(lead__email__icontains=search)
                        | Q(lead__company_name__icontains=search)
                        | Q(lead__job_title__icontains=search)
                        | Q(enrollment__campaign__name__icontains=search)
                    )

            total        = qs.count()
            paginator    = Paginator(qs, page_size)
            page_obj     = paginator.get_page(page)

            return Response({
                'results':     [_serialize_meeting(m) for m in page_obj.object_list],
                'total':       total,
                'page':        page_obj.number,
                'page_size':   page_size,
                'total_pages': paginator.num_pages,
                'has_next':    page_obj.has_next(),
                'has_prev':    page_obj.has_previous(),
            })
        except KeyServiceError:
            raise
        except Exception as exc:
            return Response({'status': 'error', 'message': str(exc)}, status=500)

    # POST — create manual meeting
    try:
        d = request.data
        lead_id = d.get('lead_id')
        if not lead_id:
            return Response({'status': 'error', 'message': 'lead_id required'}, status=400)
        lead = SDRLead.objects.get(id=lead_id, company_user=company_user)
        fields, err = _clean_meeting_fields(d)
        if err:
            return Response({'status': 'error', 'message': err}, status=400)
        new = dict(
            company_user=company_user,
            lead=lead,
            title=fields.get('title', f'Discovery Call with {lead.display_name}'),
            notes=fields.get('notes', ''),
            scheduled_at=fields.get('scheduled_at'),
            duration_minutes=fields.get('duration_minutes', 30),
            calendar_link=fields.get('calendar_link', ''),
            status=fields.get('status', 'pending'),
            is_manual=True,
        )
        if _takes_time(new['status'], new['scheduled_at']):
            with _host_booking(company_user, new['scheduled_at'], new['duration_minutes']):
                meeting = SDRMeeting.objects.create(**new)
        else:
            meeting = SDRMeeting.objects.create(**new)
        return Response({'status': 'success', 'data': _serialize_meeting(meeting)}, status=201)
    except ScheduleConflict as clash:
        return clash.response()
    except SDRLead.DoesNotExist:
        return Response({'status': 'error', 'message': 'Lead not found.'}, status=404)
    except KeyServiceError:
        raise
    except Exception as exc:
        return Response({'status': 'error', 'message': str(exc)}, status=500)


@api_view(['GET', 'PUT', 'DELETE'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def sdr_meeting_detail(request, meeting_id):
    company_user = request.user
    try:
        meeting = SDRMeeting.objects.select_related(
            'lead', 'enrollment', 'enrollment__campaign'
        ).get(id=meeting_id, company_user=company_user)
    except SDRMeeting.DoesNotExist:
        return Response({'status': 'error', 'message': 'Meeting not found.'}, status=404)

    if request.method == 'GET':
        return Response(_serialize_meeting(meeting))

    if request.method == 'PUT':
        try:
            d = request.data
            old_status = meeting.status
            fields, err = _clean_meeting_fields(d)
            if err:
                return Response({'status': 'error', 'message': err}, status=400)
            was = (_takes_time(meeting.status, meeting.scheduled_at), meeting.scheduled_at, meeting.duration_minutes)
            for field, value in fields.items():
                setattr(meeting, field, value)
            now = (_takes_time(meeting.status, meeting.scheduled_at), meeting.scheduled_at, meeting.duration_minutes)
            if now[0] and now != was:
                # A new time or length, or a call brought back: the salesperson must be free then.
                try:
                    with _host_booking(company_user, meeting.scheduled_at, meeting.duration_minutes,
                                       exclude_id=meeting.id):
                        meeting.save()
                except ScheduleConflict as clash:
                    return clash.response()
            else:
                meeting.save()

            new_status = meeting.status
            # Send completion thank-you email when status changes to completed
            if old_status != 'completed' and new_status == 'completed':
                try:
                    if meeting.enrollment and meeting.enrollment.campaign:
                        from ai_sdr_agent.agents.meeting_scheduling_agent import MeetingSchedulingAgent
                        MeetingSchedulingAgent(company=company_user.company).send_completion_email(
                            meeting.enrollment.campaign, meeting.lead, meeting
                        )
                except Exception as mail_exc:
                    logger.warning("Completion email failed for meeting %s: %s", meeting.id, mail_exc)

            # Send "you didn't show up" email when status changes to no_show
            if old_status != 'no_show' and new_status == 'no_show':
                try:
                    if meeting.enrollment and meeting.enrollment.campaign:
                        campaign = meeting.enrollment.campaign
                        lead = meeting.lead
                        outreach = _get_outreach_agent(company_user.company)
                        subject = "We missed you today"
                        body = (
                            f"Hi {lead.first_name or lead.full_name},\n\n"
                            f"We had a meeting scheduled today but it looks like you weren't able to make it — no worries at all!\n\n"
                            f"I'd love to find another time that works better for you. "
                            + (f"Feel free to pick a new slot here: {campaign.calendar_link}\n\n" if campaign.calendar_link
                               else "Just reply with a day and time that suit you.\n\n")   # it ended on an empty link
                            + f"Looking forward to connecting,\n"
                            f"{campaign.sender_name}\n{campaign.sender_title}\n{campaign.sender_company}"
                        )
                        outreach.send_email(campaign, lead.email, subject, body)
                except Exception as mail_exc:
                    logger.warning("No-show email failed for meeting %s: %s", meeting.id, mail_exc)

            # A booked call can be cancelled from the Meetings screen; the lead is told (CO-200).
            if old_status != 'cancelled' and new_status == 'cancelled' and meeting.scheduled_at:
                try:
                    if meeting.enrollment and meeting.enrollment.campaign:
                        campaign = meeting.enrollment.campaign
                        lead = meeting.lead
                        from ai_sdr_agent.agents.meeting_scheduling_agent import format_datetime_with_timezone
                        when = format_datetime_with_timezone(meeting.scheduled_at, meeting.lead_timezone or 'UTC')
                        body = (
                            f"Hi {lead.first_name or lead.full_name},\n\n"
                            f"I'm sorry, I have to cancel our call on {when}. "
                            f"If you would still like to talk, just reply with a day and time that suit you.\n\n"
                            f"Best regards,\n{campaign.sender_name}\n{campaign.sender_title}\n{campaign.sender_company}"
                        )
                        _get_outreach_agent(company_user.company).send_email(
                            campaign, lead.email, f"Cancelled: {meeting.title or 'our call'}", body)
                except Exception as mail_exc:
                    logger.warning("Cancellation email failed for meeting %s: %s", meeting.id, mail_exc)

            return Response({'status': 'success', 'data': _serialize_meeting(meeting)})
        except KeyServiceError:
            raise
        except Exception as exc:
            return Response({'status': 'error', 'message': str(exc)}, status=500)

    # DELETE
    meeting.delete()
    return Response({'status': 'success'})


# ==========================================================================
# Meeting — confirm (set scheduled_at + send confirmation email)
# ==========================================================================

@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def sdr_confirm_meeting(request, meeting_id):
    """
    Two modes via `send_approval` flag:
      - send_approval=false (default): confirm immediately, send confirmation email to lead.
      - send_approval=true: set status to awaiting_approval, email lead asking "does this time work?"
        Lead clicks Yes → /meetings/<id>/approve/ → status = scheduled
        Lead clicks Suggest → /meetings/<id>/suggest-time/ → opens booking page
    """
    company_user = request.user
    try:
        meeting = SDRMeeting.objects.select_related('lead', 'enrollment__campaign').get(
            id=meeting_id, company_user=company_user
        )
    except SDRMeeting.DoesNotExist:
        return Response({'status': 'error', 'message': 'Meeting not found.'}, status=404)

    try:
        d = request.data
        scheduled_at = d.get('scheduled_at')
        if not scheduled_at:
            return Response({'status': 'error', 'message': 'scheduled_at is required.'}, status=400)

        # Parse ISO string to datetime if needed
        if isinstance(scheduled_at, str):
            from django.utils.dateparse import parse_datetime
            parsed = parse_datetime(scheduled_at)
            if parsed is None:
                from datetime import datetime
                parsed = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
            scheduled_at = parsed

        meeting.scheduled_at = scheduled_at
        if d.get('duration_minutes'):
            meeting.duration_minutes = int(d['duration_minutes'])
        if d.get('notes'):
            meeting.notes = d['notes']

        send_approval = str(d.get('send_approval', 'false')).lower() in ('true', '1', 'yes')
        # Use browser timezone for formatting the proposed time in the email
        # so the lead sees the same time the SDR picked in the UI
        browser_tz = d.get('browser_timezone', '') or meeting.lead_timezone or 'UTC'
        if meeting.lead_timezone != browser_tz and browser_tz != 'UTC':
            meeting.lead_timezone = browser_tz

        campaign = meeting.enrollment.campaign if meeting.enrollment_id and meeting.enrollment else None

        if send_approval:
            # Lead approval flow — email lead, wait for their confirmation
            import uuid as _uuid
            meeting.approval_token = _uuid.uuid4()
            meeting.status = 'awaiting_approval'
            meeting.approval_proposed_at = timezone.now()
            with _host_booking(company_user, meeting.scheduled_at, meeting.duration_minutes, exclude_id=meeting.id):
                if campaign is None:
                    # No mailbox to ask from (checked after the clash check): the screen used to say the email was
                    # sent anyway (CO-152).
                    return Response({'status': 'error', 'code': 'no_mailbox',
                                     'message': "This call has no campaign mailbox to email the lead from. "
                                                "Confirm the time directly instead."}, status=400)
                meeting.save()

            from ai_sdr_agent.agents.meeting_scheduling_agent import MeetingSchedulingAgent
            from ai_sdr_agent.agents.meeting_scheduling_agent import format_datetime_with_timezone
            proposed_time_str = format_datetime_with_timezone(meeting.scheduled_at, browser_tz)
            email_sent, email_error = True, ''
            try:
                MeetingSchedulingAgent(company=company_user.company).send_approval_request_email(
                    campaign, meeting.lead, meeting, proposed_time_str
                )
            except KeyServiceError:
                raise
            except Exception as exc:
                logger.warning("Approval request email failed for meeting %s: %s", meeting.id, exc)
                email_sent, email_error = False, str(exc)

            return Response({
                'status': 'success',
                'mode': 'awaiting_approval',
                'email_sent': email_sent,
                'email_error': email_error,
                'message': 'Approval email sent to lead.' if email_sent else
                           f'The time is saved, but the email to the lead failed: {email_error}',
                'data': _serialize_meeting(meeting),
            })

        else:
            # Direct confirm flow (original behaviour)
            meeting.status = 'scheduled'
            meeting.confirmed_at = timezone.now()
            with _host_booking(company_user, meeting.scheduled_at, meeting.duration_minutes, exclude_id=meeting.id):
                meeting.save()

            lead = meeting.lead
            lead.status = 'meeting_scheduled'
            lead.save(update_fields=['status'])
            _give_call_a_link(meeting)

            email_sent, email_error = False, 'This call has no campaign mailbox, so the lead was not emailed.'
            if campaign:
                try:
                    from ai_sdr_agent.agents.meeting_scheduling_agent import MeetingSchedulingAgent
                    MeetingSchedulingAgent(company=company_user.company).send_confirmation_email(campaign, lead, meeting)
                    email_sent, email_error = True, ''
                except KeyServiceError:
                    raise
                except Exception as exc:
                    logger.warning("Confirmation email failed for meeting %s: %s", meeting.id, exc)
                    email_error = f'The email to the lead failed: {exc}'

            return Response({'status': 'success', 'mode': 'confirmed', 'email_sent': email_sent,
                             'email_error': email_error, 'data': _serialize_meeting(meeting)})

    except KeyServiceError:
        raise
    except ScheduleConflict as clash:
        # The salesperson is busy then. Nothing was saved, and no email went to the lead.
        return clash.response()
    except Exception as exc:
        logger.error("Confirm meeting error: %s", exc)
        return Response({'status': 'error', 'message': str(exc)}, status=500)


# ==========================================================================
# Meeting — lead approval actions (public, token-based, no auth)
# ==========================================================================

from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods


def _booking_page_url(meeting):
    """Browser-facing /book/<token> page — the React FRONTEND_URL, not the
    Django backend. Returns '' when no frontend URL is configured (so callers
    can omit the link rather than point at a dead host)."""
    from django.conf import settings as _settings
    base = (
        getattr(_settings, 'FRONTEND_URL', None)
        or os.environ.get('FRONTEND_URL', '')
    ).rstrip('/')
    if not base:
        return ''
    return f"{base}/book/{meeting.booking_token}/"


def _approval_result_page(*, ok, title, heading, message, booking_url='', accent='#16a34a', status=200, icon=None):
    """Self-contained HTML shown to a lead after they click Yes / Suggest.

    Deliberately depends on NOTHING external (no redirect to the frontend, no
    ngrok tunnel, no CSS/JS host) so the lead always sees a clear confirmation
    even if the React app is unreachable — the previous redirect-to-SITE_URL
    approach broke exactly there. If a frontend booking URL exists we still offer
    it as an optional link.
    """
    from django.http import HttpResponse
    safe_msg = (message or '').replace('\n', '<br>')
    link_html = (
        f'<a href="{booking_url}" style="display:inline-block;margin-top:22px;padding:11px 22px;'
        f'background:{accent};color:#fff;text-decoration:none;border-radius:8px;font-weight:600;">'
        f'View meeting details</a>'
        if booking_url else ''
    )
    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title></head>
<body style="margin:0;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;background:#0f172a;color:#e2e8f0;">
  <div style="max-width:480px;margin:8vh auto;padding:40px 32px;background:#1e293b;border-radius:16px;text-align:center;box-shadow:0 10px 40px rgba(0,0,0,.4);">
    <div style="width:64px;height:64px;border-radius:50%;margin:0 auto 20px;display:flex;align-items:center;justify-content:center;background:{accent}22;font-size:32px;">
      {icon or ('✅' if ok else '📅')}
    </div>
    <h1 style="margin:0 0 12px;font-size:22px;color:#f8fafc;">{heading}</h1>
    <p style="margin:0;font-size:15px;line-height:1.6;color:#94a3b8;">{safe_msg}</p>
    {link_html}
  </div>
</body></html>"""
    return HttpResponse(html, status=status, content_type='text/html')


def _confirm_action_page(*, title, heading, message, button_label, accent='#16a34a'):
    """Tiny HTML page whose button POSTs back to the same URL.

    Email security scanners and link previewers pre-fetch GET links, so a GET
    must never change state - the lead has to press the button (a POST).
    """
    from django.http import HttpResponse
    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title></head>
<body style="margin:0;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;background:#0f172a;color:#e2e8f0;">
  <div style="max-width:480px;margin:8vh auto;padding:40px 32px;background:#1e293b;border-radius:16px;text-align:center;box-shadow:0 10px 40px rgba(0,0,0,.4);">
    <h1 style="margin:0 0 12px;font-size:22px;color:#f8fafc;">{heading}</h1>
    <p style="margin:0 0 24px;font-size:15px;line-height:1.6;color:#94a3b8;">{message}</p>
    <form method="post" action="">
      <button type="submit" style="padding:12px 26px;border:0;border-radius:8px;background:{accent};color:#fff;font-size:15px;font-weight:600;cursor:pointer;">{button_label}</button>
    </form>
  </div>
</body></html>"""
    return HttpResponse(html, content_type='text/html')


_LINK_EXPIRED_PAGE = dict(
    ok=False, accent='#dc2626',
    title='Link expired',
    heading='This link is no longer valid',
    message='The meeting link is invalid or has expired. Please reply to the original email and we will help you reschedule.',
)


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def sdr_meeting_lead_approve(request, approval_token):
    """Lead confirms the proposed meeting time.

    GET only shows a confirm button (scanners pre-fetch links, so GET must not
    change state); the POST does the work. The status change is one atomic
    UPDATE, so a double click or a scanner racing the lead confirms - and
    emails - exactly once.
    """
    try:
        meeting = SDRMeeting.objects.select_related('lead', 'enrollment__campaign').get(
            approval_token=approval_token
        )
    except SDRMeeting.DoesNotExist:
        return _approval_result_page(**_LINK_EXPIRED_PAGE)

    if request.method == 'GET':
        if meeting.status == 'scheduled':
            return _approval_result_page(
                ok=True, accent='#16a34a',
                title='Meeting confirmed',
                heading="You're all set! 🎉",
                message='This meeting is already confirmed. A confirmation email with the details is in your inbox.',
                booking_url=_booking_page_url(meeting),
            )
        return _confirm_action_page(
            title='Confirm meeting',
            heading='Confirm this meeting time?',
            message='Press the button below to confirm the proposed time.',
            button_label='Yes, confirm this time',
        )

    # POST — claim the confirmation atomically. Only a proposed slot (awaiting
    # approval, with a time set) can be confirmed; a lead who asked for another
    # time, or a meeting with no time, must not flip to "scheduled".
    # A proposed time that has passed cannot be accepted: the link never expired (CO-152).
    claimed = SDRMeeting.objects.filter(
        id=meeting.id, status='awaiting_approval', scheduled_at__gt=timezone.now(),
    ).update(status='scheduled', confirmed_at=timezone.now())

    if claimed:
        lead = meeting.lead
        lead.status = 'meeting_scheduled'
        lead.save(update_fields=['status'])
        meeting.refresh_from_db()
        _give_call_a_link(meeting)
        from ai_sdr_agent.alerts import call_booked
        call_booked(meeting, accepted=True)

        # The time is settled now; that is when the CRM hears about it.
        try:
            from crm_sync_agent.signals import log_meeting
            meeting.refresh_from_db()
            log_meeting(meeting)
        except Exception:
            logger.exception("Could not send confirmed meeting %s to the CRM", meeting.id)

        if meeting.enrollment and meeting.enrollment.campaign:
            try:
                from ai_sdr_agent.agents.meeting_scheduling_agent import MeetingSchedulingAgent
                meeting.refresh_from_db()
                MeetingSchedulingAgent(company=meeting.company_user.company).send_confirmation_email(
                    meeting.enrollment.campaign, meeting.lead, meeting
                )
            except Exception as exc:
                logger.warning("Confirmation email after approval failed for meeting %s: %s", meeting.id, exc)
        return _approval_result_page(
            ok=True, accent='#16a34a',
            title='Meeting confirmed',
            heading="You're all set! 🎉",
            message=(
                'Your meeting time is confirmed. A confirmation email with the '
                'details is on its way to your inbox.'
            ),
            booking_url=_booking_page_url(meeting),
        )

    meeting.refresh_from_db()
    if meeting.status == 'scheduled':
        return _approval_result_page(
            ok=True, accent='#16a34a',
            title='Meeting confirmed',
            heading="You're all set! 🎉",
            message='This meeting is already confirmed. A confirmation email with the details is in your inbox.',
            booking_url=_booking_page_url(meeting),
        )
    if meeting.status == 'awaiting_approval' and meeting.scheduled_at and meeting.scheduled_at <= timezone.now():
        return _approval_result_page(
            ok=True, accent='#7c3aed',
            title='This time has passed',
            heading='The proposed time has already passed',
            message='Please pick another time that suits you.',
            booking_url=_booking_page_url(meeting),
        )
    return _approval_result_page(
        ok=True, accent='#7c3aed',
        title='Time no longer proposed',
        heading='This time is no longer available to confirm',
        message='No time is currently proposed for this meeting. Please reply to the original email and we will find a time that works.',
        booking_url=_booking_page_url(meeting),
    )


_UNSUBSCRIBE_NOT_DONE = dict(
    ok=False, accent='#dc2626',
    title='Not unsubscribed', icon='✉️',
    heading='We could not unsubscribe you from this link',
    message='This link is not valid any more, so nothing has been changed. Please reply to the email you '
            'received with the word "unsubscribe" and you will be taken off the list.',
)


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def sdr_unsubscribe(request, token):
    """Public unsubscribe link put in every outbound campaign email.

    GET shows a confirm button; POST unsubscribes. POST is also what mail clients
    send for one-click unsubscribe (RFC 8058 List-Unsubscribe-Post), so both the
    header and the visible link work. The address is opted out of every
    campaign in the company, not just the one that emailed it.
    """
    from ai_sdr_agent.agents.outreach_agent import (
        apply_unsubscribe, read_unsubscribe_token, unsubscribe_address, unsubscribe_target)

    # A link that cannot be honoured must say so, in words about unsubscribing,
    # and must not answer 200: mail programs take 200 from the one-click
    # unsubscribe to mean "done". It used to show the "meeting link expired" page.
    claims = read_unsubscribe_token(token)
    if claims is None:
        return _approval_result_page(status=404, **_UNSUBSCRIBE_NOT_DONE)
    target = unsubscribe_target(claims)
    if target is None or not target[1]:
        return _approval_result_page(status=410, **_UNSUBSCRIBE_NOT_DONE)
    company_id, email_addr, enrollment = target

    if request.method == 'GET':
        return _confirm_action_page(
            title='Unsubscribe',
            heading='Unsubscribe from these emails?',
            message='You will no longer receive emails from us.',
            button_label='Unsubscribe',
            accent='#dc2626',
        )

    if enrollment is not None:
        apply_unsubscribe(enrollment)
    else:
        # The campaign was deleted or its leads cleared since this email went out.
        unsubscribe_address(company_id, email_addr)
    logger.info("SDR [UNSUBSCRIBE] company=%s enrollment=%s lead=%s", company_id, claims.get('e'), email_addr)
    return _approval_result_page(
        ok=True, accent='#16a34a',
        title='Unsubscribed',
        heading="You've been unsubscribed",
        message="You won't receive any more emails from us.",
    )


@csrf_exempt
@require_GET
def sdr_meeting_lead_suggest(request, approval_token):
    """Lead clicks 'Suggest another time'. Records that they declined the
    proposed slot and points them at the booking page to pick another (with a
    graceful self-contained fallback when no frontend URL is set)."""
    try:
        meeting = SDRMeeting.objects.get(approval_token=approval_token)
    except SDRMeeting.DoesNotExist:
        return _approval_result_page(
            ok=False, accent='#dc2626',
            title='Link expired',
            heading='This link is no longer valid',
            message='The meeting link is invalid or has expired. Please reply to the original email and we will help you reschedule.',
        )

    # GET must not change state: email scanners pre-fetch links, and downgrading
    # the meeting here would make the "Yes" link stop working. The booking page
    # accepts both pending and awaiting_approval, so nothing needs updating.
    booking_url = _booking_page_url(meeting)
    if booking_url:
        from django.http import HttpResponseRedirect
        return HttpResponseRedirect(booking_url)

    # No frontend configured — show a clear message instead of a broken redirect.
    return _approval_result_page(
        ok=True, accent='#7c3aed',
        title='Let’s find another time',
        heading='No problem — let’s reschedule',
        message='Thanks for letting us know. Please reply to the original email with a few times that work for you, and we’ll get it set up.',
    )


# ==========================================================================
# Meeting — send reminder email
# ==========================================================================

@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def sdr_send_meeting_reminder(request, meeting_id):
    """Manually send (or resend) a 24-hour reminder email to the lead."""
    company_user = request.user
    try:
        meeting = SDRMeeting.objects.select_related('lead', 'enrollment__campaign').get(
            id=meeting_id, company_user=company_user
        )
    except SDRMeeting.DoesNotExist:
        return Response({'status': 'error', 'message': 'Meeting not found.'}, status=404)

    if not meeting.enrollment or not meeting.enrollment.campaign:
        return Response({'status': 'error', 'message': 'Meeting has no associated campaign/SMTP.'}, status=400)

    campaign = meeting.enrollment.campaign
    try:
        from ai_sdr_agent.agents.meeting_scheduling_agent import MeetingSchedulingAgent
        MeetingSchedulingAgent(company=company_user.company).send_reminder_email(campaign, meeting.lead, meeting)
        meeting.reminder_sent_at = timezone.now()
        meeting.save(update_fields=['reminder_sent_at'])
        return Response({'status': 'success', 'message': 'Reminder sent.', 'data': _serialize_meeting(meeting)})
    except KeyServiceError:
        raise
    except Exception as exc:
        logger.error("Send reminder error for meeting %s: %s", meeting.id, exc)
        return Response({'status': 'error', 'message': str(exc)}, status=500)


# ==========================================================================
# Meeting — generate / refresh AI prep notes
# ==========================================================================

@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def sdr_generate_meeting_prep(request, meeting_id):
    """Generate (or regenerate) AI prep notes for a meeting."""
    company_user = request.user
    try:
        meeting = SDRMeeting.objects.select_related('lead', 'enrollment__campaign').get(
            id=meeting_id, company_user=company_user
        )
    except SDRMeeting.DoesNotExist:
        return Response({'status': 'error', 'message': 'Meeting not found.'}, status=404)

    try:
        from ai_sdr_agent.agents.meeting_scheduling_agent import MeetingSchedulingAgent
        prep_notes = MeetingSchedulingAgent(company=company_user.company).generate_prep_notes(
            meeting.lead,
            meeting.enrollment,
            meeting.reply_snippet or '',
        )
        meeting.prep_notes = prep_notes
        meeting.save(update_fields=['prep_notes'])
        return Response({'status': 'success', 'prep_notes': prep_notes, 'data': _serialize_meeting(meeting)})
    except KeyServiceError:
        raise
    except Exception as exc:
        logger.error("Generate prep notes error for meeting %s: %s", meeting.id, exc)
        return Response({'status': 'error', 'message': str(exc)}, status=500)


# ==========================================================================
# Meeting — resend scheduling email
# ==========================================================================

@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def sdr_resend_scheduling_email(request, meeting_id):
    """Resend the initial scheduling email (with calendar link) to the lead."""
    company_user = request.user
    try:
        meeting = SDRMeeting.objects.select_related('lead', 'enrollment__campaign').get(
            id=meeting_id, company_user=company_user
        )
    except SDRMeeting.DoesNotExist:
        return Response({'status': 'error', 'message': 'Meeting not found.'}, status=404)

    if not meeting.enrollment or not meeting.enrollment.campaign:
        return Response({'status': 'error', 'message': 'Meeting has no associated campaign/SMTP.'}, status=400)

    campaign = meeting.enrollment.campaign
    try:
        from ai_sdr_agent.agents.meeting_scheduling_agent import MeetingSchedulingAgent
        MeetingSchedulingAgent(company=company_user.company).send_scheduling_email(
            campaign, meeting.lead, meeting, meeting.prep_notes or None
        )
        meeting.scheduling_email_sent_at = timezone.now()
        meeting.save(update_fields=['scheduling_email_sent_at'])
        return Response({'status': 'success', 'message': 'Scheduling email resent.', 'data': _serialize_meeting(meeting)})
    except KeyServiceError:
        raise
    except Exception as exc:
        logger.error("Resend scheduling email error for meeting %s: %s", meeting.id, exc)
        return Response({'status': 'error', 'message': str(exc)}, status=500)


# ==========================================================================
# Check all active campaigns for replies — triggered on Meetings tab load
# ==========================================================================

@api_view(['POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def sdr_check_all_replies(request):
    """
    Poll IMAP for replies across ALL active campaigns for this user.
    Called automatically when the Meetings tab opens — gives real-time reply detection
    without waiting for the background scheduler.
    """
    company_user = request.user
    from ai_sdr_agent.tasks import campaigns_to_read_replies
    campaigns = campaigns_to_read_replies(company_user=company_user)       # finished ones too (CO-143)

    from ai_sdr_agent.agents.email_assistant_agent import EmailAssistantAgent
    from ai_sdr_agent.agents.outreach_agent import OutreachAgent

    outreach_agent = OutreachAgent(company=company_user.company)
    email_agent = EmailAssistantAgent(company=company_user.company)
    total_new_replies = 0
    total_new_meetings = 0
    errors = []

    for campaign in campaigns:
        try:
            enrollments = list(
                campaign.enrollments
                .filter(status__in=['active', 'paused', 'completed', 'replied'])
                .exclude(lead__email='')
                .select_related('lead')
                .prefetch_related('logs')
            )
            if not enrollments:
                continue

            replies = read_inbox(campaign, enrollments, outreach_agent)
            if replies is None:
                # The button said "Check Replies complete" over an inbox it could not read (CO-197).
                errors.append(f'{campaign.name}: {campaign.inbox_error}')
                continue

            for r in replies:
                result = handle_inbox_reply(campaign, r, email_agent=email_agent, outreach_agent=outreach_agent)
                if not result or result['action'] == 'bounced':
                    continue
                if result['action'] not in ('wait',):
                    total_new_replies += 1
                if result.get('meeting_created'):
                    total_new_meetings += 1
                logger.info('SDR [check-all-replies] campaign=%d lead=%s → %s', campaign.id,
                            r['enrollment'].lead.display_name, result['action'])

            campaign.last_replies_checked_at = timezone.now()
            campaign.save(update_fields=['replies_received', 'meetings_booked', 'last_replies_checked_at'])

        except KeyServiceError:
            raise
        except Exception as exc:
            logger.error("check-all-replies failed for campaign %s: %s", campaign.id, exc)
            errors.append(str(exc))

    return Response({
        'status': 'success',
        'campaigns_checked': campaigns.count(),
        'new_replies': total_new_replies,
        'new_meetings': total_new_meetings,
        'errors': errors,
    })


# ==========================================================================
# ==========================================================================
# Google Calendar OAuth — one-time setup to get refresh_token
# ==========================================================================

@api_view(['GET'])
@authentication_classes([])
@permission_classes([])
def sdr_google_auth_start(request):
    """Redirect company owner to Google OAuth consent page (no PKCE).

    One-time developer setup helper: disabled unless DEBUG. It is unauthenticated
    and the callback hands back a refresh token, so it must not exist in production
    (companies connect Google Calendar through their own settings instead).
    """
    if not settings.DEBUG:
        return Response({'error': 'Not found.'}, status=404)
    import urllib.parse
    client_id = settings.GOOGLE_CLIENT_ID
    if not client_id or not settings.GOOGLE_CLIENT_SECRET:
        return Response({'error': 'GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET not set in .env'}, status=400)

    redirect_uri = request.build_absolute_uri('/api/sdr/google-auth/callback/')
    params = {
        'client_id': client_id,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': 'https://www.googleapis.com/auth/calendar',
        'access_type': 'offline',
        'prompt': 'consent',
    }
    auth_url = 'https://accounts.google.com/o/oauth2/auth?' + urllib.parse.urlencode(params)
    from django.shortcuts import redirect as django_redirect
    return django_redirect(auth_url)


@api_view(['GET'])
@authentication_classes([])
@permission_classes([])
def sdr_google_auth_callback(request):
    """Exchange auth code for tokens and display refresh_token (DEBUG only)."""
    if not settings.DEBUG:
        return Response({'error': 'Not found.'}, status=404)
    import requests as _requests
    client_id     = settings.GOOGLE_CLIENT_ID
    client_secret = settings.GOOGLE_CLIENT_SECRET
    redirect_uri  = request.build_absolute_uri('/api/sdr/google-auth/callback/')
    code = request.GET.get('code')

    if not code:
        return Response({'error': 'No code in callback', 'params': dict(request.GET)}, status=400)

    resp = _requests.post('https://oauth2.googleapis.com/token', data={
        'code': code,
        'client_id': client_id,
        'client_secret': client_secret,
        'redirect_uri': redirect_uri,
        'grant_type': 'authorization_code',
    })
    token = resp.json()
    refresh_token = token.get('refresh_token')
    if not refresh_token:
        return Response({'error': 'No refresh_token returned', 'response': token}, status=400)

    logger.info("Google OAuth refresh_token obtained (not logged).")
    return Response({
        'message': 'Success! Copy this refresh_token into your .env as GOOGLE_REFRESH_TOKEN',
        'refresh_token': refresh_token,
    })


def _company_for_meeting(meeting):
    """Resolve the Company that owns this SDR meeting, so we use its connected
    Google Calendar."""
    try:
        cu = getattr(meeting, 'company_user', None)
        if cu and getattr(cu, 'company', None):
            return cu.company
    except Exception:
        pass
    try:
        lead = getattr(meeting, 'lead', None)
        lead_cu = getattr(lead, 'company_user', None) if lead else None
        if lead_cu and getattr(lead_cu, 'company', None):
            return lead_cu.company
    except Exception:
        pass
    return None


def _create_google_meet_link(meeting, scheduled_at, duration_minutes=30):
    """Create a Google Meet link on the meeting's *company's* connected calendar.

    Uses the shared per-company helper (Company.google_calendar_config), the same
    connection recruitment uses — so a company that connected Google once gets
    Meet links for SDR meetings too. Returns None when not connected, and the
    caller falls back to Jitsi.

    The event's id, and the time it stands at, are set on `meeting` for the
    caller to save: they are what lets the event follow the call when it moves
    or is called off (core/google_events.py).
    """
    from core.google_calendar import create_google_event, event_state
    company = _company_for_meeting(meeting)
    created = create_google_event(
        company,
        start_dt=scheduled_at,
        duration_minutes=duration_minutes,
        summary=meeting.title or 'Meeting',
        description=(f"Meeting with {meeting.lead.display_name}" if getattr(meeting, 'lead', None) else ''),
        attendee_email=(meeting.lead.email if getattr(meeting, 'lead', None) and meeting.lead.email else ''),
    )
    if not created:
        return None
    if created['event_id']:
        meeting.google_event_id = created['event_id']
        meeting.google_event_state = event_state(scheduled_at, duration_minutes)
    return created['meet_url'] or None


# ==========================================================================
# SDR Agent Settings — per-company-user API keys (Apollo, Apify, etc.)
# ==========================================================================

@api_view(['GET', 'POST'])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def sdr_agent_settings(request):
    """
    GET  — return current settings (keys are masked for display).
    POST — save/update one or more keys. Send only the fields you want to change.
           Pass an empty string "" to clear a key.
    """
    company_user = request.user
    sdr_settings, _ = SDRAgentSettings.objects.get_or_create(company_user=company_user)

    if request.method == 'GET':
        return Response({
            # Masked: the raw secrets never leave the server once saved.
            'apollo_api_key': _mask_key(sdr_settings.apollo_api_key or ''),
            'apollo_api_key_set': bool(sdr_settings.apollo_api_key),
            'apify_api_token': _mask_key(sdr_settings.apify_api_token or ''),
            'apify_api_token_set': bool(sdr_settings.apify_api_token),
            'apify_actor_id': sdr_settings.apify_actor_id or '',
            'apify_actor_url': apify_actor_page_url(sdr_settings.apify_actor_id) if sdr_settings.apify_actor_id else '',
            'updated_at': sdr_settings.updated_at.isoformat() if sdr_settings.updated_at else None,
        })

    # POST — update only the fields that were sent
    data = request.data
    changed = False

    if 'apollo_api_key' in data:
        sdr_settings.apollo_api_key = (data['apollo_api_key'] or '').strip()
        changed = True

    if 'apify_api_token' in data:
        sdr_settings.apify_api_token = (data['apify_api_token'] or '').strip()
        changed = True

    if 'apify_actor_id' in data:
        sdr_settings.apify_actor_id = (data['apify_actor_id'] or '').strip()
        changed = True

    if changed:
        sdr_settings.save()

    return Response({
        'status': 'saved',
        'apollo_api_key_set': bool(sdr_settings.apollo_api_key),
        'apify_api_token_set': bool(sdr_settings.apify_api_token),
        'apify_actor_id': sdr_settings.apify_actor_id or '',
    })


# ==========================================================================
# Public booking endpoints — no auth required (token in URL acts as auth)
# ==========================================================================

@api_view(['GET'])
@authentication_classes([])
@permission_classes([])
def sdr_booking_info(request, token):
    """Return public meeting info for the lead's booking page (no auth)."""
    from ai_sdr_agent.models import SDRMeeting
    try:
        meeting = SDRMeeting.objects.select_related('lead', 'enrollment__campaign').get(
            booking_token=token
        )
    except SDRMeeting.DoesNotExist:
        return Response({'error': 'Booking link not found.'}, status=404)

    campaign = meeting.enrollment.campaign if meeting.enrollment_id and meeting.enrollment else None

    # A meeting that is no longer awaiting a slot is CONFIRMED, not an error.
    # Return its details with already_booked=True so the booking page can show
    # the confirmed state (this is what "View meeting details" from the approval
    # email lands on). Returning a 400 here made a successfully-confirmed meeting
    # render as "Link unavailable".
    already_booked = meeting.status not in ('pending', 'awaiting_approval')
    tz_name, slots = _free_booking_times(meeting) if not already_booked else ('UTC', [])

    return Response({
        'title': meeting.title,
        'duration_minutes': meeting.duration_minutes or 30,
        'lead_name': meeting.lead.display_name,
        'lead_first_name': meeting.lead.first_name or (meeting.lead.display_name.split()[0] if meeting.lead.display_name else ''),
        'sender_name': campaign.sender_name if campaign else '',
        'sender_title': campaign.sender_title if campaign else '',
        'sender_company': campaign.sender_company if campaign else '',
        'status': meeting.status,
        'already_booked': already_booked,
        'scheduled_at': meeting.scheduled_at.isoformat() if meeting.scheduled_at else None,
        'meet_link': meeting.calendar_link if is_video_link(meeting.calendar_link) else '',
        # The times the salesperson is free, in the company's working hours. The page offered every half hour from
        # 08:00 to 18:00 of the lead's own day, any day, and refused times afterwards (CO-201).
        'free_slots': [slot.isoformat() for slot in slots],
        'company_timezone': tz_name,
    })


BOOKING_MAX_DAYS_AHEAD = 180   # how far in the future a lead may book
BOOKING_DAYS_SHOWN = 14
WORK_HOURS = (9, 18)           # the sales agent has no working-hours setting: weekdays, company time


def _in_work_hours(when, tz_name):
    from core.scheduling.conflicts import zone_info
    local = when.astimezone(zone_info(tz_name))
    return local.weekday() < 5 and WORK_HOURS[0] <= local.hour and (local.hour, local.minute) < (WORK_HOURS[1], 0)


def _free_booking_times(meeting):
    """(company time zone, start times) a lead may book: weekdays in working hours over the next two weeks,
    at least an hour ahead, minus the salesperson's busy time and their other booked or proposed calls."""
    from datetime import datetime, time as dtime
    from core.scheduling import busy_intervals, login_user_id_for_company_user, overlaps, zone_name
    from core.scheduling.conflicts import zone_info
    from core.scheduling.sources import SOURCES
    tz_name = zone_name(meeting.company_user.company.timezone_name)
    zone = zone_info(tz_name)
    duration = timedelta(minutes=meeting.duration_minutes or 30)
    now = timezone.now()
    until = now + timedelta(days=BOOKING_DAYS_SHOWN)
    host = login_user_id_for_company_user(meeting.company_user)
    busy = busy_intervals([host], now, until, exclude=[('sdr', meeting.id)], tz_name=tz_name) if host else []
    for other in SDRMeeting.objects.filter(company_user=meeting.company_user, status__in=SOURCES['sdr'].BOOKED,
                                           scheduled_at__gte=now - timedelta(hours=8),
                                           scheduled_at__lt=until).exclude(id=meeting.id):
        busy.append((other.scheduled_at, other.scheduled_at + timedelta(minutes=other.duration_minutes or 30)))
    slots, first_day = [], now.astimezone(zone).date()
    for offset in range(BOOKING_DAYS_SHOWN + 1):
        day = first_day + timedelta(days=offset)
        if day.weekday() >= 5:
            continue
        cursor = datetime.combine(day, dtime(WORK_HOURS[0]), tzinfo=zone)
        day_end = datetime.combine(day, dtime(WORK_HOURS[1]), tzinfo=zone)
        while cursor + duration <= day_end:
            if cursor >= now + timedelta(hours=1) and not overlaps(busy, cursor, cursor + duration):
                slots.append(cursor)
            cursor += timedelta(minutes=30)
    return tz_name, slots


VIDEO_LINK_STARTS = ('https://meet.jit.si/', 'https://meet.google.com/')


def is_video_link(url):
    """A call's own room, not the campaign's scheduling page (Calendly and the like)."""
    return (url or '').startswith(VIDEO_LINK_STARTS)


def _give_call_a_link(meeting):
    """The video link, and the Google event when Google is connected, for a call that has just become scheduled.

    Only the public booking page made them. 'Set Time & Confirm' and the lead's 'Yes, this works' link sent a
    confirmation showing the campaign's scheduling page as 'Join Meeting', or nothing (CO-150)."""
    from core.google_events import follow_meeting
    room_slug = str(meeting.booking_token).replace('-', '')[:16]
    meet_link = meeting.calendar_link if is_video_link(meeting.calendar_link) else f"https://meet.jit.si/SDR-{room_slug}"
    if meeting.google_event_id:
        # Booked before, then reopened: move that event; a second one would stay in the calendar for good.
        follow_meeting(meeting)
        if is_video_link(meeting.calendar_link):
            meet_link = meeting.calendar_link
    else:
        try:
            google_link = _create_google_meet_link(meeting, meeting.scheduled_at, meeting.duration_minutes or 30)
        except KeyServiceError:
            raise
        except Exception as exc:
            logger.warning("Google Meet creation failed for meeting %s: %s", meeting.id, exc)
            google_link = None
        if google_link:
            meet_link = google_link
    SDRMeeting.objects.filter(id=meeting.id).update(
        calendar_link=meet_link, google_event_id=meeting.google_event_id,
        google_event_state=meeting.google_event_state)
    meeting.calendar_link = meet_link
    return meet_link


@api_view(['POST'])
@authentication_classes([])
@permission_classes([])
def sdr_booking_confirm(request, token):
    """Lead submits their chosen time. Sets scheduled_at, marks meeting scheduled."""
    from ai_sdr_agent.models import SDRMeeting
    try:
        meeting = SDRMeeting.objects.select_related(
            'lead', 'enrollment__campaign'
        ).get(booking_token=token)
    except SDRMeeting.DoesNotExist:
        return Response({'error': 'Booking link not found.'}, status=404)

    if meeting.status not in ('pending', 'awaiting_approval'):
        return Response({
            'error': 'already_booked',
            'message': 'This time slot has already been booked.',
            'scheduled_at': meeting.scheduled_at.isoformat() if meeting.scheduled_at else None,
        }, status=400)

    scheduled_at_raw = request.data.get('scheduled_at')
    if not scheduled_at_raw:
        return Response({'error': 'scheduled_at is required.'}, status=400)

    from django.utils.dateparse import parse_datetime
    import dateutil.parser
    try:
        scheduled_at = dateutil.parser.isoparse(scheduled_at_raw)
        # Ensure timezone-aware
        from django.utils import timezone as _tz
        if scheduled_at.tzinfo is None:
            scheduled_at = _tz.make_aware(scheduled_at)
    except KeyServiceError:
        raise
    except Exception:
        return Response({'error': 'Invalid date format. Use ISO 8601.'}, status=400)

    if scheduled_at <= timezone.now():
        return Response({'error': 'Please select a future date and time.'}, status=400)
    if scheduled_at > timezone.now() + timedelta(days=BOOKING_MAX_DAYS_AHEAD):
        return Response({
            'error': f'Please pick a time within the next {BOOKING_MAX_DAYS_AHEAD} days.',
        }, status=400)
    from core.scheduling import zone_name
    if not _in_work_hours(scheduled_at, zone_name(meeting.company_user.company.timezone_name)):
        return Response({'error': 'outside_hours', 'message': 'Please pick one of the times shown.'}, status=400)

    duration_minutes = meeting.duration_minutes or 30

    # The host can't be in two places at once: refuse a slot that overlaps another
    # scheduled meeting of the same account.
    slot_end = scheduled_at + timedelta(minutes=duration_minutes)
    # A time offered to another lead and awaiting their answer is taken too, as on the shared calendar (CO-151).
    from core.scheduling.sources import SOURCES
    for other in SDRMeeting.objects.filter(
        company_user_id=meeting.company_user_id, status__in=SOURCES['sdr'].BOOKED,
        scheduled_at__gt=scheduled_at - timedelta(hours=8), scheduled_at__lt=slot_end,
    ).exclude(id=meeting.id):
        other_end = other.scheduled_at + timedelta(minutes=other.duration_minutes or 30)
        if other.scheduled_at < slot_end and other_end > scheduled_at:
            return Response({
                'error': 'slot_unavailable',
                'message': 'That time is no longer available. Please pick another slot.',
            }, status=409)

    # Claim the slot atomically FIRST - prevents double-booking if the page is
    # submitted twice, and means a Google Meet event is only created for the one
    # request that actually wins (no orphan events / invites). Jitsi is the
    # fallback link until/unless a Meet link can be created.
    room_slug = str(meeting.booking_token).replace('-', '')[:16]
    meet_link = f"https://meet.jit.si/SDR-{room_slug}"
    try:
        # The salesperson must be free then on the shared calendar too: not on leave, not in an
        # interview or another agent's meeting, not on a company holiday. The lead is told only that
        # the time is not available, never who is busy or why.
        with _host_booking(meeting.company_user, scheduled_at, duration_minutes, exclude_id=meeting.id, public=True):
            rows = SDRMeeting.objects.filter(id=meeting.id, status__in=['pending', 'awaiting_approval']).update(
                status='scheduled',
                scheduled_at=scheduled_at,
                confirmed_at=timezone.now(),
                calendar_link=meet_link,
                reminder_sent_at=None,              # a new time is reminded again (CO-200)
            )
            if rows:
                # .update() sends no signal, so the calendar is told here. Left to the nightly
                # rebuild, the hour would stay bookable by every other agent until then.
                from core.scheduling.sync import safe_sync_id
                safe_sync_id('sdr', meeting.id)
    except ScheduleConflict:
        return Response({
            'error': 'slot_unavailable',
            'message': 'That time is no longer available. Please pick another slot.',
        }, status=409)
    if rows == 0:
        return Response({
            'error': 'already_booked',
            'message': 'This meeting was just booked by another request.',
        }, status=400)

    meeting.status = 'scheduled'
    meeting.scheduled_at = scheduled_at
    meeting.confirmed_at = timezone.now()
    # The row says the Jitsi room now; in memory it still has what it had, which keeps a reopened call's Meet link.
    meet_link = _give_call_a_link(meeting)

    lead = meeting.lead
    lead.status = 'meeting_scheduled'
    lead.save(update_fields=['status'])

    # Send confirmation email (calendar_link is already included in the email body)
    campaign = meeting.enrollment.campaign if meeting.enrollment_id and meeting.enrollment else None
    if campaign:
        try:
            from ai_sdr_agent.agents.meeting_scheduling_agent import MeetingSchedulingAgent
            MeetingSchedulingAgent(company=None).send_confirmation_email(campaign, meeting.lead, meeting)
        except KeyServiceError:
            raise
        except Exception as exc:
            logger.warning("Confirmation email failed for meeting %s: %s", meeting.id, exc)

    from ai_sdr_agent.alerts import call_booked
    call_booked(meeting)
    logger.info(
        "SDR [booking] meeting=%d lead=%s scheduled_at=%s meet_link=%s — CONFIRMED via booking page",
        meeting.id, meeting.lead.display_name, scheduled_at.isoformat(), meet_link,
    )

    return Response({
        'status': 'confirmed',
        'title': meeting.title,
        'scheduled_at': scheduled_at.isoformat(),
        'duration_minutes': meeting.duration_minutes or 30,
        'lead_name': meeting.lead.display_name,
        'sender_name': campaign.sender_name if campaign else '',
        'meet_link': meet_link,
    })