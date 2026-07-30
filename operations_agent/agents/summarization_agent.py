"""
Document Summarization Agent for Operations Agent
Accepts a document, extracts text, generates a rich structured summary,
extracts proper insights, saves only the summary (not the document), and cleans up.
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict

from marketing_agent.agents.marketing_base_agent import MarketingBaseAgent
from operations_agent.agents.document_processing_agent import DocumentProcessingAgent

logger = logging.getLogger(__name__)


class DocumentSummarizationAgent(MarketingBaseAgent):
    """
    Standalone summarization: upload → extract text → generate rich summary → save summary → delete file.
    No document storage. Only the summary is persisted.
    """

    def __init__(self):
        super().__init__(use_embeddings=False)
        self.agent_name = 'DocumentSummarizationAgent'
        self._doc_agent = DocumentProcessingAgent()

    def process(self, action: str, **kwargs) -> Dict:
        actions = {
            'summarize_file': self._summarize_file,
        }
        handler = actions.get(action)
        if not handler:
            return {'success': False, 'error': f'Unknown action: {action}'}
        try:
            return handler(**kwargs)
        except Exception as e:
            from core.api_key_service import KeyServiceError
            if isinstance(e, KeyServiceError):
                raise
            logger.error(f'{self.agent_name} error: {e}', exc_info=True)
            return {'success': False, 'error': str(e)}

    def _summarize_file(self, file_path: str, original_filename: str,
                        company_id: int, uploaded_by_id: int = None,
                        existing_summary_id: int = None) -> Dict:
        """Extract text from file, generate rich summary, save summary, delete file.

        When ``existing_summary_id`` is given (async upload flow), that pending
        placeholder row is filled in and stamped ready/failed so the client's
        status poll can follow along.
        """
        from operations_agent.models import OperationsDocumentSummary
        from core.models import Company, CompanyUser

        placeholder = None
        if existing_summary_id:
            placeholder = OperationsDocumentSummary.objects.filter(id=existing_summary_id).first()
            if placeholder:
                placeholder.processing_status = 'processing'
                placeholder.save(update_fields=['processing_status'])

        def _fail(message):
            if placeholder is not None:
                try:
                    placeholder.processing_status = 'failed'
                    placeholder.processing_error = str(message)[:2000]
                    placeholder.save(update_fields=['processing_status', 'processing_error'])
                except Exception:
                    logger.exception("Operations: failed to stamp summary %s failed", existing_summary_id)
            return {'success': False, 'error': message}

        ext = Path(original_filename).suffix.lower()
        file_type = self._doc_agent.SUPPORTED_EXTENSIONS.get(ext)
        if not file_type:
            return _fail(f'Unsupported file type: {ext}')

        file_size = os.path.getsize(file_path)

        # 1. Extract text using the document processing agent's extractors
        success, extracted_text, page_count, error = self._doc_agent._extract_text(file_path, file_type)

        # Clean up file immediately - we don't store it
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except OSError:
            pass

        if not success:
            return _fail(error or 'Text extraction failed')

        if not extracted_text or not extracted_text.strip():
            return _fail('No text could be extracted from this document')

        word_count = len(extracted_text.split())

        # 2. Generate rich summary
        if len(extracted_text) > 12000:
            summary_result = self._summarize_large(extracted_text, original_filename, page_count)
        else:
            summary_result = self._summarize_single(extracted_text, original_filename, page_count)

        if not summary_result.get('success'):
            return _fail(summary_result.get('error') or 'Summarization failed')

        # 3. Extract proper insights via dedicated LLM call
        insights = self._extract_insights(extracted_text, original_filename)

        # 4. Save summary + insights
        company = Company.objects.get(pk=company_id)
        uploaded_by = CompanyUser.objects.get(pk=uploaded_by_id) if uploaded_by_id else None

        summary_fields = dict(
            company=company,
            created_by=uploaded_by,
            original_filename=original_filename,
            file_type=file_type,
            file_size=file_size,
            page_count=page_count,
            word_count=word_count,
            rich_summary=summary_result['rich_summary'],
            # Store the full extracted text so Knowledge-QA can answer from the
            # whole document, not just the summary.
            parsed_text=extracted_text,
            key_findings=summary_result.get('key_findings', []),
            action_items=summary_result.get('action_items', []),
            # Insights fields
            sentiment=insights.get('sentiment', ''),
            sentiment_explanation=insights.get('sentiment_explanation', ''),
            topics=insights.get('topics', []),
            importance_level=insights.get('importance_level', ''),
            importance_reason=insights.get('importance_reason', ''),
            entities=insights.get('entities', {}),
            risks=insights.get('risks', []),
            opportunities=insights.get('opportunities', []),
            deadlines=insights.get('deadlines', []),
            document_category=insights.get('document_category', ''),
            # Kept 'processing' until chunks land, so a crash between the summary
            # save and chunking doesn't leave a 'ready' row with no chunks.
            processing_status='processing',
            processing_error='',
        )
        if placeholder is not None:
            for k, v in summary_fields.items():
                setattr(placeholder, k, v)
            placeholder.save()
            summary_obj = placeholder
        else:
            summary_obj = OperationsDocumentSummary.objects.create(**summary_fields)

        # Chunk + embed the full text so QA retrieval works on the whole file
        # (same pipeline as the Documents tab), and flip to 'ready' in the same
        # transaction. Graceful keyword fallback when no embedding provider is
        # configured.
        from django.db import transaction as _txn
        try:
            doc_cat = insights.get('document_category') or 'other'
            with _txn.atomic():
                chunk_count, embedded, embed_model = self._doc_agent._chunk_embed_and_store(
                    summary_obj, extracted_text, page_count, doc_cat, owner_kind='summary',
                )
                summary_obj.is_indexed = embedded
                summary_obj.embedding_model = embed_model or ''
                summary_obj.processing_status = 'ready'
                summary_obj.save(update_fields=['is_indexed', 'embedding_model', 'processing_status'])
            if embedded:
                from operations_agent.agents.knowledge_qa_agent import invalidate_answer_cache_for_company
                from operations_agent.vector_store import mark_index_dirty
                mark_index_dirty(company_id)
                invalidate_answer_cache_for_company(company_id)
        except Exception:
            logger.exception("Operations: failed to chunk/embed summarised file %s", original_filename)
            # The summary itself is valid even if chunking failed — it stays
            # searchable via legacy rich_summary scoring. Don't strand it in
            # 'processing'; mark it ready.
            try:
                summary_obj.processing_status = 'ready'
                summary_obj.save(update_fields=['processing_status'])
            except Exception:
                logger.exception("Operations: failed to stamp summary %s ready", summary_obj.id)

        self.log_action('summarize_file', {
            'summary_id': summary_obj.id,
            'filename': original_filename,
            'text_length': len(extracted_text),
        })

        return {
            'success': True,
            'summary': {
                'id': summary_obj.id,
                'original_filename': original_filename,
                'file_type': file_type,
                'page_count': page_count,
                'word_count': word_count,
                'rich_summary': summary_result['rich_summary'],
                'key_findings': summary_result.get('key_findings', []),
                'action_items': summary_result.get('action_items', []),
                'sentiment': insights.get('sentiment', ''),
                'sentiment_explanation': insights.get('sentiment_explanation', ''),
                'topics': insights.get('topics', []),
                'importance_level': insights.get('importance_level', ''),
                'importance_reason': insights.get('importance_reason', ''),
                'entities': insights.get('entities', {}),
                'risks': insights.get('risks', []),
                'opportunities': insights.get('opportunities', []),
                'deadlines': insights.get('deadlines', []),
                'document_category': insights.get('document_category', ''),
            },
        }

    # ------------------------------------------------------------------
    # Dedicated Insights Extraction (separate LLM call)
    # ------------------------------------------------------------------
    def _extract_insights(self, text: str, filename: str) -> Dict:
        """Extract structured insights from document text via a dedicated LLM call."""
        # Use first 10K chars for insight extraction
        text_sample = text[:10000]

        prompt = f"""Analyze this document and extract structured insights. Return ONLY valid JSON, no markdown, no explanation.

