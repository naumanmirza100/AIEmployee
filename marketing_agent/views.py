from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseRedirect, HttpResponse
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.urls import reverse
from core.models import UserProfile
from project_manager_agent.ai_agents.agents_registry import AgentRegistry
import json
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

from .models import Campaign, MarketResearch, CampaignPerformance, Lead, EmailTemplate, EmailSequence, EmailSequenceStep, EmailSendHistory, EmailAccount, MarketingNotification
from django.db.models import Sum, Avg, Count, F
from decimal import Decimal
from datetime import timedelta, datetime
from django.utils import timezone
from django.utils.dateparse import parse_date
import pandas as pd
import csv
from io import StringIO


def auto_pause_expired_campaigns(user=None):
    """
    Automatically pause campaigns and their sequences when end_date has passed.
    
    Args:
        user: Optional User instance to filter campaigns by owner. If None, checks all campaigns.
    
    Returns:
        dict: Summary of paused campaigns and sequences
    """
    today = timezone.now().date()
    paused_campaigns = []
    paused_sequences = []
    
    # Get campaigns that have passed their end date
    campaigns_query = Campaign.objects.filter(
        end_date__lt=today,
        status__in=['active', 'scheduled']  # Only pause active or scheduled campaigns
    )
    
    if user:
        campaigns_query = campaigns_query.filter(owner=user)
    
    expired_campaigns = campaigns_query.all()
    
    for campaign in expired_campaigns:
        # Pause the campaign
        old_status = campaign.status
        campaign.status = 'paused'
        campaign.save()
        paused_campaigns.append({
            'id': campaign.id,
            'name': campaign.name,
            'old_status': old_status,
            'end_date': campaign.end_date
        })
        
        # Pause all email sequences for this campaign
        sequences = EmailSequence.objects.filter(campaign=campaign, is_active=True)
        for sequence in sequences:
            sequence.is_active = False
            sequence.save()
            paused_sequences.append({
                'id': sequence.id,
                'name': sequence.name,
                'campaign_id': campaign.id,
                'campaign_name': campaign.name
            })
    
    return {
        'campaigns_paused': len(paused_campaigns),
        'sequences_paused': len(paused_sequences),
        'paused_campaigns': paused_campaigns,
        'paused_sequences': paused_sequences
    }


@login_required
def marketing_dashboard(request):
    """Main marketing agent dashboard - shows available agents"""
    # Auto-pause expired campaigns when accessing dashboard
    auto_pause_expired_campaigns(user=request.user)
    
    # DEBUG: Force output to terminal
    print("\n" + "=" * 60)
    print("🔥🔥🔥 marketing_dashboard VIEW CALLED! 🔥🔥🔥")
    print(f"Request path: {request.path}")
    print(f"User: {request.user.username}")
    print(f"User authenticated: {request.user.is_authenticated}")
    print("=" * 60 + "\n")
    import sys
    sys.stderr.write("\n" + "=" * 60 + "\n")
    sys.stderr.write("marketing_dashboard VIEW CALLED (stderr)!\n")
    sys.stderr.write(f"Request path: {request.path}\n")
    sys.stderr.write(f"User: {request.user.username}\n")
    sys.stderr.write("=" * 60 + "\n\n")
    
    # Check if user is a marketing agent
    try:
        profile = request.user.profile
        if not profile.is_marketing_agent() and not (request.user.is_superuser or request.user.is_staff):
            messages.error(request, 'Access denied. This dashboard is only available to Marketing Agents.')
            return redirect('dashboard')
    except UserProfile.DoesNotExist:
        messages.error(request, 'Access denied. Please complete your profile setup.')
        return redirect('dashboard')
    
    # For admin users, check session role
    if request.user.is_superuser or request.user.is_staff:
        selected_role = request.session.get('selected_role')
        if selected_role != 'marketing_agent':
            messages.error(request, 'Access denied. Please select "Marketing Agent" role to access this dashboard.')
            return redirect('select_role')
    
    # Get user's marketing data
    campaigns = Campaign.objects.filter(owner=request.user)
    recent_research = MarketResearch.objects.filter(created_by=request.user).order_by('-created_at')[:5]
    
    # Get available agents from registry
    all_agents = AgentRegistry.list_agents()
    marketing_agents = [
        agent for agent in all_agents 
        if agent.startswith('marketing') or agent in ['market_research', 'campaign', 'notification', 'outreach_campaign']
    ]
    
    # Get campaign stats
    active_campaigns = campaigns.filter(status='active').count()
    total_budget = sum(float(c.budget) for c in campaigns)
    total_spend = sum(float(c.actual_spend) for c in campaigns)
    
    print(f"Rendering template: marketing/dashboard.html")
    print(f"Campaigns found: {campaigns.count()}")
    print("=" * 60 + "\n")
    sys.stderr.write(f"Rendering template: marketing/dashboard.html\n")
    sys.stderr.write(f"Campaigns found: {campaigns.count()}\n")
    sys.stderr.write("=" * 60 + "\n\n")
    
    return render(request, 'marketing/dashboard.html', {
        'campaigns': campaigns[:10],  # Recent campaigns
        'recent_research': recent_research,
        'available_agents': marketing_agents,
        'stats': {
            'total_campaigns': campaigns.count(),
            'active_campaigns': active_campaigns,
            'total_budget': total_budget,
            'total_spend': total_spend,
            'budget_remaining': total_budget - total_spend,
        }
    })


