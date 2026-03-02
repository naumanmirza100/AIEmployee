"""
Frontline Agent Services
Enterprise-level service layer for knowledge retrieval and ticket automation
"""
import logging
from datetime import timedelta
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
    
    def search_knowledge(
        self,
        query: str,
        max_results: int = 5,
        company_id: Optional[int] = None,
        scope_document_type: Optional[List[str]] = None,
        scope_document_ids: Optional[List[int]] = None,
    ) -> Dict:
        """
        Search knowledge base (FAQs, policies, manuals, uploaded documents) for relevant information.
        scope_document_type: optional list of document types to restrict uploaded docs (e.g. ['policy']).
        scope_document_ids: optional list of document IDs to restrict uploaded docs to specific documents.
        """
        logger.info(f"Searching knowledge base for: {query[:100]} (company_id: {company_id}, scope: type={scope_document_type}, ids={scope_document_ids})")
        
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
                documents = self._search_documents(
                    query, company_id, max_results,
                    scope_document_type=scope_document_type,
                    scope_document_ids=scope_document_ids,
                )
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
    
    def _search_documents(
        self,
        query: str,
        company_id: int,
        max_results: int,
        scope_document_type: Optional[List[str]] = None,
        scope_document_ids: Optional[List[int]] = None,
    ) -> List[Dict]:
        """
        Search uploaded documents for company using hybrid search (chunk embeddings + keyword) and RRF.
        Returns the top_k chunks re-ranked by language model.
        """
        try:
            from Frontline_agent.models import Document, DocumentChunk
            from django.db.models import Q
            import json
            
            # Base document filter
            all_documents = Document.objects.filter(
                company_id=company_id,
                is_indexed=True,
                processed=True
            )
            if scope_document_type:
                all_documents = all_documents.filter(document_type__in=scope_document_type)
            if scope_document_ids:
                all_documents = all_documents.filter(id__in=scope_document_ids)
                
            doc_ids = list(all_documents.values_list('id', flat=True))
            if not doc_ids:
                return []
                
            all_chunks = DocumentChunk.objects.filter(document_id__in=doc_ids).select_related('document')

            # 1. Semantic Search
            semantic_results = []
            if self.embedding_service.is_available():
                try:
                    logger.info("Generating query embedding for hybrid search")
                    query_embedding = self.embedding_service.generate_embedding(query)
                    if query_embedding:
                        chunks_with_embeddings = all_chunks.exclude(embedding__isnull=True).exclude(embedding='')
                        for chunk in chunks_with_embeddings:
                            try:
                                chunk_emb = json.loads(chunk.embedding) if isinstance(chunk.embedding, str) else chunk.embedding
                                similarity = self.embedding_service.cosine_similarity(query_embedding, chunk_emb)
                                semantic_results.append({
                                    'chunk_id': chunk.id,
                                    'document_id': chunk.document_id,
                                    'score': similarity,
                                    'content': chunk.chunk_text,
                                    'title': f"{chunk.document.title} (Chunk {chunk.chunk_index})",
                                    'file_format': chunk.document.file_format,
                                    'document_type': chunk.document.document_type
                                })
                            except Exception as e:
                                pass
                        semantic_results.sort(key=lambda x: x['score'], reverse=True)
                        semantic_results = semantic_results[:50] # Top 50 semantic
                except Exception as e:
                    logger.warning(f"Semantic search failed: {e}")
            
            # 2. Keyword Search
            keyword_results = []
            matching_chunks = all_chunks.filter(chunk_text__icontains=query)[:50]
            for chunk in matching_chunks:
                keyword_results.append({
                    'chunk_id': chunk.id,
                    'document_id': chunk.document_id,
                    'score': 1.0, # Base keyword score
                    'content': chunk.chunk_text,
                    'title': f"{chunk.document.title} (Chunk {chunk.chunk_index})",
                    'file_format': chunk.document.file_format,
                    'document_type': chunk.document.document_type
                })
                
            # 3. Reciprocal Rank Fusion (RRF)
            # RRF Score = sum(1 / (k + rank))
            k = 60
            chunk_scores = {}
            chunk_data = {}
            
            for rank, res in enumerate(semantic_results):
                cid = res['chunk_id']
                chunk_scores[cid] = chunk_scores.get(cid, 0) + (1.0 / (k + rank + 1))
                chunk_data[cid] = res
                
            for rank, res in enumerate(keyword_results):
                cid = res['chunk_id']
                chunk_scores[cid] = chunk_scores.get(cid, 0) + (1.0 / (k + rank + 1))
                if cid not in chunk_data:
                    chunk_data[cid] = res
                    
            # 4. Sort and return top chunks
            sorted_chunks = sorted(chunk_scores.items(), key=lambda x: x[1], reverse=True)[:max_results*2]
            
            results = []
            for cid, score in sorted_chunks:
                data = chunk_data[cid]
                results.append({
                    'id': data['document_id'],
                    'chunk_id': cid,
                    'title': data['title'],
                    'content': data['content'],
                    'file_format': data['file_format'],
                    'document_type': data['document_type'],
                    'similarity_score': round(score, 3),
                    'search_method': 'hybrid'
                })
                
            # Fallback for monolithic documents that don't have chunks yet
            if not results:
                docs = all_documents.filter(document_content__icontains=query)[:max_results]
                for doc in docs:
                    results.append({
                        'id': doc.id,
                        'chunk_id': None,
                        'title': doc.title,
                        'content': (doc.document_content[:2000] + '...') if doc.document_content and len(doc.document_content) > 2000 else doc.document_content,
                        'file_format': doc.file_format,
                        'document_type': doc.document_type,
                        'similarity_score': 0.5,
                        'search_method': 'keyword_fallback'
                    })

            # 5. LLM Re-Ranking
            if results and self.embedding_service.is_available():
                results = self._llm_rerank(query, results, top_k=max_results)
                
            return results[:max_results]
        except Exception as e:
            logger.error(f"Document search failed: {e}", exc_info=True)
            return []

    def _llm_rerank(self, query: str, candidates: List[Dict], top_k: int) -> List[Dict]:
        """
        Use LLM cross-encoding logic to re-rank retrieved candidate chunks.
        """
        try:
            if not candidates:
                return candidates
                
            chunks_text = ""
            for i, cand in enumerate(candidates):
                chunks_text += f"\n--- Chunk {i} ---\n{cand['content'][:1000]}\n"
                
            prompt = f"""Given the user query, evaluate the following document chunks.
For each chunk, score it from 0 to 10 on how well it directly answers or contains information highly relevant to the query.
Return ONLY a JSON list of integers representing the scores in the exact order of the chunks. E.g. [8, 0, 5, 2]

Query: {query}

Chunks:
{chunks_text}
"""
            import openai
            from django.conf import settings
            client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a precise document retrieval evaluator. Output ONLY a valid JSON list of integers."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0
            )
            raw = response.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            import json
            scores = json.loads(raw.strip())
            
            # Apply rerank scores if the lists match in size
            if len(scores) == len(candidates):
                for cand, score in zip(candidates, scores):
                    cand['rerank_score'] = cand['similarity_score'] + (score / 10.0)
                candidates.sort(key=lambda x: x.get('rerank_score', 0), reverse=True)
                
            return candidates[:top_k]
        except Exception as e:
            logger.warning(f"LLM reranking failed: {e}")
            return candidates[:top_k]

    
    def get_answer(
        self,
        question: str,
        company_id: Optional[int] = None,
        scope_document_type: Optional[List[str]] = None,
        scope_document_ids: Optional[List[int]] = None,
    ) -> Dict:
        """
        Get answer to a question from knowledge base and uploaded documents.
        scope_document_type / scope_document_ids restrict search to specific document types or IDs.
        """
        logger.info(f"Getting answer for question: {question[:100]} (company_id: {company_id}, scope: type={scope_document_type}, ids={scope_document_ids})")
        
        # Check if embeddings are available for semantic search
        use_semantic = self.embedding_service.is_available()
        if use_semantic:
            logger.info("Using semantic search (embeddings) for query")
        else:
            logger.info("Using keyword search (embeddings not available)")
        
        # Try full question first - this will use semantic search if embeddings are available
        search_results = self.search_knowledge(
            question, max_results=5, company_id=company_id,
            scope_document_type=scope_document_type,
            scope_document_ids=scope_document_ids,
        )
        
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
                    keyword_results = self.search_knowledge(
                        keyword, max_results=3, company_id=company_id,
                        scope_document_type=scope_document_type,
                        scope_document_ids=scope_document_ids,
                    )
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
                # For documents, we now use the context from the intelligent chunking
                # Combine top 3 chunks to give LLM maximum context
                content_chunks = []
                for res in search_results['results'][:3]:
                    if res.get('type', res.get('document_type', 'document')) == 'document' and res.get('content'):
                        content_chunks.append(f"--- Document: {res.get('title', 'Unknown')} ---\n{res.get('content')}")
                
                content = "\n\n".join(content_chunks)
                document_id = best_match.get('id') or best_match.get('document_id')
                
                # Check minimum similarity if semantic search is used
                if similarity_score < 0.2 and not content:
                    logger.warning(f"Document {document_id} has low similarity ({similarity_score}) and no content.")
                    return {
                        'success': True,
                        'answer': None,
                        'has_verified_info': False,
                        'message': 'No verified information found in knowledge base'
                    }

                # Use the chunk content retrieved by _search_documents
                answer = content
                logger.info(f"Using document chunk content (length: {len(answer)}, doc_id: {document_id})")
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
            
            priority = classification.get('priority', 'medium')
            sla_hours = {'urgent': 4, 'high': 8, 'medium': 24, 'low': 48}.get((priority or 'medium').lower(), 24)
            sla_due_at = timezone.now() + timedelta(hours=sla_hours) if not can_auto_resolve else None
            with transaction.atomic():
                ticket = Ticket.objects.create(
                    title=title,
                    description=description,
                    category=classification.get('category', 'other'),
                    priority=priority,
                    created_by=user,
                    company_id=company_id,
                    status='auto_resolved' if can_auto_resolve else 'open',
                    auto_resolved=can_auto_resolve,
                    resolution=resolution_text if can_auto_resolve else None,
                    resolution_confidence=classification.get('confidence', 0.0) if can_auto_resolve else None,
                    resolved_at=timezone.now() if can_auto_resolve else None,
                    sla_due_at=sla_due_at,
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
