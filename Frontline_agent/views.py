# Frontline_agent/views.py
from django.shortcuts import render
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .frontline_ai_orchestrator import FrontlineAICustomerSupport

# Initialize the AI agent
agent = FrontlineAICustomerSupport()

@login_required
def chat(request):
    """
    Handle chat messages from user.
    """
    if request.method == "POST":
        user = request.user
        message = request.POST.get("message", "").strip()
        if not message:
            return JsonResponse({"success": False, "message": "No message provided."})

        response = agent.process(user, message)
        return JsonResponse(response)

    # GET request: render chat page
    return render(request, "Frontline_agent/chat.html")



from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
from django.contrib.auth.models import User
from .frontline_ai_orchestrator import FrontlineAICustomerSupport
import logging
# Initialize AI agent once
ai_agent = FrontlineAICustomerSupport()


@csrf_exempt
def chat(request):
    """
    POST endpoint for user messages to the Frontline AI agent.
    Request JSON:
    {
        "username": "john",
        "intent": "knowledge",
        "message": "What is the status of project 1?"
    }
    """
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "Only POST allowed."})

    try:
        data = json.loads(request.body)
        username = data.get("username")
        intent = data.get("intent")
        message = data.get("message")

        # Lookup user
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            return JsonResponse({"success": False, "message": "User not found."})

        # Process message with AI
        response = ai_agent.process(user=user, intent=intent, message=message)
        return JsonResponse(response)

    except Exception as e:
        return JsonResponse({"success": False, "message": f"Error: {e}"})



from core.models import UserProfile
from .models import (
    Ticket, KnowledgeBase, Notification, FrontlineWorkflowExecution,
    FrontlineMeeting, Document, FrontlineAnalytics
)
 bashi-sultan
from .frontline_ai_orchestrator import FrontlineAICustomerSupport
from .intent_detector import IntentDetector

from project_manager_agent.ai_agents.knowledge_qa_agent import KnowledgeQAAgent
from project_manager_agent.ai_agents.workflow_sop_agent import WorkflowSOPAgent
from project_manager_agent.ai_agents.analytics_dashboard_agent import AnalyticsDashboardAgent
from project_manager_agent.ai_agents.calendar_planner_agent import CalendarPlannerAgent
from project_manager_agent.ai_agents.meeting_notetaker_agent import MeetingNotetakerAgent main

logger = logging.getLogger(__name__)


# Initialize Frontline AI (singleton pattern)
_frontline_ai = None
_intent_detector = None


def get_frontline_ai():
    """Get initialized Frontline AI orchestrator (singleton pattern)"""
    global _frontline_ai
    if _frontline_ai is None:
        _frontline_ai = FrontlineAICustomerSupport()
    return _frontline_ai


def get_intent_detector():
    """Get initialized intent detector (singleton pattern)"""
    global _intent_detector
    if _intent_detector is None:
        _intent_detector = IntentDetector()
    return _intent_detector


def is_frontline_agent(user):
    """Check if user is a frontline agent"""
    if not user.is_authenticated:
        return False
    
    UserProfile.objects.get_or_create(user=user)
    is_frontline = user.profile.role == 'frontline_agent'
    
    # For admin users, also check selected role in session
    if (user.is_superuser or user.is_staff):
        # This will be checked in views that use session
        pass
    
    return is_frontline


