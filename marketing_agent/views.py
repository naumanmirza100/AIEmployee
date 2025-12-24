from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from core.models import UserProfile
from core.ai_agents.agents_registry import AgentRegistry
import json

from .models import Campaign, MarketResearch, CampaignPerformance


@login_required
def marketing_dashboard(request):
    """Main marketing agent dashboard - shows available agents"""
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
        if agent.startswith('marketing') or agent in ['market_research', 'campaign', 'notification']
    ]
    
    # Get campaign stats
    active_campaigns = campaigns.filter(status='active').count()
    total_budget = sum(float(c.budget) for c in campaigns)
    total_spend = sum(float(c.actual_spend) for c in campaigns)
    
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
def marketing_agents_test(request):
    """Marketing agents testing interface"""
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
        if agent.startswith('marketing') or agent in ['market_research', 'campaign', 'notification']
    ]
    
    return render(request, 'marketing/agents_test.html', {
        'campaigns': campaigns,
        'available_agents': marketing_agents
    })
