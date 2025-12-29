"""
Frontline Agent Services
Enterprise-level service layer for knowledge retrieval and ticket automation
"""
import logging
from typing import Dict, List, Optional, Tuple
from django.utils import timezone
from django.db import transaction

from .database_service import PayPerProjectDatabaseService
from .rules import TicketClassificationRules

logger = logging.getLogger(__name__)


class KnowledgeService:
    """
    Service for retrieving knowledge from PayPerProject database.
    Provides read-only access to FAQs, policies, and manuals.
    """
    
    def __init__(self):
        self.db_service = PayPerProjectDatabaseService()
        logger.info("KnowledgeService initialized")
    
    def search_knowledge(self, query: str, max_results: int = 5) -> Dict:
        """
        Search knowledge base (FAQs, policies, manuals) for relevant information.
        
        Args:
            query: Search query
            max_results: Maximum number of results per category
            
        Returns:
            Dictionary with search results and metadata
        """
        logger.info(f"Searching knowledge base for: {query[:100]}")
        
        try:
            # Search all knowledge sources
            faqs = self.db_service.get_faqs(search_term=query, limit=max_results)
            policies = self.db_service.get_policies(search_term=query, limit=max_results)
            manuals = self.db_service.get_manuals(search_term=query, limit=max_results)
            
            all_results = []
            
            # Format FAQs
            for faq in faqs:
                all_results.append({
                    'type': 'faq',
                    'question': faq.get('question', ''),
                    'answer': faq.get('answer', ''),
                    'category': faq.get('category', ''),
                    'source': 'PayPerProject Database'
                })
            
            # Format policies
            for policy in policies:
                all_results.append({
                    'type': 'policy',
                    'title': policy.get('title', ''),
                    'content': policy.get('content', ''),
                    'policy_type': policy.get('policy_type', ''),
                    'source': 'PayPerProject Database'
                })
            
            # Format manuals
            for manual in manuals:
                all_results.append({
                    'type': 'manual',
                    'title': manual.get('title', ''),
                    'content': manual.get('content', ''),
                    'manual_type': manual.get('manual_type', ''),
                    'source': 'PayPerProject Database'
                })
            
            logger.info(f"Found {len(all_results)} knowledge base results")
            
            return {
                'success': True,
                'query': query,
                'results': all_results,
                'count': len(all_results),
                'sources': {
                    'faqs': len(faqs),
                    'policies': len(policies),
                    'manuals': len(manuals)
                }
            }
        except Exception as e:
            logger.error(f"Knowledge search failed: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'results': [],
                'count': 0
            }
    
    def get_answer(self, question: str) -> Dict:
        """
        Get answer to a question from knowledge base.
        
        Args:
            question: User's question
            
        Returns:
            Dictionary with answer or indication that no answer was found
        """
        logger.info(f"Getting answer for question: {question[:100]}")
        
        search_results = self.search_knowledge(question, max_results=3)
        
        if search_results['success'] and search_results['count'] > 0:
            # Return the most relevant result
            best_match = search_results['results'][0]
            
            if best_match['type'] == 'faq':
                answer = best_match.get('answer', '')
            else:
                answer = best_match.get('content', '')
            
            logger.info(f"Found answer in knowledge base")
            return {
                'success': True,
                'answer': answer,
                'source': best_match.get('source', 'PayPerProject Database'),
                'type': best_match.get('type', 'unknown'),
                'has_verified_info': True
            }
        else:
            logger.info("No verified information found in knowledge base")
            return {
                'success': True,
                'answer': None,
                'has_verified_info': False,
                'message': 'No verified information found in knowledge base'
            }