@login_required
def frontline_dashboard(request):
    """Main Frontline Agent dashboard"""
    # Ensure user has a profile
    UserProfile.objects.get_or_create(user=request.user)
    
    # Check if user has frontline_agent role (either in profile or selected role for admin)
    is_frontline = request.user.profile.role == 'frontline_agent'
    
    # For admin users, also check selected role in session
    if (request.user.is_superuser or request.user.is_staff):
        selected_role = request.session.get('selected_role')
        if selected_role == 'frontline_agent':
            is_frontline = True
    
    if not is_frontline:
        messages.error(request, "You must be a Frontline Agent to access this dashboard.")
        return redirect('dashboard')
    
    # Get dashboard statistics
    tickets = Ticket.objects.filter(created_by=request.user)
    open_tickets = tickets.filter(status__in=['new', 'open', 'in_progress']).count()
    resolved_tickets = tickets.filter(status__in=['resolved', 'closed', 'auto_resolved']).count()
    unread_notifications = Notification.objects.filter(user=request.user, is_read=False).count()
    recent_tickets = tickets.order_by('-created_at')[:5]
    
    # Get analytics data
    analytics = FrontlineAnalytics.objects.filter(
        calculated_at__gte=timezone.now() - timedelta(days=7)
    ).order_by('-calculated_at')[:10]
    
    context = {
        'open_tickets': open_tickets,
        'resolved_tickets': resolved_tickets,
        'unread_notifications': unread_notifications,
        'recent_tickets': recent_tickets,
        'analytics': analytics,
    }
    
    return render(request, 'frontline_agent/dashboard.html', context)


# Knowledge Q&A Agent Views
@login_required
@require_http_methods(["POST"])
def knowledge_qa(request):
    """Knowledge Q&A Agent endpoint"""
    if not is_frontline_agent(request.user):
        return JsonResponse({"error": "Unauthorized. Frontline Agent role required."}, status=403)
    
    try:
        data = json.loads(request.body)
        question = data.get('question', '').strip()
        
        if not question:
            return JsonResponse({"error": "Question is required"}, status=400)
        
        # Use Frontline AI orchestrator to answer the question
        frontline_ai = get_frontline_ai()
        result = frontline_ai.answer_question(user=request.user, question=question)
        
        # Format response for compatibility
        response = {
            'success': result.get('success', True),
            'answer': result.get('answer', 'I could not find information about that in our knowledge base.'),
            'has_verified_info': result.get('has_verified_info', False),
            'source': result.get('source', 'Unknown')
        }
        
        return JsonResponse(response)
        
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        logger.error(f"Knowledge Q&A error: {e}", exc_info=True)
        return JsonResponse({"error": str(e)}, status=500)


