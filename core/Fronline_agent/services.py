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
                        'id': doc.get('id'),
                        'title': doc.get('title', ''),
                        'content': doc.get('content', ''),
                        'document_id': doc.get('id'),
                        'file_format': doc.get('file_format', ''),
                        'source': 'Uploaded Document',
                        'similarity_score': doc.get('similarity_score'),
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
                    # Generate query embedding for semantic search
                    logger.info(f"Generating query embedding for semantic search: {query[:100]}")
                    query_embedding = self.embedding_service.generate_embedding(query)
                    
                    # If embedding generation failed (e.g., quota exceeded), fall back to keyword search
                    if not query_embedding:
                        logger.info("Query embedding generation failed, falling back to keyword search")
                        raise ValueError("Embedding generation failed")
                    
                    logger.info(f"Query embedding generated successfully (dimension: {len(query_embedding)})")
                    
                    if query_embedding:
                        # Get documents with embeddings
                        documents_with_embeddings = all_documents.exclude(embedding__isnull=True).exclude(embedding=[])
                        
                        logger.info(f"Found {documents_with_embeddings.count()} documents with embeddings for company {company_id}")
                        
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
                                logger.info(f"Processing {len(doc_embeddings)} documents with embeddings for similarity search")
                                
                                # Calculate all similarities first for debugging
                                all_scores = []
                                for doc_data in doc_embeddings:
                                    try:
                                        doc_embedding = doc_data['embedding']
                                        # Ensure embedding is a list (not JSON string)
                                        if isinstance(doc_embedding, str):
                                            import json
                                            doc_embedding = json.loads(doc_embedding)
                                        
                                        similarity = self.embedding_service.cosine_similarity(query_embedding, doc_embedding)
                                        all_scores.append({
                                            'id': doc_data['document_id'],
                                            'score': similarity,
                                            'title': doc_data['metadata'].get('title', 'Unknown')
                                        })
                                    except Exception as e:
                                        logger.error(f"Error calculating similarity for doc {doc_data['document_id']}: {e}")
                                
                                # Sort by similarity
                                all_scores.sort(key=lambda x: x['score'], reverse=True)
                                
                                # Log top 5 scores for debugging
                                top_5 = all_scores[:5] if len(all_scores) >= 5 else all_scores
                                logger.warning(f"Top 5 similarity scores: {[(d['id'], round(d['score'], 3), d['title'][:50]) for d in top_5]}")
                                
                                # Log ALL scores for debugging (to see if document 8 is included)
                                logger.info(f"All similarity scores (total: {len(all_scores)}): {[(d['id'], round(d['score'], 3), d['title'][:30]) for d in all_scores]}")
                                
                                # Use top results regardless of threshold
                                # Some embedding models produce lower similarity scores, so we'll take the top N
                                # and let the user see the results even if scores seem low
                                if all_scores:
                                    # Take top max_results documents (always return something if we have documents)
                                    similar_docs = all_scores[:max_results]
                                    scores = [round(d['score'], 3) for d in similar_docs]
                                    logger.warning(f"Returning top {len(similar_docs)} documents (max_results={max_results}) with similarity scores: {scores}")
                                    logger.info(f"Document IDs being returned: {[d['id'] for d in similar_docs]}")
                                    
                                    # Check if document 8 is in the results
                                    doc_8_in_results = any(d['id'] == 8 for d in similar_docs)
                                    logger.info(f"Document 8 (nlp) in results: {doc_8_in_results}")
                                else:
                                    similar_docs = []
                                    logger.warning(f"No documents with embeddings found. Total documents processed: {len(all_scores)}")
                                
                                if similar_docs:
                                    # Get full document objects
                                    doc_ids = [d['id'] for d in similar_docs]
                                    documents = Document.objects.filter(id__in=doc_ids)
                                    
                                    # Create a map for similarity scores
                                    similarity_map = {d['id']: d['score'] for d in similar_docs}
                                    
                                    # Sort by similarity
                                    documents = sorted(documents, key=lambda d: similarity_map.get(d.id, 0), reverse=True)
                                    
                                    results = []
                                    for doc in documents:
                                        content = doc.document_content or ''
                                        similarity = similarity_map.get(doc.id, 0)
                                        
                                        # Extract snippet - try to find the most relevant section
                                        query_lower = query.lower()
                                        content_lower = content.lower()
                                        
                                        # Extract keywords from query (remove common words)
                                        import re
                                        query_words = re.findall(r'\b\w+\b', query_lower)
                                        stop_words = {'what', 'is', 'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'how', 'do', 'does', 'can', 'will'}
                                        keywords = [w for w in query_words if w not in stop_words and len(w) > 2]
                                        
                                        # Try to find the most relevant section by searching for keywords
                                        best_snippet = None
                                        best_start = 0
                                        
                                        if keywords:
                                            # Search for each keyword and find the best match
                                            for keyword in keywords:
                                                idx = content_lower.find(keyword)
                                                if idx >= 0:
                                                    # Extract large context around keyword (3000 chars)
                                                    start = max(0, idx - 1000)
                                                    end = min(len(content), idx + len(keyword) + 2000)
                                                    snippet = content[start:end]
                                                    if start > 0:
                                                        snippet = '...' + snippet
                                                    if end < len(content):
                                                        snippet = snippet + '...'
                                                    
                                                    # Use this snippet if it's better (contains more keywords or is longer)
                                                    if best_snippet is None or len(snippet) > len(best_snippet):
                                                        best_snippet = snippet
                                                        best_start = start
                                            
                                            if best_snippet:
                                                snippet = best_snippet
                                            else:
                                                # No keywords found, use first 3000 chars
                                                snippet = content[:3000] + '...' if len(content) > 3000 else content
                                        else:
                                            # No keywords, use first 3000 chars
                                            snippet = content[:3000] + '...' if len(content) > 3000 else content
                                        
                                        # For semantic search results, we want more content since we know it's relevant
                                        # Use up to 5000 chars to give LLM enough context
                                        if len(snippet) < 5000 and len(content) > len(snippet):
                                            # Try to expand the snippet if there's more content
                                            remaining = min(5000 - len(snippet), len(content) - len(snippet))
                                            if best_start > 0:
                                                # Add content before
                                                add_before = min(remaining // 2, best_start)
                                                snippet = content[best_start - add_before:best_start] + snippet
                                            if len(snippet) < 5000:
                                                # Add content after
                                                add_after = min(5000 - len(snippet), len(content) - (best_start + len(snippet)))
                                                if add_after > 0:
                                                    snippet = snippet + content[best_start + len(snippet):best_start + len(snippet) + add_after]
                                        
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
        Uses semantic search (embeddings) if available, with keyword fallback.
        
        Args:
            question: User's question
            company_id: Optional company ID to search company-specific documents
            
        Returns:
            Dictionary with answer or indication that no answer was found
        """
        logger.info(f"Getting answer for question: {question[:100]} (company_id: {company_id})")
        
        # Check if embeddings are available for semantic search
        use_semantic = self.embedding_service.is_available()
        if use_semantic:
            logger.info("Using semantic search (embeddings) for query")
        else:
            logger.info("Using keyword search (embeddings not available)")
        
        # Try full question first - this will use semantic search if embeddings are available
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
            # Get the most relevant result
            best_match = search_results['results'][0]
            # similarity_score can be None for FAQ/policy/manual (non-document) results
            _raw = best_match.get('similarity_score')
            similarity_score = _raw if _raw is not None else 0.0
            
            # Check if similarity is too low - might be irrelevant document
            if similarity_score < 0.2:
                logger.warning(f"Similarity score too low ({similarity_score}), document might not be relevant")
            
            if best_match['type'] == 'faq':
                answer = best_match.get('answer', '')
            elif best_match['type'] == 'document':
                # For documents, fetch full content and let LLM extract the answer
                content = best_match.get('content', '')
                document_id = best_match.get('id') or best_match.get('document_id')
                
                # Always fetch full document content
                if document_id:
                    try:
                        from Frontline_agent.models import Document
                        doc = Document.objects.filter(id=document_id).first()
                        if doc and doc.document_content:
                            full_content = doc.document_content
                            
                            # Extract keywords from question to verify relevance
                            import re
                            query_lower = question.lower()
                            query_words = re.findall(r'\b\w+\b', query_lower)
                            stop_words = {'what', 'is', 'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'how', 'do', 'does', 'can', 'will', 'are', 'was', 'were'}
                            keywords = [w for w in query_words if w not in stop_words and len(w) > 2]
                            
                            # Check if document contains any keywords (basic relevance check)
                            content_lower = full_content.lower()
                            has_keywords = any(kw in content_lower for kw in keywords) if keywords else True
                            
                            if not has_keywords and similarity_score < 0.3:
                                # Document doesn't seem relevant, return None to trigger "no info" response
                                logger.warning(f"Document {document_id} doesn't contain keywords {keywords} and similarity is low ({similarity_score})")
                                return {
                                    'success': True,
                                    'answer': None,
                                    'has_verified_info': False,
                                    'message': 'No verified information found in knowledge base'
                                }
                            
                            # SIMPLE APPROACH: Use reasonable amount of content
                            # Semantic search already found this document as relevant
                            # Pass enough content for LLM to find answer, but not so much it gets confused
                            
                            # For documents up to 15000 chars, use full content
                            # For larger documents, use first 15000 chars (enough for LLM to find answer)
                            if len(full_content) <= 15000:
                                answer = full_content
                                logger.info(f"Using full document content (length: {len(answer)}, doc_id: {document_id}, has_keywords: {has_keywords})")
                            else:
                                # Large document - use first 15000 chars
                                # Semantic search found this doc, so relevant info is likely in the content
                                answer = full_content[:15000]
                                logger.info(f"Using first 15000 chars of document (total: {len(full_content)}, doc_id: {document_id}, has_keywords: {has_keywords})")
                            
                            # Log content preview for debugging
                            logger.info(f"Document content preview: {answer[:500]}")
                        else:
                            answer = content
                            logger.warning(f"Document {document_id} not found or has no content, using snippet")
                    except Exception as e:
                        logger.error(f"Error fetching full document content: {e}", exc_info=True)
                        answer = content
                else:
                    answer = content
                    logger.warning(f"No document_id in best_match, using snippet content")
            else:
                answer = best_match.get('content', '')
            
            # Ensure we have actual content
            if not answer or len(answer.strip()) == 0:
                logger.warning(f"Document found but content is empty. Document ID: {best_match.get('id')}")
                answer = "I found a document in the knowledge base, but it appears to be empty or could not be processed."
            
            # Build citation for "Source: doc name / section"
            doc_id = best_match.get('id') or best_match.get('document_id')
            doc_title = best_match.get('title', '')
            source_label = best_match.get('source', 'PayPerProject Database')
            if best_match.get('type') == 'faq':
                citation_title = best_match.get('question', '') or 'FAQ'
            elif best_match.get('type') in ('policy', 'manual'):
                citation_title = best_match.get('title', '') or (best_match.get('policy_type') or best_match.get('manual_type') or 'Document')
            else:
                citation_title = doc_title or 'Uploaded Document'
            citation_display = f"{source_label}" + (f" – {citation_title}" if citation_title else "")
            citations = [{
                'source': source_label,
                'document_title': citation_title or None,
                'document_id': doc_id if best_match.get('type') == 'document' else None,
                'type': best_match.get('type', 'unknown'),
            }]
            logger.info(f"Found answer in knowledge base (type: {best_match.get('type')}, answer length: {len(answer)}, similarity: {best_match.get('similarity_score', 'N/A')})")
            return {
                'success': True,
                'answer': answer,
                'source': citation_display,
                'type': best_match.get('type', 'unknown'),
                'has_verified_info': True,
                'document_id': doc_id if best_match.get('type') == 'document' else None,
                'document_title': doc_title or citation_title or None,
                'citations': citations,
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
    
    def process_ticket(self, title: str, description: str, user_id: int, llm_extraction: Optional[Dict] = None, company_id: Optional[int] = None) -> Dict:
        """
        Process a ticket: classify, search for solution, and determine action.
        Optionally augments classification with LLM intent/entity extraction.
        
        Args:
            title: Ticket title
            description: Ticket description
            user_id: User ID who created the ticket
            llm_extraction: Optional dict from LLM with intent, entities, suggested_category, suggested_priority
            company_id: Optional company ID for the ticket (used for workflow triggers)
            
        Returns:
            Processing result dictionary
        """
        logger.info(f"Processing ticket from user {user_id}: {title[:50]}")
        
        # Classify ticket (rule-based)
        classification = self.classify_ticket(title, description)
        
        # Augment with LLM extraction when available
        valid_categories = {'technical', 'billing', 'account', 'feature_request', 'bug', 'other'}
        valid_priorities = {'low', 'medium', 'high', 'urgent'}
        if llm_extraction:
            if llm_extraction.get('suggested_category') and llm_extraction['suggested_category'].lower() in valid_categories:
                classification['category'] = llm_extraction['suggested_category'].lower()
                classification['llm_category'] = True
            if llm_extraction.get('suggested_priority') and llm_extraction['suggested_priority'].lower() in valid_priorities:
                classification['priority'] = llm_extraction['suggested_priority'].lower()
                classification['llm_priority'] = True
            if llm_extraction.get('entities'):
                classification['entities'] = llm_extraction['entities']
            if llm_extraction.get('intent'):
                classification['intent'] = llm_extraction['intent']
        
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
                    company_id=company_id,
                    status='auto_resolved' if can_auto_resolve else 'open',
                    auto_resolved=can_auto_resolve,
                    resolution=resolution_text if can_auto_resolve else None,
                    resolution_confidence=classification.get('confidence', 0.0) if can_auto_resolve else None,
                    resolved_at=timezone.now() if can_auto_resolve else None
                )
                
                logger.info(f"Ticket created: ID {ticket.id}, Status: {ticket.status}")
                
                out = {
                    'success': True,
                    'ticket_id': ticket.id,
                    'ticket_status': ticket.status,
                    'classification': classification,
                    'auto_resolved': can_auto_resolve,
                    'resolution': resolution_text if can_auto_resolve else None,
                    'should_escalate': classification.get('should_escalate', False),
                    'message': 'Ticket processed successfully'
                }
                if classification.get('intent'):
                    out['intent'] = classification['intent']
                if classification.get('entities'):
                    out['entities'] = classification['entities']
                return out
        except Exception as e:
            logger.error(f"Failed to create ticket: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'classification': classification
            }