**Document:** {filename}

**Text:**
\"\"\"
{text_sample}
\"\"\"

Return this exact JSON structure:
{{
  "sentiment": "positive" or "negative" or "neutral" or "mixed",
  "sentiment_explanation": "Brief 1-sentence explanation of the overall tone",
  "document_category": "One of: report, financial, legal, technical, marketing, hr, operations, strategic, research, correspondence, other",
  "importance_level": "critical" or "high" or "medium" or "low",
  "importance_reason": "Brief 1-sentence reason for the importance level",
  "topics": ["topic1", "topic2", "topic3"],
  "entities": {{
    "people": ["person names mentioned"],
    "organizations": ["company/org names"],
    "locations": ["places mentioned"],
    "dates": ["important dates found"],
    "amounts": ["monetary values or key numbers"]
  }},
  "risks": ["risk or concern 1", "risk or concern 2"],
  "opportunities": ["opportunity 1", "opportunity 2"],
  "deadlines": ["deadline description with date if available"]
}}

Rules:
- Extract ONLY what is actually in the document, do NOT invent anything
- Keep each array to max 5 most important items
- If a field has no relevant data, use empty string for strings, empty array [] for arrays, empty object {{}} for entities
- "topics" should be 3-6 broad topic labels
- "risks" = anything concerning, problematic, or needing attention
- "opportunities" = positive possibilities, recommendations, growth areas
- "deadlines" = any time-sensitive items, due dates, milestones
- Return ONLY the JSON object, nothing else"""

        try:
            result = self._call_llm_for_reasoning(prompt, temperature=0.1, max_tokens=1500)
            if not result or not result.strip():
                logger.warning('Insights extraction returned empty response')
                return {}

            # Clean up response - remove markdown code fences if present
            cleaned = result.strip()
            if cleaned.startswith('```'):
                cleaned = cleaned.split('\n', 1)[-1]
            if cleaned.endswith('```'):
                cleaned = cleaned.rsplit('```', 1)[0]
            cleaned = cleaned.strip()

            insights = json.loads(cleaned)

            # Validate and sanitize
            insights['sentiment'] = str(insights.get('sentiment', '')).lower()[:30]
            insights['sentiment_explanation'] = str(insights.get('sentiment_explanation', ''))[:500]
            insights['document_category'] = str(insights.get('document_category', ''))[:50]
            insights['importance_level'] = str(insights.get('importance_level', '')).lower()[:20]
            insights['importance_reason'] = str(insights.get('importance_reason', ''))[:500]
            insights['topics'] = [str(t)[:100] for t in insights.get('topics', [])][:6]
            insights['risks'] = [str(r)[:300] for r in insights.get('risks', [])][:5]
            insights['opportunities'] = [str(o)[:300] for o in insights.get('opportunities', [])][:5]
            insights['deadlines'] = [str(d)[:300] for d in insights.get('deadlines', [])][:5]

            # Sanitize entities
            entities = insights.get('entities', {})
            if not isinstance(entities, dict):
                entities = {}
            for key in ['people', 'organizations', 'locations', 'dates', 'amounts']:
                entities[key] = [str(v)[:200] for v in entities.get(key, [])][:5]
            insights['entities'] = entities

            return insights

        except json.JSONDecodeError as e:
            logger.warning(f'Failed to parse insights JSON: {e}')
            return {}
        except Exception as e:
            from core.api_key_service import KeyServiceError
            if isinstance(e, KeyServiceError):
                raise
            logger.error(f'Insights extraction failed: {e}', exc_info=True)
            return {}

    # ------------------------------------------------------------------
    # Single-pass summary (< 12K chars)
    # ------------------------------------------------------------------
    def _summarize_single(self, text: str, filename: str, page_count: int) -> Dict:
        prompt = f"""You are a professional document analyst. Analyze the following document thoroughly and produce a comprehensive, well-structured summary.