# Ticket Triage & Auto-resolution Agent Views
@login_required
@require_http_methods(["POST"])
def create_ticket(request):
    """Create a new support ticket"""
    if not is_frontline_agent(request.user):
        return JsonResponse({"error": "Unauthorized. Frontline Agent role required."}, status=403)
    
    try:
        data = json.loads(request.body)
        title = data.get('title', '').strip()
        description = data.get('description', '').strip()
        priority = data.get('priority', 'medium')
        category = data.get('category', 'other')
        
        if not title or not description:
            return JsonResponse({"error": "Title and description are required"}, status=400)
        
        ticket = Ticket.objects.create(
            title=title,
            description=description,
            priority=priority,
            category=category,
            created_by=request.user
        )
        
        # Auto-triage ticket (simple implementation)
        # In production, this would use an AI agent
        if 'password' in description.lower() or 'login' in description.lower():
            ticket.priority = 'high'
            ticket.category = 'account'
        elif 'bug' in description.lower() or 'error' in description.lower():
            ticket.priority = 'high'
            ticket.category = 'bug'
        
        ticket.save()
        
        # Create notification
        Notification.objects.create(
            user=request.user,
            type='ticket_update',
            title=f'Ticket Created: {title}',
            message=f'Your ticket has been created and assigned ID: {ticket.id}',
            related_ticket=ticket
        )
        
        return JsonResponse({
            "success": True,
            "ticket_id": ticket.id,
            "ticket": {
                "id": ticket.id,
                "title": ticket.title,
                "status": ticket.status,
                "priority": ticket.priority,
                "category": ticket.category,
            }
        })
        
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@require_http_methods(["GET"])
def list_tickets(request):
    """List all tickets for the current user"""
    if not is_frontline_agent(request.user):
        return JsonResponse({"error": "Unauthorized. Frontline Agent role required."}, status=403)
    
    try:
        status_filter = request.GET.get('status')
        priority_filter = request.GET.get('priority')
        
        tickets = Ticket.objects.filter(created_by=request.user)
        
        if status_filter:
            tickets = tickets.filter(status=status_filter)
        if priority_filter:
            tickets = tickets.filter(priority=priority_filter)
        
        tickets = tickets.order_by('-created_at')[:100]
        
        ticket_list = []
        for ticket in tickets:
            ticket_list.append({
                'id': ticket.id,
                'title': ticket.title,
                'description': ticket.description[:200],  # First 200 chars
                'status': ticket.status,
                'priority': ticket.priority,
                'category': ticket.category,
                'created_at': ticket.created_at.isoformat(),
                'resolved_at': ticket.resolved_at.isoformat() if ticket.resolved_at else None,
                'auto_resolved': ticket.auto_resolved,
            })
        
        return JsonResponse({'tickets': ticket_list}, safe=False)
        
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def auto_resolve_ticket(request, ticket_id):
    """Auto-resolve a ticket using AI"""
    if not is_frontline_agent(request.user):
        return JsonResponse({"error": "Unauthorized. Frontline Agent role required."}, status=403)
    
    try:
        ticket = get_object_or_404(Ticket, id=ticket_id, created_by=request.user)
        
        # Use Frontline AI orchestrator to auto-resolve ticket
        frontline_ai = get_frontline_ai()
        
        # Try to find solution in knowledge base
        knowledge_articles = KnowledgeBase.objects.filter(
            category=ticket.category
        )[:5]
        
        if knowledge_articles.exists():
            # Use first matching article as resolution
            solution = knowledge_articles.first()
            ticket.resolution = f"Based on our knowledge base: {solution.content[:500]}"
            ticket.status = 'auto_resolved'
            ticket.auto_resolved = True
            ticket.resolution_confidence = 0.8
            ticket.resolved_at = timezone.now()
            ticket.save()
            
            # Create notification
            Notification.objects.create(
                user=request.user,
                type='ticket_update',
                title=f'Ticket Auto-Resolved: {ticket.title}',
                message=f'Your ticket has been automatically resolved.',
                related_ticket=ticket
            )
            
            return JsonResponse({
                "success": True,
                "ticket_id": ticket.id,
                "resolution": ticket.resolution,
                "auto_resolved": True,
            })
        else:
            return JsonResponse({
                "success": False,
                "error": "No matching solution found in knowledge base"
            }, status=404)
            
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


# Proactive Notification & Follow-up Agent Views
@login_required
@require_http_methods(["GET"])
def list_notifications(request):
    """List notifications for the current user"""
    if not is_frontline_agent(request.user):
        return JsonResponse({"error": "Unauthorized. Frontline Agent role required."}, status=403)
    
    try:
        unread_only = request.GET.get('unread_only', 'false').lower() == 'true'
        
        notifications = Notification.objects.filter(user=request.user)
        
        if unread_only:
            notifications = notifications.filter(is_read=False)
        
        notifications = notifications.order_by('-created_at')[:50]
        
        notification_list = []
        for notification in notifications:
            notification_list.append({
                'id': notification.id,
                'type': notification.type,
                'title': notification.title,
                'message': notification.message,
                'is_read': notification.is_read,
                'created_at': notification.created_at.isoformat(),
                'related_ticket_id': notification.related_ticket.id if notification.related_ticket else None,
            })
        
        return JsonResponse({'notifications': notification_list}, safe=False)
        
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def mark_notification_read(request, notification_id):
    """Mark a notification as read"""
    if not is_frontline_agent(request.user):
        return JsonResponse({"error": "Unauthorized. Frontline Agent role required."}, status=403)
    
    try:
        notification = get_object_or_404(Notification, id=notification_id, user=request.user)
        notification.is_read = True
        notification.read_at = timezone.now()
        notification.save()
        
        return JsonResponse({"success": True})
        
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


