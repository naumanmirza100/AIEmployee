"""
Frontline Agent API Views
Enterprise-level API endpoints with authentication and logging
"""
import logging
import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views import View

# Initialize logging
from .logging_config import setup_frontline_logging
setup_frontline_logging()

from .frontline_agent import FrontlineAgent
from .services import KnowledgeService, TicketAutomationService

logger = logging.getLogger(__name__)

# Initialize agent (singleton)
_frontline_agent = None


def get_frontline_agent():
    """Get or create Frontline Agent instance (singleton)"""
    global _frontline_agent
    if _frontline_agent is None:
        _frontline_agent = FrontlineAgent()
    return _frontline_agent


@require_http_methods(["GET"])
@login_required
def knowledge_api(request):
    """
    API endpoint for knowledge base queries.
    Returns verified answers from PayPerProject database only.
    
    Query parameters:
    - q: Question to search for
    
    Returns:
    - answer: Answer from knowledge base or indication that no info exists
    - has_verified_info: Boolean indicating if verified info was found
    - source: Source of the information
    """
    question = request.GET.get('q', '').strip()
    
    if not question:
        logger.warning("Knowledge API called without question parameter")
        return JsonResponse({
            'success': False,
            'error': 'Question parameter (q) is required'
        }, status=400)
    
    logger.info(f"Knowledge API request from user {request.user.id}: {question[:100]}")
    
    try:
        agent = get_frontline_agent()
        result = agent.answer_question(question)
        
        logger.info(f"Knowledge API response: has_verified_info={result.get('has_verified_info', False)}")
        
        return JsonResponse(result)
    except Exception as e:
        logger.error(f"Knowledge API error: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'An error occurred while processing your question',
            'answer': None,
            'has_verified_info': False
        }, status=500)


@require_http_methods(["POST"])
@login_required
def create_ticket_api(request):
    """
    API endpoint for creating and processing tickets.
    Classifies ticket, searches for solutions, and auto-resolves if possible.
    
    POST data:
    - title: Ticket title (required)
    - description: Ticket description (required)
    - message: Alternative to description (optional)
    
    Returns:
    - ticket_id: Created ticket ID
    - ticket_status: Status of the ticket
    - auto_resolved: Boolean indicating if ticket was auto-resolved
    - resolution: Resolution text if auto-resolved
    - should_escalate: Boolean indicating if ticket should be escalated
    - response: Formatted response message
    """
    try:
        data = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        data = request.POST.dict()
    
    title = data.get('title', '').strip()
    description = data.get('description', '').strip() or data.get('message', '').strip()
    
    if not title:
        title = description[:100] if description else 'Support Request'
    
    if not description:
        logger.warning("Create ticket API called without description")
        return JsonResponse({
            'success': False,
            'error': 'Description or message is required'
        }, status=400)
    
    logger.info(f"Create ticket API request from user {request.user.id}: {title[:50]}")
    
    try:
        agent = get_frontline_agent()
        result = agent.process_ticket(
            title=title,
            description=description,
            user_id=request.user.id
        )
        
        if not result.get('success', False):
            logger.error(f"Ticket processing failed: {result.get('error')}")
            return JsonResponse(result, status=500)
        
        # Format response message
        if result.get('auto_resolved', False):
            response_message = result.get('formatted_response') or result.get('resolution', 'Your issue has been resolved.')
        elif result.get('should_escalate', False):
            response_message = f"Thank you for contacting us. Your ticket (ID: {result['ticket_id']}) has been created and assigned to a human agent for review. We'll get back to you soon."
        else:
            response_message = f"Your ticket (ID: {result['ticket_id']}) has been created and is being reviewed. We'll update you shortly."
        
        logger.info(f"Ticket {result['ticket_id']} processed: status={result['ticket_status']}, auto_resolved={result.get('auto_resolved', False)}")
        
        return JsonResponse({
            'success': True,
            'ticket_id': result['ticket_id'],
            'ticket_status': result['ticket_status'],
            'resolved': result.get('auto_resolved', False),
            'response': response_message,
            'classification': result.get('classification', {}),
            'should_escalate': result.get('should_escalate', False)
        })
    except Exception as e:
        logger.error(f"Create ticket API error: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'An error occurred while processing your ticket',
            'ticket_id': None,
            'response': 'An error occurred. Please try again or contact support directly.'
        }, status=500)


@require_http_methods(["GET"])
@login_required
def search_knowledge_api(request):
    """
    API endpoint for searching knowledge base.
    
    Query parameters:
    - q: Search query (required)
    - max_results: Maximum results per category (default: 5)
    
    Returns:
    - results: List of knowledge base results
    - count: Total number of results
    - sources: Breakdown by source type
    """
    query = request.GET.get('q', '').strip()
    max_results = int(request.GET.get('max_results', 5))
    
    if not query:
        return JsonResponse({
            'success': False,
            'error': 'Query parameter (q) is required'
        }, status=400)
    
    logger.info(f"Search knowledge API request from user {request.user.id}: {query[:100]}")
    
    try:
        agent = get_frontline_agent()
        result = agent.search_knowledge(query)
        
        logger.info(f"Search knowledge API: found {result.get('count', 0)} results")
        
        return JsonResponse(result)
    except Exception as e:
        logger.error(f"Search knowledge API error: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'An error occurred while searching knowledge base',
            'results': [],
            'count': 0
        }, status=500)


@require_http_methods(["GET"])
@login_required
def ticket_classification_api(request):
    """
    API endpoint for ticket classification (without creating ticket).
    
    Query parameters:
    - title: Ticket title (optional)
    - description: Ticket description (required)
    
    Returns:
    - classification: Classification results
    """
    title = request.GET.get('title', '').strip()
    description = request.GET.get('description', '').strip()
    
    if not description:
        return JsonResponse({
            'success': False,
            'error': 'Description parameter is required'
        }, status=400)
    
    logger.info(f"Ticket classification API request from user {request.user.id}")
    
    try:
        ticket_service = TicketAutomationService()
        classification = ticket_service.classify_ticket(title, description)
        
        logger.info(f"Classification result: {classification}")
        
        return JsonResponse({
            'success': True,
            'classification': classification
        })
    except Exception as e:
        logger.error(f"Ticket classification API error: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'An error occurred while classifying ticket'
        }, status=500)