class TicketAutomationService:
    """
    Service for ticket automation including classification and auto-resolution.
    """
    
    def __init__(self):
        self.classification_rules = TicketClassificationRules()
        self.knowledge_service = KnowledgeService()
        logger.info("TicketAutomationService initialized")
    
    def classify_ticket(self, title: str, description: str) -> Dict:
        """
        Classify a ticket using rule-based classification.
        
        Args:
            title: Ticket title
            description: Ticket description
            
        Returns:
            Classification dictionary
        """
        logger.info(f"Classifying ticket: {title[:50]}")
        
        classification = self.classification_rules.classify_ticket(description, title)
        
        logger.info(f"Classification result: {classification}")
        
        return classification
    
    def find_solution(self, description: str, category: str) -> Optional[Dict]:
        """
        Search knowledge base for potential solution.
        
        Args:
            description: Ticket description
            category: Ticket category
            
        Returns:
            Solution dictionary if found, None otherwise
        """
        logger.info(f"Searching for solution in category: {category}")
        
        # Search knowledge base with description and category
        search_query = f"{description} {category}"
        search_results = self.knowledge_service.search_knowledge(search_query, max_results=3)
        
        if search_results['success'] and search_results['count'] > 0:
            best_match = search_results['results'][0]
            logger.info(f"Found potential solution in knowledge base")
            return {
                'solution': best_match.get('answer') or best_match.get('content', ''),
                'source': best_match.get('source', 'PayPerProject Database'),
                'type': best_match.get('type', 'unknown')
            }
        
        logger.info("No solution found in knowledge base")
        return None
    
    def auto_resolve_ticket(
        self, 
        title: str, 
        description: str, 
        classification: Optional[Dict] = None
    ) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Attempt to auto-resolve a ticket.
        
        Args:
            title: Ticket title
            description: Ticket description
            classification: Optional pre-computed classification
            
        Returns:
            Tuple of (can_auto_resolve, resolution_text, solution_data)
        """
        logger.info(f"Attempting auto-resolution for ticket: {title[:50]}")
        
        # Get classification if not provided
        if not classification:
            classification = self.classify_ticket(title, description)
        
        # Check if auto-resolvable
        if not classification.get('auto_resolvable', False):
            logger.info("Ticket is not auto-resolvable")
            return False, None, None
        
        # Check if should escalate (don't auto-resolve if escalation needed)
        if classification.get('should_escalate', False):
            logger.info("Ticket requires escalation, cannot auto-resolve")
            return False, None, None
        
        # Search for solution
        solution = self.find_solution(description, classification.get('category', 'other'))
        
        if not solution:
            logger.info("No solution found in knowledge base, cannot auto-resolve")
            return False, None, None
        
        # Auto-resolve with solution
        resolution_text = solution.get('solution', '')
        logger.info("Ticket can be auto-resolved")
        
        return True, resolution_text, solution
    
    def process_ticket(self, title: str, description: str, user_id: int) -> Dict:
        """
        Process a ticket: classify, search for solution, and determine action.
        
        Args:
            title: Ticket title
            description: Ticket description
            user_id: User ID who created the ticket
            
        Returns:
            Processing result dictionary
        """
        logger.info(f"Processing ticket from user {user_id}: {title[:50]}")
        
        # Classify ticket
        classification = self.classify_ticket(title, description)
        
        # Search for solution
        solution = self.find_solution(description, classification.get('category', 'other'))
        
        # Determine if can auto-resolve
        can_auto_resolve, resolution_text, solution_data = self.auto_resolve_ticket(
            title, description, classification
        )
        
        # Create ticket in database
        try:
            from Frontline_agent.models import Ticket
            from django.contrib.auth.models import User
            
            user = User.objects.get(id=user_id)
            
            with transaction.atomic():
                ticket = Ticket.objects.create(
                    title=title,
                    description=description,
                    category=classification.get('category', 'other'),
                    priority=classification.get('priority', 'medium'),
                    created_by=user,
                    status='auto_resolved' if can_auto_resolve else 'open',
                    auto_resolved=can_auto_resolve,
                    resolution=resolution_text if can_auto_resolve else None,
                    resolution_confidence=classification.get('confidence', 0.0) if can_auto_resolve else None,
                    resolved_at=timezone.now() if can_auto_resolve else None
                )
                
                logger.info(f"Ticket created: ID {ticket.id}, Status: {ticket.status}")
                
                return {
                    'success': True,
                    'ticket_id': ticket.id,
                    'ticket_status': ticket.status,
                    'classification': classification,
                    'auto_resolved': can_auto_resolve,
                    'resolution': resolution_text if can_auto_resolve else None,
                    'should_escalate': classification.get('should_escalate', False),
                    'message': 'Ticket processed successfully'
                }
        except Exception as e:
            logger.error(f"Failed to create ticket: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'classification': classification
            }