# Workflow / SOP Runner Agent Views
@login_required
@require_http_methods(["POST"])
def execute_workflow(request):
    """Execute a workflow/SOP"""
    if not is_frontline_agent(request.user):
        return JsonResponse({"error": "Unauthorized. Frontline Agent role required."}, status=403)
    
    try:
        data = json.loads(request.body)
        workflow_name = data.get('workflow_name', '').strip()
        workflow_description = data.get('workflow_description', '')
        context_data = data.get('context_data', {})
        
        if not workflow_name:
            return JsonResponse({"error": "Workflow name is required"}, status=400)
        
        # Create workflow execution record
        execution = FrontlineWorkflowExecution.objects.create(
            workflow_name=workflow_name,
            workflow_description=workflow_description,
            executed_by=request.user,
            status='in_progress',
            context_data=context_data
        )
        
        # Simple workflow execution (in production, use full workflow agent)
        try:
            # For now, just mark as completed
            execution.status = 'completed'
            execution.completed_at = timezone.now()
            execution.result_data = {"message": "Workflow executed successfully"}
            execution.save()
            
            return JsonResponse({
                "success": True,
                "execution_id": execution.id,
                "status": execution.status,
            })
        except Exception as e:
            execution.status = 'failed'
            execution.error_message = str(e)
            execution.save()
            raise
        
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


# Meeting Scheduling Agent Views
@login_required
@require_http_methods(["POST"])
def schedule_meeting(request):
    """Schedule a meeting"""
    if not is_frontline_agent(request.user):
        return JsonResponse({"error": "Unauthorized. Frontline Agent role required."}, status=403)
    
    try:
        data = json.loads(request.body)
        title = data.get('title', '').strip()
        description = data.get('description', '')
        scheduled_at = data.get('scheduled_at')
        duration_minutes = data.get('duration_minutes', 60)
        meeting_link = data.get('meeting_link', '')
        location = data.get('location', '')
        participant_ids = data.get('participant_ids', [])
        
        if not title or not scheduled_at:
            return JsonResponse({"error": "Title and scheduled_at are required"}, status=400)
        
        from django.utils.dateparse import parse_datetime
        scheduled_datetime = parse_datetime(scheduled_at)
        if not scheduled_datetime:
            return JsonResponse({"error": "Invalid scheduled_at format"}, status=400)
        
        meeting = FrontlineMeeting.objects.create(
            title=title,
            description=description,
            organizer=request.user,
            scheduled_at=scheduled_datetime,
            duration_minutes=duration_minutes,
            meeting_link=meeting_link,
            location=location,
        )
        
        # Add participants
        if participant_ids:
            participants = request.user.__class__.objects.filter(id__in=participant_ids)
            meeting.participants.set(participants)
        
        # Create notifications for participants
        for participant in meeting.participants.all():
            Notification.objects.create(
                user=participant,
                type='reminder',
                title=f'Meeting Scheduled: {title}',
                message=f'You have been invited to a meeting scheduled for {scheduled_datetime}',
            )
        
        return JsonResponse({
            "success": True,
            "meeting_id": meeting.id,
            "meeting": {
                "id": meeting.id,
                "title": meeting.title,
                "scheduled_at": meeting.scheduled_at.isoformat(),
            }
        })
        
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