@login_required
@require_http_methods(["POST"])
def test_marketing_qa(request):
    """Test Marketing Q&A Agent"""
    try:
        agent = AgentRegistry.get_agent("marketing_qa")
        data = json.loads(request.body)
        question = data.get('question', '')
        
        if not question:
            return JsonResponse({
                'success': False,
                'error': 'Question is required'
            }, status=400)
        
        # Process with agent
        result = agent.process(
            question=question,
            user_id=request.user.id
        )
        
        return JsonResponse(result)
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["POST"])
def test_market_research(request):
    """Test Market Research Agent"""
    try:
        agent = AgentRegistry.get_agent("market_research")
        data = json.loads(request.body)
        
        research_type = data.get('research_type', 'market_trend')
        topic = data.get('topic', '')
        
        if not topic:
            return JsonResponse({
                'success': False,
                'error': 'Research topic is required'
            }, status=400)
        
        # Optional context
        additional_context = data.get('context', {})
        
        # Process with agent
        result = agent.process(
            research_type=research_type,
            topic=topic,
            user_id=request.user.id,
            additional_context=additional_context
        )
        
        return JsonResponse(result)
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["POST"])
def test_outreach_campaign(request):
    """Test Outreach & Campaign Agent"""
    try:
        agent = AgentRegistry.get_agent("outreach_campaign")
        
        # Handle FormData (file upload) or JSON
        # Check content_type first to avoid accessing request.body when handling FormData
        content_type = request.content_type or ''
        if 'multipart/form-data' in content_type:
            # FormData request (file upload)
            action = request.POST.get('action', 'design')
            campaign_data_str = request.POST.get('campaign_data', '{}')
            try:
                campaign_data = json.loads(campaign_data_str)
            except:
                campaign_data = {}
            
            context_str = request.POST.get('context', '{}')
            try:
                context = json.loads(context_str)
            except:
                context = {}
            
            campaign_id = request.POST.get('campaign_id')
            if campaign_id:
                try:
                    campaign_id = int(campaign_id)
                except:
                    campaign_id = None
        else:
            # JSON request
            data = json.loads(request.body)
            action = data.get('action', 'design')
            campaign_data = data.get('campaign_data', {})
            campaign_id = data.get('campaign_id')
            context = data.get('context', {})
        
        if not action:
            return JsonResponse({
                'success': False,
                'error': 'Action is required'
            }, status=400)
        
        # Get leads file if present (for create_multi_channel and launch)
        leads_file = request.FILES.get('file') if 'file' in request.FILES else None
        
        # Process with agent - need to pass leads_file for create_multi_channel and launch
        if action == 'create_multi_channel' and leads_file:
            # Call create_multi_channel_campaign directly with file
            result = agent.create_multi_channel_campaign(
                user_id=request.user.id,
                campaign_data=campaign_data,
                context=context,
                leads_file=leads_file
            )
        elif action == 'launch' and leads_file:
            # Call launch_campaign directly with file
            result = agent.launch_campaign(
                campaign_id=campaign_id,
                user_id=request.user.id,
                campaign_data=campaign_data,
                context=context,
                leads_file=leads_file
            )
        else:
            # Use process method for other actions
            result = agent.process(
                action=action,
                user_id=request.user.id,
                campaign_data=campaign_data,
                campaign_id=campaign_id,
                context=context
            )
        
        print("result test_outreach_campaign", result)
        return JsonResponse(result)
        
    except Exception as e:
        print("error test_outreach_campaign", e)
        import traceback
        return JsonResponse({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc() if settings.DEBUG else None
        }, status=500)


@login_required
def documents_list(request):
    """List all marketing documents for the current user"""
    from marketing_agent.models import MarketingDocument
    from project_manager_agent.ai_agents.agents_registry import AgentRegistry
    
    documents = MarketingDocument.objects.filter(created_by=request.user).order_by('-created_at')
    
    # Get document type filter
    document_type = request.GET.get('type', '')
    if document_type:
        documents = documents.filter(document_type=document_type)
    
    # Get campaign filter
    campaign_id = request.GET.get('campaign_id', '')
    if campaign_id:
        try:
            documents = documents.filter(campaign_id=int(campaign_id))
        except ValueError:
            pass
    
    return render(request, 'marketing/documents_list.html', {
        'documents': documents,
        'document_types': MarketingDocument.DOCUMENT_TYPE_CHOICES,
        'campaigns': Campaign.objects.filter(owner=request.user),
        'selected_type': document_type,
        'selected_campaign_id': campaign_id,
    })


@login_required
def document_detail(request, document_id):
    """View a specific marketing document"""
    from marketing_agent.models import MarketingDocument
    from marketing_agent.document_generator import DocumentGenerator
    
    document = get_object_or_404(MarketingDocument, id=document_id, created_by=request.user)
    
    # Get available download formats
    available_formats = DocumentGenerator.get_available_formats(document.document_type)
    
    return render(request, 'marketing/document_detail.html', {
        'document': document,
        'available_formats': available_formats,
    })


@login_required
def document_download(request, document_id, format_type):
    """Download document in specified format"""
    from marketing_agent.models import MarketingDocument
    from marketing_agent.document_generator import DocumentGenerator
    
    document = get_object_or_404(MarketingDocument, id=document_id, created_by=request.user)
    
    try:
        if format_type == 'pdf':
            return DocumentGenerator.generate_pdf(document)
        elif format_type == 'docx':
            return DocumentGenerator.generate_docx(document)
        elif format_type == 'pptx':
            if document.document_type != 'presentation':
                return JsonResponse({'error': 'PPTX format is only available for presentations'}, status=400)
            return DocumentGenerator.generate_pptx(document)
        else:
            return JsonResponse({'error': f'Unsupported format: {format_type}'}, status=400)
    except ImportError as e:
        return JsonResponse({'error': str(e)}, status=500)
    except Exception as e:
        return JsonResponse({'error': f'Error generating document: {str(e)}'}, status=500)


@login_required
@require_http_methods(["POST"])
def test_document_authoring(request):
    """Test Document Authoring Agent"""
    try:
        agent = AgentRegistry.get_agent("document_authoring")
        data = json.loads(request.body)
        
        action = data.get('action', 'create')
        document_type = data.get('document_type', 'strategy')
        document_data = data.get('document_data', {})
        campaign_id = data.get('campaign_id')
        context = data.get('context', {})
        
        if not document_type:
            return JsonResponse({
                'success': False,
                'error': 'document_type is required'
            }, status=400)
        
        # Process with agent
        result = agent.process(
            action=action,
            user_id=request.user.id,
            document_type=document_type,
            document_data=document_data,
            campaign_id=campaign_id,
            context=context
        )
        
        return JsonResponse(result)
        
    except Exception as e:
        import traceback
        return JsonResponse({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc() if settings.DEBUG else None
        }, status=500)


@login_required
@require_http_methods(["POST"])
def test_proactive_notification(request):
    """Test Proactive Notification Agent"""
    try:
        agent = AgentRegistry.get_agent("proactive_notification")
        data = json.loads(request.body)
        
        action = data.get('action', 'monitor')
        campaign_id = data.get('campaign_id')
        context = data.get('context', {})
        
        # Process with agent
        result = agent.process(
            action=action,
            user_id=request.user.id,
            campaign_id=campaign_id,
            context=context
        )
        
        return JsonResponse(result)
        
    except Exception as e:
        import traceback
        return JsonResponse({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc() if settings.DEBUG else None
        }, status=500)


@login_required
@require_http_methods(["GET"])
def get_notifications(request):
    """Get notifications for the current user"""
    try:
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
            user_id=request.user.id,
            unread_only=unread_only,
            notification_type=notification_type,
            campaign_id=campaign_id
        )
        
        return JsonResponse(result)
        
    except Exception as e:
        import traceback
        return JsonResponse({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc() if settings.DEBUG else None
        }, status=500)


