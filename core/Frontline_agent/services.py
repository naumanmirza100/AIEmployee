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
        max_age_days: Optional[int] = None,
        company_user_id: Optional[int] = None,
    ) -> Dict:
        """
        Search knowledge base (FAQs, policies, manuals, uploaded documents) for relevant information.
        scope_document_type: optional list of document types to restrict uploaded docs (e.g. ['policy']).
        scope_document_ids: optional list of document IDs to restrict uploaded docs to specific documents.
        max_age_days: optional recency filter — only uploaded docs updated within this window are searched.
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
                    max_age_days=max_age_days,
                    company_user_id=company_user_id,
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
        max_age_days: Optional[int] = None,
        company_user_id: Optional[int] = None,
    ) -> List[Dict]:
        """
        Search uploaded documents for company using hybrid search (chunk embeddings + keyword) and RRF.
        Returns the top_k chunks re-ranked by language model.
        Enforces: superseded-revision exclusion, processing_status='ready', and
        per-document visibility (company vs private → allowed_users).
        """
        try:
            from Frontline_agent.models import Document, DocumentChunk
            from django.db.models import Q
            from django.utils import timezone
            from datetime import timedelta
            import json

            # Base document filter
            all_documents = Document.objects.filter(
                company_id=company_id,
                is_indexed=True,
                processed=True,
                superseded_by__isnull=True,          # skip old revisions
                processing_status='ready',           # skip in-flight / failed docs
            )
            # Visibility gate: 'company' docs are available to any company user.
            # 'private' docs require the asker to be in allowed_users.
            if company_user_id is not None:
                all_documents = all_documents.filter(
                    Q(visibility='company') | Q(visibility='private', allowed_users__id=company_user_id)
                ).distinct()
            else:
                # No user context (e.g. public widget): company-wide visibility only.
                all_documents = all_documents.filter(visibility='company')
            if scope_document_type:
                all_documents = all_documents.filter(document_type__in=scope_document_type)
            if scope_document_ids:
                all_documents = all_documents.filter(id__in=scope_document_ids)
            if max_age_days is not None and max_age_days > 0:
                cutoff = timezone.now() - timedelta(days=int(max_age_days))
                all_documents = all_documents.filter(updated_at__gte=cutoff)
                
            doc_ids = list(all_documents.values_list('id', flat=True))
            if not doc_ids:
                return []
                
            all_chunks = DocumentChunk.objects.filter(document_id__in=doc_ids).select_related('document')

            # 1. Semantic Search
            # Prefers a FAISS inner-product index (O(log N)); falls back to the
            # legacy per-chunk JSON scan (O(N)) when faiss isn't installed or
            # the company has no built index yet.
            semantic_results = []
            if self.embedding_service.is_available():
                try:
                    logger.info("Generating query embedding for hybrid search")
                    query_embedding = self.embedding_service.generate_embedding(query)
                    if query_embedding:
                        semantic_results = self._semantic_search(
                            query_embedding=query_embedding,
                            company_id=company_id,
                            allowed_doc_ids=doc_ids,
                            all_chunks=all_chunks,
                        )
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
            # RRF Score = sum(1 / (k + rank)) — good for ordering, but the magnitude
            # is tiny (top hit ≈ 0.016) and MUST NOT be compared against the
            # cosine-space confidence threshold. We preserve the true semantic
            # score alongside the RRF score so `get_answer` can gate on the real one.
            k = 60
            chunk_scores = {}
            chunk_data = {}
            semantic_score_by_chunk = {}

            for rank, res in enumerate(semantic_results):
                cid = res['chunk_id']
                chunk_scores[cid] = chunk_scores.get(cid, 0) + (1.0 / (k + rank + 1))
                chunk_data[cid] = res
                # `res['score']` is cosine similarity from _semantic_search.
                semantic_score_by_chunk[cid] = float(res.get('score') or 0.0)

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
                    # RRF score — used for ordering inside this function only.
                    'similarity_score': round(score, 3),
                    # True cosine similarity (None when only keyword-matched).
                    # This is what `get_answer` compares against the confidence threshold.
                    'semantic_score': (round(semantic_score_by_chunk[cid], 3)
                                       if cid in semantic_score_by_chunk else None),
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

    def _semantic_search(self, *, query_embedding, company_id,
                         allowed_doc_ids, all_chunks):
        """Run the semantic half of hybrid search. Uses FAISS when available,
        else the legacy JSON-scan path. Returns a list of chunk dicts shaped
        for RRF (chunk_id, document_id, score, content, title, ...)."""
        import json as _json
        from Frontline_agent import vector_store as _vs

        # ---- FAISS path ---------------------------------------------------
        if _vs.FAISS_AVAILABLE:
            store = _vs.get_store(company_id)
            if store is not None:
                # Candidate set = chunks whose parent document survived our filters.
                candidate_chunk_ids = set(all_chunks.values_list('id', flat=True))
                hits = store.search(query_embedding, k=50,
                                    candidate_chunk_ids=candidate_chunk_ids)
                if hits:
                    hit_ids = [cid for cid, _ in hits]
                    # Single DB fetch for metadata on the small top-k set.
                    chunk_map = {c.id: c for c in all_chunks.filter(id__in=hit_ids)}
                    out = []
                    for cid, score in hits:
                        c = chunk_map.get(cid)
                        if c is None:
                            continue
                        out.append({
                            'chunk_id': c.id,
                            'document_id': c.document_id,
                            'score': float(score),
                            'content': c.chunk_text,
                            'title': f"{c.document.title} (Chunk {c.chunk_index})",
                            'file_format': c.document.file_format,
                            'document_type': c.document.document_type,
                        })
                    return out

        # ---- Legacy JSON-scan fallback -----------------------------------
        # Used when faiss isn't installed, the tenant has no built index yet,
        # or the FAISS call returned no hits (e.g. dim mismatch mid-rebuild).
        semantic_results = []
        chunks_with_embeddings = all_chunks.exclude(embedding__isnull=True).exclude(embedding='')
        for chunk in chunks_with_embeddings:
            try:
                chunk_emb = _json.loads(chunk.embedding) if isinstance(chunk.embedding, str) else chunk.embedding
                similarity = self.embedding_service.cosine_similarity(query_embedding, chunk_emb)
                semantic_results.append({
                    'chunk_id': chunk.id,
                    'document_id': chunk.document_id,
                    'score': similarity,
                    'content': chunk.chunk_text,
                    'title': f"{chunk.document.title} (Chunk {chunk.chunk_index})",
                    'file_format': chunk.document.file_format,
                    'document_type': chunk.document.document_type,
                })
            except Exception:
                pass
        semantic_results.sort(key=lambda x: x['score'], reverse=True)
        return semantic_results[:50]

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
        min_similarity: Optional[float] = None,
        max_age_days: Optional[int] = None,
        max_results: int = 5,
        company_user_id: Optional[int] = None,
    ) -> Dict:
        """
        Get answer to a question from knowledge base and uploaded documents.

        Filters:
        - scope_document_type / scope_document_ids: restrict uploaded-doc search
        - min_similarity: override the default confidence threshold (0.0–1.0).
          Matches with a lower score are treated as "no verified info" and escalate.
        - max_age_days: skip uploaded documents not updated within this many days.
        - max_results: number of top chunks to feed to the LLM (default 5).
        """
        from django.conf import settings as _dj_settings
        default_threshold = float(getattr(_dj_settings, 'FRONTLINE_RAG_MIN_CONFIDENCE', 0.3))
        threshold = float(min_similarity) if min_similarity is not None else default_threshold

        logger.info(
            "Getting answer: q=%s company_id=%s scope_type=%s scope_ids=%s "
            "threshold=%.2f max_age_days=%s max_results=%d",
            question[:100], company_id, scope_document_type, scope_document_ids,
            threshold, max_age_days, max_results,
        )

        # Try full question first - will use semantic search if embeddings are available
        search_results = self.search_knowledge(
            question, max_results=max_results, company_id=company_id,
            scope_document_type=scope_document_type,
            scope_document_ids=scope_document_ids,
            max_age_days=max_age_days,
            company_user_id=company_user_id,
        )

        # Keyword fallback if initial search came up empty
        if not search_results['success'] or search_results['count'] == 0:
            import re
            stop_words = {
                'the','a','an','and','or','but','in','on','at','to','for','of','with','by',
                'is','are','was','were','be','been','being','have','has','had','do','does','did',
                'will','would','should','could','may','might','must','can','what','when','where',
                'who','why','how','this','that','these','those','i','you','he','she','it','we',
                'they','me','him','her','us','them'
            }
            words = re.findall(r'\b\w+\b', question.lower())
            keywords = [w for w in words if w not in stop_words and len(w) > 2]
            for keyword in keywords[:3]:
                kw_results = self.search_knowledge(
                    keyword, max_results=max(3, max_results // 2), company_id=company_id,
                    scope_document_type=scope_document_type,
                    scope_document_ids=scope_document_ids,
                    max_age_days=max_age_days,
                    company_user_id=company_user_id,
                )
                if kw_results['success'] and kw_results['count'] > 0:
                    search_results = kw_results
                    logger.info(f"Found results using keyword: {keyword}")
                    break

        if not (search_results['success'] and search_results['count'] > 0):
            logger.info("No verified information found in knowledge base")
            return {
                'success': True, 'answer': None, 'has_verified_info': False,
                'confidence': 'none', 'citations': [],
                'message': 'No verified information found in knowledge base',
            }

        best_match = search_results['results'][0]
        best_type = best_match.get('type', 'unknown')
        # Confidence is gated on the TRUE cosine similarity from semantic search
        # (`semantic_score`), NOT the RRF score (`similarity_score`), which is an
        # ordering-only quantity in the ~0.01–0.05 range and would fail every
        # 0.3 threshold. A None here means the match came from keyword search
        # only — we treat that as "low but not zero" and still answer, rather
        # than escalating a perfectly good keyword hit.
        sem_raw = best_match.get('semantic_score')
        best_score_f = float(sem_raw) if sem_raw is not None else None

        # Confidence enforcement: for document matches, reject below threshold.
        # FAQ / policy / manual entries are curated — trust them regardless of score.
        if (best_type == 'document'
                and best_score_f is not None
                and best_score_f < threshold):
            logger.info(
                "Top document match below confidence threshold (%.3f < %.3f) — escalating",
                best_score_f, threshold,
            )
            return {
                'success': True, 'answer': None, 'has_verified_info': False,
                'confidence': 'low', 'best_score': round(best_score_f, 3),
                'threshold': round(threshold, 3),
                'citations': [],
                'message': 'No sufficiently confident match found in knowledge base',
            }

        # Build answer content + multi-source citations
        if best_type == 'faq':
            answer = best_match.get('answer', '')
            citations = [{
                'type': 'faq',
                'source': best_match.get('source', 'PayPerProject Database'),
                'title': best_match.get('question') or 'FAQ',
                'document_id': None,
                'chunk_id': None,
                'score': None,
                'snippet': (answer[:200] if answer else None),
            }]
        elif best_type == 'document':
            # Aggregate the top `max_results` document chunks (LLM sees them all)
            doc_chunks = [r for r in search_results['results']
                          if r.get('type') == 'document' and r.get('content')]
            # Order already reflects RRF + LLM rerank; take up to max_results
            doc_chunks = doc_chunks[:max_results]

            content_parts = [
                f"--- Document: {r.get('title', 'Unknown')} ---\n{r.get('content')}"
                for r in doc_chunks
            ]
            answer = "\n\n".join(content_parts) or ''

            # Surface the cosine score when we have one (helpful for the UI);
            # fall back to the RRF score otherwise so the citation isn't score-less.
            def _display_score(row):
                s = row.get('semantic_score')
                if s is not None:
                    return round(float(s), 3)
                s = row.get('similarity_score')
                return round(float(s), 3) if s is not None else None

            citations = [{
                'type': 'document',
                'source': r.get('source', 'Uploaded Document'),
                'title': r.get('title') or 'Uploaded Document',
                'document_id': r.get('document_id') or r.get('id'),
                'chunk_id': r.get('chunk_id'),
                'score': _display_score(r),
                'snippet': (r.get('content') or '')[:200],
            } for r in doc_chunks]
            logger.info(
                "Using %d document chunks as context (top score: %s)",
                len(doc_chunks),
                f"{best_score_f:.3f}" if best_score_f is not None else "keyword-only",
            )
        else:
            # Policy / manual / other curated sources
            answer = best_match.get('content', '') or ''
            label = best_match.get('title') or (
                best_match.get('policy_type') or best_match.get('manual_type') or 'Document'
            )
            citations = [{
                'type': best_type,
                'source': best_match.get('source', 'PayPerProject Database'),
                'title': label,
                'document_id': None,
                'chunk_id': None,
                'score': None,
                'snippet': (answer[:200] if answer else None),
            }]

        if not answer or not answer.strip():
            logger.warning("Top match produced empty content (id=%s)", best_match.get('id'))
            answer = "I found a document in the knowledge base, but it appears to be empty or could not be processed."

        primary = citations[0]
        source_display = f"{primary['source']}"
        if primary.get('title'):
            source_display += f" – {primary['title']}"

        # confidence label: 'high' well above threshold, 'medium' otherwise.
        # keyword-only matches (best_score_f is None) → 'medium' (we have something).
        if best_score_f is not None and best_score_f >= max(threshold + 0.2, 0.5):
            _confidence_label = 'high'
        else:
            _confidence_label = 'medium'
        return {
            'success': True,
            'answer': answer,
            'has_verified_info': True,
            'confidence': _confidence_label,
            'best_score': (round(best_score_f, 3)
                           if best_type == 'document' and best_score_f is not None
                           else None),
            'threshold': round(threshold, 3),
            'source': source_display,
            'type': best_type,
            'document_id': primary.get('document_id'),
            'document_title': primary.get('title'),
            'citations': citations,
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
                    intent=classification.get('intent'),
                    entities=classification.get('entities') or {}
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
