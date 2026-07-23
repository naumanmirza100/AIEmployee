"""
Operations Knowledge Q&A Agent

Answers user questions about uploaded operations documents (PDFs, DOCX, XLSX, etc.).
Uses keyword-based retrieval over document chunks + Groq LLM for answer generation.
Returns well-structured markdown responses with headings, sub-headings, and source citations.

Kept deliberately simple and defensive: every failure mode returns a friendly message
instead of raising, so the chat UI never crashes.
"""

import hashlib
import json as _json
import logging
import operator
import re
import threading
import time
from functools import reduce
from typing import Dict, List, Optional, Tuple

from django.conf import settings
from django.db.models import Q

from marketing_agent.agents.marketing_base_agent import MarketingBaseAgent
from operations_agent.models import (
    OperationsDocument,
    OperationsDocumentChunk,
    OperationsDocumentSummary,
)

try:
    import numpy as _np
    _HAS_NUMPY = True
except Exception:  # pragma: no cover
    _np = None
    _HAS_NUMPY = False

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# In-process caches (mirrors core/HR_agent/services.py). These make the
# semantic fallback fast and let repeat questions skip re-embedding.
#   * _CHUNK_EMBEDDING_CACHE — chunk_id -> numpy vector (parsed once)
#   * _QUERY_EMBEDDING_CACHE — sha256(query) -> numpy vector
#   * _CHUNK_JUNK_CACHE      — chunk_id -> bool (TOC/junk classification)
# Bounded to avoid unbounded growth; half-drop eviction when full.
# ---------------------------------------------------------------------------
_CACHE_LOCK = threading.Lock()
_CHUNK_EMBEDDING_CACHE: dict = {}
_CHUNK_JUNK_CACHE: dict = {}
_QUERY_EMBEDDING_CACHE: dict = {}
_CACHE_MAX = 20_000

# Answer cache: sha256({company, question}) -> (timestamp, response dict)
_ANSWER_CACHE_LOCK = threading.Lock()
_ANSWER_CACHE: dict = {}
_ANSWER_CACHE_MAX = 2000


def _parse_embedding(raw):
    if raw is None:
        return None
    try:
        vec = _json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return None
    if not vec:
        return None
    if _HAS_NUMPY:
        try:
            arr = _np.asarray(vec, dtype=_np.float32)
            return arr if arr.size else None
        except Exception:
            return vec
    return vec