@login_required
@require_http_methods(["POST"])
def mark_notification_read(request, notification_id):
    """Mark a notification as read"""
    try:
        notification = MarketingNotification.objects.get(
            id=notification_id,
            user=request.user
        )
        notification.mark_as_read()
        
        return JsonResponse({
            'success': True,
            'message': 'Notification marked as read'
        })
        
    except MarketingNotification.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Notification not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["POST"])
def delete_notification(request, notification_id):
    """Delete a notification"""
    try:
        notification = MarketingNotification.objects.get(
            id=notification_id,
            user=request.user
        )
        notification.delete()
        
        return JsonResponse({
            'success': True,
            'message': 'Notification deleted successfully'
        })
        
    except MarketingNotification.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Notification not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
def marketing_agents_test(request):
    """Marketing agents testing interface"""
    # Auto-pause expired campaigns when accessing agents test page
    auto_pause_expired_campaigns(user=request.user)
    
    import sys
    print("=" * 50, file=sys.stderr)
    print("marketing_agents_test VIEW CALLED!", file=sys.stderr)
    print(f"Request path: {request.path}", file=sys.stderr)
    print("=" * 50, file=sys.stderr)
    
    # Check access
    try:
        profile = request.user.profile
        if not profile.is_marketing_agent() and not (request.user.is_superuser or request.user.is_staff):
            messages.error(request, 'Access denied.')
            return redirect('dashboard')
    except UserProfile.DoesNotExist:
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    
    # Get campaigns for context
    campaigns = Campaign.objects.filter(owner=request.user)
    
    # Get available marketing agents
    all_agents = AgentRegistry.list_agents()
    marketing_agents = [
        agent for agent in all_agents 
        if agent.startswith('marketing') or agent in ['market_research', 'campaign', 'notification', 'outreach_campaign']
    ]
    
    print(f"Rendering template: marketing/agents_test.html", file=sys.stderr)
    print("=" * 50, file=sys.stderr)
    
    # Get email accounts
    email_accounts = EmailAccount.objects.filter(owner=request.user).order_by('-is_default', '-is_active', '-created_at')
    
    response = render(request, 'marketing/agents_test.html', {
        'campaigns': campaigns.order_by('-created_at'),
        'available_agents': marketing_agents,
        'email_accounts': email_accounts,
    })
    
    # Add cache-busting headers to prevent browser caching
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    
    return response


@login_required
def get_campaign_details(request, campaign_id):
    """Get campaign details by ID for auto-filling forms"""
    import sys
    print(f"=== get_campaign_details called ===", file=sys.stderr)
    print(f"campaign_id: {campaign_id}", file=sys.stderr)
    print(f"request.method: {request.method}", file=sys.stderr)
    print(f"request.user: {request.user}", file=sys.stderr)
    
    # Only allow GET requests
    if request.method != 'GET':
        return JsonResponse({
            'success': False,
            'error': 'Method not allowed. Only GET requests are supported.'
        }, status=405)
    
    try:
        # Get campaign - must belong to the current user
        print(f"Looking for campaign ID: {campaign_id}, owner: {request.user.id}", file=sys.stderr)
        campaign = Campaign.objects.get(id=campaign_id, owner=request.user)
        print(f"Found campaign: {campaign.name}", file=sys.stderr)
        # Helper function to safely convert values
        def safe_value(value, convert_float=False):
            if value is None:
                return None
            if convert_float:
                try:
                    return float(value)
                except (ValueError, TypeError):
                    return None
            return str(value) if value else None
        print(f"Campaign: {campaign}", file=sys.stderr)
        # Build response with all campaign data
        campaign_data = {
            'id': campaign.id,
            'name': safe_value(campaign.name) or '',
            'description': safe_value(campaign.description) or '',
            'campaign_type': safe_value(campaign.campaign_type) or '',
            'budget': safe_value(campaign.budget, convert_float=True),
            'target_revenue': safe_value(campaign.target_revenue, convert_float=True),
            'target_leads': campaign.target_leads if campaign.target_leads is not None else None,
            'target_conversions': campaign.target_conversions if campaign.target_conversions is not None else None,
            'age_range': safe_value(campaign.age_range) or '',
            'location': safe_value(campaign.location) or '',
            'interests': safe_value(campaign.interests) or '',
            'industry': safe_value(campaign.industry) or '',
            'company_size': safe_value(campaign.company_size) or '',
            'language': safe_value(campaign.language) or '',
            'start_date': campaign.start_date.strftime('%Y-%m-%d') if campaign.start_date else None,
            'end_date': campaign.end_date.strftime('%Y-%m-%d') if campaign.end_date else None,
            'status': safe_value(campaign.status) or '',
            'channels': campaign.channels if campaign.channels else [],
            'goals': campaign.goals if campaign.goals else {},
            'target_audience': campaign.target_audience if campaign.target_audience else {},
        }
        print(f"Returning campaign data: {campaign_data}", file=sys.stderr)
        return JsonResponse({
            'success': True,
            'campaign': campaign_data
        })
        
    except Campaign.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Campaign not found'
        }, status=404)
    except Exception as e:
        import traceback
        return JsonResponse({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc() if settings.DEBUG else None
        }, status=500)


@login_required
def campaigns_list(request):
    """List all campaigns for the current user"""
    # Auto-pause expired campaigns before listing
    auto_pause_expired_campaigns(user=request.user)
    
    campaigns = Campaign.objects.filter(owner=request.user).order_by('-created_at')
    
    # Count active campaigns
    active_count = 0
    for campaign in campaigns:
        if campaign.status == 'active':
            active_count += 1
    
    return render(request, 'marketing/campaigns_list.html', {
        'campaigns': campaigns,
        'active_count': active_count,
    })