**Document:** {filename}
**Pages:** {page_count}

---
**FULL DOCUMENT TEXT:**
\"\"\"
{text[:10000]}
\"\"\"
---

Generate a detailed, professional summary in **Markdown format** with the following structure:

## Overview
A clear 2-3 sentence overview of what this document is about, its purpose, and main conclusion.

## Key Points
- Bullet point each major point or topic covered
- Be specific and include important details, names, dates, and figures
- Cover ALL significant sections

## Detailed Analysis
Provide in-depth analysis organized by the document's sections or themes. Use ### subheadings for each. Under each, explain with relevant details.

## Key Findings
A numbered list of the most important findings or takeaways.

## Action Items
If the document contains recommendations or next steps, list them. If none, write "No specific action items identified."

IMPORTANT:
- Read and analyze the ENTIRE text
- Use proper markdown (##, ###, -, 1., **bold**)
- Be professional and thorough
- Include specific details (names, dates, numbers)
- Do NOT invent information
- Return ONLY the markdown summary"""

        try:
            result = self._call_llm_for_writing(
                prompt,
                system_prompt="You are an expert document analyst. Produce comprehensive, professionally formatted summaries in Markdown. Be thorough and detailed.",
                temperature=0.3,
                max_tokens=3000,
            )

            if not result or not result.strip():
                return {'success': False, 'error': 'LLM returned empty response'}

            rich_summary = result.strip()
            key_findings = self._extract_section_items(rich_summary, 'Key Findings')
            action_items = self._extract_section_items(rich_summary, 'Action Items')

            return {
                'success': True,
                'rich_summary': rich_summary,
                'key_findings': key_findings,
                'action_items': action_items,
            }
        except Exception as e:
            from core.api_key_service import KeyServiceError
            if isinstance(e, KeyServiceError):
                raise
            logger.error(f'Single-pass summarization failed: {e}', exc_info=True)
            return {'success': False, 'error': str(e)}

    # ------------------------------------------------------------------
    # Chunked summary (> 12K chars)
    # ------------------------------------------------------------------
    def _summarize_large(self, text: str, filename: str, page_count: int) -> Dict:
        chunk_size = 8000
        overlap = 500
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunks.append(text[start:end])
            start = end - overlap

        # Phase 1: Summarize each chunk.
        # Run concurrently — a 65k-char doc is ~9 chunks, and doing them one at a
        # time was the bulk of the wait (~40-90s). Bounded pool so we don't
        # hammer the provider's rate limit. Results are slotted back by index so
        # section order is preserved regardless of completion order.
        from concurrent.futures import ThreadPoolExecutor
        from core.api_key_service import KeyServiceError

        def _summarize_chunk(idx_chunk):
            i, chunk = idx_chunk
            prompt = f"""Summarize this section (Part {i + 1} of {len(chunks)}) of "{filename}".
Extract ALL key points, findings, names, dates, and important details.

\"\"\"
{chunk}
\"\"\"

Provide a detailed bullet-point summary. Be thorough and specific."""
            try:
                result = self._call_llm_for_reasoning(prompt, temperature=0.2, max_tokens=1000)
                if result and result.strip():
                    return i, f"**Section {i + 1}:**\n{result.strip()}"
                return i, None
            except Exception as e:
                if isinstance(e, KeyServiceError):
                    return i, e          # propagate after the pool drains
                logger.warning(f'Chunk {i + 1} summarization failed: {e}')
                return i, None

        max_workers = min(5, len(chunks)) or 1
        slots = [None] * len(chunks)
        key_error = None
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            for i, value in pool.map(_summarize_chunk, enumerate(chunks)):
                if isinstance(value, KeyServiceError):
                    key_error = key_error or value
                else:
                    slots[i] = value

        # A key/quota failure must surface to the caller, not be silently partial.
        if key_error is not None:
            raise key_error

        chunk_summaries = [s for s in slots if s]

        if not chunk_summaries:
            return {'success': False, 'error': 'Failed to summarize any section'}

        # Phase 2: Combine
        combined = '\n\n'.join(chunk_summaries)
        final_prompt = f"""You are a professional document analyst. Below are section-by-section summaries of "{filename}" ({page_count} pages).

Combine into ONE comprehensive summary in **Markdown format**:

{combined[:8000]}

---

Structure:

## Overview
2-3 sentence overview of the entire document.

## Key Points
- All major points with specific details

## Detailed Analysis
Organized by themes using ### subheadings with in-depth explanations.

## Key Findings
Numbered list of most important findings.

## Action Items
Recommendations or next steps. If none, write "No specific action items identified."

Be thorough, use proper markdown, include all significant details. Return ONLY the markdown."""

        try:
            result = self._call_llm_for_writing(
                final_prompt,
                system_prompt="You are an expert document analyst producing comprehensive summaries in Markdown.",
                temperature=0.3,
                max_tokens=3000,
            )

            if not result or not result.strip():
                return {'success': False, 'error': 'Final summary returned empty'}

            rich_summary = result.strip()
            key_findings = self._extract_section_items(rich_summary, 'Key Findings')
            action_items = self._extract_section_items(rich_summary, 'Action Items')

            return {
                'success': True,
                'rich_summary': rich_summary,
                'key_findings': key_findings,
                'action_items': action_items,
            }
        except Exception as e:
            from core.api_key_service import KeyServiceError
            if isinstance(e, KeyServiceError):
                raise
            logger.error(f'Large doc summarization failed: {e}', exc_info=True)
            return {'success': False, 'error': str(e)}

    # ------------------------------------------------------------------
    @staticmethod
    def _extract_section_items(markdown_text: str, section_name: str) -> list:
        """Extract bullet/numbered items from a section in the markdown."""
        import re
        items = []
        lines = markdown_text.split('\n')
        in_section = False

        for line in lines:
            stripped = line.strip()
            if stripped.lower().startswith(f'## {section_name.lower()}'):
                in_section = True
                continue
            if in_section and stripped.startswith('## '):
                break
            if in_section and stripped:
                for prefix in ['- ', '* ', '• ']:
                    if stripped.startswith(prefix):
                        items.append(stripped[len(prefix):].strip())
                        break
                else:
                    match = re.match(r'^\d+[\.\)]\s*(.+)', stripped)
                    if match:
                        items.append(match.group(1).strip())

        return items