def _cache_get_chunk_vec(chunk_id, raw):
    with _CACHE_LOCK:
        hit = _CHUNK_EMBEDDING_CACHE.get(chunk_id)
        if hit is not None:
            return hit
    vec = _parse_embedding(raw)
    if vec is None:
        return None
    with _CACHE_LOCK:
        if len(_CHUNK_EMBEDDING_CACHE) >= _CACHE_MAX:
            for k in list(_CHUNK_EMBEDDING_CACHE.keys())[: _CACHE_MAX // 2]:
                _CHUNK_EMBEDDING_CACHE.pop(k, None)
        _CHUNK_EMBEDDING_CACHE[chunk_id] = vec
    return vec


def _cache_get_query_vec(query, embedding_service):
    key = hashlib.sha256((query or '').strip().lower().encode('utf-8')).hexdigest()
    with _CACHE_LOCK:
        hit = _QUERY_EMBEDDING_CACHE.get(key)
        if hit is not None:
            return hit
    raw = embedding_service.generate_embedding(query)
    vec = _parse_embedding(raw)
    if vec is None:
        return None
    with _CACHE_LOCK:
        if len(_QUERY_EMBEDDING_CACHE) > 512:
            for k in list(_QUERY_EMBEDDING_CACHE.keys())[:256]:
                _QUERY_EMBEDDING_CACHE.pop(k, None)
        _QUERY_EMBEDDING_CACHE[key] = vec
    return vec


def _semantic_score(qvec, cvec):
    if qvec is None or cvec is None:
        return None
    if _HAS_NUMPY and isinstance(qvec, _np.ndarray) and isinstance(cvec, _np.ndarray):
        if qvec.shape != cvec.shape:
            return None
        denom = float(_np.linalg.norm(qvec)) * float(_np.linalg.norm(cvec))
        if denom == 0.0:
            return None
        return float(_np.dot(qvec, cvec) / denom)
    try:
        import math as _m
        dot = sum(x * y for x, y in zip(qvec, cvec))
        na = _m.sqrt(sum(x * x for x in qvec))
        nb = _m.sqrt(sum(y * y for y in cvec))
        if na == 0 or nb == 0:
            return None
        return dot / (na * nb)
    except Exception:
        return None


def _is_junk_chunk(chunk_id, text) -> bool:
    with _CACHE_LOCK:
        hit = _CHUNK_JUNK_CACHE.get(chunk_id)
        if hit is not None:
            return hit
    try:
        from operations_agent.chunking import looks_like_toc_or_index
        verdict = looks_like_toc_or_index(text or '')
    except Exception:
        verdict = False
    with _CACHE_LOCK:
        if len(_CHUNK_JUNK_CACHE) >= _CACHE_MAX:
            for k in list(_CHUNK_JUNK_CACHE.keys())[: _CACHE_MAX // 2]:
                _CHUNK_JUNK_CACHE.pop(k, None)
        _CHUNK_JUNK_CACHE[chunk_id] = verdict
    return verdict


# --- Answer cache helpers (mirrors core/HR_agent/hr_agent.py) --------------

def _answer_cache_key(company_id, question) -> str:
    payload = _json.dumps(
        {'c': int(company_id or 0), 'q': (question or '').strip().lower()},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def _answer_cache_get(key, ttl_seconds):
    with _ANSWER_CACHE_LOCK:
        entry = _ANSWER_CACHE.get(key)
        if not entry:
            return None
        ts, resp = entry
        if time.time() - ts > ttl_seconds:
            _ANSWER_CACHE.pop(key, None)
            return None
        return resp


def _answer_cache_put(key, resp):
    with _ANSWER_CACHE_LOCK:
        if len(_ANSWER_CACHE) >= _ANSWER_CACHE_MAX:
            for k in list(_ANSWER_CACHE.keys())[: _ANSWER_CACHE_MAX // 2]:
                _ANSWER_CACHE.pop(k, None)
        _ANSWER_CACHE[key] = (time.time(), resp)


def invalidate_answer_cache_for_company(company_id) -> None:
    """Called from the processing pipeline when a new doc goes live. Clears the
    answer cache so the next question sees the fresh document."""
    if not company_id:
        return
    with _ANSWER_CACHE_LOCK:
        _ANSWER_CACHE.clear()


SYSTEM_PROMPT = (
    "You are the Operations Knowledge Assistant for a company's internal document library. "
    "You answer questions strictly based on the provided document excerpts (contracts, invoices, "
    "reports, memos, policies, manuals, spreadsheets, presentations).\n\n"
    "SCOPE RULES — read these first:\n"
    "- Your ONLY job is answering questions about the user's uploaded operations documents.\n"
    "- If the question is personal, conversational, or unrelated to the documents (e.g. "
    "\"do you have kids\", \"how are you\", \"what's the weather\", \"tell me a joke\", "
    "questions about yourself, opinions, or general knowledge), do NOT summarise the document "
    "excerpts. Instead, reply with a brief, friendly one-liner explaining that you only answer "
    "questions about the uploaded documents, and suggest 1–2 example questions the user could ask.\n"
    "- If the provided excerpts clearly do not address the user's question, say so plainly. Do "
    "NOT pad the answer with unrelated content from the excerpts just because it was retrieved.\n\n"
    "FORMATTING RULES — apply only when actually answering a document question:\n"
    "1. Respond in GitHub-flavored Markdown.\n"
    "2. Start with a one-line direct answer (no heading).\n"
    "3. Then use `## Section` headings and `### Sub-section` sub-headings to organise details.\n"
    "4. Use short bullet lists (`- item`) for key points, numbered lists for steps.\n"
    "5. Use **bold** for important terms, numbers, dates, and names.\n"
    "6. If the answer includes tabular data, format as a Markdown table.\n"
    "7. At the end, add a `## Sources` section listing the document titles and page numbers you used.\n"
    "   Do NOT include a Sources section when refusing an off-topic question.\n\n"
    "CONTENT RULES:\n"
    "- Only use facts present in the excerpts. If the answer is not in the excerpts, say so clearly "
    "and suggest what document the user should upload.\n"
    "- Never invent numbers, dates, names, or clauses.\n"
    "- NO preamble. NO meta-commentary like \"Based on the provided excerpts…\" or \"According to the "
    "document content…\" — just answer directly.\n"
    "- Do NOT block-quote chunk text verbatim; synthesise the answer in your own words.\n"
    "- Be concise but complete — aim for clarity over length.\n"
    "- If the user asks for a list of documents or a count, answer from the document metadata provided.\n"
)


# Very short list of English stopwords for keyword retrieval
_STOPWORDS = {
    'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'am', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'this', 'that',
    'these', 'those', 'what', 'which', 'who', 'whom', 'when', 'where',
    'why', 'how', 'of', 'to', 'in', 'on', 'at', 'by', 'for', 'with',
    'about', 'as', 'from', 'into', 'out', 'and', 'or', 'but', 'if',
    'then', 'else', 'not', 'no', 'do', 'does', 'did', 'have', 'has',
    'had', 'can', 'could', 'should', 'would', 'will', 'shall', 'may',
    'might', 'must', 'any', 'all', 'some', 'me', 'my', 'your', 'our',
    'tell', 'show', 'give', 'please', 'list', 'find', 'get',
}


def _tokenize(text: str) -> List[str]:
    if not text:
        return []
    words = re.findall(r"[A-Za-z0-9]{2,}", text.lower())
    return [w for w in words if w not in _STOPWORDS]


# Patterns for clearly off-topic / conversational questions that should never trigger
# a document summary. Kept narrow to avoid catching legitimate doc queries like
# "do you have any contracts about X" — those mention doc-domain words.
_OFF_TOPIC_PATTERNS = [
    re.compile(r"\b(do|did|have|had)\s+you\s+(have|own|get|got)\s+(any\s+)?(kids?|children|"
               r"family|wife|husband|spouse|partner|girlfriend|boyfriend|pets?|dogs?|cats?|"
               r"siblings?|brothers?|sisters?|parents?|mom|dad|mother|father)\b", re.I),
    re.compile(r"\b(are|were|r)\s+you\s+(married|single|divorced|alive|dead|human|real|"
               r"sentient|conscious|happy|sad|tired|bored|ok|okay|fine|sure|there|here|"
               r"a\s+(bot|robot|ai|machine|person|human|man|woman|girl|boy))\b", re.I),
    re.compile(r"\bhow\s+(are|r|do|did)\s+you(?:\s+(doing|feel|feeling|today))?\b", re.I),
    re.compile(r"\bhow'?s\s+(it\s+going|your\s+day|life)\b", re.I),
    re.compile(r"\b(what'?s|what\s+is|what\s+are)\s+your\s+(name|age|favou?rite|"
               r"opinion|view|gender|religion|hobby|job|salary)\b", re.I),
    re.compile(r"\bwho\s+(are|made|built|created|trained)\s+you\b", re.I),
    re.compile(r"\bwhat\s+are\s+you\b", re.I),
    re.compile(r"\btell\s+me\s+(a\s+)?(joke|story|secret|riddle|poem|something\s+funny)\b", re.I),
    re.compile(r"\b(what'?s|what\s+is|how'?s|how\s+is)\s+the\s+weather\b", re.I),
    re.compile(r"\bdo\s+you\s+(like|love|hate|enjoy|prefer|believe|think|feel|dream|sleep|eat|"
               r"drink|exist|live)\b", re.I),
    re.compile(r"\bcan\s+you\s+(sing|dance|cook|drive|swim|fly|cry|laugh|feel|dream)\b", re.I),
    # Pure greetings / small talk with nothing else of substance. Allow a short
    # trailing address like "hi there" / "hello team" but not a full sentence.
    re.compile(r"^\s*(hi|hello|hey|yo|sup|hiya|howdy|greetings|good\s+(morning|afternoon|"
               r"evening|night))(\s+(there|everyone|all|team|guys|folks|friend|buddy))?"
               r"[\s.!?,]*$", re.I),
    re.compile(r"^\s*(thanks|thank\s+you|thx|ty|cheers|bye|goodbye|see\s+ya|cya)[\s.!?,]*$", re.I),
]


def _looks_off_topic(question: str) -> bool:
    """True for personal, conversational, or general-knowledge questions that have
    nothing to do with the user's uploaded operations documents."""
    if not question:
        return False
    return any(pat.search(question) for pat in _OFF_TOPIC_PATTERNS)


def _score_chunk(chunk_text: str, question_tokens: List[str]) -> int:
    """Return a simple keyword-overlap score."""
    if not chunk_text or not question_tokens:
        return 0
    chunk_lower = chunk_text.lower()
    score = 0
    for tok in set(question_tokens):
        # count occurrences capped at 3 per token to avoid spammy over-weight
        cnt = chunk_lower.count(tok)
        score += min(cnt, 3) * (2 if len(tok) >= 5 else 1)
    return score


class OperationsKnowledgeQAAgent(MarketingBaseAgent):
    """Answer questions against operations documents using RAG-style keyword retrieval + Groq."""

    MAX_CONTEXT_CHARS = 12000           # how much doc text we pass to the LLM
    MAX_CHUNKS = 8                      # top-K retrieved chunks
    MAX_HISTORY = 6                     # last N messages for context
    MAX_TOKENS_RESPONSE = 1400

    def __init__(self):
        try:
            super().__init__(use_embeddings=False)
        except Exception as e:
            # Even if Groq init fails, don't raise — let answer() return a safe error.
            logger.error(f"OperationsKnowledgeQAAgent init warning: {e}")
        self.agent_name = 'OperationsKnowledgeQAAgent'
        # Per-phase retrieval timing, bubbled into the answer response.
        self.last_retrieval_timing: dict = {}
        self.last_retrieval_path: str = ''

    # ──────────────────────────────────────────────
    # Public entrypoint
    # ──────────────────────────────────────────────
    def answer(
        self,
        question: str,
        company_id: int,
        chat_history: Optional[List[Dict]] = None,
        document_ids: Optional[List[int]] = None,
    ) -> Dict:
        """Generate a markdown answer with source citations.

        Args:
            question: user's question
            company_id: scoping
            chat_history: [{'role': 'user'|'assistant', 'content': str}, ...]
            document_ids: optional filter to search only within specific documents

        Returns: {success, answer, sources, suggested_title, error}
        """
        _t_overall = time.time()
        timing_ms: Dict = {}
        try:
            question = (question or '').strip()
            if not question:
                return {
                    'success': False,
                    'error': 'Please enter a question.',
                    'answer': '',
                    'sources': [],
                }

            # Answer cache — only for un-scoped, first-turn questions. Scoped
            # (document_ids) and follow-up (chat_history) queries depend on extra
            # state, so they're never cached to avoid serving the wrong answer.
            cache_ttl = int(getattr(settings, 'OPERATIONS_ANSWER_CACHE_TTL_SECONDS', 300))
            cache_key = None
            if cache_ttl > 0 and not document_ids and not chat_history:
                cache_key = _answer_cache_key(company_id, question)
                cached = _answer_cache_get(cache_key, cache_ttl)
                if cached is not None:
                    out = dict(cached)
                    out['cache_hit'] = True
                    out['timing_ms'] = {'total': int((time.time() - _t_overall) * 1000), 'cache': True}
                    return out

            # Route: "list/show all documents" style meta-questions answered from metadata
            meta_answer = self._maybe_answer_meta(question, company_id)
            if meta_answer is not None:
                return meta_answer

            # Fast path: obvious off-topic / conversational questions — never feed
            # document context to the LLM, just politely redirect.
            if _looks_off_topic(question):
                return self._off_topic_response(question, company_id)

            # Retrieve relevant chunks
            _t_retr = time.time()
            context_text, sources, is_relevant = self._build_context(
                question, company_id, document_ids,
            )
            timing_ms['retrieval'] = int((time.time() - _t_retr) * 1000)
            timing_ms['retrieval_breakdown'] = dict(self.last_retrieval_timing)
            timing_ms['retrieval_path'] = self.last_retrieval_path

            if not context_text:
                return {
                    'success': True,
                    'answer': (
                        "I couldn't find any processed documents that match your question.\n\n"
                        "**What you can try:**\n"
                        "- Upload a document from the **Documents** tab and wait for processing to finish\n"
                        "- Rephrase your question with more specific terms (document names, keywords, dates)\n"
                        "- Ask a broader question like *\"what documents do I have?\"*"
                    ),
                    'sources': [],
                    'suggested_title': question[:60],
                }

            # Build prompt — when retrieval was weak (fallback-only), tell the LLM
            # explicitly so it doesn't pretend the excerpts answer the question.
            history_block = self._format_history(chat_history or [])
            if is_relevant:
                context_header = "RELEVANT DOCUMENT EXCERPTS:"
                instructions = (
                    "Answer the question using the formatting and content rules. "
                    "Cite sources in the final `## Sources` section."
                )
            else:
                context_header = (
                    "NOTE: No document excerpts matched the user's question. The text "
                    "below is just generic context from the most recent documents — it "
                    "very likely does NOT answer the question.\n\n"
                    "RECENT DOCUMENT CONTEXT (for orientation only):"
                )
                instructions = (
                    "Because no excerpts actually matched the question:\n"
                    "- If the question is off-topic or conversational, reply with a brief "
                    "one-liner explaining you only answer questions about uploaded "
                    "documents, and suggest 1–2 example doc questions.\n"
                    "- Otherwise, say plainly that none of the uploaded documents address "
                    "the question and suggest what the user could upload or ask instead.\n"
                    "- Do NOT summarise the recent-document context as if it were the answer. "
                    "Do NOT include a `## Sources` section in this case."
                )
            prompt = (
                f"{history_block}"
                f"USER QUESTION:\n{question}\n\n"
                f"{context_header}\n{context_text}\n\n"
                f"{instructions}"
            )

            _t_llm = time.time()
            llm_response = self._call_llm_for_reasoning(
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT,
                temperature=0.2,
                max_tokens=self.MAX_TOKENS_RESPONSE,
            )
            timing_ms['llm'] = int((time.time() - _t_llm) * 1000)

            answer_text = ''
            if isinstance(llm_response, dict):
                answer_text = (llm_response.get('content') or llm_response.get('text') or '').strip()
            elif isinstance(llm_response, str):
                answer_text = llm_response.strip()

            if not answer_text:
                return {
                    'success': False,
                    'error': 'The AI returned an empty response. Please try again.',
                    'answer': 'Sorry, I could not generate a response. Please try rephrasing your question.',
                    'sources': sources,
                }

            # Ensure a sources section is present — but only when retrieval was
            # actually relevant. For weak/fallback retrieval we deliberately omit
            # sources so the user isn't misled into thinking those docs answered them.
            if is_relevant and '## Sources' not in answer_text and sources:
                answer_text += '\n\n## Sources\n' + '\n'.join(
                    f"- **{s.get('title')}** (page {s.get('page') or 'n/a'})" for s in sources
                )

            timing_ms['total'] = int((time.time() - _t_overall) * 1000)
            response = {
                'success': True,
                'answer': answer_text,
                'sources': sources if is_relevant else [],
                'suggested_title': self._suggest_title(question),
                'cache_hit': False,
                'timing_ms': timing_ms,
            }
            # Cache only relevant, un-scoped, first-turn answers.
            if cache_key and is_relevant:
                _answer_cache_put(cache_key, {
                    'success': True,
                    'answer': answer_text,
                    'sources': sources,
                    'suggested_title': response['suggested_title'],
                })
            return response

        except Exception as e:
            from core.api_key_service import KeyServiceError
            if isinstance(e, KeyServiceError):
                raise
            logger.error(f'OperationsKnowledgeQAAgent.answer error: {e}', exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'answer': (
                    "Something went wrong while generating the answer. "
                    "Please try again in a moment."
                ),
                'sources': [],
            }

    # ──────────────────────────────────────────────
    # Meta-question handling (document listing / counts)
    # ──────────────────────────────────────────────
    def _maybe_answer_meta(self, question: str, company_id: int) -> Optional[Dict]:
        q = question.lower()
        list_trigger = any(p in q for p in [
            'list all documents', 'list my documents', 'list the documents',
            'show all documents', 'show me all documents', 'show my documents',
            'what documents', 'which documents', 'how many documents',
            'documents do i have', 'uploaded documents',
        ])
        if not list_trigger:
            return None

        docs = OperationsDocument.objects.filter(company_id=company_id).order_by('-created_at')
        total = docs.count()
        # Files summarised via the Summarization tab are a separate library, but
        # they're still "documents the user has" as far as this question goes.
        summaries = (
            OperationsDocumentSummary.objects
            .filter(company_id=company_id).order_by('-created_at')
        )
        summary_total = summaries.count()

        if total == 0 and summary_total == 0:
            return {
                'success': True,
                'answer': (
                    "You don't have any documents uploaded yet.\n\n"
                    "**Next step:** go to the **Documents** tab and upload PDFs, Word, Excel, CSV, or PowerPoint files. "
                    "Once processed, you can ask questions here about their content."
                ),
                'sources': [],
                'suggested_title': 'Documents overview',
            }

        lines = []
        if total:
            lines += [
                f"You have **{total} document{'s' if total != 1 else ''}** in your library"
                + (f" and **{summary_total} summarised file{'s' if summary_total != 1 else ''}**." if summary_total else "."),
                '',
                '## Document Library',
                '',
                '| # | Title | Type | Pages | Uploaded |',
                '|---|-------|------|-------|----------|',
            ]
            for idx, d in enumerate(docs[:50], start=1):
                title = (d.title or d.original_filename or 'Untitled').replace('|', '\\|')
                lines.append(
                    f"| {idx} | {title} | {d.file_type.upper()} | {d.page_count or '-'} | "
                    f"{d.created_at.strftime('%Y-%m-%d')} |"
                )
            if total > 50:
                lines.append('')
                lines.append(f"_Showing first 50 of {total} documents._")
        else:
            lines.append(
                f"You have **{summary_total} summarised file{'s' if summary_total != 1 else ''}** "
                f"and no documents in your main library yet."
            )

        if summary_total:
            lines += [
                '',
                '## Summarised Files',
                '',
                '| # | File | Summarised |',
                '|---|------|-----------|',
            ]
            for idx, s in enumerate(summaries[:50], start=1):
                name = (s.original_filename or 'Untitled').replace('|', '\\|')
                lines.append(f"| {idx} | {name} | {s.created_at.strftime('%Y-%m-%d')} |")

        # Breakdown by type
        from collections import Counter
        type_counts = Counter(d.document_type for d in docs)
        if type_counts:
            lines.append('')
            lines.append('### Breakdown by category')
            for cat, cnt in sorted(type_counts.items(), key=lambda x: -x[1]):
                lines.append(f"- **{cat.title()}**: {cnt}")

        return {
            'success': True,
            'answer': '\n'.join(lines),
            'sources': [
                {'title': d.title or d.original_filename, 'page': None, 'document_id': d.id}
                for d in docs[:10]
            ],
            'suggested_title': 'My documents',
        }

    # ──────────────────────────────────────────────
    # Off-topic / conversational responses
    # ──────────────────────────────────────────────
    def _off_topic_response(self, question: str, company_id: int) -> Dict:
        """Friendly redirect for personal / conversational questions. Suggests 1–2
        example questions grounded in the user's actual documents when possible."""
        recent_titles: List[str] = []
        try:
            recent_titles = list(
                OperationsDocument.objects
                .filter(company_id=company_id, is_processed=True)
                .order_by('-created_at')
                .values_list('title', flat=True)[:2]
            )
        except Exception:
            recent_titles = []
        recent_titles = [t for t in recent_titles if t]

        if recent_titles:
            examples = ' or '.join(f"*\"What does **{t}** cover?\"*" for t in recent_titles)
            suggestion = f"For example, you could ask: {examples}"
        else:
            suggestion = (
                "Try asking something like *\"What documents do I have?\"* or upload a "
                "document from the **Documents** tab to get started."
            )

        return {
            'success': True,
            'answer': (
                "I'm the Operations Knowledge Assistant — I can only answer questions "
                f"about your uploaded documents, so I can't help with that one.\n\n{suggestion}"
            ),
            'sources': [],
            'suggested_title': self._suggest_title(question),
        }

    # ──────────────────────────────────────────────
    # Context building / retrieval
    # ──────────────────────────────────────────────
    def _build_context(
        self,
        question: str,
        company_id: int,
        document_ids: Optional[List[int]],
    ) -> Tuple[str, List[Dict], bool]:
        """Keyword-based retrieval over OperationsDocumentChunk *and*
        OperationsDocumentSummary.

        Summaries are uploaded through the Summarization tab and live in their own
        table with no chunks, so they used to be invisible here — a user could
        summarise a file and then be told nothing matched when they asked about it.

        Returns (context_text, sources, is_relevant) where is_relevant is True only
        when at least one chunk actually matched the question's keywords. When
        is_relevant is False, the context (if any) is recent-doc fallback material
        that should NOT be presented as if it answered the question.
        """
        self.last_retrieval_timing = {}
        self.last_retrieval_path = ''
        _t_all = time.time()

        tokens = _tokenize(question)
        if not tokens:
            return '', [], False

        chunk_qs = OperationsDocumentChunk.objects.filter(
            document__company_id=company_id,
            document__is_processed=True,
        )
        if document_ids:
            chunk_qs = chunk_qs.filter(document_id__in=document_ids)

        # ---- 1. Semantic retrieval (FAISS → cached cosine fallback) --------
        # Returns {chunk_id: semantic_score}. Empty when no embeddings exist,
        # in which case we lean entirely on the keyword path below (no regression
        # from the previous keyword-only behaviour).
        semantic_hits = self._semantic_hits(question, company_id, chunk_qs)

        # ---- 2. Keyword retrieval (DB-side icontains) ----------------------
        _t_kw = time.time()
        keyword_q = reduce(operator.or_, (Q(content__icontains=tok) for tok in set(tokens)))
        candidate_rows = list(
            chunk_qs.filter(keyword_q)
            .order_by('-document__created_at', 'chunk_index')
            .values(
                'id', 'content', 'page_number', 'document_id',
                'document__title', 'document__original_filename',
            )[:200]
        )
        keyword_scores: Dict[int, float] = {}
        row_by_id: Dict[int, Dict] = {}
        for row in candidate_rows:
            cid = row.get('id')
            row_by_id[cid] = row
            s = _score_chunk(row.get('content') or '', tokens)
            if s > 0:
                keyword_scores[cid] = s
        self.last_retrieval_timing['keyword'] = int((time.time() - _t_kw) * 1000)

        # ---- 3. Reciprocal-rank fusion of the two rankings ----------------
        chunk_scored = self._rrf_merge(semantic_hits, keyword_scores)

        # Materialise any RRF-selected chunks that keyword search didn't already
        # load (semantic-only hits). Fresh queryset + .only() — the MSSQL plan
        # workaround from the HR reference.
        missing_ids = [cid for cid, _score in chunk_scored if cid not in row_by_id]
        if missing_ids:
            _t_fetch = time.time()
            fetched = OperationsDocumentChunk.objects.filter(id__in=missing_ids).only(
                'id', 'content', 'page_number', 'document_id',
                'document__title', 'document__original_filename',
            ).select_related('document')
            for c in fetched:
                row_by_id[c.id] = {
                    'id': c.id,
                    'content': c.content,
                    'page_number': c.page_number,
                    'document_id': c.document_id,
                    'document__title': c.document.title,
                    'document__original_filename': c.document.original_filename,
                }
            self.last_retrieval_timing['chunk_fetch'] = int((time.time() - _t_fetch) * 1000)

        scored: List[Tuple[float, Dict]] = []
        for cid, score in chunk_scored:
            row = row_by_id.get(cid)
            if row is None:
                continue
            if _is_junk_chunk(cid, row.get('content')):
                continue
            scored.append((score, row))

        # Summaries live in their own table with no chunks. Search them too, unless
        # the user pinned the question to specific documents (those ids address
        # OperationsDocument rows, which summaries are not part of).
        if not document_ids:
            for s, srow in self._score_summaries(company_id, tokens):
                scored.append((float(s), srow))

        # Fallback: if nothing matched, grab summary/parsed_text of most recent docs
        if not scored:
            fb_text, fb_sources = self._fallback_context(company_id, document_ids, tokens)
            self.last_retrieval_timing['search_total'] = int((time.time() - _t_all) * 1000)
            return fb_text, fb_sources, False

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[: self.MAX_CHUNKS]

        parts: List[str] = []
        sources: List[Dict] = []
        total_chars = 0
        for _, row in top:
            title = row.get('document__title') or row.get('document__original_filename')
            page = row.get('page_number')
            header = f"[Source: {title} | Page {page or 'n/a'}]"
            content = (row.get('content') or '').strip()
            # Trim very long chunks
            if len(content) > 2500:
                content = content[:2500] + '…'
            block = f"{header}\n{content}\n"
            if total_chars + len(block) > self.MAX_CONTEXT_CHARS:
                break
            parts.append(block)
            total_chars += len(block)
            sources.append({
                'title': title,
                'page': page,
                'document_id': row.get('document_id'),
                'summary_id': row.get('summary_id'),
            })

        # Deduplicate sources by (title, page)
        seen = set()
        unique_sources = []
        for s in sources:
            key = (s['title'], s['page'])
            if key in seen:
                continue
            seen.add(key)
            unique_sources.append(s)

        self.last_retrieval_timing['search_total'] = int((time.time() - _t_all) * 1000)
        return '\n---\n'.join(parts), unique_sources, True

    # ──────────────────────────────────────────────
    # Semantic retrieval + fusion (RAG)
    # ──────────────────────────────────────────────
    def _semantic_hits(self, question, company_id, chunk_qs) -> Dict[int, float]:
        """Return {chunk_id: cosine_score} via FAISS (fast) or a cached Python
        scan (fallback). Empty dict when no embedding provider / no vectors —
        the caller then relies purely on keyword retrieval.
        """
        try:
            from core.Frontline_agent.embedding_service import EmbeddingService
        except Exception:
            return {}

        svc = EmbeddingService()
        if not svc.is_available():
            self.last_retrieval_path += 'no_embeddings|'
            return {}

        _t_q = time.time()
        qvec = _cache_get_query_vec(question, svc)
        self.last_retrieval_timing['query_embed'] = int((time.time() - _t_q) * 1000)
        if qvec is None:
            return {}

        hits: Dict[int, float] = {}

        # FAISS path — O(log N).
        try:
            from operations_agent import vector_store as _vs
            if _vs.FAISS_AVAILABLE:
                store = _vs.get_store(company_id)
                if store is not None:
                    _t_c = time.time()
                    candidate_ids = set(chunk_qs.values_list('id', flat=True))
                    self.last_retrieval_timing['faiss_candidates'] = int((time.time() - _t_c) * 1000)
                    _t_s = time.time()
                    faiss_hits = store.search(qvec, k=50, candidate_chunk_ids=candidate_ids)
                    self.last_retrieval_timing['faiss_search'] = int((time.time() - _t_s) * 1000)
                    if faiss_hits:
                        self.last_retrieval_path += f'faiss(hits={len(faiss_hits)})|'
                        return {cid: float(score) for cid, score in faiss_hits}
        except Exception:
            logger.exception("Operations FAISS search failed; falling back to Python scan")

        # Python-scan fallback — only chunks that actually have a vector.
        _t_j = time.time()
        scanned = 0
        rows = (chunk_qs.exclude(embedding__isnull=True)
                .only('id', 'content', 'embedding')
                .iterator(chunk_size=500))
        for c in rows:
            scanned += 1
            if _is_junk_chunk(c.id, c.content):
                continue
            cvec = _cache_get_chunk_vec(c.id, c.embedding)
            score = _semantic_score(qvec, cvec)
            if score is not None:
                hits[c.id] = score
        self.last_retrieval_timing['json_scan'] = int((time.time() - _t_j) * 1000)
        self.last_retrieval_timing['json_scan_chunks'] = scanned
        if hits:
            self.last_retrieval_path += f'json_scan(scanned={scanned})|'
        # Keep only the strongest 50 semantic hits.
        return dict(sorted(hits.items(), key=lambda kv: kv[1], reverse=True)[:50])

    @staticmethod
    def _rrf_merge(semantic_hits: Dict[int, float], keyword_scores: Dict[int, float],
                   k: int = 60) -> List[Tuple[int, float]]:
        """Reciprocal-rank fusion of the semantic and keyword rankings.

        Each list contributes 1/(k + rank) to a chunk's fused score, so a chunk
        ranked highly by either signal surfaces. Returns [(chunk_id, score)]
        sorted best-first.
        """
        rrf: Dict[int, float] = {}
        for rank, (cid, _s) in enumerate(
            sorted(semantic_hits.items(), key=lambda kv: kv[1], reverse=True)
        ):
            rrf[cid] = rrf.get(cid, 0.0) + 1.0 / (k + rank + 1)
        for rank, (cid, _s) in enumerate(
            sorted(keyword_scores.items(), key=lambda kv: kv[1], reverse=True)
        ):
            rrf[cid] = rrf.get(cid, 0.0) + 1.0 / (k + rank + 1)
        return sorted(rrf.items(), key=lambda kv: kv[1], reverse=True)

    def _score_summaries(self, company_id: int, tokens: List[str]) -> List[Tuple[int, Dict]]:
        """Keyword-score standalone summaries from the Summarization tab.

        Rows are shaped like chunk rows so the caller's ranking and rendering
        treat both sources identically.
        """
        keyword_q = reduce(
            operator.or_,
            (Q(rich_summary__icontains=tok) | Q(original_filename__icontains=tok)
             for tok in set(tokens)),
        )
        rows = (
            OperationsDocumentSummary.objects
            .filter(company_id=company_id)
            .filter(keyword_q)
            .order_by('-created_at')
            .values('id', 'original_filename', 'rich_summary', 'key_findings')[:50]
        )

        scored: List[Tuple[int, Dict]] = []
        for row in rows:
            body = row.get('rich_summary') or ''
            findings = row.get('key_findings') or []
            if isinstance(findings, list) and findings:
                body = f"{body}\n\nKey findings:\n" + '\n'.join(
                    f"- {f}" for f in findings if isinstance(f, str)
                )
            score = _score_chunk(body, tokens)
            if score <= 0:
                continue
            scored.append((score, {
                'content': body,
                'page_number': None,
                'document_id': None,
                'summary_id': row['id'],
                # Flagged in the title so the LLM cites it as a summary, not the source file.
                'document__title': f"{row['original_filename']} (summary)",
                'document__original_filename': row['original_filename'],
            }))
        return scored

    def _fallback_context(
        self,
        company_id: int,
        document_ids: Optional[List[int]],
        tokens: List[str],
    ) -> Tuple[str, List[Dict]]:
        """No keyword match: provide recent-doc summaries so the LLM can at least orient."""
        docs_qs = OperationsDocument.objects.filter(
            company_id=company_id, is_processed=True,
        )
        if document_ids:
            docs_qs = docs_qs.filter(id__in=document_ids)
        docs = list(docs_qs.order_by('-created_at')[:5])
        if not docs:
            return '', []

        parts = []
        sources = []
        total = 0
        for d in docs:
            snippet = (d.summary or d.parsed_text or '').strip()
            if not snippet:
                continue
            if len(snippet) > 1800:
                snippet = snippet[:1800] + '…'
            block = f"[Source: {d.title or d.original_filename}]\n{snippet}\n"
            if total + len(block) > self.MAX_CONTEXT_CHARS:
                break
            parts.append(block)
            total += len(block)
            sources.append({
                'title': d.title or d.original_filename,
                'page': None,
                'document_id': d.id,
            })
        return '\n---\n'.join(parts), sources

    # ──────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────
    def _format_history(self, chat_history: List[Dict]) -> str:
        if not chat_history:
            return ''
        recent = chat_history[-self.MAX_HISTORY:]
        lines = ['CONVERSATION SO FAR:']
        for m in recent:
            role = (m.get('role') or '').strip()
            content = (m.get('content') or '').strip()
            if role not in ('user', 'assistant') or not content:
                continue
            if len(content) > 600:
                content = content[:600] + '…'
            prefix = 'User' if role == 'user' else 'Assistant'
            lines.append(f"{prefix}: {content}")
        lines.append('')
        return '\n'.join(lines) + '\n'

    def _suggest_title(self, question: str) -> str:
        q = (question or '').strip()
        if not q:
            return 'Chat'
        # Take first 8 words, title-case first letter
        words = q.split()
        title = ' '.join(words[:8])
        if len(q) > len(title):
            title += '…'
        return title[0].upper() + title[1:] if title else 'Chat'