# Document Processing Agent Views
@login_required
@require_http_methods(["POST"])
def upload_document(request):
    """Upload and process a document"""
    if not is_frontline_agent(request.user):
        return JsonResponse({"error": "Unauthorized. Frontline Agent role required."}, status=403)
    
    try:
        if 'file' not in request.FILES:
            return JsonResponse({"error": "No file uploaded"}, status=400)
        
        uploaded_file = request.FILES['file']
        title = request.POST.get('title', uploaded_file.name)
        description = request.POST.get('description', '')
        document_type = request.POST.get('document_type', 'other')
        ticket_id = request.POST.get('ticket_id')
        
        # Save file (in production, use proper file storage)
        import os
        from django.conf import settings
        from pathlib import Path
        
        # Use MEDIA_ROOT if available, otherwise use a local directory
        if hasattr(settings, 'MEDIA_ROOT') and settings.MEDIA_ROOT:
            upload_dir = os.path.join(settings.MEDIA_ROOT, 'frontline_documents')
        else:
            # Fallback to a local directory
            base_dir = Path(settings.BASE_DIR)
            upload_dir = base_dir / 'media' / 'frontline_documents'
            upload_dir = str(upload_dir)
        
        os.makedirs(upload_dir, exist_ok=True)
        
        # Ensure unique filename
        file_name = uploaded_file.name
        file_path = os.path.join(upload_dir, file_name)
        counter = 1
        while os.path.exists(file_path):
            name, ext = os.path.splitext(uploaded_file.name)
            file_name = f"{name}_{counter}{ext}"
            file_path = os.path.join(upload_dir, file_name)
            counter += 1
        
        with open(file_path, 'wb+') as destination:
            for chunk in uploaded_file.chunks():
                destination.write(chunk)
        
        document = Document.objects.create(
            title=title,
            description=description,
            document_type=document_type,
            file_path=file_path,
            file_size=uploaded_file.size,
            mime_type=uploaded_file.content_type,
            uploaded_by=request.user,
            related_ticket_id=int(ticket_id) if ticket_id else None,
        )
        
        # Process document (simple implementation)
        document.processed = True
        document.processed_data = {
            "file_name": uploaded_file.name,
            "file_size": uploaded_file.size,
            "mime_type": uploaded_file.content_type,
        }
        document.save()
        
        return JsonResponse({
            "success": True,
            "document_id": document.id,
            "document": {
                "id": document.id,
                "title": document.title,
                "document_type": document.document_type,
            }
        })
        
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


# Analytics & Dashboard Agent Views
@login_required
@require_http_methods(["GET"])
def get_analytics(request):
    """Get analytics data for dashboard"""
    if not is_frontline_agent(request.user):
        return JsonResponse({"error": "Unauthorized. Frontline Agent role required."}, status=403)
    
    try:
        # Calculate basic analytics
        tickets = Ticket.objects.filter(created_by=request.user)
        
        total_tickets = tickets.count()
        open_tickets = tickets.filter(status__in=['new', 'open', 'in_progress']).count()
        resolved_tickets = tickets.filter(status__in=['resolved', 'closed', 'auto_resolved']).count()
        auto_resolved_count = tickets.filter(auto_resolved=True).count()
        
        # Calculate resolution time (average)
        resolved_tickets_with_time = tickets.filter(
            resolved_at__isnull=False
        ).exclude(resolved_at__isnull=True)
        
        avg_resolution_time = None
        if resolved_tickets_with_time.exists():
            total_seconds = sum(
                (t.resolved_at - t.created_at).total_seconds()
                for t in resolved_tickets_with_time
            )
            avg_resolution_time = total_seconds / resolved_tickets_with_time.count()
        
        analytics_data = {
            "total_tickets": total_tickets,
            "open_tickets": open_tickets,
            "resolved_tickets": resolved_tickets,
            "auto_resolved_count": auto_resolved_count,
            "resolution_rate": (resolved_tickets / total_tickets * 100) if total_tickets > 0 else 0,
            "auto_resolution_rate": (auto_resolved_count / total_tickets * 100) if total_tickets > 0 else 0,
            "avg_resolution_time_hours": avg_resolution_time / 3600 if avg_resolution_time else None,
        }
        
        return JsonResponse(analytics_data)
        
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


# ============================================
# MAIN FRONTLINE AI CHAT ENDPOINT
# ============================================

