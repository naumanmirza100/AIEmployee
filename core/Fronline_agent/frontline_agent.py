"""
Frontline Agent - Main Agent Implementation
Enterprise-level AI agent that uses only verified database information
"""
import logging
from typing import Dict, Optional
from django.conf import settings

# Initialize logging
from .logging_config import setup_frontline_logging
setup_frontline_logging()

from project_manager_agent.ai_agents.base_agent import BaseAgent
from .services import KnowledgeService, TicketAutomationService
from .prompts import (
    FRONTLINE_SYSTEM_PROMPT,
    get_knowledge_prompt,
    get_ticket_prompt,
    FRONTLINE_AUTO_RESOLVE_PROMPT
)

logger = logging.getLogger(__name__)


class FrontlineAgent(BaseAgent):
    """
    Frontline Support AI Agent for PayPerProject.
    Uses only verified information from PayPerProject database.
    Never guesses or assumes - only provides verified answers.
    """
    
    def __init__(self, company_id: Optional[int] = None):
        """Initialize Frontline Agent"""
        super().__init__()
        self.company_id = company_id
        self.knowledge_service = KnowledgeService(company_id=company_id)
        self.ticket_service = TicketAutomationService()
        self.system_prompt = FRONTLINE_SYSTEM_PROMPT
        logger.info(f"FrontlineAgent initialized (company_id: {company_id})")
    
    def answer_question(self, question: str, company_id: Optional[int] = None) -> Dict:
        """
        Answer a question using only verified knowledge base information.
        
        Args:
            question: User's question
            
        Returns:
            Dictionary with answer or indication that no verified info exists
        """
        logger.info(f"Processing question: {question[:100]} (company_id: {company_id})")
        
        # Use provided company_id or instance company_id
        search_company_id = company_id or self.company_id
        
        # Search knowledge base
        knowledge_result = self.knowledge_service.get_answer(question, company_id=search_company_id)
        
        if not knowledge_result.get('has_verified_info', False):
            logger.info("No verified information found, cannot answer")
            return {
                'success': True,
                'answer': "I don't have verified information about this topic in our knowledge base. Let me create a ticket for a human agent to assist you.",
                'has_verified_info': False,
                'source': None
            }
        
        # Use LLM to format the answer nicely, but only using verified information
        try:
            # Log what we're passing to the prompt
            logger.info(f"Knowledge result keys: {knowledge_result.keys()}")
            answer_content = knowledge_result.get('answer', '')
            logger.info(f"Knowledge result answer length: {len(answer_content)}")
            logger.info(f"Knowledge result answer preview (first 500): {answer_content[:500]}")
            
            # Check if keywords are in the content
            question_lower = question.lower()
            import re
            query_words = re.findall(r'\b\w+\b', question_lower)
            stop_words = {'what', 'is', 'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'how', 'do', 'does', 'can', 'will', 'are', 'was', 'were'}
            keywords = [w for w in query_words if w not in stop_words and len(w) > 2]
            
            for keyword in keywords:
                if keyword in answer_content.lower():
                    # Find the context around the keyword
                    idx = answer_content.lower().find(keyword)
                    start = max(0, idx - 200)
                    end = min(len(answer_content), idx + 500)
                    logger.info(f"Found keyword '{keyword}' at position {idx}, context: {answer_content[start:end]}")
            
            prompt = get_knowledge_prompt(question, [knowledge_result])
            
            # Log the prompt to see what's being sent to LLM
            logger.info(f"Prompt length: {len(prompt)}")
            logger.info(f"Prompt preview (first 1000): {prompt[:1000]}")
            
            # Check if the prompt contains the relevant section
            if any(kw in prompt.lower() for kw in keywords):
                logger.info(f"Prompt contains keywords: {keywords}")
            else:
                logger.warning(f"Prompt does NOT contain keywords: {keywords}")
            
            formatted_answer = self._call_llm(
                prompt=prompt,
                system_prompt=self.system_prompt,
                temperature=0.3,  # Low temperature for factual responses
                max_tokens=500
            )
            
            logger.info("Answer generated from verified knowledge base")
            
            return {
                'success': True,
                'answer': formatted_answer,
                'has_verified_info': True,
                'source': knowledge_result.get('source', 'PayPerProject Database'),
                'type': knowledge_result.get('type', 'unknown')
            }
        except Exception as e:
            logger.error(f"Error generating answer: {e}", exc_info=True)
            # Fallback to direct answer from knowledge base
            return {
                'success': True,
                'answer': knowledge_result.get('answer', ''),
                'has_verified_info': True,
                'source': knowledge_result.get('source', 'PayPerProject Database'),
                'type': knowledge_result.get('type', 'unknown')
            }
    
    def process_ticket(self, title: str, description: str, user_id: int) -> Dict:
        """
        Process a support ticket: classify, search for solution, auto-resolve if possible.
        
        Args:
            title: Ticket title
            description: Ticket description
            user_id: User ID who created the ticket
            
        Returns:
            Processing result dictionary
        """
        logger.info(f"Processing ticket from user {user_id}: {title[:50]}")
        
        # Use ticket service to process
        result = self.ticket_service.process_ticket(title, description, user_id)
        
        if not result.get('success', False):
            logger.error(f"Ticket processing failed: {result.get('error')}")
            return result
        
        # If auto-resolved, format the response nicely
        if result.get('auto_resolved', False):
            try:
                resolution = result.get('resolution', '')
                prompt = FRONTLINE_AUTO_RESOLVE_PROMPT.format(
                    ticket_title=title,
                    ticket_description=description,
                    category=result['classification'].get('category', 'other'),
                    priority=result['classification'].get('priority', 'medium'),
                    solution=resolution
                )
                
                formatted_response = self._call_llm(
                    prompt=prompt,
                    system_prompt=self.system_prompt,
                    temperature=0.3,
                    max_tokens=300
                )
                
                result['formatted_response'] = formatted_response
                logger.info(f"Ticket {result['ticket_id']} auto-resolved with formatted response")
            except Exception as e:
                logger.warning(f"Error formatting auto-resolution response: {e}")
                # Use direct resolution text
                result['formatted_response'] = result.get('resolution', '')
        
        return result
    
    def search_knowledge(self, query: str, company_id: Optional[int] = None) -> Dict:
        """
        Search knowledge base for information.
        
        Args:
            query: Search query
            company_id: Optional company ID to search company-specific documents
            
        Returns:
            Search results dictionary
        """
        search_company_id = company_id or self.company_id
        logger.info(f"Searching knowledge base: {query[:100]} (company_id: {search_company_id})")
        return self.knowledge_service.search_knowledge(query, company_id=search_company_id)
    
    def process(self, action: str, **kwargs) -> Dict:
        """
        Main processing method for the agent.
        
        Args:
            action: Action to perform ('answer_question', 'process_ticket', 'search_knowledge')
            **kwargs: Action-specific parameters
            
        Returns:
            Processing result dictionary
        """
        logger.info(f"Processing action: {action}")
        
        if action == 'answer_question':
            question = kwargs.get('question', '')
            if not question:
                return {'success': False, 'error': 'Question is required'}
            return self.answer_question(question)
        
        elif action == 'process_ticket':
            title = kwargs.get('title', '')
            description = kwargs.get('description', '')
            user_id = kwargs.get('user_id')
            
            if not all([title, description, user_id]):
                return {'success': False, 'error': 'Title, description, and user_id are required'}
            return self.process_ticket(title, description, user_id)
        
        elif action == 'search_knowledge':
            query = kwargs.get('query', '')
            if not query:
                return {'success': False, 'error': 'Query is required'}
            return self.search_knowledge(query)
        
        else:
            logger.warning(f"Unknown action: {action}")
            return {'success': False, 'error': f'Unknown action: {action}'}
