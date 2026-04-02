"""
Document Summarization Agent for Operations Agent
Accepts a document, extracts text, generates a rich structured summary,
saves only the summary (not the document), and cleans up.
"""

import os
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
            logger.error(f'{self.agent_name} error: {e}', exc_info=True)
            return {'success': False, 'error': str(e)}

    def _summarize_file(self, file_path: str, original_filename: str,
                        company_id: int, uploaded_by_id: int = None) -> Dict:
        """Extract text from file, generate rich summary, save summary, delete file."""
        from operations_agent.models import OperationsDocumentSummary
        from core.models import Company, CompanyUser

        ext = Path(original_filename).suffix.lower()
        file_type = self._doc_agent.SUPPORTED_EXTENSIONS.get(ext)
        if not file_type:
            return {'success': False, 'error': f'Unsupported file type: {ext}'}

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
            return {'success': False, 'error': error or 'Text extraction failed'}

        if not extracted_text or not extracted_text.strip():
            return {'success': False, 'error': 'No text could be extracted from this document'}

        word_count = len(extracted_text.split())

        # 2. Generate rich summary
        if len(extracted_text) > 12000:
            summary_result = self._summarize_large(extracted_text, original_filename, page_count)
        else:
            summary_result = self._summarize_single(extracted_text, original_filename, page_count)

        if not summary_result.get('success'):
            return summary_result

        # 3. Save summary only
        company = Company.objects.get(pk=company_id)
        uploaded_by = CompanyUser.objects.get(pk=uploaded_by_id) if uploaded_by_id else None

        summary_obj = OperationsDocumentSummary.objects.create(
            company=company,
            created_by=uploaded_by,
            original_filename=original_filename,
            file_type=file_type,
            file_size=file_size,
            page_count=page_count,
            word_count=word_count,
            rich_summary=summary_result['rich_summary'],
            key_findings=summary_result.get('key_findings', []),
            action_items=summary_result.get('action_items', []),
        )

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
            },
        }

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

        # Phase 1: Summarize each chunk
        chunk_summaries = []
        for i, chunk in enumerate(chunks):
            prompt = f"""Summarize this section (Part {i + 1} of {len(chunks)}) of "{filename}".
Extract ALL key points, findings, names, dates, and important details.

\"\"\"
{chunk}
\"\"\"

Provide a detailed bullet-point summary. Be thorough and specific."""

            try:
                result = self._call_llm_for_reasoning(prompt, temperature=0.2, max_tokens=1000)
                if result and result.strip():
                    chunk_summaries.append(f"**Section {i + 1}:**\n{result.strip()}")
            except Exception as e:
                logger.warning(f'Chunk {i + 1} summarization failed: {e}')

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
