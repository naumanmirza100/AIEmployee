"""
Document Processing Agent for Operations Agent
Handles document upload, parsing, text extraction, chunking, entity extraction,
and auto-classification for PDF, DOCX, Excel, PPT, CSV, and TXT files.
"""

import os
import hashlib
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from django.conf import settings
from django.utils import timezone

from marketing_agent.agents.marketing_base_agent import MarketingBaseAgent

logger = logging.getLogger(__name__)

# Chunk config
CHUNK_SIZE = 1000       # ~1000 chars per chunk
CHUNK_OVERLAP = 150     # overlap between chunks


class DocumentProcessingAgent(MarketingBaseAgent):
    """
    Processes uploaded documents: extracts text, metadata, entities,
    auto-classifies type, chunks for RAG, and optionally generates embeddings.
    """

    SUPPORTED_EXTENSIONS = {
        '.pdf': 'pdf',
        '.docx': 'docx',
        '.xlsx': 'xlsx',
        '.csv': 'csv',
        '.pptx': 'pptx',
        '.txt': 'txt',
        '.md': 'txt',
    }

    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB

    def __init__(self):
        super().__init__(use_embeddings=False)
        self.agent_name = 'DocumentProcessingAgent'

    # ------------------------------------------------------------------
    # Main entry
    # ------------------------------------------------------------------
    def process(self, action: str, **kwargs) -> Dict:
        actions = {
            'process_file': self._process_file,
            'classify': self._classify_document,
            'extract_entities': self._extract_entities,
        }
        handler = actions.get(action)
        if not handler:
            return {'success': False, 'error': f'Unknown action: {action}'}
        try:
            return handler(**kwargs)
        except Exception as e:
            logger.error(f'{self.agent_name} error: {e}', exc_info=True)
            return {'success': False, 'error': str(e)}

    # ------------------------------------------------------------------
    # File processing pipeline
    # ------------------------------------------------------------------
    def _process_file(self, file_path: str, original_filename: str,
                      company_id: int, uploaded_by_id: int,
                      title: str = '', tags: str = '') -> Dict:
        """Full pipeline: validate → extract → classify → entities → chunk → save."""
        from operations_agent.models import OperationsDocument, OperationsDocumentChunk
        from core.models import Company, CompanyUser

        # 1. Validate
        ext = Path(original_filename).suffix.lower()
        file_type = self.SUPPORTED_EXTENSIONS.get(ext)
        if not file_type:
            return {'success': False, 'error': f'Unsupported file type: {ext}. Supported: {", ".join(self.SUPPORTED_EXTENSIONS.keys())}'}

        file_size = os.path.getsize(file_path)
        if file_size > self.MAX_FILE_SIZE:
            return {'success': False, 'error': f'File too large ({file_size / 1024 / 1024:.1f} MB). Max: 50 MB'}

        # 2. Extract text
        success, extracted_text, page_count, error = self._extract_text(file_path, file_type)
        if not success:
            return {'success': False, 'error': error}

        if not extracted_text or not extracted_text.strip():
            return {'success': False, 'error': 'No text could be extracted from this document'}

        # 3. Auto-classify document type via LLM
        doc_type = self._classify_document(text=extracted_text[:3000])

        # 4. Extract entities via LLM
        entities = self._extract_entities(text=extracted_text[:4000])

        # 4b. Generate summary & key insights via LLM
        summary_result = self._generate_summary(text=extracted_text[:5000])
        summary = summary_result.get('summary', '') if isinstance(summary_result, dict) else ''
        key_insights = summary_result.get('key_insights', []) if isinstance(summary_result, dict) else []

        # 5. Build metadata
        metadata = {
            'original_filename': original_filename,
            'file_extension': ext,
            'char_count': len(extracted_text),
            'word_count': len(extracted_text.split()),
            'page_count': page_count,
        }

        # 6. Save OperationsDocument
        company = Company.objects.get(pk=company_id)
        uploaded_by = CompanyUser.objects.get(pk=uploaded_by_id) if uploaded_by_id else None

        doc = OperationsDocument.objects.create(
            company=company,
            uploaded_by=uploaded_by,
            title=title or Path(original_filename).stem,
            original_filename=original_filename,
            file=file_path,
            file_type=file_type,
            document_type=doc_type.get('document_type', 'other') if isinstance(doc_type, dict) else 'other',
            file_size=file_size,
            page_count=page_count,
            parsed_text=extracted_text,
            summary=summary,
            key_insights=key_insights,
            metadata=metadata,
            entities=entities.get('entities', {}) if isinstance(entities, dict) else {},
            tags=tags,
            is_processed=True,
            processed_at=timezone.now(),
        )

        # 7. Chunk text
        chunks = self._chunk_text(extracted_text, page_count)
        chunk_objs = []
        for chunk_data in chunks:
            chunk_objs.append(OperationsDocumentChunk(
                document=doc,
                chunk_index=chunk_data['index'],
                content=chunk_data['content'],
                page_number=chunk_data.get('page'),
                token_count=len(chunk_data['content'].split()),
            ))
        if chunk_objs:
            OperationsDocumentChunk.objects.bulk_create(chunk_objs)

        self.log_action('process_file', {
            'document_id': doc.id,
            'filename': original_filename,
            'chunks': len(chunk_objs),
        })

        return {
            'success': True,
            'document': {
                'id': doc.id,
                'title': doc.title,
                'file_type': doc.file_type,
                'document_type': doc.document_type,
                'page_count': page_count,
                'word_count': metadata['word_count'],
                'chunks_created': len(chunk_objs),
                'entities': doc.entities,
                'summary': summary,
                'key_insights': key_insights,
            },
        }

    # ------------------------------------------------------------------
    # Text extraction
    # ------------------------------------------------------------------
    def _extract_text(self, file_path: str, file_type: str) -> Tuple[bool, str, int, Optional[str]]:
        """Returns (success, text, page_count, error)."""
        try:
            if file_type == 'pdf':
                return self._extract_pdf(file_path)
            elif file_type == 'docx':
                return self._extract_docx(file_path)
            elif file_type == 'xlsx':
                return self._extract_xlsx(file_path)
            elif file_type == 'csv':
                return self._extract_csv(file_path)
            elif file_type == 'pptx':
                return self._extract_pptx(file_path)
            elif file_type == 'txt':
                return self._extract_txt(file_path)
            else:
                return False, '', 0, f'Unsupported file type: {file_type}'
        except Exception as e:
            logger.error(f'Text extraction failed for {file_path}: {e}', exc_info=True)
            return False, '', 0, str(e)

    @staticmethod
    def _extract_pdf(file_path: str) -> Tuple[bool, str, int, Optional[str]]:
        try:
            import pdfplumber
            pages_text = []
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    text = page.extract_text() or ''
                    pages_text.append(text)
            return True, '\n\n'.join(pages_text), len(pages_text), None
        except ImportError:
            try:
                from PyPDF2 import PdfReader
                reader = PdfReader(file_path)
                pages_text = [p.extract_text() or '' for p in reader.pages]
                return True, '\n\n'.join(pages_text), len(pages_text), None
            except ImportError:
                return False, '', 0, 'No PDF library available (install pdfplumber or PyPDF2)'
        except Exception as e:
            return False, '', 0, f'PDF extraction failed: {e}'

    @staticmethod
    def _extract_docx(file_path: str) -> Tuple[bool, str, int, Optional[str]]:
        try:
            from docx import Document
            doc = Document(file_path)
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            page_count = max(1, len(paragraphs) // 40)  # ~40 paragraphs per page estimate
            return True, '\n\n'.join(paragraphs), page_count, None
        except ImportError:
            return False, '', 0, 'python-docx not installed'
        except Exception as e:
            return False, '', 0, f'DOCX extraction failed: {e}'

    @staticmethod
    def _extract_xlsx(file_path: str) -> Tuple[bool, str, int, Optional[str]]:
        try:
            import pandas as pd
            xls = pd.ExcelFile(file_path)
            all_text = []
            for sheet_name in xls.sheet_names:
                df = pd.read_excel(xls, sheet_name=sheet_name)
                all_text.append(f'--- Sheet: {sheet_name} ---')
                all_text.append(df.to_string(index=False))
            return True, '\n\n'.join(all_text), len(xls.sheet_names), None
        except ImportError:
            return False, '', 0, 'pandas/openpyxl not installed'
        except Exception as e:
            return False, '', 0, f'Excel extraction failed: {e}'

    @staticmethod
    def _extract_csv(file_path: str) -> Tuple[bool, str, int, Optional[str]]:
        try:
            import pandas as pd
            df = pd.read_csv(file_path)
            return True, df.to_string(index=False), 1, None
        except ImportError:
            return False, '', 0, 'pandas not installed'
        except Exception as e:
            return False, '', 0, f'CSV extraction failed: {e}'

    @staticmethod
    def _extract_pptx(file_path: str) -> Tuple[bool, str, int, Optional[str]]:
        try:
            from pptx import Presentation
            prs = Presentation(file_path)
            slides_text = []
            for i, slide in enumerate(prs.slides, 1):
                texts = []
                for shape in slide.shapes:
                    if hasattr(shape, 'text') and shape.text.strip():
                        texts.append(shape.text)
                if texts:
                    slides_text.append(f'--- Slide {i} ---\n' + '\n'.join(texts))
            return True, '\n\n'.join(slides_text), len(prs.slides), None
        except ImportError:
            return False, '', 0, 'python-pptx not installed'
        except Exception as e:
            return False, '', 0, f'PPTX extraction failed: {e}'

    @staticmethod
    def _extract_txt(file_path: str) -> Tuple[bool, str, int, Optional[str]]:
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
            page_count = max(1, len(text) // 3000)
            return True, text, page_count, None
        except Exception as e:
            return False, '', 0, f'Text extraction failed: {e}'

    # ------------------------------------------------------------------
    # Chunking
    # ------------------------------------------------------------------
    def _chunk_text(self, text: str, page_count: int) -> List[Dict]:
        """Split text into overlapping chunks."""
        chunks = []
        idx = 0
        start = 0
        while start < len(text):
            end = start + CHUNK_SIZE
            chunk_content = text[start:end]
            # Estimate page number
            page = min(page_count, max(1, int((start / max(1, len(text))) * page_count) + 1))
            chunks.append({
                'index': idx,
                'content': chunk_content,
                'page': page,
            })
            idx += 1
            start = end - CHUNK_OVERLAP
        return chunks

    # ------------------------------------------------------------------
    # LLM-based classification
    # ------------------------------------------------------------------
    def _classify_document(self, text: str = '', **kwargs) -> Dict:
        """Classify document type using LLM."""
        if not text:
            return {'document_type': 'other'}
        try:
            prompt = f"""Classify the following document into exactly ONE of these types:
report, invoice, contract, memo, spreadsheet, presentation, policy, manual, other

Document excerpt:
\"\"\"
{text[:2000]}
\"\"\"

Respond with ONLY the type name (one word, lowercase). Nothing else."""

            result = self._call_llm_for_reasoning(prompt, temperature=0.1, max_tokens=20)
            doc_type = result.strip().lower().replace('.', '').replace('"', '').split()[0] if result else 'other'
            valid_types = ['report', 'invoice', 'contract', 'memo', 'spreadsheet', 'presentation', 'policy', 'manual', 'other']
            if doc_type not in valid_types:
                doc_type = 'other'
            return {'document_type': doc_type}
        except Exception as e:
            logger.warning(f'Classification failed, defaulting to other: {e}')
            return {'document_type': 'other'}

    # ------------------------------------------------------------------
    # LLM-based entity extraction
    # ------------------------------------------------------------------
    def _extract_entities(self, text: str = '', **kwargs) -> Dict:
        """Extract key entities from document text using LLM."""
        if not text:
            return {'entities': {}}
        try:
            prompt = f"""Extract key entities from the following document. Return a JSON object with these keys:
- dates: list of important dates found
- amounts: list of monetary amounts found
- names: list of person names found
- organizations: list of organization/company names found
- key_terms: list of important domain-specific terms

Document excerpt:
\"\"\"
{text[:3000]}
\"\"\"

Return ONLY valid JSON. No explanation."""

            result = self._call_llm_for_reasoning(prompt, temperature=0.1, max_tokens=500)

            import json
            # Try to parse JSON from response
            cleaned = result.strip()
            if cleaned.startswith('```'):
                cleaned = cleaned.split('\n', 1)[-1].rsplit('```', 1)[0]
            entities = json.loads(cleaned)
            return {'entities': entities}
        except Exception as e:
            logger.warning(f'Entity extraction failed: {e}')
            return {'entities': {}}

    # ------------------------------------------------------------------
    # LLM-based summary generation
    # ------------------------------------------------------------------
    def _generate_summary(self, text: str = '', **kwargs) -> Dict:
        """Generate a concise summary and key insights from document text."""
        if not text:
            return {'summary': '', 'key_insights': []}
        try:
            prompt = f"""Analyze the following document and provide:
1. A clear, concise summary (3-5 sentences) that captures the main purpose, content, and conclusions.
2. A list of 3-6 key insights or findings from the document.

Document excerpt:
\"\"\"
{text[:4500]}
\"\"\"

Return ONLY valid JSON in this exact format:
{{
  "summary": "Your summary here...",
  "key_insights": ["Insight 1", "Insight 2", "Insight 3"]
}}

No explanation outside the JSON."""

            result = self._call_llm_for_reasoning(prompt, temperature=0.2, max_tokens=800)

            import json
            cleaned = result.strip()
            if cleaned.startswith('```'):
                cleaned = cleaned.split('\n', 1)[-1].rsplit('```', 1)[0]
            parsed = json.loads(cleaned)
            return {
                'summary': parsed.get('summary', ''),
                'key_insights': parsed.get('key_insights', []),
            }
        except Exception as e:
            logger.warning(f'Summary generation failed: {e}')
            return {'summary': '', 'key_insights': []}
