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
import json
import logging

from api.authentication import CompanyUserTokenAuthentication
from api.permissions import IsCompanyUserOnly
from marketing_agent.models import (
    Campaign, Lead, EmailTemplate, EmailSequence, EmailSequenceStep,
    EmailSendHistory, EmailAccount, CampaignContact, MarketingNotification,
    MarketResearch
)
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
        total_budget = sum(float(c.budget) for c in campaigns)
        total_spend = sum(float(c.actual_spend) for c in campaigns)
        
        # Get recent campaigns
        recent_campaigns = campaigns.order_by('-created_at')[:10]
        
        return Response({
            'status': 'success',
            'data': {
                'stats': {
                    'total_campaigns': campaigns.count(),
                    'active_campaigns': active_campaigns,
                    'paused_campaigns': campaigns.filter(status='paused').count(),
                    'completed_campaigns': campaigns.filter(status='completed').count(),
                    'total_budget': float(total_budget),
                    'total_spend': float(total_spend),
                    'budget_remaining': float(total_budget - total_spend),
                },
                'recent_campaigns': [
                    {
                        'id': c.id,
                        'name': c.name,
                        'status': c.status,
                        'start_date': c.start_date.isoformat() if c.start_date else None,
                        'end_date': c.end_date.isoformat() if c.end_date else None,
                        'budget': float(c.budget),
                        'actual_spend': float(c.actual_spend),
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
                        'budget': float(c.budget),
                        'actual_spend': float(c.actual_spend),
                        'target_revenue': float(c.target_revenue) if c.target_revenue else None,
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


@api_view(["GET"])
@authentication_classes([CompanyUserTokenAuthentication])
@permission_classes([IsCompanyUserOnly])
def get_campaign(request, campaign_id):
    """Get campaign details"""
    try:
        company_user = request.user
        user = _get_or_create_user_for_company_user(company_user)
        
        campaign = get_object_or_404(Campaign, id=campaign_id, owner=user)
        
        # Get leads count
        leads_count = campaign.leads.count()
        
        # Get sequences
        sequences = EmailSequence.objects.filter(campaign=campaign)
        
        return Response({
            'status': 'success',
            'data': {
                'campaign': {
                    'id': campaign.id,
                    'name': campaign.name,
                    'description': campaign.description,
                    'status': campaign.status,
                    'campaign_type': campaign.campaign_type,
                    'start_date': campaign.start_date.isoformat() if campaign.start_date else None,
                    'end_date': campaign.end_date.isoformat() if campaign.end_date else None,
                    'budget': float(campaign.budget),
                    'actual_spend': float(campaign.actual_spend),
                    'target_revenue': float(campaign.target_revenue) if campaign.target_revenue else None,
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
            }
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
        
        campaign = Campaign.objects.create(
            name=data.get('name', 'New Campaign'),
            description=data.get('description', ''),
            status=data.get('status', 'draft'),
            campaign_type=data.get('campaign_type', 'email'),
            start_date=data.get('start_date'),
            end_date=data.get('end_date'),
            budget=data.get('budget', 0),
            target_revenue=data.get('target_revenue'),
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