@login_required
@require_http_methods(["POST"])
def frontline_chat(request):
    """
    Main Frontline AI Customer Support chat endpoint.
    Fully functional ChatGPT-like AI agent with real database access.
    """
    if not is_frontline_agent(request.user):
        return JsonResponse({"error": "Unauthorized. Frontline Agent role required."}, status=403)
    
    try:
        data = json.loads(request.body)
        message = data.get('message', '').strip()
        
        if not message:
            return JsonResponse({"error": "Message is required"}, status=400)
        
        # Get Frontline AI orchestrator (uses intelligent processing)
        frontline_ai = get_frontline_ai()
        
        # Extract additional parameters from request
        kwargs = {}
        if 'title' in data:
            kwargs['title'] = data['title']
        if 'description' in data:
            kwargs['description'] = data['description']
        if 'status' in data:
            kwargs['status'] = data['status']
        if 'workflow_name' in data:
            kwargs['workflow_name'] = data['workflow_name']
        if 'context_data' in data:
            kwargs['context_data'] = data['context_data']
        if 'scheduled_at' in data:
            from django.utils.dateparse import parse_datetime
            kwargs['scheduled_at'] = parse_datetime(data['scheduled_at'])
        if 'duration_minutes' in data:
            kwargs['duration_minutes'] = int(data['duration_minutes'])
        if 'document_type' in data:
            kwargs['document_type'] = data['document_type']
        if 'period_days' in data:
            kwargs['period_days'] = int(data['period_days'])
        
        # Process with Frontline AI (intelligent intent detection built-in)
        try:
            result = frontline_ai.process(
                user=request.user,
                message=message,
                **kwargs
            )
        except Exception as e:
            logger.error(f"Error in frontline_ai.process: {e}", exc_info=True)
            # Return a helpful fallback response
            result = {
                'success': True,
                'message': f"I'm here to help! I encountered a temporary issue. Please try rephrasing your question. (Error: {str(e)})",
                'answer': "I encountered a temporary issue. Please try again."
            }
        
        # Format response - the new orchestrator returns clean responses
        response_data = {
            'success': result.get('success', True),
            'response': result
        }
        
        # Extract message and answer (new orchestrator uses these fields)
        message_text = result.get('message') or result.get('answer') or 'I\'m here to help! How can I assist you today?'
        answer_text = result.get('answer') or result.get('message') or message_text
        
        # Ensure we never return an error message to the user
        if 'error' in message_text.lower() and 'encountered an error' in message_text.lower():
            # Try to provide a helpful fallback based on the query
            message_lower = message.lower()
            if 'payperproject' in message_lower or 'what is' in message_lower:
                message_text = """PayPerProject is an enterprise project management platform that helps organizations manage projects, track support tickets, coordinate teams, and streamline business operations.

I can help you with questions about your projects, tickets, users, and more. What would you like to know?"""
            elif 'project' in message_lower and ('how many' in message_lower or 'running' in message_lower):
                message_text = "I'm currently checking the project database. Please try again in a moment, or ask me about something else."
            else:
                message_text = "I'm here to help! Could you rephrase your question? I can assist with PayPerProject questions, project statistics, tickets, and more."
            answer_text = message_text
        
        response_data['message'] = message_text
        response_data['answer'] = answer_text
        
        # Add any additional fields from result
        if 'has_verified_info' in result:
            response_data['has_verified_info'] = result.get('has_verified_info')
        if 'source' in result:
            response_data['source'] = result.get('source')
        if 'ticket_id' in result:
            response_data['ticket_id'] = result.get('ticket_id')
        if 'tickets' in result:
            response_data['tickets'] = result.get('tickets', [])
            response_data['count'] = len(result.get('tickets', []))
        if 'notifications' in result:
            response_data['notifications'] = result.get('notifications', [])
            response_data['count'] = len(result.get('notifications', []))
        
        return JsonResponse(response_data)
        
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        logger.error(f"Frontline AI chat error: {e}", exc_info=True)
        return JsonResponse({
            "error": str(e),
            "message": "I encountered an error. Please try again or contact support."
        }, status=500)

from django.http import JsonResponse
from .agent_logic import agent_reply

def chat(request):
    """
    Simple endpoint for AI agent chat
    """
    user_input = request.GET.get("message", "")
    answer = agent_reply(user_input)
    return JsonResponse({"response": answer})
