"""
Operations Knowledge Q&A Agent

Answers user questions about uploaded operations documents (PDFs, DOCX, XLSX, etc.).
Uses keyword-based retrieval over document chunks + Groq LLM for answer generation.
Returns well-structured markdown responses with headings, sub-headings, and source citations.

Kept deliberately simple and defensive: every failure mode returns a friendly message
instead of raising, so the chat UI never crashes.
"""

import logging
import re
from typing import Dict, List, Optional, Tuple

from marketing_agent.agents.marketing_base_agent import MarketingBaseAgent
from operations_agent.models import OperationsDocument, OperationsDocumentChunk

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = (
    "You are the Operations Knowledge Assistant for a company's internal document library. "
    "You answer questions strictly based on the provided document excerpts (contracts, invoices, "
    "reports, memos, policies, manuals, spreadsheets, presentations).\n\n"
    "FORMATTING RULES — always follow:\n"
    "1. Respond in GitHub-flavored Markdown.\n"
    "2. Start with a one-line direct answer (no heading).\n"
    "3. Then use `## Section` headings and `### Sub-section` sub-headings to organise details.\n"
    "4. Use short bullet lists (`- item`) for key points, numbered lists for steps.\n"
    "5. Use **bold** for important terms, numbers, dates, and names.\n"
    "6. If the answer includes tabular data, format as a Markdown table.\n"
    "7. At the end, add a `## Sources` section listing the document titles and page numbers you used.\n\n"
    "CONTENT RULES:\n"
    "- Only use facts present in the excerpts. If the answer is not in the excerpts, say so clearly "
    "and suggest what document the user should upload.\n"
    "- Never invent numbers, dates, names, or clauses.\n"
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
        try:
            question = (question or '').strip()
            if not question:
                return {
                    'success': False,
                    'error': 'Please enter a question.',
                    'answer': '',
                    'sources': [],
                }

            if not getattr(self, 'groq_client', None):
                return {
                    'success': False,
                    'error': 'AI service is not configured. Please set GROQ_API_KEY.',
                    'answer': (
                        "I'm unable to reach the AI service right now. "
                        "An administrator needs to configure the GROQ_API_KEY. "
                        "Once configured you can ask me anything about your uploaded operations documents."
                    ),
                    'sources': [],
                }

            # Route: "list/show all documents" style meta-questions answered from metadata
            meta_answer = self._maybe_answer_meta(question, company_id)
            if meta_answer is not None:
                return meta_answer

            # Retrieve relevant chunks
            context_text, sources = self._build_context(question, company_id, document_ids)

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

            # Build prompt
            history_block = self._format_history(chat_history or [])
            prompt = (
                f"{history_block}"
                f"USER QUESTION:\n{question}\n\n"
                f"RELEVANT DOCUMENT EXCERPTS:\n{context_text}\n\n"
                "Answer the question using the formatting and content rules. "
                "Cite sources in the final `## Sources` section."
            )

            llm_response = self._call_llm_for_reasoning(
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT,
                temperature=0.2,
                max_tokens=self.MAX_TOKENS_RESPONSE,
            )

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

            # Ensure a sources section is present — append if the LLM forgot
            if '## Sources' not in answer_text and sources:
                answer_text += '\n\n## Sources\n' + '\n'.join(
                    f"- **{s.get('title')}** (page {s.get('page') or 'n/a'})" for s in sources
                )

            return {
                'success': True,
                'answer': answer_text,
                'sources': sources,
                'suggested_title': self._suggest_title(question),
            }

        except Exception as e:
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
        if total == 0:
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

        # Build a markdown table of documents
        lines = [
            f"You have **{total} document{'s' if total != 1 else ''}** in your library.",
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
    # Context building / retrieval
    # ──────────────────────────────────────────────
    def _build_context(
        self,
        question: str,
        company_id: int,
        document_ids: Optional[List[int]],
    ) -> Tuple[str, List[Dict]]:
        """Keyword-based retrieval over OperationsDocumentChunk."""
        tokens = _tokenize(question)
        if not tokens:
            return '', []

        chunk_qs = OperationsDocumentChunk.objects.filter(
            document__company_id=company_id,
            document__is_processed=True,
        ).select_related('document')

        if document_ids:
            chunk_qs = chunk_qs.filter(document_id__in=document_ids)

        # Pull a reasonable working set then score in Python.
        # We don't want to load everything on huge libraries → limit to 500 chunks,
        # prioritising recent documents.
        chunk_qs = chunk_qs.order_by('-document__created_at', 'chunk_index')[:500]

        scored: List[Tuple[int, OperationsDocumentChunk]] = []
        for ch in chunk_qs:
            s = _score_chunk(ch.content, tokens)
            if s > 0:
                scored.append((s, ch))

        # Fallback: if no keyword matches, grab summary/parsed_text of most recent docs
        if not scored:
            return self._fallback_context(company_id, document_ids, tokens)

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[: self.MAX_CHUNKS]

        parts: List[str] = []
        sources: List[Dict] = []
        total_chars = 0
        for _, ch in top:
            doc = ch.document
            header = f"[Source: {doc.title or doc.original_filename} | Page {ch.page_number or 'n/a'}]"
            content = ch.content.strip()
            # Trim very long chunks
            if len(content) > 2500:
                content = content[:2500] + '…'
            block = f"{header}\n{content}\n"
            if total_chars + len(block) > self.MAX_CONTEXT_CHARS:
                break
            parts.append(block)
            total_chars += len(block)
            sources.append({
                'title': doc.title or doc.original_filename,
                'page': ch.page_number,
                'document_id': doc.id,
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

        return '\n---\n'.join(parts), unique_sources

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
