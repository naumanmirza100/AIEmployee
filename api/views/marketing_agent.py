"""
Marketing Agent API Views for Company Users
Similar structure to recruitment_agent.py
"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db.models import Q, Count, Sum, Avg
from django.contrib.auth.models import User
from django.http import HttpResponse
from datetime import timedelta, datetime
import json
import logging
import csv
import smtplib
import socket

from api.authentication import CompanyUserTokenAuthentication
from api.permissions import IsCompanyUserOnly
from marketing_agent.models import (
    Campaign, Lead, EmailTemplate, EmailSequence, EmailSequenceStep,
    EmailSendHistory, EmailAccount, CampaignContact, MarketingNotification,
    MarketResearch, MarketingDocument, Reply,
)
from marketing_agent.services.email_service import EmailService
from project_manager_agent.ai_agents.agents_registry import AgentRegistry

logger = logging.getLogger(__name__)


def _get_or_create_user_for_company_user(company_user):
    """
    Get or create a Django User for a CompanyUser.
    This is needed because marketing models use User, not CompanyUser.
    """
    try:
        # Try to find existing user with matching email
        user = User.objects.get(email=company_user.email)
        return user
    except User.DoesNotExist:
        # Create a new User for this company user
        username = f"company_user_{company_user.id}_{company_user.email}"
        user = User.objects.create_user(
            username=username,
            email=company_user.email,
            password=None,  # Password not used for company users
            first_name=company_user.full_name.split()[0] if company_user.full_name else '',
            last_name=' '.join(company_user.full_name.split()[1:]) if company_user.full_name and len(company_user.full_name.split()) > 1 else ''
        )
        return user


@api_view(["GET"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def marketing_dashboard(request):
    """
    Marketing Agent Dashboard - Returns overview stats for company user
    """
    try:
        company_user = request.user
        user = _get_or_create_user_for_company_user(company_user)
        
        # Auto-pause expired campaigns
        from marketing_agent.views import auto_pause_expired_campaigns
        auto_pause_expired_campaigns(user=user)
        
        # Get user's marketing data
        campaigns = Campaign.objects.filter(owner=user)
        recent_research = MarketResearch.objects.filter(created_by=user).order_by('-created_at')[:5]
        
        # Get campaign stats
        active_campaigns = campaigns.filter(status='active').count()
        recent_campaigns = campaigns.order_by('-created_at')[:10]
        
        return Response({
            'status': 'success',
            'data': {
                'stats': {
                    'total_campaigns': campaigns.count(),
                    'active_campaigns': active_campaigns,
                    'paused_campaigns': campaigns.filter(status='paused').count(),
                    'completed_campaigns': campaigns.filter(status='completed').count(),
                },
                'recent_campaigns': [
                    {
                        'id': c.id,
                        'name': c.name,
                        'description': c.description or '',
                        'status': c.status,
                        'campaign_type': c.campaign_type or 'email',
                        'start_date': c.start_date.isoformat() if c.start_date else None,
                        'end_date': c.end_date.isoformat() if c.end_date else None,
                        'created_at': c.created_at.isoformat(),
                    }
                    for c in recent_campaigns
                ],
                'recent_research': [
                    {
                        'id': r.id,
                        'topic': r.topic,
                        'research_type': r.research_type,
                        'created_at': r.created_at.isoformat(),
                    }
                    for r in recent_research
                ]
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.exception("marketing_dashboard failed")
        return Response(
            {'status': 'error', 'message': 'Failed to load marketing dashboard', 'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["GET"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def list_campaigns(request):
    """List all campaigns for company user"""
    try:
        company_user = request.user
        user = _get_or_create_user_for_company_user(company_user)
        
        campaigns = Campaign.objects.filter(owner=user).order_by('-created_at')
        
        # Optional filters
        status_filter = request.GET.get('status')
        if status_filter:
            campaigns = campaigns.filter(status=status_filter)
        
        # Pagination
        page = int(request.GET.get('page', 1))
        limit = int(request.GET.get('limit', 20))
        offset = (page - 1) * limit
        
        total = campaigns.count()
        campaigns_page = campaigns[offset:offset + limit]
        
        return Response({
            'status': 'success',
            'data': {
                'campaigns': [
                    {
                        'id': c.id,
                        'name': c.name,
                        'description': c.description,
                        'status': c.status,
                        'campaign_type': c.campaign_type,
                        'start_date': c.start_date.isoformat() if c.start_date else None,
                        'end_date': c.end_date.isoformat() if c.end_date else None,
                        'target_leads': c.target_leads,
                        'target_conversions': c.target_conversions,
                        'created_at': c.created_at.isoformat(),
                        'updated_at': c.updated_at.isoformat(),
                    }
                    for c in campaigns_page
                ],
                'total': total,
                'page': page,
                'limit': limit,
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.exception("list_campaigns failed")
        return Response(
            {'status': 'error', 'message': 'Failed to list campaigns', 'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


def _build_campaign_detail(campaign, user):
    """Build full campaign detail: email_stats, analytics, chart_data, email_sends, leads.

    Open/click rate:
    - total_sent: emails with status in sent, delivered, opened, clicked.
    - total_opened: emails with status opened or clicked (tracking pixel load or reply implies open).
    - total_clicked: emails with status clicked (tracked link click).
    - open_rate = (total_opened / total_sent) * 100
    - click_rate = (total_clicked / total_sent) * 100
    When a lead replies, the triggering_email is marked as opened (see Reply post_save signal).
    """
    leads = campaign.leads.all().order_by('-created_at')[:200]
    all_email_sends = EmailSendHistory.objects.filter(campaign=campaign)
    total_sent = all_email_sends.filter(status__in=['sent', 'delivered', 'opened', 'clicked']).count()
    total_opened = all_email_sends.filter(status__in=['opened', 'clicked']).count()
    total_clicked = all_email_sends.filter(status='clicked').count()
    # Use Reply model so total matches Email Sending page (count of reply events, not unique contacts)
    total_replied = Reply.objects.filter(campaign=campaign).count()
    total_failed = all_email_sends.filter(status='failed').count()
    total_bounced = all_email_sends.filter(status='bounced').count()
    # Positive = interested, requested_info, neutral, objection (show as Positive/Neutral on dashboard)
    positive_replies = Reply.objects.filter(
        campaign=campaign,
        interest_level__in=['positive', 'neutral', 'requested_info', 'objection']
    ).count()
    # Negative = not interested + unsubscribe
    negative_replies = Reply.objects.filter(
        campaign=campaign,
        interest_level__in=['negative', 'unsubscribe']
    ).count()
    open_rate = (total_opened / total_sent * 100) if total_sent > 0 else 0
    click_rate = (total_clicked / total_sent * 100) if total_sent > 0 else 0
    reply_rate = (total_replied / total_sent * 100) if total_sent > 0 else 0
    click_through_rate = (total_clicked / total_opened * 100) if total_opened > 0 else 0
    # Leads engagement: % of leads (who were sent at least one email) who opened, clicked, or replied
    leads_sent_to = all_email_sends.values_list('lead_id', flat=True).distinct().count()
    lead_ids_opened_clicked = set(
        all_email_sends.filter(status__in=['opened', 'clicked']).values_list('lead_id', flat=True).distinct()
    )
    lead_ids_replied = set(Reply.objects.filter(campaign=campaign).values_list('lead_id', flat=True).distinct())
    engaged_lead_ids = lead_ids_opened_clicked | lead_ids_replied
    leads_engagement_rate = (len(engaged_lead_ids) / leads_sent_to * 100) if leads_sent_to > 0 else 0
    engagement = round(leads_engagement_rate, 2)
    target_leads = campaign.target_leads
    target_conversions = campaign.target_conversions
    leads_count = campaign.leads.count()
    leads_progress = (leads_count / target_leads * 100) if target_leads and target_leads > 0 else None
    # Conversion = positive replies (interested, requested_info, etc.), not clicks
    total_conversions = positive_replies
    conversion_progress = (total_conversions / target_conversions * 100) if target_conversions and target_conversions > 0 else None

    analytics = {
        'open_rate_percent': round(open_rate, 2),
        'click_rate_percent': round(click_rate, 2),
        'reply_rate': round(reply_rate, 2),
        'click_through_rate': round(click_through_rate, 2),
        'engagement': round(engagement, 2),
        'target_leads': target_leads,
        'target_conversions': target_conversions,
        'leads_progress': round(leads_progress, 1) if leads_progress is not None else None,
        'conversion_progress': round(conversion_progress, 1) if conversion_progress is not None else None,
    }

    email_stats = {
        'total_sent': total_sent,
        'total_opened': total_opened,
        'total_clicked': total_clicked,
        'total_replied': total_replied,
        'positive_replies': positive_replies,
        'negative_replies': negative_replies,
        'total_leads': leads_count,
        'total_failed': total_failed,
        'total_bounced': total_bounced,
        'engaged_leads_count': len(engaged_lead_ids),
        'leads_sent_to': leads_sent_to,
    }

    # Chart data (last 30 days)
    thirty_days_ago = timezone.now() - timedelta(days=30)
    recent_email_sends = all_email_sends.filter(
        Q(sent_at__gte=thirty_days_ago) | Q(created_at__gte=thirty_days_ago, sent_at__isnull=True)
    )
    metrics_by_date = {}
    for i in range(30):
        date_obj = (timezone.now().date() - timedelta(days=i))
        date_str = date_obj.strftime('%Y-%m-%d')
        metrics_by_date[date_str] = {'sent': 0, 'opened': 0, 'clicked': 0, 'replied': 0}
    for email_send in recent_email_sends:
        email_date = email_send.sent_at.date() if email_send.sent_at else email_send.created_at.date()
        date_str = email_date.strftime('%Y-%m-%d')
        if date_str in metrics_by_date:
            if email_send.status in ['sent', 'delivered', 'opened', 'clicked']:
                metrics_by_date[date_str]['sent'] += 1
            if email_send.status in ['opened', 'clicked']:
                metrics_by_date[date_str]['opened'] += 1
            if email_send.status == 'clicked':
                metrics_by_date[date_str]['clicked'] += 1
    recent_replies = Reply.objects.filter(
        campaign=campaign, replied_at__isnull=False, replied_at__gte=thirty_days_ago
    )
    for reply in recent_replies:
        if reply.replied_at:
            date_str = reply.replied_at.date().strftime('%Y-%m-%d')
            if date_str in metrics_by_date:
                metrics_by_date[date_str]['replied'] += 1
    sorted_dates = sorted(metrics_by_date.keys())
    dates_formatted = []
    impressions_list = []
    clicks_list = []
    conversions_list = []
    replied_list = []
    for date_str in sorted_dates:
        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            dates_formatted.append(date_obj.strftime('%b %d'))
        except (ValueError, TypeError):
            dates_formatted.append(date_str)
        impressions_list.append(metrics_by_date[date_str]['sent'])
        clicks_list.append(metrics_by_date[date_str]['clicked'])
        conversions_list.append(metrics_by_date[date_str]['opened'])
        replied_list.append(metrics_by_date[date_str]['replied'])
    dates_iso_list = list(sorted_dates)
    if not dates_formatted:
        for i in range(6, -1, -1):
            date_obj = timezone.now().date() - timedelta(days=i)
            dates_iso_list.append(date_obj.strftime('%Y-%m-%d'))
            dates_formatted.append(date_obj.strftime('%b %d'))
            impressions_list.append(0)
            clicks_list.append(0)
            conversions_list.append(0)
            replied_list.append(0)
    chart_data = {
        'dates': dates_formatted,
        'dates_iso': dates_iso_list,
        'impressions': impressions_list,
        'clicks': clicks_list,
        'conversions': conversions_list,
        'replied': replied_list,
    }

    recent_sends = EmailSendHistory.objects.filter(campaign=campaign).order_by('-sent_at', '-created_at')[:10]
    email_sends = [
        {
            'id': e.id,
            'recipient_email': e.recipient_email,
            'subject': e.subject,
            'status': e.status,
            'sent_at': e.sent_at.isoformat() if e.sent_at else None,
        }
        for e in recent_sends
    ]

    leads_data = [
        {
            'id': l.id,
            'email': l.email,
            'first_name': l.first_name or '',
            'last_name': l.last_name or '',
            'phone': l.phone or '',
            'company': l.company or '',
            'job_title': l.job_title or '',
            'status': l.status,
            'source': l.source or '',
            'notes': l.notes or '',
        }
        for l in leads
    ]

    return {
        'email_stats': email_stats,
        'analytics': analytics,
        'chart_data': chart_data,
        'email_sends': email_sends,
        'leads': leads_data,
    }


@api_view(["GET"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def get_campaign(request, campaign_id):
    """Get campaign details. Use ?detail=1 for full detail (stats, analytics, email_sends, leads)."""
    try:
        company_user = request.user
        user = _get_or_create_user_for_company_user(company_user)
        
        campaign = get_object_or_404(Campaign, id=campaign_id, owner=user)
        
        leads_count = campaign.leads.count()
        sequences = EmailSequence.objects.filter(campaign=campaign)
        
        campaign_data = {
            'id': campaign.id,
            'name': campaign.name,
            'description': campaign.description,
            'status': campaign.status,
            'campaign_type': campaign.campaign_type,
            'start_date': campaign.start_date.isoformat() if campaign.start_date else None,
            'end_date': campaign.end_date.isoformat() if campaign.end_date else None,
            'target_leads': campaign.target_leads,
            'target_conversions': campaign.target_conversions,
            'age_range': campaign.age_range,
            'interests': campaign.interests,
            'location': campaign.location,
            'industry': campaign.industry,
            'company_size': campaign.company_size,
            'language': campaign.language,
            'leads_count': leads_count,
            'sequences_count': sequences.count(),
            'created_at': campaign.created_at.isoformat(),
            'updated_at': campaign.updated_at.isoformat(),
        }
        
        data = {'campaign': campaign_data}
        
        if request.GET.get('detail') == '1':
            detail = _build_campaign_detail(campaign, user)
            data['email_stats'] = detail['email_stats']
            data['analytics'] = detail['analytics']
            data['chart_data'] = detail['chart_data']
            data['email_sends'] = detail['email_sends']
            data['leads'] = detail['leads']
        
        return Response({
            'status': 'success',
            'data': data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.exception("get_campaign failed")
        return Response(
            {'status': 'error', 'message': 'Failed to get campaign', 'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def create_campaign(request):
    """Create a new campaign"""
    try:
        company_user = request.user
        user = _get_or_create_user_for_company_user(company_user)
        
        data = request.data
        name = (data.get('name') or 'New Campaign').strip()
        if not name:
            name = 'New Campaign'
        
        if Campaign.objects.filter(owner=user, name__iexact=name).exists():
            return Response(
                {'status': 'error', 'message': 'A campaign with this name already exists.', 'error': 'duplicate_name'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        campaign = Campaign.objects.create(
            name=name,
            description=data.get('description', ''),
            status=data.get('status', 'draft'),
            campaign_type=data.get('campaign_type', 'email'),
            start_date=data.get('start_date'),
            end_date=data.get('end_date'),
            target_leads=data.get('target_leads'),
            target_conversions=data.get('target_conversions'),
            age_range=data.get('age_range', ''),
            interests=data.get('interests', ''),
            location=data.get('location', ''),
            industry=data.get('industry', ''),
            company_size=data.get('company_size', ''),
            language=data.get('language', ''),
            owner=user,
        )
        
        return Response({
            'status': 'success',
            'message': 'Campaign created successfully',
            'data': {
                'campaign': {
                    'id': campaign.id,
                    'name': campaign.name,
                    'status': campaign.status,
                }
            }
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        logger.exception("create_campaign failed")
        return Response(
            {'status': 'error', 'message': 'Failed to create campaign', 'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["PUT", "PATCH"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def update_campaign(request, campaign_id):
    """Update campaign"""
    try:
        company_user = request.user
        user = _get_or_create_user_for_company_user(company_user)
        campaign = get_object_or_404(Campaign, id=campaign_id, owner=user)
        data = request.data
        if data.get('name') is not None:
            campaign.name = (data.get('name') or '').strip() or campaign.name
        if data.get('description') is not None:
            campaign.description = data.get('description', '')
        if data.get('campaign_type') is not None:
            campaign.campaign_type = data.get('campaign_type', campaign.campaign_type)
        if data.get('status') is not None:
            campaign.status = data.get('status', campaign.status)
        if 'target_leads' in data:
            campaign.target_leads = data.get('target_leads') or None
        if 'target_conversions' in data:
            campaign.target_conversions = data.get('target_conversions') or None
        if data.get('age_range') is not None:
            campaign.age_range = data.get('age_range', '')
        if data.get('location') is not None:
            campaign.location = data.get('location', '')
        if data.get('industry') is not None:
            campaign.industry = data.get('industry', '')
        if data.get('interests') is not None:
            campaign.interests = data.get('interests', '')
        if data.get('company_size') is not None:
            campaign.company_size = data.get('company_size', '')
        if data.get('language') is not None:
            campaign.language = data.get('language', '')
        if data.get('start_date'):
            try:
                campaign.start_date = datetime.strptime(str(data['start_date'])[:10], '%Y-%m-%d').date()
            except (ValueError, TypeError):
                pass
        if data.get('end_date'):
            try:
                campaign.end_date = datetime.strptime(str(data['end_date'])[:10], '%Y-%m-%d').date()
            except (ValueError, TypeError):
                pass
        campaign.save()
        return Response({
            'status': 'success',
            'message': 'Campaign updated successfully',
            'data': {'campaign_id': campaign.id}
        }, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception("update_campaign failed")
        return Response(
            {'status': 'error', 'message': 'Failed to update campaign', 'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def campaign_stop(request, campaign_id):
    """Stop an active campaign"""
    try:
        company_user = request.user
        user = _get_or_create_user_for_company_user(company_user)
        campaign = get_object_or_404(Campaign, id=campaign_id, owner=user)
        if campaign.status != 'active':
            return Response(
                {'status': 'error', 'message': f'Campaign "{campaign.name}" is not active and cannot be stopped.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        campaign.status = 'paused'
        campaign.save()
        return Response({
            'status': 'success',
            'message': f'Campaign "{campaign.name}" has been stopped successfully.',
            'data': {'campaign_id': campaign.id, 'status': campaign.status}
        }, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception("campaign_stop failed")
        return Response(
            {'status': 'error', 'message': 'Failed to stop campaign', 'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def campaign_delete(request, campaign_id):
    """Delete a campaign"""
    try:
        company_user = request.user
        user = _get_or_create_user_for_company_user(company_user)
        campaign = Campaign.objects.filter(id=campaign_id, owner=user).first()
        if not campaign:
            return Response(
                {'status': 'error', 'message': 'Campaign not found.', 'error': 'not_found'},
                status=status.HTTP_404_NOT_FOUND
            )
        name = campaign.name
        campaign.delete()
        return Response({
            'status': 'success',
            'message': f'Campaign "{name}" has been deleted successfully.',
            'data': {}
        }, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception("campaign_delete failed")
        return Response(
            {'status': 'error', 'message': 'Failed to delete campaign', 'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["GET"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def list_campaign_leads(request, campaign_id):
    """List leads for a campaign (paginated)"""
    try:
        company_user = request.user
        user = _get_or_create_user_for_company_user(company_user)
        campaign = get_object_or_404(Campaign, id=campaign_id, owner=user)
        leads = campaign.leads.all().order_by('-created_at')
        page = int(request.GET.get('page', 1))
        limit = int(request.GET.get('limit', 100))
        offset = (page - 1) * limit
        total = leads.count()
        leads_page = leads[offset:offset + limit]
        return Response({
            'status': 'success',
            'data': {
                'leads': [
                    {
                        'id': l.id, 'email': l.email, 'first_name': l.first_name or '',
                        'last_name': l.last_name or '', 'phone': l.phone or '',
                        'company': l.company or '', 'job_title': l.job_title or '',
                        'status': l.status, 'source': l.source or '', 'notes': l.notes or '',
                    }
                    for l in leads_page
                ],
                'total': total,
                'page': page,
                'limit': limit,
            }
        }, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception("list_campaign_leads failed")
        return Response(
            {'status': 'error', 'message': 'Failed to list leads', 'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def add_campaign_lead(request, campaign_id):
    """Add a lead to campaign"""
    try:
        company_user = request.user
        user = _get_or_create_user_for_company_user(company_user)
        campaign = get_object_or_404(Campaign, id=campaign_id, owner=user)
        data = request.data
        email = (data.get('email') or '').strip().lower()
        if not email:
            return Response(
                {'status': 'error', 'message': 'Email is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        lead, created = Lead.objects.get_or_create(
            email=email, owner=user,
            defaults={
                'first_name': (data.get('first_name') or '').strip(),
                'last_name': (data.get('last_name') or '').strip(),
                'phone': (data.get('phone') or '').strip(),
                'company': (data.get('company') or '').strip(),
                'job_title': (data.get('job_title') or '').strip(),
                'source': (data.get('source') or '').strip(),
            }
        )
        if campaign not in lead.campaigns.all():
            campaign.leads.add(lead)
            CampaignContact.objects.get_or_create(
                campaign=campaign, lead=lead,
                defaults={
                    'sequence': EmailSequence.objects.filter(campaign=campaign, is_active=True).first(),
                    'current_step': 0,
                }
            )
        return Response({
            'status': 'success',
            'message': 'Lead added successfully',
            'data': {'lead_id': lead.id}
        }, status=status.HTTP_201_CREATED)
    except Exception as e:
        logger.exception("add_campaign_lead failed")
        return Response(
            {'status': 'error', 'message': 'Failed to add lead', 'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["PUT", "PATCH"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def update_campaign_lead(request, campaign_id, lead_id):
    """Update a lead"""
    try:
        company_user = request.user
        user = _get_or_create_user_for_company_user(company_user)
        campaign = get_object_or_404(Campaign, id=campaign_id, owner=user)
        lead = get_object_or_404(Lead, id=lead_id, owner=user)
        if not campaign.leads.filter(id=lead.id).exists():
            return Response(
                {'status': 'error', 'message': 'Lead not in this campaign'},
                status=status.HTTP_404_NOT_FOUND
            )
        data = request.data
        if data.get('email'):
            email = str(data.get('email', '')).strip().lower()
            if Lead.objects.filter(email=email, owner=user).exclude(id=lead_id).exists():
                return Response(
                    {'status': 'error', 'message': 'Email already exists'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            lead.email = email
        if 'first_name' in data:
            lead.first_name = (data.get('first_name') or '').strip()
        if 'last_name' in data:
            lead.last_name = (data.get('last_name') or '').strip()
        if 'phone' in data:
            lead.phone = (data.get('phone') or '').strip()
        if 'company' in data:
            lead.company = (data.get('company') or '').strip()
        if 'job_title' in data:
            lead.job_title = (data.get('job_title') or '').strip()
        if 'source' in data:
            lead.source = (data.get('source') or '').strip()
        if data.get('status'):
            lead.status = data.get('status', lead.status)
        if 'notes' in data:
            lead.notes = (data.get('notes') or '').strip()
        lead.save()
        return Response({
            'status': 'success',
            'message': 'Lead updated successfully',
            'data': {'lead_id': lead.id}
        }, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception("update_campaign_lead failed")
        return Response(
            {'status': 'error', 'message': 'Failed to update lead', 'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def delete_campaign_lead(request, campaign_id, lead_id):
    """Remove lead from campaign (delete lead if no other campaigns)"""
    try:
        company_user = request.user
        user = _get_or_create_user_for_company_user(company_user)
        campaign = get_object_or_404(Campaign, id=campaign_id, owner=user)
        lead = get_object_or_404(Lead, id=lead_id, owner=user)
        campaign.leads.remove(lead)
        if lead.campaigns.count() == 0:
            lead.delete()
            message = 'Lead deleted successfully'
        else:
            message = 'Lead removed from campaign'
        return Response({
            'status': 'success',
            'message': message,
            'data': {}
        }, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception("delete_campaign_lead failed")
        return Response(
            {'status': 'error', 'message': 'Failed to delete lead', 'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


def _upload_leads_from_file(campaign, user, uploaded_file):
    """Process CSV/Excel and add leads to campaign. Returns (created_count, error_message)."""
    try:
        import pandas as pd
    except ImportError:
        return (0, 'pandas is required for Excel files. For CSV only, use csv module.')
    file_extension = (uploaded_file.name or '').split('.')[-1].lower()
    if file_extension not in ['csv', 'xlsx', 'xls']:
        return (0, 'Invalid file format. Please upload CSV, XLSX, or XLS files.')
    from django.db import transaction
    if file_extension == 'csv':
        df = pd.read_csv(uploaded_file)
    else:
        df = pd.read_excel(uploaded_file)
    if df.empty:
        return (0, 'File is empty')
    df.columns = df.columns.str.lower().str.strip()
    if 'email' not in df.columns:
        return (0, 'Email column is required in the file')
    # Support "first name"/"last name" (with space) and "name" columns
    def _get(row, *keys):
        for k in keys:
            if k in row and pd.notna(row.get(k)) and str(row.get(k)).strip():
                return str(row.get(k)).strip()
        return ''
    created_count = 0
    with transaction.atomic():
        for index, row in df.iterrows():
            try:
                email = str(row['email']).strip().lower()
                if not email or pd.isna(row['email']) or email == 'nan':
                    continue
                first = _get(row, 'first_name', 'first name')
                last = _get(row, 'last_name', 'last name')
                if not first and not last:
                    name_val = _get(row, 'name')
                    if name_val:
                        parts = name_val.split(None, 1)
                        first = parts[0] or ''
                        last = parts[1] if len(parts) > 1 else ''
                lead, created = Lead.objects.get_or_create(
                    email=email, owner=user,
                    defaults={
                        'first_name': first,
                        'last_name': last,
                        'phone': _get(row, 'phone'),
                        'company': _get(row, 'company'),
                        'job_title': _get(row, 'job_title'),
                        'source': _get(row, 'source'),
                    }
                )
                if created:
                    created_count += 1
                else:
                    if not lead.first_name and first:
                        lead.first_name = first
                    if not lead.last_name and last:
                        lead.last_name = last
                    v = _get(row, 'phone')
                    if not lead.phone and v:
                        lead.phone = v
                    v = _get(row, 'company')
                    if not lead.company and v:
                        lead.company = v
                    v = _get(row, 'job_title', 'job title')
                    if not lead.job_title and v:
                        lead.job_title = v
                    v = _get(row, 'source')
                    if not lead.source and v:
                        lead.source = v
                    lead.save()
                    created_count += 1
                campaign.leads.add(lead)
                CampaignContact.objects.get_or_create(
                    campaign=campaign, lead=lead,
                    defaults={
                        'sequence': EmailSequence.objects.filter(campaign=campaign, is_active=True).first(),
                        'current_step': 0,
                    }
                )
            except Exception:
                continue
    return (created_count, None)


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def upload_campaign_leads(request, campaign_id):
    """Upload leads from CSV/Excel file (multipart/form-data, file=...)"""
    try:
        company_user = request.user
        user = _get_or_create_user_for_company_user(company_user)
        campaign = Campaign.objects.filter(id=campaign_id, owner=user).first()
        if not campaign:
            return Response(
                {'status': 'error', 'message': 'Campaign not found.', 'error': 'not_found'},
                status=status.HTTP_404_NOT_FOUND
            )
        if 'file' not in request.FILES:
            return Response(
                {'status': 'error', 'message': 'No file uploaded', 'error': 'no_file'},
                status=status.HTTP_400_BAD_REQUEST
            )
        uploaded_file = request.FILES['file']
        created_count, err = _upload_leads_from_file(campaign, user, uploaded_file)
        if err:
            return Response(
                {'status': 'error', 'message': err, 'error': 'upload_failed'},
                status=status.HTTP_400_BAD_REQUEST
            )
        return Response({
            'status': 'success',
            'message': f'Successfully added {created_count} lead(s) to the campaign.',
            'data': {'created_count': created_count}
        }, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception("upload_campaign_leads failed")
        return Response(
            {'status': 'error', 'message': 'Failed to upload leads', 'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["GET"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def export_campaign_leads(request, campaign_id):
    """Export campaign leads as CSV"""
    try:
        company_user = request.user
        user = _get_or_create_user_for_company_user(company_user)
        campaign = get_object_or_404(Campaign, id=campaign_id, owner=user)
        leads = campaign.leads.all().order_by('-created_at')
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="campaign_{campaign.id}_leads.csv"'
        writer = csv.writer(response)
        writer.writerow(['Email', 'First Name', 'Last Name', 'Phone', 'Company', 'Job Title', 'Status', 'Source'])
        for lead in leads:
            writer.writerow([
                lead.email, lead.first_name or '', lead.last_name or '',
                lead.phone or '', lead.company or '', lead.job_title or '',
                lead.status, lead.source or ''
            ])
        return response
    except Exception as e:
        logger.exception("export_campaign_leads failed")
        return Response(
            {'status': 'error', 'message': 'Failed to export leads', 'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def marketing_qa(request):
    """Marketing Q&A Agent"""
    try:
        company_user = request.user
        user = _get_or_create_user_for_company_user(company_user)
        
        agent = AgentRegistry.get_agent("marketing_qa")
        question = request.data.get('question', '')
        
        if not question:
            return Response(
                {'status': 'error', 'message': 'Question is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        result = agent.process(
            question=question,
            user_id=user.id
        )
        
        return Response({
            'status': 'success',
            'data': result
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.exception("marketing_qa failed")
        return Response(
            {'status': 'error', 'message': 'Marketing Q&A failed', 'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def market_research(request):
    """Market Research Agent"""
    try:
        company_user = request.user
        user = _get_or_create_user_for_company_user(company_user)
        
        agent = AgentRegistry.get_agent("market_research")
        data = request.data
        
        research_type = data.get('research_type', 'market_trend')
        topic = data.get('topic', '')
        additional_context = data.get('context', {})
        
        if not topic:
            return Response(
                {'status': 'error', 'message': 'Research topic is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        result = agent.process(
            research_type=research_type,
            topic=topic,
            user_id=user.id,
            additional_context=additional_context
        )
        
        return Response({
            'status': 'success',
            'data': result
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.exception("market_research failed")
        return Response(
            {'status': 'error', 'message': 'Market research failed', 'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def outreach_campaign(request):
    """Outreach & Campaign Agent"""
    try:
        company_user = request.user
        user = _get_or_create_user_for_company_user(company_user)
        
        agent = AgentRegistry.get_agent("outreach_campaign")
        data = request.data
        
        action = data.get('action', 'design')
        campaign_data = data.get('campaign_data', {})
        campaign_id = data.get('campaign_id')
        context = data.get('context', {})
        leads_file = request.FILES.get('file')
        
        # When sent as multipart/form-data, campaign_data and context are JSON strings
        if isinstance(campaign_data, str):
            try:
                campaign_data = json.loads(campaign_data) if campaign_data else {}
            except (TypeError, ValueError):
                campaign_data = {}
        if isinstance(context, str):
            try:
                context = json.loads(context) if context else {}
            except (TypeError, ValueError):
                context = {}
        if campaign_id is not None and not isinstance(campaign_id, int):
            try:
                campaign_id = int(campaign_id) if campaign_id else None
            except (TypeError, ValueError):
                campaign_id = None
        
        if action == 'create_multi_channel' and leads_file:
            result = agent.create_multi_channel_campaign(
                user_id=user.id,
                campaign_data=campaign_data,
                context=context,
                leads_file=leads_file
            )
        elif action == 'launch' and leads_file:
            result = agent.launch_campaign(
                campaign_id=campaign_id,
                user_id=user.id,
                campaign_data=campaign_data,
                context=context,
                leads_file=leads_file
            )
        else:
            result = agent.process(
                action=action,
                user_id=user.id,
                campaign_data=campaign_data,
                campaign_id=campaign_id,
                context=context
            )
        
        return Response({
            'status': 'success',
            'data': result
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.exception("outreach_campaign failed")
        return Response(
            {'status': 'error', 'message': 'Outreach campaign failed', 'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["GET"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def list_documents(request):
    """List marketing documents for company user. Query: type, campaign_id."""
    try:
        company_user = request.user
        user = _get_or_create_user_for_company_user(company_user)
        qs = MarketingDocument.objects.filter(created_by=user).select_related('campaign').order_by('-created_at')
        doc_type = request.query_params.get('type', '').strip()
        if doc_type:
            qs = qs.filter(document_type=doc_type)
        campaign_id = request.query_params.get('campaign_id', '')
        if campaign_id:
            try:
                qs = qs.filter(campaign_id=int(campaign_id))
            except ValueError:
                pass
        documents = []
        for doc in qs:
            documents.append({
                'id': doc.id,
                'document_type': doc.document_type,
                'document_type_display': doc.get_document_type_display(),
                'title': doc.title,
                'status': doc.status,
                'status_display': doc.get_status_display(),
                'campaign_id': doc.campaign_id,
                'campaign_name': doc.campaign.name if doc.campaign else None,
                'created_at': doc.created_at.isoformat() if doc.created_at else None,
                'updated_at': doc.updated_at.isoformat() if doc.updated_at else None,
                'content_preview': (doc.content[:200] + '...') if doc.content and len(doc.content) > 200 else (doc.content or ''),
            })
        return Response({
            'status': 'success',
            'data': {
                'documents': documents,
                'count': len(documents),
            },
        }, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception("list_documents failed")
        return Response(
            {'status': 'error', 'message': 'List documents failed', 'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["GET"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def document_detail(request, document_id):
    """Get a single marketing document by id."""
    try:
        company_user = request.user
        user = _get_or_create_user_for_company_user(company_user)
        document = get_object_or_404(MarketingDocument, id=document_id, created_by=user)
        from marketing_agent.document_generator import DocumentGenerator
        available_formats = DocumentGenerator.get_available_formats(document.document_type)
        return Response({
            'status': 'success',
            'data': {
                'id': document.id,
                'document_type': document.document_type,
                'document_type_display': document.get_document_type_display(),
                'title': document.title,
                'content': document.content,
                'status': document.status,
                'status_display': document.get_status_display(),
                'campaign_id': document.campaign_id,
                'campaign_name': document.campaign.name if document.campaign else None,
                'created_at': document.created_at.isoformat() if document.created_at else None,
                'updated_at': document.updated_at.isoformat() if document.updated_at else None,
                'available_formats': [{'code': c, 'name': n} for c, n in available_formats],
            },
        }, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception("document_detail failed")
        return Response(
            {'status': 'error', 'message': 'Document not found', 'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["GET"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def document_download(request, document_id, format_type):
    """Download document as PDF, DOCX, or PPTX. Returns file response."""
    try:
        company_user = request.user
        user = _get_or_create_user_for_company_user(company_user)
        document = get_object_or_404(MarketingDocument, id=document_id, created_by=user)
        from marketing_agent.document_generator import DocumentGenerator
        if format_type == 'pdf':
            response = DocumentGenerator.generate_pdf(document)
        elif format_type == 'pptx':
            if document.document_type != 'presentation':
                return Response(
                    {'status': 'error', 'message': 'PPTX is only available for presentations'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            response = DocumentGenerator.generate_pptx(document)
        else:
            return Response(
                {'status': 'error', 'message': f'Unsupported format: {format_type}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        return response
    except ImportError as e:
        logger.exception("document_download import error")
        return Response(
            {'status': 'error', 'message': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    except Exception as e:
        logger.exception("document_download failed")
        return Response(
            {'status': 'error', 'message': 'Download failed', 'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["POST", "DELETE"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def document_delete(request, document_id):
    """Delete a marketing document. Only the creator can delete."""
    try:
        company_user = request.user
        user = _get_or_create_user_for_company_user(company_user)
        document = get_object_or_404(MarketingDocument, id=document_id, created_by=user)
        document.delete()
        return Response({
            'status': 'success',
            'data': {'message': 'Document deleted successfully'},
        }, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception("document_delete failed")
        return Response(
            {'status': 'error', 'message': 'Delete failed', 'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def document_authoring(request):
    """Document Authoring Agent"""
    try:
        company_user = request.user
        user = _get_or_create_user_for_company_user(company_user)
        
        agent = AgentRegistry.get_agent("document_authoring")
        data = request.data
        
        action = data.get('action', 'create')
        document_type = data.get('document_type', 'strategy')
        document_data = data.get('document_data', {})
        campaign_id = data.get('campaign_id')
        context = data.get('context', {})
        
        if not document_type:
            return Response(
                {'status': 'error', 'message': 'document_type is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        result = agent.process(
            action=action,
            user_id=user.id,
            document_type=document_type,
            document_data=document_data,
            campaign_id=campaign_id,
            context=context
        )
        
        return Response({
            'status': 'success',
            'data': result
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.exception("document_authoring failed")
        return Response(
            {'status': 'error', 'message': 'Document authoring failed', 'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["GET"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def get_notifications(request):
    """Get notifications for company user"""
    try:
        company_user = request.user
        user = _get_or_create_user_for_company_user(company_user)
        
        agent = AgentRegistry.get_agent("proactive_notification")
        
        unread_only = request.GET.get('unread_only', 'false').lower() == 'true'
        notification_type = request.GET.get('type')
        campaign_id = request.GET.get('campaign_id')
        
        if campaign_id:
            try:
                campaign_id = int(campaign_id)
            except ValueError:
                campaign_id = None
        
        result = agent.get_notifications(
            user_id=user.id,
            unread_only=unread_only,
            notification_type=notification_type,
            campaign_id=campaign_id
        )
        
        return Response({
            'status': 'success',
            'data': result
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.exception("get_notifications failed")
        return Response(
            {'status': 'error', 'message': 'Failed to get notifications', 'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def proactive_notification_monitor(request):
    """Run Proactive Notification Agent (monitor campaigns)."""
    try:
        company_user = request.user
        user = _get_or_create_user_for_company_user(company_user)
        data = request.data or {}
        action = data.get('action', 'monitor')
        campaign_id = data.get('campaign_id')
        context = data.get('context', {})
        if campaign_id is not None:
            try:
                campaign_id = int(campaign_id)
            except (ValueError, TypeError):
                campaign_id = None
        agent = AgentRegistry.get_agent("proactive_notification")
        result = agent.process(
            action=action,
            user_id=user.id,
            campaign_id=campaign_id,
            context=context
        )
        return Response({'status': 'success', 'data': result}, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception("proactive_notification_monitor failed")
        return Response(
            {'status': 'error', 'message': 'Monitor failed', 'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def mark_notification_read(request, notification_id):
    """Mark a marketing notification as read."""
    try:
        company_user = request.user
        user = _get_or_create_user_for_company_user(company_user)
        notification = MarketingNotification.objects.get(id=notification_id, user=user)
        notification.mark_as_read()
        return Response({'status': 'success', 'message': 'Notification marked as read'}, status=status.HTTP_200_OK)
    except MarketingNotification.DoesNotExist:
        return Response(
            {'status': 'error', 'message': 'Notification not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.exception("mark_notification_read failed")
        return Response(
            {'status': 'error', 'message': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def delete_notification(request, notification_id):
    """Delete a marketing notification."""
    try:
        company_user = request.user
        user = _get_or_create_user_for_company_user(company_user)
        notification = MarketingNotification.objects.get(id=notification_id, user=user)
        notification.delete()
        return Response({'status': 'success', 'message': 'Notification deleted successfully'}, status=status.HTTP_200_OK)
    except MarketingNotification.DoesNotExist:
        return Response(
            {'status': 'error', 'message': 'Notification not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.exception("delete_notification failed")
        return Response(
            {'status': 'error', 'message': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["GET"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def list_sequences(request, campaign_id):
    """List email sequences for a campaign (for frontend sequence management page)."""
    try:
        company_user = request.user
        user = _get_or_create_user_for_company_user(company_user)
        campaign = Campaign.objects.filter(id=campaign_id, owner=user).first()
        if not campaign:
            return Response(
                {'status': 'error', 'message': 'Campaign not found.', 'error': 'not_found'},
                status=status.HTTP_404_NOT_FOUND
            )
        email_accounts = EmailAccount.objects.filter(owner=user, is_active=True).order_by('-is_default', 'email')
        main_sequences = EmailSequence.objects.filter(
            campaign=campaign,
            is_sub_sequence=False
        ).prefetch_related('steps__template', 'email_account', 'sub_sequences__steps__template')
        templates = EmailTemplate.objects.filter(campaign=campaign, is_active=True).order_by('name')
        sequences_data = []
        for sequence in main_sequences:
            steps = sequence.steps.all().order_by('step_order')
            sequence_emails_sent = EmailSendHistory.objects.filter(
                campaign=campaign,
                email_template__sequence_steps__sequence=sequence
            )
            total_sent = sequence_emails_sent.count()
            total_opened = sequence_emails_sent.filter(status__in=['opened', 'clicked']).count()
            total_clicked = sequence_emails_sent.filter(status='clicked').count()
            open_rate = (total_opened / total_sent * 100) if total_sent > 0 else 0
            click_rate = (total_clicked / total_sent * 100) if total_sent > 0 else 0
            campaign_is_active = campaign.status == 'active'
            effective_is_active = campaign_is_active and sequence.is_active
            sub_sequences_data = []
            for sub_seq in sequence.sub_sequences.all().order_by('id'):
                sub_steps = sub_seq.steps.all().order_by('step_order')
                sub_emails_sent = EmailSendHistory.objects.filter(
                    campaign=campaign,
                    email_template__sequence_steps__sequence=sub_seq
                )
                sub_sent = sub_emails_sent.count()
                sub_opened = sub_emails_sent.filter(status__in=['opened', 'clicked']).count()
                sub_clicked = sub_emails_sent.filter(status='clicked').count()
                sub_open_rate = (sub_opened / sub_sent * 100) if sub_sent > 0 else 0
                sub_click_rate = (sub_clicked / sub_sent * 100) if sub_sent > 0 else 0
                sub_effective = campaign_is_active and sub_seq.is_active
                sub_sequences_data.append({
                    'id': sub_seq.id,
                    'name': sub_seq.name,
                    'is_active': sub_seq.is_active,
                    'effective_is_active': sub_effective,
                    'is_sub_sequence': True,
                    'parent_sequence_id': sequence.id,
                    'interest_level': sub_seq.interest_level or 'any',
                    'email_account': sub_seq.email_account.email if sub_seq.email_account else None,
                    'email_account_id': sub_seq.email_account_id,
                    'steps': [
                        {
                            'id': s.id,
                            'step_order': s.step_order,
                            'template_id': s.template_id,
                            'template_name': s.template.name if s.template else None,
                            'template_subject': s.template.subject if s.template else None,
                            'delay_days': s.delay_days,
                            'delay_hours': s.delay_hours,
                            'delay_minutes': s.delay_minutes,
                        }
                        for s in sub_steps
                    ],
                    'total_sent': sub_sent,
                    'total_opened': sub_opened,
                    'total_clicked': sub_clicked,
                    'open_rate': round(sub_open_rate, 2),
                    'click_rate': round(sub_click_rate, 2),
                })
            sequences_data.append({
                'id': sequence.id,
                'name': sequence.name,
                'is_active': sequence.is_active,
                'effective_is_active': effective_is_active,
                'is_sub_sequence': False,
                'sub_sequences': sub_sequences_data,
                'email_account': sequence.email_account.email if sequence.email_account else None,
                'email_account_id': sequence.email_account_id,
                'steps': [
                    {
                        'id': s.id,
                        'step_order': s.step_order,
                        'template_id': s.template_id,
                        'template_name': s.template.name if s.template else None,
                        'template_subject': s.template.subject if s.template else None,
                        'delay_days': s.delay_days,
                        'delay_hours': s.delay_hours,
                        'delay_minutes': s.delay_minutes,
                    }
                    for s in steps
                ],
                'total_sent': total_sent,
                'total_opened': total_opened,
                'total_clicked': total_clicked,
                'open_rate': round(open_rate, 2),
                'click_rate': round(click_rate, 2),
            })
        templates_data = [
            {'id': t.id, 'name': t.name, 'subject': t.subject, 'html_content': t.html_content or ''}
            for t in templates
        ]
        has_main_sequence = len(sequences_data) > 0
        email_accounts_data = [{'id': a.id, 'email': a.email, 'is_default': getattr(a, 'is_default', False)} for a in email_accounts]
        return Response({
            'status': 'success',
            'data': {
                'campaign': {'id': campaign.id, 'name': campaign.name, 'status': campaign.status},
                'sequences': sequences_data,
                'templates': templates_data,
                'email_accounts': email_accounts_data,
                'has_main_sequence': has_main_sequence,
            }
        }, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception("list_sequences failed")
        return Response(
            {'status': 'error', 'message': 'Failed to list sequences', 'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


MIN_STEP_DELAY_MINUTES = 5


def _step_total_minutes(step_data):
    """Total delay of a step in minutes."""
    days = int(step_data.get('delay_days', 0) or 0)
    hours = int(step_data.get('delay_hours', 0) or 0)
    minutes = int(step_data.get('delay_minutes', 0) or 0)
    return days * 24 * 60 + hours * 60 + minutes


def _validate_sequence_steps(steps_data):
    """
    Validate step delays: first step >= 5 min, each next step >= previous total + 5 min gap.
    Returns (True, None) or (False, error_message).
    """
    if not steps_data:
        return True, None
    prev_total = 0
    for i, step in enumerate(steps_data):
        total = _step_total_minutes(step)
        if i == 0:
            if total < MIN_STEP_DELAY_MINUTES:
                return False, (
                    f'Step 1 delay must be at least {MIN_STEP_DELAY_MINUTES} minutes.'
                )
        else:
            min_required = prev_total + MIN_STEP_DELAY_MINUTES
            if total < min_required:
                return False, (
                    f'Step {i + 1} delay must be at least {MIN_STEP_DELAY_MINUTES} minutes after the previous step '
                    f'(minimum {min_required} minutes total).'
                )
        prev_total = total
    return True, None


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def create_sequence(request, campaign_id):
    """Create a new email sequence (main sequence only - 1 per campaign)."""
    try:
        company_user = request.user
        user = _get_or_create_user_for_company_user(company_user)
        campaign = Campaign.objects.filter(id=campaign_id, owner=user).first()
        if not campaign:
            return Response(
                {'status': 'error', 'message': 'Campaign not found.', 'error': 'not_found'},
                status=status.HTTP_404_NOT_FOUND
            )
        data = request.data
        is_sub_sequence = data.get('is_sub_sequence', False)
        if not is_sub_sequence:
            existing = EmailSequence.objects.filter(campaign=campaign, is_sub_sequence=False).first()
            if existing:
                return Response(
                    {'status': 'error', 'message': f'Only one main sequence per campaign. "{existing.name}" already exists. Edit or delete it first.', 'error': 'duplicate'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        steps_data = [s for s in data.get('steps', []) if s.get('template_id')]
        valid, err = _validate_sequence_steps(steps_data)
        if not valid:
            return Response(
                {'status': 'error', 'message': err, 'error': 'validation'},
                status=status.HTTP_400_BAD_REQUEST
            )
        parent_sequence = None
        if is_sub_sequence:
            parent_id = data.get('parent_sequence_id')
            if not parent_id:
                return Response(
                    {'status': 'error', 'message': 'Sub-sequence requires parent_sequence_id.', 'error': 'validation'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            parent_sequence = EmailSequence.objects.filter(
                id=parent_id, campaign=campaign, is_sub_sequence=False
            ).first()
            if not parent_sequence:
                return Response(
                    {'status': 'error', 'message': 'Parent sequence not found or not a main sequence.', 'error': 'not_found'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        campaign_is_active = campaign.status == 'active'
        effective_is_active = campaign_is_active and data.get('is_active', True)
        sequence = EmailSequence.objects.create(
            name=data.get('name', 'New Sequence'),
            campaign=campaign,
            email_account_id=data.get('email_account_id') or None,
            is_active=effective_is_active,
            parent_sequence=parent_sequence,
            is_sub_sequence=is_sub_sequence,
            interest_level=data.get('interest_level', 'any') if is_sub_sequence else 'any',
        )
        for idx, step_data in enumerate(steps_data, start=1):
            template_id = step_data.get('template_id')
            if not template_id:
                continue
            template = EmailTemplate.objects.filter(id=template_id, campaign=campaign).first()
            if not template:
                continue
            EmailSequenceStep.objects.create(
                sequence=sequence,
                template=template,
                step_order=idx,
                delay_days=step_data.get('delay_days', 0),
                delay_hours=step_data.get('delay_hours', 0),
                delay_minutes=step_data.get('delay_minutes', 0),
            )
        return Response({
            'status': 'success',
            'data': {'sequence_id': sequence.id, 'message': 'Sequence created successfully.'},
        }, status=status.HTTP_201_CREATED)
    except Exception as e:
        logger.exception("create_sequence failed")
        return Response(
            {'status': 'error', 'message': str(e), 'error': 'create_failed'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["GET"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def get_sequence_details(request, campaign_id, sequence_id):
    """Get sequence details with steps and stats."""
    try:
        company_user = request.user
        user = _get_or_create_user_for_company_user(company_user)
        campaign = Campaign.objects.filter(id=campaign_id, owner=user).first()
        if not campaign:
            return Response(
                {'status': 'error', 'message': 'Campaign not found.', 'error': 'not_found'},
                status=status.HTTP_404_NOT_FOUND
            )
        sequence = EmailSequence.objects.filter(id=sequence_id, campaign=campaign).first()
        if not sequence:
            return Response(
                {'status': 'error', 'message': 'Sequence not found.', 'error': 'not_found'},
                status=status.HTTP_404_NOT_FOUND
            )
        steps = sequence.steps.all().order_by('step_order')
        sequence_emails_sent = EmailSendHistory.objects.filter(
            campaign=campaign,
            email_template__sequence_steps__sequence=sequence
        )
        total_sent = sequence_emails_sent.count()
        total_opened = sequence_emails_sent.filter(status__in=['opened', 'clicked']).count()
        total_clicked = sequence_emails_sent.filter(status='clicked').count()
        open_rate = (total_opened / total_sent * 100) if total_sent > 0 else 0
        click_rate = (total_clicked / total_sent * 100) if total_sent > 0 else 0
        steps_data = [{
            'id': s.id,
            'template_id': s.template_id,
            'template_name': s.template.name if s.template else None,
            'step_order': s.step_order,
            'delay_days': s.delay_days,
            'delay_hours': s.delay_hours,
            'delay_minutes': s.delay_minutes,
        } for s in steps]
        return Response({
            'status': 'success',
            'data': {
                'sequence': {
                    'id': sequence.id,
                    'name': sequence.name,
                    'is_active': sequence.is_active,
                    'is_sub_sequence': sequence.is_sub_sequence,
                    'parent_sequence_id': sequence.parent_sequence_id,
                    'interest_level': (sequence.interest_level or 'any') if sequence.is_sub_sequence else 'any',
                    'email_account_id': sequence.email_account_id,
                    'email_account': sequence.email_account.email if sequence.email_account else None,
                    'steps': steps_data,
                    'stats': {
                        'total_sent': total_sent,
                        'total_opened': total_opened,
                        'total_clicked': total_clicked,
                        'open_rate': round(open_rate, 2),
                        'click_rate': round(click_rate, 2),
                    },
                }
            },
        }, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception("get_sequence_details failed")
        return Response(
            {'status': 'error', 'message': str(e), 'error': 'failed'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["PUT", "PATCH"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def update_sequence(request, campaign_id, sequence_id):
    """Update an existing sequence."""
    try:
        company_user = request.user
        user = _get_or_create_user_for_company_user(company_user)
        campaign = Campaign.objects.filter(id=campaign_id, owner=user).first()
        if not campaign:
            return Response(
                {'status': 'error', 'message': 'Campaign not found.', 'error': 'not_found'},
                status=status.HTTP_404_NOT_FOUND
            )
        sequence = EmailSequence.objects.filter(id=sequence_id, campaign=campaign).first()
        if not sequence:
            return Response(
                {'status': 'error', 'message': 'Sequence not found.', 'error': 'not_found'},
                status=status.HTTP_404_NOT_FOUND
            )
        data = request.data
        sequence.name = data.get('name', sequence.name)
        if 'email_account_id' in data:
            sequence.email_account_id = data.get('email_account_id') or None
        campaign_is_active = campaign.status == 'active'
        sequence.is_active = campaign_is_active and data.get('is_active', sequence.is_active)
        if sequence.is_sub_sequence and 'interest_level' in data:
            sequence.interest_level = data.get('interest_level', sequence.interest_level) or 'any'
        sequence.save()
        if 'steps' in data:
            sequence.steps.all().delete()
            for idx, step_data in enumerate(data['steps'], start=1):
                template_id = step_data.get('template_id')
                if not template_id:
                    continue
                template = EmailTemplate.objects.filter(id=template_id, campaign=campaign).first()
                if not template:
                    continue
                EmailSequenceStep.objects.create(
                    sequence=sequence,
                    template=template,
                    step_order=idx,
                    delay_days=step_data.get('delay_days', 0),
                    delay_hours=step_data.get('delay_hours', 0),
                    delay_minutes=step_data.get('delay_minutes', 0),
                )
        return Response({
            'status': 'success',
            'data': {'message': 'Sequence updated successfully.'},
        }, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception("update_sequence failed")
        return Response(
            {'status': 'error', 'message': str(e), 'error': 'failed'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def delete_sequence(request, campaign_id, sequence_id):
    """Delete a sequence."""
    try:
        company_user = request.user
        user = _get_or_create_user_for_company_user(company_user)
        campaign = Campaign.objects.filter(id=campaign_id, owner=user).first()
        if not campaign:
            return Response(
                {'status': 'error', 'message': 'Campaign not found.', 'error': 'not_found'},
                status=status.HTTP_404_NOT_FOUND
            )
        sequence = EmailSequence.objects.filter(id=sequence_id, campaign=campaign).first()
        if not sequence:
            return Response(
                {'status': 'error', 'message': 'Sequence not found.', 'error': 'not_found'},
                status=status.HTTP_404_NOT_FOUND
            )
        name = sequence.name
        sequence.delete()
        return Response({
            'status': 'success',
            'data': {'message': f'Sequence "{name}" deleted successfully.'},
        }, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception("delete_sequence failed")
        return Response(
            {'status': 'error', 'message': str(e), 'error': 'failed'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def create_template(request, campaign_id):
    """Create an email template for a campaign."""
    try:
        company_user = request.user
        user = _get_or_create_user_for_company_user(company_user)
        campaign = Campaign.objects.filter(id=campaign_id, owner=user).first()
        if not campaign:
            return Response(
                {'status': 'error', 'message': 'Campaign not found.', 'error': 'not_found'},
                status=status.HTTP_404_NOT_FOUND
            )
        data = request.data
        name = (data.get('name') or 'New Template').strip() or 'New Template'
        subject = (data.get('subject') or '').strip() or 'No subject'
        template = EmailTemplate.objects.create(
            campaign=campaign,
            name=name,
            email_type=data.get('email_type', 'initial'),
            subject=subject,
            html_content=data.get('html_content', ''),
            text_content=data.get('text_content', ''),
            followup_sequence_number=data.get('followup_sequence_number', 0),
        )
        return Response({
            'status': 'success',
            'data': {'template_id': template.id, 'message': 'Template created successfully.'},
        }, status=status.HTTP_201_CREATED)
    except Exception as e:
        logger.exception("create_template failed")
        return Response(
            {'status': 'error', 'message': str(e), 'error': 'failed'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["PUT", "PATCH"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def update_template(request, campaign_id, template_id):
    """Update an email template."""
    try:
        company_user = request.user
        user = _get_or_create_user_for_company_user(company_user)
        campaign = Campaign.objects.filter(id=campaign_id, owner=user).first()
        if not campaign:
            return Response(
                {'status': 'error', 'message': 'Campaign not found.', 'error': 'not_found'},
                status=status.HTTP_404_NOT_FOUND
            )
        template = EmailTemplate.objects.filter(id=template_id, campaign=campaign).first()
        if not template:
            return Response(
                {'status': 'error', 'message': 'Template not found.', 'error': 'not_found'},
                status=status.HTTP_404_NOT_FOUND
            )
        data = request.data
        if 'name' in data:
            template.name = (data.get('name') or '').strip() or template.name
        if 'subject' in data:
            template.subject = (data.get('subject') or '').strip() or template.subject
        if 'email_type' in data:
            template.email_type = data.get('email_type', template.email_type)
        if 'html_content' in data:
            template.html_content = data.get('html_content', template.html_content)
        if 'text_content' in data:
            template.text_content = data.get('text_content', template.text_content)
        if 'followup_sequence_number' in data:
            template.followup_sequence_number = data.get('followup_sequence_number', template.followup_sequence_number)
        if 'is_active' in data:
            template.is_active = data.get('is_active', template.is_active)
        template.save()
        return Response({
            'status': 'success',
            'data': {'message': 'Template updated successfully.'},
        }, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception("update_template failed")
        return Response(
            {'status': 'error', 'message': str(e), 'error': 'failed'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def delete_template(request, campaign_id, template_id):
    """Delete an email template."""
    try:
        company_user = request.user
        user = _get_or_create_user_for_company_user(company_user)
        campaign = Campaign.objects.filter(id=campaign_id, owner=user).first()
        if not campaign:
            return Response(
                {'status': 'error', 'message': 'Campaign not found.', 'error': 'not_found'},
                status=status.HTTP_404_NOT_FOUND
            )
        template = EmailTemplate.objects.filter(id=template_id, campaign=campaign).first()
        if not template:
            return Response(
                {'status': 'error', 'message': 'Template not found.', 'error': 'not_found'},
                status=status.HTTP_404_NOT_FOUND
            )
        name = template.name
        template.delete()
        return Response({
            'status': 'success',
            'data': {'message': f'Template "{name}" deleted successfully.'},
        }, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception("delete_template failed")
        return Response(
            {'status': 'error', 'message': str(e), 'error': 'failed'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def test_email_template(request, campaign_id, template_id):
    """
    Send a test email for a template so you can verify dynamic values ({{ first_name }}, etc.).
    Body: { "test_email": "you@example.com", "lead_id": 123 } (lead_id optional).
    If lead_id is provided, uses that lead's first_name, last_name, etc. Otherwise uses sample data.
    """
    try:
        company_user = request.user
        user = _get_or_create_user_for_company_user(company_user)
        campaign = Campaign.objects.filter(id=campaign_id, owner=user).first()
        if not campaign:
            return Response(
                {'status': 'error', 'message': 'Campaign not found.', 'error': 'not_found'},
                status=status.HTTP_404_NOT_FOUND
            )
        template = EmailTemplate.objects.filter(id=template_id, campaign=campaign).first()
        if not template:
            return Response(
                {'status': 'error', 'message': 'Template not found.', 'error': 'not_found'},
                status=status.HTTP_404_NOT_FOUND
            )
        test_email = (request.data.get('test_email') or '').strip()
        if not test_email:
            return Response(
                {'status': 'error', 'message': 'test_email is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        lead_id = request.data.get('lead_id')
        if lead_id is not None:
            lead = campaign.leads.filter(id=lead_id).first()
            if not lead:
                return Response(
                    {'status': 'error', 'message': 'Lead not found in this campaign.'},
                    status=status.HTTP_404_NOT_FOUND
                )
        else:
            # Dummy lead with sample values so {{ first_name }}, {{ last_name }} etc. are filled
            lead = Lead(
                email=test_email,
                first_name='Test',
                last_name='User',
                company='Test Company',
                owner=campaign.owner,
            )
        from marketing_agent.services.email_service import EmailService
        email_service = EmailService()
        result = email_service.send_email(
            template=template,
            lead=lead,
            campaign=campaign,
            test_email=test_email,
        )
        if not result.get('success'):
            return Response(
                {'status': 'error', 'message': result.get('error', 'Failed to send test email.')},
                status=status.HTTP_400_BAD_REQUEST
            )
        return Response({
            'status': 'success',
            'data': {'message': f'Test email sent to {test_email}. Check your inbox to verify dynamic values (e.g. first_name, last_name).'},
        }, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception("test_email_template failed")
        return Response(
            {'status': 'error', 'message': str(e), 'error': 'failed'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


def _get_pending_and_upcoming_emails(campaign):
    """
    Compute pending (ready to send) and upcoming (scheduled within 24h) emails for a campaign.
    Returns (pending_list, upcoming_list) of JSON-serializable dicts.
    """
    now = timezone.now()
    horizon = now + timedelta(hours=24)
    pending_list = []
    upcoming_list = []

    if campaign.status != 'active':
        return pending_list, upcoming_list

    email_svc = EmailService()
    # Main sequence contacts: not completed, not replied
    contacts = (
        CampaignContact.objects
        .filter(
            campaign=campaign,
            sequence__is_active=True,
            sequence__isnull=False,
            completed=False,
            replied=False,
        )
        .select_related('lead', 'sequence')
        .prefetch_related('sequence__steps__template')
    )[:200]

    for contact in contacts:
        sequence = contact.sequence
        steps = list(sequence.steps.all().order_by('step_order'))
        next_step = next((s for s in steps if s.step_order == contact.current_step + 1), None)
        if not next_step:
            continue
        if contact.current_step == 0:
            reference_time = contact.started_at if contact.started_at else contact.created_at
        else:
            if contact.last_sent_at and contact.last_sent_at <= now:
                time_since_last = now - contact.last_sent_at
                reference_time = contact.last_sent_at if time_since_last <= timedelta(hours=24) else now
            else:
                reference_time = now
        next_send_time = reference_time + timedelta(
            days=next_step.delay_days,
            hours=next_step.delay_hours,
            minutes=next_step.delay_minutes,
        )
        if contact.current_step > 0 and next_send_time < now - timedelta(hours=1):
            reference_time = now
            next_send_time = reference_time + timedelta(
                days=next_step.delay_days,
                hours=next_step.delay_hours,
                minutes=next_step.delay_minutes,
            )
        existing_email = EmailSendHistory.objects.filter(
            campaign=campaign,
            lead=contact.lead,
            email_template=next_step.template,
        ).first()
        if existing_email and existing_email.status in ['sent', 'delivered', 'opened', 'clicked']:
            continue
        if next_send_time <= now:
            is_retry = existing_email and existing_email.status in ['pending', 'failed']
            rendered_subject = email_svc.render_with_lead(next_step.template.subject or '', contact.lead, campaign)
            pending_list.append({
                'recipient_email': contact.lead.email,
                'subject': rendered_subject,
                'sequence_name': sequence.name,
                'sequence_id': sequence.id,
                'step_order': next_step.step_order,
                'template_name': next_step.template.name,
                'is_sub_sequence': False,
                'is_retry': is_retry,
                'previous_status': existing_email.status if existing_email else None,
            })
        elif next_send_time <= horizon:
            upcoming_list.append({
                'lead_email': contact.lead.email,
                'sequence_name': sequence.name,
                'sequence_id': sequence.id,
                'next_send_time': next_send_time.isoformat(),
                'step_order': next_step.step_order,
                'template_name': next_step.template.name,
                'delay_days': next_step.delay_days,
                'delay_hours': next_step.delay_hours,
                'delay_minutes': next_step.delay_minutes,
                'is_sub_sequence': False,
            })

    # Sub-sequence contacts: replied, sub_sequence active, not sub_sequence_completed
    sub_contacts = (
        CampaignContact.objects
        .filter(
            campaign=campaign,
            sub_sequence__is_active=True,
            sub_sequence__isnull=False,
            sub_sequence_completed=False,
            replied=True,
        )
        .select_related('lead', 'sequence', 'sub_sequence', 'sub_sequence__parent_sequence')
        .prefetch_related('sub_sequence__steps__template')
    )[:200]

    for contact in sub_contacts:
        sub_sequence = contact.sub_sequence
        if not sub_sequence:
            continue
        parent_sequence = getattr(sub_sequence, 'parent_sequence', None) or contact.sequence
        if not parent_sequence:
            continue
        steps = list(sub_sequence.steps.all().order_by('step_order'))
        next_step = next((s for s in steps if s.step_order == contact.sub_sequence_step + 1), None)
        if not next_step:
            continue
        if contact.sub_sequence_step == 0:
            reference_time = contact.replied_at or contact.updated_at
        else:
            if contact.sub_sequence_last_sent_at and contact.sub_sequence_last_sent_at <= now:
                time_since = now - contact.sub_sequence_last_sent_at
                reference_time = contact.sub_sequence_last_sent_at if time_since <= timedelta(hours=24) else now
            else:
                reference_time = now
        next_send_time = reference_time + timedelta(
            days=next_step.delay_days,
            hours=next_step.delay_hours,
            minutes=next_step.delay_minutes,
        )
        if contact.sub_sequence_step > 0 and next_send_time < now - timedelta(hours=1):
            reference_time = now
            next_send_time = reference_time + timedelta(
                days=next_step.delay_days,
                hours=next_step.delay_hours,
                minutes=next_step.delay_minutes,
            )
        existing_email = EmailSendHistory.objects.filter(
            campaign=campaign,
            lead=contact.lead,
            email_template=next_step.template,
        ).first()
        if existing_email and existing_email.status in ['sent', 'delivered', 'opened', 'clicked']:
            continue
        if next_send_time <= now:
            is_retry = existing_email and existing_email.status in ['pending', 'failed']
            rendered_subject = email_svc.render_with_lead(next_step.template.subject or '', contact.lead, campaign)
            pending_list.append({
                'recipient_email': contact.lead.email,
                'subject': rendered_subject,
                'sequence_name': parent_sequence.name,
                'sequence_id': parent_sequence.id,
                'sub_sequence_name': sub_sequence.name,
                'step_order': next_step.step_order,
                'template_name': next_step.template.name,
                'is_sub_sequence': True,
                'is_retry': is_retry,
                'previous_status': existing_email.status if existing_email else None,
            })
        elif next_send_time <= horizon:
            upcoming_list.append({
                'lead_email': contact.lead.email,
                'sequence_name': parent_sequence.name,
                'sequence_id': parent_sequence.id,
                'sub_sequence_name': sub_sequence.name,
                'next_send_time': next_send_time.isoformat(),
                'step_order': next_step.step_order,
                'template_name': next_step.template.name,
                'delay_days': next_step.delay_days,
                'delay_hours': next_step.delay_hours,
                'delay_minutes': next_step.delay_minutes,
                'is_sub_sequence': True,
            })

    return pending_list, upcoming_list


@api_view(["GET"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def get_email_status_full(request, campaign_id):
    """Full email sending status (stats + recent emails) for frontend email status page."""
    try:
        company_user = request.user
        user = _get_or_create_user_for_company_user(company_user)
        campaign = Campaign.objects.filter(id=campaign_id, owner=user).first()
        if not campaign:
            return Response(
                {'status': 'error', 'message': 'Campaign not found.', 'error': 'not_found'},
                status=status.HTTP_404_NOT_FOUND
            )
        all_email_history = (
            EmailSendHistory.objects
            .filter(campaign=campaign)
            .select_related('email_template', 'lead')
            .order_by('-sent_at', '-created_at')
        )
        pending_emails, upcoming_emails = _get_pending_and_upcoming_emails(campaign)
        # total_replied = count of Reply records (each reply event), not unique contacts
        try:
            total_replied = Reply.objects.filter(campaign=campaign).count()
        except Exception:
            total_replied = CampaignContact.objects.filter(campaign=campaign, replied=True).count()
        stats = {
            'total_sent': all_email_history.filter(status__in=['sent', 'delivered', 'opened', 'clicked']).count(),
            'total_opened': all_email_history.filter(status__in=['opened', 'clicked']).count(),
            'total_clicked': all_email_history.filter(status='clicked').count(),
            'total_failed': all_email_history.filter(status='failed').count(),
            'total_bounced': all_email_history.filter(status='bounced').count(),
            'total_replied': total_replied,
            'pending_count': len(pending_emails),
            'upcoming_count': len(upcoming_emails),
        }
        if stats['total_sent'] > 0:
            stats['open_rate'] = round((stats['total_opened'] / stats['total_sent']) * 100, 1)
            stats['click_rate'] = round((stats['total_clicked'] / stats['total_sent']) * 100, 1)
            stats['bounce_rate'] = round((stats['total_bounced'] / stats['total_sent']) * 100, 1)
        else:
            stats['open_rate'] = 0
            stats['click_rate'] = 0
            stats['bounce_rate'] = 0
        last_5_min = timezone.now() - timedelta(minutes=5)
        currently_sending = all_email_history.filter(sent_at__gte=last_5_min).exists() or len(pending_emails) > 0
        recent_emails = list(all_email_history[:100])
        email_ids = [e.id for e in recent_emails]
        template_ids = [e.email_template_id for e in recent_emails if e.email_template_id]

        # Map email_id -> interest_level from latest Reply (for Replied column)
        # Use contact.reply_interest_level when Reply.interest_level is 'not_analyzed' (match Django)
        replied_map = {}
        try:
            for reply in Reply.objects.filter(
                campaign=campaign,
                triggering_email_id__in=email_ids,
            ).select_related('contact').order_by('-replied_at'):
                eid = reply.triggering_email_id
                if eid and eid not in replied_map:
                    level = reply.interest_level or 'not_analyzed'
                    if level == 'not_analyzed' and getattr(reply, 'contact', None):
                        level = (reply.contact.reply_interest_level or 'not_analyzed')
                    replied_map[eid] = level
        except Exception:
            pass

        # Per-email type (Sequence vs Sub-Sequence): context-aware like Django view.
        # Sub-Sequence only when this send was part of sub-sequence flow (sent after reply).
        contacts_by_lead = {}
        for c in CampaignContact.objects.filter(campaign=campaign).select_related(
            'sequence', 'sub_sequence', 'sub_sequence__parent_sequence'
        ):
            if c.lead_id not in contacts_by_lead:
                contacts_by_lead[c.lead_id] = []
            contacts_by_lead[c.lead_id].append(c)

        def get_email_type_and_sequence(email_send):
            """Determine type from template steps + contact timing (match Django view logic)."""
            if not email_send.email_template_id:
                return ('initial', 'Initial / Other')
            template_steps = list(
                EmailSequenceStep.objects.filter(
                    template_id=email_send.email_template_id,
                    sequence__campaign=campaign,
                ).select_related('sequence', 'sequence__parent_sequence')
            )
            if not template_steps:
                return ('initial', 'Initial / Other')
            sent_at = email_send.sent_at
            contacts = (contacts_by_lead.get(email_send.lead_id) or []) if email_send.lead_id else []
            # Sub-sequence: template in sub_sequence AND contact has that sub_sequence AND sent_at >= replied_at
            for step in template_steps:
                seq = step.sequence
                if not seq.is_sub_sequence:
                    continue
                for contact in contacts:
                    if contact.sub_sequence_id != seq.id:
                        continue
                    if not contact.replied_at or not sent_at or sent_at < contact.replied_at:
                        continue
                    parent = getattr(seq, 'parent_sequence', None)
                    return ('sub_sequence', parent.name if parent else seq.name)
            # Main sequence: template in main sequence and send in main flow
            for step in template_steps:
                seq = step.sequence
                if seq.is_sub_sequence:
                    continue
                for contact in contacts:
                    if contact.sequence_id == seq.id:
                        if not contact.created_at or not sent_at or sent_at >= contact.created_at:
                            return ('sequence', seq.name)
                        break
            # Fallback: single step (e.g. no contact or no sent_at)
            step = template_steps[0]
            seq = step.sequence
            if seq.is_sub_sequence and seq.parent_sequence_id:
                return ('sub_sequence', (seq.parent_sequence.name if seq.parent_sequence else seq.name))
            return ('sequence', seq.name)

        emails_by_sequence = {}
        for email_send in recent_emails:
            email_type, seq_name = get_email_type_and_sequence(email_send)
            is_replied = email_send.id in replied_map
            reply_interest_level = replied_map.get(email_send.id)
            if seq_name not in emails_by_sequence:
                emails_by_sequence[seq_name] = []
            emails_by_sequence[seq_name].append({
                'id': email_send.id,
                'recipient_email': email_send.recipient_email,
                'subject': email_send.subject,
                'status': email_send.status,
                'sent_at': email_send.sent_at.isoformat() if email_send.sent_at else None,
                'template_name': email_send.email_template.name if email_send.email_template else None,
                'type': email_type,
                'is_replied': is_replied,
                'reply_interest_level': reply_interest_level,
            })

        # Replies (from Reply model) - for "Replied contacts" section
        replies_list = []
        replies_by_sequence = {}
        try:
            all_replies = list(
                Reply.objects.filter(campaign=campaign)
                .select_related('lead', 'sequence', 'sub_sequence', 'triggering_email', 'contact')
                .order_by('-replied_at')[:100]
            )
            for reply in all_replies:
                seq_name = reply.sequence.name if reply.sequence else 'No Sequence'
                seq_id = reply.sequence_id or 'no_sequence'
                reply_content = (reply.reply_content or '').strip()
                if len(reply_content) > 400:
                    reply_content = reply_content[:400] + '…'
                interest_level = reply.interest_level or 'not_analyzed'
                if interest_level == 'not_analyzed' and getattr(reply, 'contact', None):
                    interest_level = (reply.contact.reply_interest_level or 'not_analyzed')
                r = {
                    'id': reply.id,
                    'lead_email': reply.lead.email if reply.lead else None,
                    'sequence_name': seq_name,
                    'sequence_id': reply.sequence_id,
                    'sub_sequence_name': reply.sub_sequence.name if reply.sub_sequence else None,
                    'sub_sequence_id': reply.sub_sequence_id,
                    'interest_level': interest_level,
                    'replied_at': reply.replied_at.isoformat() if reply.replied_at else None,
                    'reply_subject': reply.reply_subject or '',
                    'reply_content': reply_content,
                    'in_reply_to_subject': reply.triggering_email.subject if reply.triggering_email else None,
                }
                replies_list.append(r)
                if seq_id not in replies_by_sequence:
                    replies_by_sequence[seq_id] = {'sequence_name': seq_name, 'replies': []}
                replies_by_sequence[seq_id]['replies'].append(r)
        except Exception as e:
            logger.warning("Could not load replies for email status: %s", e)

        return Response({
            'status': 'success',
            'data': {
                'campaign': {'id': campaign.id, 'name': campaign.name},
                'stats': stats,
                'currently_sending': currently_sending,
                'emails_by_sequence': emails_by_sequence,
                'total_emails_shown': len(recent_emails),
                'pending_emails': pending_emails,
                'upcoming_emails': upcoming_emails,
                'replies': replies_list,
                'replies_by_sequence': replies_by_sequence,
            }
        }, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception("get_email_status_full failed")
        return Response(
            {'status': 'error', 'message': 'Failed to get email status', 'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# ---------- Email Accounts (token auth) ----------

@api_view(["GET"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def list_email_accounts(request):
    """List email accounts for the company user (no passwords). Includes sent/opened/clicked counts from sequences using this account."""
    try:
        company_user = request.user
        user = _get_or_create_user_for_company_user(company_user)
        accounts = EmailAccount.objects.filter(owner=user).order_by('-is_default', '-is_active', '-created_at')
        data = []
        for a in accounts:
            # Template IDs used in sequences that use this account
            template_ids = list(
                EmailSequenceStep.objects.filter(sequence__email_account_id=a.id)
                .values_list('template_id', flat=True)
                .distinct()
            )
            sent_qs = EmailSendHistory.objects.filter(email_template_id__in=template_ids) if template_ids else EmailSendHistory.objects.none()
            sent_count = sent_qs.filter(status__in=['sent', 'delivered', 'opened', 'clicked']).count()
            opened_count = sent_qs.filter(status__in=['opened', 'clicked']).count()
            clicked_count = sent_qs.filter(status='clicked').count()
            open_rate = round((opened_count / sent_count * 100), 1) if sent_count > 0 else 0
            click_rate = round((clicked_count / sent_count * 100), 1) if sent_count > 0 else 0
            data.append({
                'id': a.id,
                'name': a.name,
                'account_type': a.account_type,
                'email': a.email,
                'smtp_host': a.smtp_host,
                'smtp_port': a.smtp_port,
                'use_tls': a.use_tls,
                'use_ssl': a.use_ssl,
                'is_active': a.is_active,
                'is_default': a.is_default,
                'test_status': getattr(a, 'test_status', 'not_tested') or 'not_tested',
                'test_error': getattr(a, 'test_error', '') or '',
                'last_tested_at': a.last_tested_at.isoformat() if a.last_tested_at else None,
                'created_at': a.created_at.isoformat() if a.created_at else None,
                'updated_at': a.updated_at.isoformat() if a.updated_at else None,
                'sent_count': sent_count,
                'opened_count': opened_count,
                'clicked_count': clicked_count,
                'open_rate': open_rate,
                'click_rate': click_rate,
            })
        return Response({'status': 'success', 'data': data}, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception("list_email_accounts failed")
        return Response(
            {'status': 'error', 'message': str(e), 'error': 'failed'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def create_email_account(request):
    """Create an email account."""
    try:
        company_user = request.user
        user = _get_or_create_user_for_company_user(company_user)
        data = request.data
        name = (data.get('name') or '').strip() or 'Email Account'
        email = (data.get('email') or '').strip()
        if not email:
            return Response(
                {'status': 'error', 'message': 'Email is required.', 'error': 'validation'},
                status=status.HTTP_400_BAD_REQUEST
            )
        smtp_host = (data.get('smtp_host') or '').strip()
        if not smtp_host:
            return Response(
                {'status': 'error', 'message': 'SMTP host is required.', 'error': 'validation'},
                status=status.HTTP_400_BAD_REQUEST
            )
        smtp_port = int(data.get('smtp_port', 587))
        smtp_username = (data.get('smtp_username') or '').strip() or email
        smtp_password = data.get('smtp_password') or ''
        if not smtp_password:
            return Response(
                {'status': 'error', 'message': 'SMTP password is required.', 'error': 'validation'},
                status=status.HTTP_400_BAD_REQUEST
            )
        account = EmailAccount.objects.create(
            owner=user,
            name=name,
            account_type=data.get('account_type', 'smtp'),
            email=email,
            smtp_host=smtp_host,
            smtp_port=smtp_port,
            smtp_username=smtp_username,
            smtp_password=smtp_password,
            use_tls=data.get('use_tls', True),
            use_ssl=data.get('use_ssl', False),
            is_gmail_app_password=data.get('is_gmail_app_password', False),
            imap_host=data.get('imap_host', ''),
            imap_port=int(data.get('imap_port')) if data.get('imap_port') else None,
            imap_use_ssl=data.get('imap_use_ssl', True),
            imap_username=data.get('imap_username', ''),
            imap_password=data.get('imap_password', ''),
            enable_imap_sync=data.get('enable_imap_sync', False),
            is_active=data.get('is_active', True),
            is_default=data.get('is_default', False),
        )
        return Response({
            'status': 'success',
            'data': {'account_id': account.id, 'message': 'Email account created successfully.'},
        }, status=status.HTTP_201_CREATED)
    except Exception as e:
        logger.exception("create_email_account failed")
        return Response(
            {'status': 'error', 'message': str(e), 'error': 'failed'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["GET"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def get_email_account(request, account_id):
    """Get a single email account (for edit). Password returned as masked; send new password on update if changing."""
    try:
        company_user = request.user
        user = _get_or_create_user_for_company_user(company_user)
        account = EmailAccount.objects.filter(id=account_id, owner=user).first()
        if not account:
            return Response(
                {'status': 'error', 'message': 'Account not found.', 'error': 'not_found'},
                status=status.HTTP_404_NOT_FOUND
            )
        return Response({
            'status': 'success',
            'data': {
                'id': account.id,
                'name': account.name,
                'account_type': account.account_type,
                'email': account.email,
                'smtp_host': account.smtp_host,
                'smtp_port': account.smtp_port,
                'smtp_username': account.smtp_username,
                'smtp_password': '',  # Never return password; frontend sends new one on update if changing
                'use_tls': account.use_tls,
                'use_ssl': account.use_ssl,
                'is_gmail_app_password': account.is_gmail_app_password,
                'imap_host': account.imap_host or '',
                'imap_port': account.imap_port,
                'imap_use_ssl': account.imap_use_ssl,
                'imap_username': account.imap_username or '',
                'imap_password': '',
                'enable_imap_sync': account.enable_imap_sync,
                'is_active': account.is_active,
                'is_default': account.is_default,
                'test_status': getattr(account, 'test_status', 'not_tested') or 'not_tested',
            },
        }, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception("get_email_account failed")
        return Response(
            {'status': 'error', 'message': str(e), 'error': 'failed'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["PUT", "PATCH"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def update_email_account(request, account_id):
    """Update an email account. Omit smtp_password to keep existing."""
    try:
        company_user = request.user
        user = _get_or_create_user_for_company_user(company_user)
        account = EmailAccount.objects.filter(id=account_id, owner=user).first()
        if not account:
            return Response(
                {'status': 'error', 'message': 'Account not found.', 'error': 'not_found'},
                status=status.HTTP_404_NOT_FOUND
            )
        data = request.data
        account.name = (data.get('name') or account.name or '').strip() or account.name
        account.account_type = data.get('account_type', account.account_type)
        account.email = (data.get('email') or account.email or '').strip() or account.email
        account.smtp_host = (data.get('smtp_host') or account.smtp_host or '').strip() or account.smtp_host
        account.smtp_port = int(data.get('smtp_port', account.smtp_port))
        account.smtp_username = (data.get('smtp_username') or account.smtp_username or '').strip() or account.smtp_username
        if data.get('smtp_password'):
            account.smtp_password = data['smtp_password']
        account.use_tls = data.get('use_tls', account.use_tls)
        account.use_ssl = data.get('use_ssl', account.use_ssl)
        account.is_gmail_app_password = data.get('is_gmail_app_password', account.is_gmail_app_password)
        account.imap_host = data.get('imap_host', account.imap_host or '')
        account.imap_port = int(data.get('imap_port')) if data.get('imap_port') else account.imap_port
        account.imap_use_ssl = data.get('imap_use_ssl', account.imap_use_ssl)
        account.imap_username = data.get('imap_username', account.imap_username or '')
        if data.get('imap_password'):
            account.imap_password = data['imap_password']
        account.enable_imap_sync = data.get('enable_imap_sync', account.enable_imap_sync)
        account.is_active = data.get('is_active', account.is_active)
        account.is_default = data.get('is_default', account.is_default)
        account.save()
        return Response({
            'status': 'success',
            'data': {'message': 'Email account updated successfully.'},
        }, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception("update_email_account failed")
        return Response(
            {'status': 'error', 'message': str(e), 'error': 'failed'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def delete_email_account(request, account_id):
    """Delete an email account."""
    try:
        company_user = request.user
        user = _get_or_create_user_for_company_user(company_user)
        account = EmailAccount.objects.filter(id=account_id, owner=user).first()
        if not account:
            return Response(
                {'status': 'error', 'message': 'Account not found.', 'error': 'not_found'},
                status=status.HTTP_404_NOT_FOUND
            )
        name = account.name
        account.delete()
        return Response({
            'status': 'success',
            'data': {'message': f'Email account "{name}" deleted successfully.'},
        }, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception("delete_email_account failed")
        return Response(
            {'status': 'error', 'message': str(e), 'error': 'failed'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["POST"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def test_email_account(request, account_id):
    """Send a test email using this account."""
    try:
        company_user = request.user
        user = _get_or_create_user_for_company_user(company_user)
        account = EmailAccount.objects.filter(id=account_id, owner=user).first()
        if not account:
            return Response(
                {'status': 'error', 'message': 'Account not found.', 'error': 'not_found'},
                status=status.HTTP_404_NOT_FOUND
            )
        test_email = (request.data.get('test_email') or account.email or '').strip()
        if not test_email:
            return Response(
                {'status': 'error', 'message': 'Test email address is required.', 'error': 'validation'},
                status=status.HTTP_400_BAD_REQUEST
            )
        from django.core.mail import EmailMessage
        from django.core.mail.backends.smtp import EmailBackend
        backend = EmailBackend(
            host=account.smtp_host,
            port=account.smtp_port,
            username=account.smtp_username,
            password=account.smtp_password,
            use_tls=account.use_tls,
            use_ssl=account.use_ssl,
            fail_silently=False,
            timeout=10,
        )
        email = EmailMessage(
            subject='Test Email from Marketing Agent',
            body='This is a test email to verify your email account settings are correct.\n\nIf you received this email, your SMTP configuration is working correctly.',
            from_email=account.email,
            to=[test_email],
            connection=backend,
        )
        email.send()
        account.last_tested_at = timezone.now()
        account.test_status = 'success'
        account.test_error = ''
        account.save(update_fields=['last_tested_at', 'test_status', 'test_error'])
        return Response({
            'status': 'success',
            'data': {'message': f'Test email sent successfully to {test_email}.'},
        }, status=status.HTTP_200_OK)
    except smtplib.SMTPAuthenticationError as e:
        account.last_tested_at = timezone.now()
        account.test_status = 'failed'
        account.test_error = str(e)
        account.save(update_fields=['last_tested_at', 'test_status', 'test_error'])
        return Response(
            {'status': 'error', 'message': f'Authentication failed. Check username and password (use App Password for Gmail). {str(e)}', 'error': 'smtp'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    except (smtplib.SMTPException, socket.timeout, OSError) as e:
        account.last_tested_at = timezone.now()
        account.test_status = 'failed'
        account.test_error = str(e)
        account.save(update_fields=['last_tested_at', 'test_status', 'test_error'])
        return Response(
            {'status': 'error', 'message': str(e), 'error': 'smtp'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    except Exception as e:
        logger.exception("test_email_account failed")
        return Response(
            {'status': 'error', 'message': str(e), 'error': 'failed'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