@login_required
def campaign_detail(request, campaign_id):
    """View campaign details with analytics"""
    # Auto-pause expired campaigns before showing details
    auto_pause_expired_campaigns(user=request.user)
    
    campaign = get_object_or_404(Campaign, id=campaign_id, owner=request.user)
    leads = campaign.leads.all().order_by('-created_at')
    
    # Get performance metrics
    performance_metrics = campaign.performance_metrics.all()
    
    # Calculate key analytics
    analytics = {
        'impressions': performance_metrics.filter(metric_name='impressions').aggregate(total=Sum('metric_value'))['total'] or Decimal('0'),
        'clicks': performance_metrics.filter(metric_name='clicks').aggregate(total=Sum('metric_value'))['total'] or Decimal('0'),
        'conversions': performance_metrics.filter(metric_name='conversions').aggregate(total=Sum('metric_value'))['total'] or Decimal('0'),
        'revenue': performance_metrics.filter(metric_name='revenue').aggregate(total=Sum('metric_value'))['total'] or Decimal('0'),
        'open_rate': performance_metrics.filter(metric_name='open_rate').aggregate(avg=Avg('metric_value'))['avg'],
        'click_through_rate': performance_metrics.filter(metric_name='click_through_rate').aggregate(avg=Avg('metric_value'))['avg'],
        'engagement_rate': performance_metrics.filter(metric_name='engagement').aggregate(avg=Avg('metric_value'))['avg'],
        'cac': performance_metrics.filter(metric_name='cac').aggregate(avg=Avg('metric_value'))['avg'],
    }
    
    # Calculate derived metrics
    total_impressions = float(analytics['impressions']) if analytics['impressions'] else 0
    total_clicks = float(analytics['clicks']) if analytics['clicks'] else 0
    total_conversions = float(analytics['conversions']) if analytics['conversions'] else 0
    total_revenue = float(analytics['revenue']) if analytics['revenue'] else 0
    
    # Calculate rates (use actual metrics if available, otherwise calculate from totals)
    analytics['ctr'] = float(analytics['click_through_rate']) if analytics['click_through_rate'] else (total_clicks / total_impressions * 100 if total_impressions > 0 else 0)
    analytics['conversion_rate'] = (total_conversions / total_clicks * 100) if total_clicks > 0 else 0
    analytics['engagement'] = float(analytics['engagement_rate']) if analytics['engagement_rate'] else analytics['ctr']
    
    # Calculate ROI
    roi = campaign.get_roi()
    analytics['roi'] = roi if roi is not None else 0
    
    # Calculate budget utilization
    budget_utilization = (float(campaign.actual_spend) / float(campaign.budget) * 100) if float(campaign.budget) > 0 else 0
    analytics['budget_utilization'] = budget_utilization
    analytics['budget_remaining'] = float(campaign.budget) - float(campaign.actual_spend)
    
    # Get target values for comparison
    analytics['target_revenue'] = float(campaign.target_revenue) if campaign.target_revenue else None
    analytics['target_leads'] = campaign.target_leads
    analytics['target_conversions'] = campaign.target_conversions
    
    # Calculate progress towards targets
    if analytics['target_revenue']:
        analytics['revenue_progress'] = (total_revenue / analytics['target_revenue'] * 100) if analytics['target_revenue'] > 0 else 0
    else:
        analytics['revenue_progress'] = None
    
    if analytics['target_conversions']:
        analytics['conversion_progress'] = (total_conversions / analytics['target_conversions'] * 100) if analytics['target_conversions'] > 0 else 0
    else:
        analytics['conversion_progress'] = None
    
    if analytics['target_leads']:
        analytics['leads_progress'] = (leads.count() / analytics['target_leads'] * 100) if analytics['target_leads'] > 0 else 0
    else:
        analytics['leads_progress'] = None
    
    # Get recent performance data for charts (last 30 days)
    thirty_days_ago = timezone.now().date() - timedelta(days=30)
    recent_metrics = performance_metrics.filter(date__gte=thirty_days_ago).order_by('date')
    
    # Prepare chart data
    metrics_by_date = {}
    for metric in recent_metrics:
        date_str = metric.date.strftime('%Y-%m-%d')
        if date_str not in metrics_by_date:
            metrics_by_date[date_str] = {'impressions': 0, 'clicks': 0, 'conversions': 0, 'revenue': 0}
        
        if metric.metric_name == 'impressions':
            metrics_by_date[date_str]['impressions'] += float(metric.metric_value)
        elif metric.metric_name == 'clicks':
            metrics_by_date[date_str]['clicks'] += float(metric.metric_value)
        elif metric.metric_name == 'conversions':
            metrics_by_date[date_str]['conversions'] += float(metric.metric_value)
        elif metric.metric_name == 'revenue':
            metrics_by_date[date_str]['revenue'] += float(metric.metric_value)
    
    # Convert to arrays for chart (JSON serializable)
    sorted_dates = sorted(metrics_by_date.keys())
    dates_formatted = []
    impressions_list = []
    clicks_list = []
    conversions_list = []
    revenue_list = []
    
    for date_str in sorted_dates:
        # Format date for display (short format)
        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            dates_formatted.append(date_obj.strftime('%b %d'))
        except:
            dates_formatted.append(date_str)
        impressions_list.append(metrics_by_date[date_str]['impressions'])
        clicks_list.append(metrics_by_date[date_str]['clicks'])
        conversions_list.append(metrics_by_date[date_str]['conversions'])
        revenue_list.append(metrics_by_date[date_str]['revenue'])
    
    # Get email templates and sequences
    email_templates = EmailTemplate.objects.filter(campaign=campaign).order_by('followup_sequence_number', 'created_at')
    email_sequences = EmailSequence.objects.filter(campaign=campaign, is_active=True)
    has_active_sequence = email_sequences.exists()
    
    # Check if campaign has email templates (required for launch)
    has_email_templates = email_templates.filter(is_active=True).exists()
    
    # Get email send history (recent sends)
    # Order by sent_at for sent emails (newest first), then by created_at for pending emails
    # For campaign detail page: Show only recent emails (last 10) for summary view
    recent_email_sends = EmailSendHistory.objects.filter(campaign=campaign).order_by(
        '-sent_at',
        '-created_at'
    )[:10]  # Only last 10 for summary
    
    # Calculate stats - 'sent' and 'delivered' are treated the same (emails are set to 'sent' on successful send)
    email_stats = {
        'total_sent': EmailSendHistory.objects.filter(campaign=campaign, status__in=['sent', 'delivered', 'opened', 'clicked']).count(),
        'total_opened': EmailSendHistory.objects.filter(campaign=campaign, status__in=['opened', 'clicked']).count(),
        'total_clicked': EmailSendHistory.objects.filter(campaign=campaign, status='clicked').count(),
        'total_failed': EmailSendHistory.objects.filter(campaign=campaign, status='failed').count(),
        'total_bounced': EmailSendHistory.objects.filter(campaign=campaign, status='bounced').count(),
    }
    
    # Convert chart data to JSON for template
    analytics['chart_data'] = {
        'dates': json.dumps(dates_formatted),
        'impressions': json.dumps(impressions_list),
        'clicks': json.dumps(clicks_list),
        'conversions': json.dumps(conversions_list),
        'revenue': json.dumps(revenue_list),
    }
    
    return render(request, 'marketing/campaign_detail.html', {
        'campaign': campaign,
        'leads': leads,
        'analytics': analytics,
        'email_templates': email_templates,
        'email_sequences': email_sequences,
        'has_email_templates': has_email_templates,
        'has_active_sequence': has_active_sequence,
        'email_sends': recent_email_sends,  # Only recent 10 for summary
        'email_stats': email_stats,
    })


