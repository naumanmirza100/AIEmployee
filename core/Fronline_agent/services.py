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
from .embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


class KnowledgeService:
    """
    Service for retrieving knowledge from PayPerProject database.
    Provides read-only access to FAQs, policies, manuals, and uploaded documents.
    """
    
    def __init__(self, company_id: Optional[int] = None):
        self.db_service = PayPerProjectDatabaseService()
        self.company_id = company_id
        self.embedding_service = EmbeddingService()
        logger.info(f"KnowledgeService initialized (company_id: {company_id}, embeddings: {self.embedding_service.is_available()})")
    
    def search_knowledge(self, query: str, max_results: int = 5, company_id: Optional[int] = None) -> Dict:
        """
        Search knowledge base (FAQs, policies, manuals, uploaded documents) for relevant information.
        
        Args:
            query: Search query
            max_results: Maximum number of results per category
            company_id: Optional company ID to filter documents
            
        Returns:
            Dictionary with search results and metadata
        """
        logger.info(f"Searching knowledge base for: {query[:100]} (company_id: {company_id})")
        
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
            
            # Search uploaded documents if company_id is provided
            documents_count = 0
            if company_id:
                documents = self._search_documents(query, company_id, max_results)
                documents_count = len(documents)
                for doc in documents:
                    all_results.append({
                        'type': 'document',
                        'title': doc.get('title', ''),
                        'content': doc.get('content', ''),
                        'document_id': doc.get('id'),
                        'file_format': doc.get('file_format', ''),
                        'source': 'Uploaded Document'
                    })
            
            logger.info(f"Found {len(all_results)} knowledge base results (including {documents_count} documents)")
            
            return {
                'success': True,
                'query': query,
                'results': all_results,
                'count': len(all_results),
                'sources': {
                    'faqs': len(faqs),
                    'policies': len(policies),
                    'manuals': len(manuals),
                    'documents': documents_count
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
    
    def _search_documents(self, query: str, company_id: int, max_results: int) -> List[Dict]:
        """
        Search uploaded documents for company using semantic search (embeddings) with keyword fallback.
        """
        try:
            from Frontline_agent.models import Document
            from django.db.models import Q
            
            # Get all indexed documents for the company
            all_documents = Document.objects.filter(
                company_id=company_id,
                is_indexed=True,
                processed=True
            )
            
            # Try semantic search first if embeddings are available
            if self.embedding_service.is_available():
                try:
                    # Generate query embedding
                    query_embedding = self.embedding_service.generate_embedding(query)
                    
                    # If embedding generation failed (e.g., quota exceeded), fall back to keyword search
                    if not query_embedding:
                        logger.info("Query embedding generation failed, falling back to keyword search")
                        raise ValueError("Embedding generation failed")
                    
                    if query_embedding:
                        # Get documents with embeddings
                        documents_with_embeddings = all_documents.exclude(embedding__isnull=True).exclude(embedding=[])
                        
                        if documents_with_embeddings.exists():
                            # Prepare document embeddings for similarity search
                            doc_embeddings = []
                            for doc in documents_with_embeddings:
                                if doc.embedding:  # Ensure embedding exists
                                    doc_embeddings.append({
                                        'document_id': doc.id,
                                        'embedding': doc.embedding,
                                        'metadata': {
                                            'title': doc.title,
                                            'description': doc.description,
                                            'document_type': doc.document_type,
                                            'file_format': doc.file_format,
                                        }
                                    })
                            
                            if doc_embeddings:
                                # Find similar documents using cosine similarity
                                similar_docs = self.embedding_service.find_similar_documents(
                                    query_embedding=query_embedding,
                                    document_embeddings=doc_embeddings,
                                    top_k=max_results,
                                    similarity_threshold=0.5  # Minimum similarity score
                                )
                                
                                if similar_docs:
                                    # Get full document objects
                                    doc_ids = [d['document_id'] for d in similar_docs]
                                    documents = Document.objects.filter(id__in=doc_ids)
                                    
                                    # Create a map for similarity scores
                                    similarity_map = {d['document_id']: d['similarity'] for d in similar_docs}
                                    
                                    # Sort by similarity
                                    documents = sorted(documents, key=lambda d: similarity_map.get(d.id, 0), reverse=True)
                                    
                                    results = []
                                    for doc in documents:
                                        content = doc.document_content or ''
                                        similarity = similarity_map.get(doc.id, 0)
                                        
                                        # Extract snippet (first 500 chars or around query)
                                        if query.lower() in content.lower():
                                            query_lower = query.lower()
                                            content_lower = content.lower()
                                            idx = content_lower.find(query_lower)
                                            if idx >= 0:
                                                start = max(0, idx - 150)
                                                end = min(len(content), idx + len(query) + 150)
                                                snippet = content[start:end]
                                                if start > 0:
                                                    snippet = '...' + snippet
                                                if end < len(content):
                                                    snippet = snippet + '...'
                                            else:
                                                snippet = content[:500] + '...' if len(content) > 500 else content
                                        else:
                                            snippet = content[:500] + '...' if len(content) > 500 else content
                                        
                                        results.append({
                                            'id': doc.id,
                                            'title': doc.title,
                                            'content': snippet,
                                            'file_format': doc.file_format,
                                            'document_type': doc.document_type,
                                            'similarity_score': round(similarity, 3),  # Add similarity score
                                            'search_method': 'semantic'
                                        })
                                    
                                    logger.info(f"Semantic search found {len(results)} documents")
                                    return results
                                
                                logger.info("Semantic search found no similar documents, falling back to keyword search")
                except Exception as e:
                    logger.warning(f"Semantic search failed, falling back to keyword search: {e}")
            
            # Fallback to keyword search
            logger.info("Using keyword-based search")
            documents = all_documents.filter(
                Q(title__icontains=query) |
                Q(description__icontains=query) |
                Q(document_content__icontains=query)
            )[:max_results]
            
            results = []
            for doc in documents:
                # Extract relevant snippet from content
                content = doc.document_content or ''
                if query.lower() in content.lower():
                    # Find snippet around query
                    query_lower = query.lower()
                    content_lower = content.lower()
                    idx = content_lower.find(query_lower)
                    if idx >= 0:
                        start = max(0, idx - 100)
                        end = min(len(content), idx + len(query) + 100)
                        snippet = content[start:end]
                        if start > 0:
                            snippet = '...' + snippet
                        if end < len(content):
                            snippet = snippet + '...'
                    else:
                        snippet = content[:200] + '...' if len(content) > 200 else content
                else:
                    snippet = content[:200] + '...' if len(content) > 200 else content
                
                results.append({
                    'id': doc.id,
                    'title': doc.title,
                    'content': snippet,
                    'file_format': doc.file_format,
                    'document_type': doc.document_type,
                    'search_method': 'keyword'
                })
            
            return results
        except Exception as e:
            logger.error(f"Document search failed: {e}", exc_info=True)
            return []
    
    def get_answer(self, question: str, company_id: Optional[int] = None) -> Dict:
        """
        Get answer to a question from knowledge base and uploaded documents.
        
        Args:
            question: User's question
            company_id: Optional company ID to search company-specific documents
            
        Returns:
            Dictionary with answer or indication that no answer was found
        """
        logger.info(f"Getting answer for question: {question[:100]} (company_id: {company_id})")
        
        # Try full question first
        search_results = self.search_knowledge(question, max_results=5, company_id=company_id)
        
        # If no results, try extracting keywords and searching again
        if not search_results['success'] or search_results['count'] == 0:
            # Extract keywords (remove common words)
            import re
            stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'should', 'could', 'may', 'might', 'must', 'can', 'what', 'when', 'where', 'who', 'why', 'how', 'this', 'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'me', 'him', 'her', 'us', 'them'}
            words = re.findall(r'\b\w+\b', question.lower())
            keywords = [w for w in words if w not in stop_words and len(w) > 2]
            
            if keywords:
                # Try searching with individual keywords
                for keyword in keywords[:3]:  # Try top 3 keywords
                    keyword_results = self.search_knowledge(keyword, max_results=3, company_id=company_id)
                    if keyword_results['success'] and keyword_results['count'] > 0:
                        search_results = keyword_results
                        logger.info(f"Found results using keyword: {keyword}")
                        break
        
        if search_results['success'] and search_results['count'] > 0:
            # Return the most relevant result
            best_match = search_results['results'][0]
            
            if best_match['type'] == 'faq':
                answer = best_match.get('answer', '')
            elif best_match['type'] == 'document':
                answer = best_match.get('content', '')
            else:
                answer = best_match.get('content', '')
            
            logger.info(f"Found answer in knowledge base (type: {best_match.get('type')})")
            return {
                'success': True,
                'answer': answer,
                'source': best_match.get('source', 'PayPerProject Database'),
                'type': best_match.get('type', 'unknown'),
                'has_verified_info': True,
                'document_id': best_match.get('document_id') if best_match.get('type') == 'document' else None
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