@login_required
@require_http_methods(["POST"])
def campaign_stop(request, campaign_id):
    """Stop an active campaign"""
    campaign = get_object_or_404(Campaign, id=campaign_id, owner=request.user)
    
    if campaign.status != 'active':
        messages.error(request, f'Campaign "{campaign.name}" is not active and cannot be stopped.')
        return redirect('campaign_detail', campaign_id=campaign.id)
    
    campaign.status = 'paused'
    campaign.save()
    messages.success(request, f'Campaign "{campaign.name}" has been stopped successfully.')
    return redirect('campaign_detail', campaign_id=campaign.id)


@login_required
@require_http_methods(["POST"])
def campaign_delete(request, campaign_id):
    """Delete a campaign"""
    campaign = get_object_or_404(Campaign, id=campaign_id, owner=request.user)
    campaign_name = campaign.name
    campaign.delete()
    messages.success(request, f'Campaign "{campaign_name}" has been deleted successfully.')
    return redirect('campaigns_list')


@login_required
def campaign_edit(request, campaign_id):
    """Edit campaign page"""
    campaign = get_object_or_404(Campaign, id=campaign_id, owner=request.user)
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body) if request.content_type == 'application/json' else request.POST
            
            # Update campaign fields
            campaign.name = data.get('name', campaign.name)
            campaign.description = data.get('description', campaign.description)
            campaign.campaign_type = data.get('campaign_type', campaign.campaign_type)
            campaign.status = data.get('status', campaign.status)
            campaign.budget = data.get('budget', campaign.budget)
            campaign.target_revenue = data.get('target_revenue') or None
            campaign.target_leads = data.get('target_leads') or None
            campaign.target_conversions = data.get('target_conversions') or None
            campaign.age_range = data.get('age_range', '')
            campaign.location = data.get('location', '')
            campaign.industry = data.get('industry', '')
            campaign.interests = data.get('interests', '')
            campaign.company_size = data.get('company_size', '')
            campaign.language = data.get('language', '')
            
            if data.get('start_date'):
                try:
                    from datetime import datetime
                    campaign.start_date = datetime.strptime(data.get('start_date'), '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    pass
            
            if data.get('end_date'):
                try:
                    from datetime import datetime
                    campaign.end_date = datetime.strptime(data.get('end_date'), '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    pass
            
            campaign.save()
            
            if request.content_type == 'application/json':
                return JsonResponse({
                    'success': True,
                    'message': 'Campaign updated successfully',
                    'campaign_id': campaign.id
                })
            else:
                messages.success(request, 'Campaign updated successfully.')
                return redirect('campaign_detail', campaign_id=campaign.id)
        
        except Exception as e:
            if request.content_type == 'application/json':
                return JsonResponse({
                    'success': False,
                    'error': str(e)
                }, status=400)
            else:
                messages.error(request, f'Error updating campaign: {str(e)}')
                return redirect('campaign_edit', campaign_id=campaign.id)
    
    return render(request, 'marketing/campaign_edit.html', {
        'campaign': campaign,
    })


@login_required
@require_http_methods(["POST"])
def upload_leads(request, campaign_id):
    """Upload leads from CSV/Excel file"""
    import logging
    logger = logging.getLogger(__name__)
    print("upload_leads", request)
    try:
        campaign = get_object_or_404(Campaign, id=campaign_id, owner=request.user)
        logger.info(f'Upload leads request for campaign {campaign_id} by user {request.user.username}')
        print("request.FILES", request.FILES, '\n\n\n')
        if 'file' not in request.FILES:
            logger.warning('No file in request.FILES')
            print("No file in request.FILES")
            return JsonResponse({'success': False, 'error': 'No file uploaded'}, status=400)
        
        uploaded_file = request.FILES['file']
        logger.info(f'File received: {uploaded_file.name}, size: {uploaded_file.size}')
        
        file_extension = uploaded_file.name.split('.')[-1].lower()
        
        if file_extension not in ['csv', 'xlsx', 'xls']:
            logger.warning(f'Invalid file format: {file_extension}')
            return JsonResponse({'success': False, 'error': 'Invalid file format. Please upload CSV, XLSX, or XLS files.'}, status=400)
        
        try:
            # Read the file
            if file_extension == 'csv':
                df = pd.read_csv(uploaded_file)
            else:
                df = pd.read_excel(uploaded_file)
        
            if df.empty:
                return JsonResponse({'success': False, 'error': 'File is empty'}, status=400)
            
            # Normalize column names (lowercase, strip spaces)
            df.columns = df.columns.str.lower().str.strip()
            print("column",df.columns)
            # Required: email
            if 'email' not in df.columns:
                print("Email column is required in the file")
                return JsonResponse({'success': False, 'error': 'Email column is required in the file'}, status=400)
            # Process leads
            created_count = 0
            updated_count = 0
            skipped_count = 0
            errors = []
            
            # Use transaction to ensure all leads are saved before returning
            from django.db import transaction
            from django.db import connection
            
            with transaction.atomic():
                for index, row in df.iterrows():
                    try:
                        print(f"\n=== Processing Row {index + 2} ===")
                        email = str(row['email']).strip().lower()
                        print(f"email: {email}")
                        if not email or pd.isna(row['email']) or email == 'nan':
                            logger.warning(f'Row {index + 2}: Skipping row with empty/invalid email: {row.get("email", "N/A")}')
                            skipped_count += 1
                            continue
                        
                        # Get or create lead
                        lead, created = Lead.objects.get_or_create(
                            email=email,
                            owner=request.user,
                            defaults={
                                'first_name': str(row.get('first_name', '')).strip() if pd.notna(row.get('first_name')) else '',
                                'last_name': str(row.get('last_name', '')).strip() if pd.notna(row.get('last_name')) else '',
                                'phone': str(row.get('phone', '')).strip() if pd.notna(row.get('phone')) else '',
                                'company': str(row.get('company', '')).strip() if pd.notna(row.get('company')) else '',
                                'job_title': str(row.get('job_title', '')).strip() if pd.notna(row.get('job_title')) else '',
                                'source': str(row.get('source', '')).strip() if pd.notna(row.get('source')) else '',
                            }
                        )
                        print(f"lead: {lead.email} - {'New' if created else 'Existing'}")
                        if created:
                            created_count += 1
                            print(f"✓ Lead {email} CREATED (count: {created_count})")
                        else:
                            print(f"✓ Lead {email} already EXISTS")
                            print(f"Updating lead {email}...")
                            # Update existing lead fields if empty
                            updated = False
                            if not lead.first_name and pd.notna(row.get('first_name')):
                                lead.first_name = str(row.get('first_name', '')).strip()
                                updated = True
                            if not lead.last_name and pd.notna(row.get('last_name')):
                                lead.last_name = str(row.get('last_name', '')).strip()
                                updated = True
                            if not lead.phone and pd.notna(row.get('phone')):
                                lead.phone = str(row.get('phone', '')).strip()
                                updated = True
                            if not lead.company and pd.notna(row.get('company')):
                                lead.company = str(row.get('company', '')).strip()
                                updated = True
                            if not lead.job_title and pd.notna(row.get('job_title')):
                                lead.job_title = str(row.get('job_title', '')).strip()
                                updated = True
                            if updated:
                                lead.save()
                                updated_count += 1
                                print(f"✓ Lead {email} UPDATED (count: {updated_count})")
                            else:
                                print(f"✓ Lead {email} already UPDATED")
                        
                        # Always associate with campaign (even if lead already exists)
                        # Don't check inside transaction - just add (it's safe to add even if already there)
                        print(f"Adding lead {email} to campaign {campaign.id}...")
                        campaign.leads.add(lead)  # ManyToMany.add() is safe to call even if already added
                        print(f"✓ Added lead {email} to campaign")
                        logger.info(f'DEBUG Row {index + 2}: Added lead {email} to campaign {campaign.id}')
                        # Count as added to campaign if it wasn't newly created
                        if not created:
                            created_count += 1  # Count as "added to campaign"
                        
                        # Always ensure CampaignContact exists for automation tracking
                        from marketing_agent.models import CampaignContact, EmailSequence
                        from django.utils import timezone
                        from django.core.exceptions import MultipleObjectsReturned
                        print(f"Creating CampaignContact for {email}...")
                        try:
                            # Use filter().first() to safely check for existing contact
                            # This handles cases where duplicates might exist
                            contact = CampaignContact.objects.filter(
                                campaign=campaign,
                                lead=lead
                            ).first()
                            
                            if not contact:
                                # Create new contact if it doesn't exist
                                contact = CampaignContact.objects.create(
                                    campaign=campaign,
                                    lead=lead,
                                    sequence=campaign.email_sequences.filter(is_active=True).first(),
                                    current_step=0,
                                    started_at=timezone.now(),
                                )
                                print(f"✓ CampaignContact created for {email}")
                            else:
                                print(f"✓ CampaignContact already exists for {email}")
                        except MultipleObjectsReturned:
                            # If duplicates exist, just use the first one
                            contact = CampaignContact.objects.filter(
                                campaign=campaign,
                                lead=lead
                            ).first()
                            print(f"✓ Using existing CampaignContact for {email} (duplicates found)")
                        except Exception as e:
                            logger.warning(f'Error creating CampaignContact for {email}: {str(e)}')
                            print(f"⚠ Warning creating CampaignContact for {email}: {str(e)}")
                        print(f"=== Row {index + 2} COMPLETE ===\n")
                    except Exception as e:
                        import traceback
                        error_trace = traceback.format_exc()
                        print(f"ERROR processing row {index + 2}: {str(e)}")
                        print(f"Full traceback:\n{error_trace}")
                        logger.error(f'Row {index + 2}: Error processing lead - {str(e)}', exc_info=True)
                        errors.append(f"Row {index + 2}: {str(e)}")
                        skipped_count += 1
            
            # Transaction commits here automatically
            
            # After transaction commits, refresh and ensure CampaignContact exists
            campaign.refresh_from_db()
            
            # Ensure CampaignContact exists for ALL leads in campaign (backfill if needed)
            from marketing_agent.models import CampaignContact, EmailSequence
            from django.utils import timezone
            from django.core.exceptions import MultipleObjectsReturned
            contacts_created = 0
            for lead in campaign.leads.all():
                try:
                    # Use filter().first() to safely check for existing contact
                    contact = CampaignContact.objects.filter(
                        campaign=campaign,
                        lead=lead
                    ).first()
                    
                    if not contact:
                        # Create new contact if it doesn't exist
                        contact = CampaignContact.objects.create(
                    campaign=campaign,
                    lead=lead,
                            sequence=campaign.email_sequences.filter(is_active=True).first(),
                            current_step=0,
                            started_at=timezone.now(),
                        )
                    contacts_created += 1
                except MultipleObjectsReturned:
                    # If duplicates exist, just use the first one (already exists)
                    pass
                except Exception as e:
                    logger.warning(f'Error creating CampaignContact for lead {lead.email}: {str(e)}')
            
            # Force refresh from database to get latest state
            campaign.refresh_from_db()
            
            # Get updated lead count after upload
            updated_lead_count = campaign.leads.count()
            contact_count = CampaignContact.objects.filter(campaign=campaign).count()
            
            # Debug: Log all leads in campaign
            all_leads = list(campaign.leads.all().values_list('email', flat=True))
            logger.info(f'Upload complete: {created_count} created, {updated_count} updated, {skipped_count} skipped, {contacts_created} contacts created, total leads: {updated_lead_count}, total contacts: {contact_count}')
            logger.info(f'DEBUG: All leads in campaign after upload: {all_leads}')
            
            # Double-check by querying the relationship directly
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM marketing_agent_campaign_leads WHERE campaign_id = %s", [campaign.id])
                direct_count = cursor.fetchone()[0]
                logger.info(f'DEBUG: Direct database query shows {direct_count} leads in campaign_leads table')
            
            if updated_lead_count == 0 and created_count > 0:
                logger.error(f'ERROR: Created {created_count} leads but campaign shows 0 leads! This indicates a transaction or save issue.')
            
            # Include detailed error information
            error_message = ''
            if errors:
                error_message = f' Errors: {"; ".join(errors[:5])}'
            if skipped_count > 0:
                if created_count == 0 and updated_count == 0:
                    error_message += f' All {skipped_count} lead(s) were skipped. Possible reasons: emails are empty/invalid, or leads already exist in this campaign. Check CSV format and ensure "Email" column exists.'
                else:
                    error_message += f' {skipped_count} row(s) skipped (empty email or invalid data).'
            
            return JsonResponse({
                'success': True,
                'message': f'Successfully processed {created_count + updated_count} lead(s). Total leads in campaign: {updated_lead_count}.{error_message}',
                'created': created_count,
                'updated': updated_count,
                'skipped': skipped_count,
                'total_leads': updated_lead_count,
                'total_contacts': contact_count,
                'errors': errors[:10]  # Limit errors shown
            })
            
        except Exception as e:
            logger.error(f'Error processing file: {str(e)}', exc_info=True)
            return JsonResponse({'success': False, 'error': f'Error processing file: {str(e)}'}, status=500)
            
    except Exception as e:
        logger.error(f'Error in upload_leads view: {str(e)}', exc_info=True)
        return JsonResponse({'success': False, 'error': f'Error: {str(e)}'}, status=500)


@login_required
@require_http_methods(["POST"])
def add_lead(request, campaign_id):
    """Add a single lead manually"""
    campaign = get_object_or_404(Campaign, id=campaign_id, owner=request.user)
    
    email = request.POST.get('email', '').strip().lower()
    if not email:
        return JsonResponse({'success': False, 'error': 'Email is required'}, status=400)
    
    try:
        lead, created = Lead.objects.get_or_create(
            email=email,
            owner=request.user,
            defaults={
                'first_name': request.POST.get('first_name', '').strip(),
                'last_name': request.POST.get('last_name', '').strip(),
                'phone': request.POST.get('phone', '').strip(),
                'company': request.POST.get('company', '').strip(),
                'job_title': request.POST.get('job_title', '').strip(),
                'source': request.POST.get('source', '').strip(),
            }
        )
        
        if not created:
            # Update existing lead
            if request.POST.get('first_name'):
                lead.first_name = request.POST.get('first_name', '').strip()
            if request.POST.get('last_name'):
                lead.last_name = request.POST.get('last_name', '').strip()
            if request.POST.get('phone'):
                lead.phone = request.POST.get('phone', '').strip()
            if request.POST.get('company'):
                lead.company = request.POST.get('company', '').strip()
            if request.POST.get('job_title'):
                lead.job_title = request.POST.get('job_title', '').strip()
            if request.POST.get('source'):
                lead.source = request.POST.get('source', '').strip()
            lead.save()
        
        # Associate with campaign
        if campaign not in lead.campaigns.all():
            campaign.leads.add(lead)
            # Create CampaignContact for automation tracking
            from marketing_agent.models import CampaignContact, EmailSequence
            CampaignContact.objects.get_or_create(
                campaign=campaign,
                lead=lead,
                defaults={
                    'sequence': campaign.email_sequences.filter(is_active=True).first(),
                    'current_step': 0,
                }
            )
        
        return JsonResponse({
            'success': True,
            'message': 'Lead added successfully',
            'lead_id': lead.id
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def edit_lead(request, campaign_id, lead_id):
    """Edit a lead"""
    campaign = get_object_or_404(Campaign, id=campaign_id, owner=request.user)
    lead = get_object_or_404(Lead, id=lead_id, owner=request.user)
    
    try:
        if request.POST.get('email'):
            email = request.POST.get('email', '').strip().lower()
            # Check if email is already taken by another lead
            if Lead.objects.filter(email=email, owner=request.user).exclude(id=lead_id).exists():
                return JsonResponse({'success': False, 'error': 'Email already exists'}, status=400)
            lead.email = email
        
        if request.POST.get('first_name') is not None:
            lead.first_name = request.POST.get('first_name', '').strip()
        if request.POST.get('last_name') is not None:
            lead.last_name = request.POST.get('last_name', '').strip()
        if request.POST.get('phone') is not None:
            lead.phone = request.POST.get('phone', '').strip()
        if request.POST.get('company') is not None:
            lead.company = request.POST.get('company', '').strip()
        if request.POST.get('job_title') is not None:
            lead.job_title = request.POST.get('job_title', '').strip()
        if request.POST.get('source') is not None:
            lead.source = request.POST.get('source', '').strip()
        if request.POST.get('status'):
            lead.status = request.POST.get('status')
        if request.POST.get('notes') is not None:
            lead.notes = request.POST.get('notes', '').strip()
        
        lead.save()
        
        return JsonResponse({
            'success': True,
            'message': 'Lead updated successfully'
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def delete_lead(request, campaign_id, lead_id):
    """Remove a lead from campaign (or delete if no other campaigns)"""
    campaign = get_object_or_404(Campaign, id=campaign_id, owner=request.user)
    lead = get_object_or_404(Lead, id=lead_id, owner=request.user)
    
    try:
        # Remove from campaign
        campaign.leads.remove(lead)
        
        # If lead is not associated with any other campaigns, delete it
        if lead.campaigns.count() == 0:
            lead.delete()
            message = 'Lead deleted successfully'
        else:
            message = 'Lead removed from campaign'
        
        return JsonResponse({
            'success': True,
            'message': message
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def mark_contact_replied(request, campaign_id, lead_id):
    """Mark a contact as having replied - stops automation for this contact and analyzes reply with AI"""
    campaign = get_object_or_404(Campaign, id=campaign_id, owner=request.user)
    lead = get_object_or_404(Lead, id=lead_id, owner=request.user)
    
    try:
        from marketing_agent.models import CampaignContact, EmailSequence
        from marketing_agent.utils.reply_analyzer import ReplyAnalyzer
        
        # Get or create contact (handle multiple contacts per campaign/lead - use first one or create)
        # Note: There can be multiple contacts if lead is in multiple sequences
        contact = CampaignContact.objects.filter(
            campaign=campaign,
            lead=lead
        ).first()
        
        if not contact:
            # Create new contact
            contact = CampaignContact.objects.create(
                campaign=campaign,
                lead=lead,
                current_step=0
            )
            created = True
        else:
            created = False
        
        # Get reply data from request
        if request.content_type == 'application/json':
            data = json.loads(request.body)
            reply_subject = data.get('reply_subject', '')
            reply_content = data.get('reply_content', '')
        else:
            reply_subject = request.POST.get('reply_subject', '')
            reply_content = request.POST.get('reply_content', '')
        
        # Analyze reply with AI if content is provided
        interest_level = 'not_analyzed'
        analysis = ''
        if reply_content or reply_subject:
            try:
                analyzer = ReplyAnalyzer()
                analysis_result = analyzer.analyze_reply(
                    reply_subject=reply_subject,
                    reply_content=reply_content,
                    campaign_name=campaign.name
                )
                interest_level = analysis_result.get('interest_level', 'neutral')
                analysis = analysis_result.get('analysis', '')
                logger.info(f"AI analyzed reply for {lead.email}: {interest_level} (confidence: {analysis_result.get('confidence', 0)}%)")
            except Exception as e:
                logger.error(f"Error analyzing reply with AI: {str(e)}")
                interest_level = 'not_analyzed'
                analysis = f'AI analysis failed: {str(e)}'
        
        # First, determine which sequence this reply is for (to check if it's a sub-sequence reply)
        is_sub_sequence_reply = False
        reply_sequence = None
        reply_sub_sequence = None
        triggering_email = None
        
        try:
            from marketing_agent.models import Reply, EmailSendHistory
            # Try to find the most recent email sent to this lead (the one likely triggering this reply)
            triggering_email = EmailSendHistory.objects.filter(
                campaign=campaign,
                lead=lead
            ).order_by('-sent_at').first()
            
            if triggering_email and triggering_email.email_template:
                # Find which sequence this email template belongs to
                # Check if it's part of a sequence step
                sequence_steps = triggering_email.email_template.sequence_steps.all()
                if sequence_steps.exists():
                    seq_step = sequence_steps.first()
                    reply_sequence = seq_step.sequence
                    # Check if it's a sub-sequence
                    if reply_sequence and reply_sequence.is_sub_sequence:
                        is_sub_sequence_reply = True
                        reply_sub_sequence = reply_sequence
                        reply_sequence = reply_sequence.parent_sequence  # Main sequence
                else:
                    # Fallback: use contact's current sequence
                    reply_sequence = contact.sequence
                    # Check if contact is currently in a sub-sequence
                    if contact.sub_sequence:
                        is_sub_sequence_reply = True
                        reply_sub_sequence = contact.sub_sequence
            else:
                # Fallback: use contact's current sequence
                reply_sequence = contact.sequence
                # Check if contact is currently in a sub-sequence
                if contact.sub_sequence:
                    is_sub_sequence_reply = True
                    reply_sub_sequence = contact.sub_sequence
        except (ImportError, AttributeError, Exception) as e:
            logger.warning(f'Could not determine reply sequence: {str(e)}')
            reply_sequence = contact.sequence
            if contact.sub_sequence:
                is_sub_sequence_reply = True
                reply_sub_sequence = contact.sub_sequence
        
        # Create Reply record to preserve reply history (EACH REPLY IS A SEPARATE RECORD - NO OVERWRITE)
        sub_sequence = None
        try:
            reply_record = Reply.objects.create(
                contact=contact,
                campaign=campaign,
                lead=lead,
                sequence=reply_sequence,
                sub_sequence=reply_sub_sequence,
                reply_subject=reply_subject,
                reply_content=reply_content,
                interest_level=interest_level,
                analysis=analysis,
                triggering_email=triggering_email,
                replied_at=timezone.now()
            )
            logger.info(f"Created Reply record #{reply_record.id} for {lead.email} - {'Sub-sequence reply' if is_sub_sequence_reply else 'Main sequence reply'} (sequence: {reply_sequence.name if reply_sequence else 'None'})")
        except (ImportError, AttributeError, Exception) as e:
            # Reply model doesn't exist yet or migration not applied - skip creating Reply record
            logger.warning(f'Could not create Reply record (model may not exist yet): {str(e)}')
        
        # ONLY start sub-sequence if:
        # 1. This is NOT a reply to a sub-sequence email (is_sub_sequence_reply == False)
        # 2. Contact is NOT already in a sub-sequence
        # 3. This is a reply to a main sequence email
        if not is_sub_sequence_reply and not contact.sub_sequence and contact.sequence:
            # First try to find sub-sequence matching the detected interest level
            target_interest = interest_level if interest_level and interest_level != 'not_analyzed' else 'neutral'
            
            # Map AI interest levels to sub-sequence interest levels
            interest_mapping = {
                'positive': 'positive',
                'negative': 'negative',
                'neutral': 'neutral',
                'not_analyzed': 'any'
            }
            target_interest = interest_mapping.get(target_interest, 'any')
            
            # Look for sub-sequences matching the interest level
            sub_sequences = EmailSequence.objects.filter(
                parent_sequence=contact.sequence,
                is_sub_sequence=True,
                is_active=True,
                interest_level=target_interest
            )
            
            # If no exact match, try 'any'
            if not sub_sequences.exists() and target_interest != 'any':
                sub_sequences = EmailSequence.objects.filter(
                    parent_sequence=contact.sequence,
                    is_sub_sequence=True,
                    is_active=True,
                    interest_level='any'
                )
            
            # If still no match, get any active sub-sequence as fallback
            if not sub_sequences.exists():
                sub_sequences = EmailSequence.objects.filter(
                    parent_sequence=contact.sequence,
                    is_sub_sequence=True,
                    is_active=True
                ).order_by('created_at')
            
            if sub_sequences.exists():
                sub_sequence = sub_sequences.first()
                logger.info(f"Found sub-sequence '{sub_sequence.name}' (interest: {sub_sequence.interest_level}) for contact {lead.email} after main sequence reply (detected interest: {target_interest})")
        
        # Mark as replied - but don't start sub-sequence if it's a sub-sequence reply
        # This updates CampaignContact with the latest reply info (for backward compatibility)
        # BUT won't start a new sub-sequence if replying to sub-sequence email
        contact.mark_replied(
            reply_subject=reply_subject,
            reply_content=reply_content,
            interest_level=interest_level,
            analysis=analysis,
            sub_sequence=sub_sequence if not is_sub_sequence_reply else None  # Only pass sub_sequence if not a sub-sequence reply
        )
        
        if is_sub_sequence_reply:
            message = f'Reply received from {lead.email} for sub-sequence email. Reply recorded (sub-sequence continues).'
        else:
            message = f'Contact {lead.email} marked as replied. Main sequence stopped.'
            if sub_sequence:
                message += f' Sub-sequence "{sub_sequence.name}" started.'
            else:
                message += ' No sub-sequence found.'
        
        return JsonResponse({
            'success': True,
            'message': message,
            'contact_id': contact.id,
            'interest_level': interest_level,
            'analysis': analysis,
            'sub_sequence_started': sub_sequence is not None,
            'sub_sequence_name': sub_sequence.name if sub_sequence else None
        })
        
    except Exception as e:
        logger.error(f"Error marking contact as replied: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@login_required
def export_leads(request, campaign_id):
    """Export leads to CSV"""
    campaign = get_object_or_404(Campaign, id=campaign_id, owner=request.user)
    leads = campaign.leads.all().order_by('-created_at')
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="campaign_{campaign_id}_leads.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Email', 'First Name', 'Last Name', 'Phone', 'Company', 'Job Title', 'Status', 'Source', 'Notes', 'Created At'])
    
    for lead in leads:
        writer.writerow([
            lead.email,
            lead.first_name,
            lead.last_name,
            lead.phone,
            lead.company,
            lead.job_title,
            lead.get_status_display(),
            lead.source,
            lead.notes,
            lead.created_at.strftime('%Y-%m-%d %H:%M:%S')
        ])
    
    return response
