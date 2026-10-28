"""
Document Processing Agent for Operations Agent
Handles document upload, parsing, text extraction, chunking, entity extraction,
and auto-classification for PDF, DOCX, Excel, PPT, CSV, and TXT files.
"""

import os
import re
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple
from django.db import DatabaseError, transaction
from django.utils import timezone

from marketing_agent.agents.marketing_base_agent import MarketingBaseAgent

# A line that carries money or a figure: PKR 18,500,000 / Rs. 650,000 / $1,200 / 12.5%.
_FIGURE_LINE = re.compile(r'(PKR|Rs\.?|USD|EUR|GBP|[$€£])\s?\d|\d[\d,.]*\s?(%|percent|million|lakh|crore)|\d{1,3}(,\d{3})+',
                          re.IGNORECASE)


def _entity_excerpt(text: str, head: int = 3000, extra: int = 2500) -> str:
    """The start of the document, plus the lines further on that carry amounts.

    Only the first 3,000 characters were read, and a contract's fees come after its definitions: the FinEdge
    agreement's PKR 18,500,000 starts at character 3,183, so its entities had no amounts at all.
    """
    if len(text) <= head:
        return text
    lines, size = [], 0
    for line in text[head:].splitlines():
        line = line.strip()
        if line and _FIGURE_LINE.search(line) and size + len(line) <= extra:
            lines.append(line)
            size += len(line) + 1
    return text[:head] + ('\n...\n' + '\n'.join(lines) if lines else '')

logger = logging.getLogger(__name__)

# Chunk config
CHUNK_SIZE = 1000       # ~1000 chars per chunk
CHUNK_OVERLAP = 150     # overlap between chunks

# What one file may be read to (CO-216): about 500 pages of text, 1,000 PDF pages, 20,000 rows a sheet, and a Word,
# Excel or PowerPoint file that unpacks to no more than 200 MB.
MAX_TEXT_CHARS = 1_500_000
MAX_PDF_PAGES = 1000
MAX_SHEET_ROWS = 20_000
MAX_UNPACKED_BYTES = 200 * 1024 * 1024

# The agent key Operations resolves against — matches the name used for its LLM
# calls, so embeddings draw on the same BYOK/managed/platform key.
OPERATIONS_AGENT_KEY = 'operations_agent'


def build_embedding_service(company_id):
    """Construct an EmbeddingService bound to this company, or None.

    Embeddings historically resolved only from env keys, so a tenant with a
    valid `operations_agent` key still indexed every chunk with no vector and
    QA silently degraded to keyword-only retrieval — see
    OPERATIONS_QA_DIAGNOSIS.md.

    `company_id` support landed with the Frontline embedding work; until that
    is merged everywhere, fall back to the no-argument form rather than raising
    a TypeError that the callers' broad `except` would swallow into "no
    embeddings at all". Returns None when the service cannot be imported.
    """
    try:
        from core.Frontline_agent.embedding_service import EmbeddingService
    except Exception:
        return None
    if company_id:
        try:
            return EmbeddingService(company_id=company_id,
                                    agent_key_name=OPERATIONS_AGENT_KEY)
        except TypeError:
            logger.debug("EmbeddingService has no per-company support yet; "
                         "falling back to env-keyed construction.")
    return EmbeddingService()


def _as_text(value) -> str:
    """One item from the AI as plain text: an object such as {"value": 18500000, "currency": "PKR"} becomes
    "18500000 PKR", a list is joined."""
    if isinstance(value, dict):
        return ' '.join(_as_text(v) for v in value.values() if v not in (None, '')).strip()
    if isinstance(value, (list, tuple)):
        return ', '.join(_as_text(v) for v in value if v not in (None, '')).strip()
    return '' if value is None else str(value).strip()


def rows_as_lines(df, sheet_name='') -> str:
    """A sheet as one line per row, each value with its column's name: "Month: 2026-09; Cloud hosting: 2.0; …".

    It was printed as one wide grid under a single header row. Cut into passages, a row lost its header, and the AI
    read the wrong column: "what did cloud hosting cost in September?" got 4.1, which was mobile-app revenue from
    the other sheet; the sheet says 2.0 (Operations clean run, 28 Oct 2026)."""
    import math
    columns = [str(c).strip() for c in df.columns]
    named = [not c.lower().startswith('unnamed') for c in columns]
    prefix = f'[{sheet_name}] ' if sheet_name else ''
    lines = [prefix + 'Columns: ' + ' | '.join(c for c, keep in zip(columns, named) if keep)] if any(named) else []
    for values in df.itertuples(index=False, name=None):
        cells = []
        for column, keep, value in zip(columns, named, values):
            if value is None or (isinstance(value, float) and math.isnan(value)) or str(value).strip() == '':
                continue
            if isinstance(value, float) and value.is_integer():
                value = int(value)
            cells.append(f'{column}: {value}' if keep else str(value))
        if cells:
            lines.append(prefix + '; '.join(cells))
    return '\n'.join(lines)


def clean_items(values, *, items=10, chars=300) -> list:
    """The AI's list as short strings, empty ones dropped. The Documents tab saved whatever parsed, and an item that
    came back as an object could not be printed: the document's page failed to draw (CO-268)."""
    if not isinstance(values, (list, tuple)):
        values = [values] if values not in (None, '', {}) else []
    out = []
    for value in values:
        text = _as_text(value)[:chars]
        if text and text not in out:
            out.append(text)
    return out[:items]


def clean_entities(entities) -> dict:
    """The AI's groups of names, dates and amounts: each a list of strings, anything else dropped."""
    if not isinstance(entities, dict):
        return {}
    return {str(key)[:50]: clean_items(values, items=15, chars=200)
            for key, values in entities.items() if clean_items(values)}


def no_text_message(file_type) -> str:
    """Why a file gave no text, and what to do. It said only "No text could be extracted from this document"
    (found on the live run, 28 Oct 2026: a scanned invoice)."""
    if file_type == 'pdf':
        return ('No text could be read from this PDF. It looks like a scan or a photo of a page, and Operations reads '
                'text, not pictures of text. Upload the original document, or a PDF whose text you can select.')
    return 'This file has no text in it to read. Check that it is the right file, then upload it again.'


#: What the processing returns when the entry was deleted while it was being processed (CO-172).
DELETED_MEANWHILE = 'The document was deleted while it was being processed.'


def _deleted_meanwhile(file_path):
    """Stop quietly for an entry deleted during processing: remove the uploaded file, make nothing."""
    try:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
    except OSError:
        pass
    logger.info("Operations: %s (%s)", DELETED_MEANWHILE, file_path)
    return {'success': False, 'error': DELETED_MEANWHILE, 'deleted': True}


def _invalidate_operations_indexes(company_id, has_embeddings: bool) -> None:
    """After a doc goes live, rebuild the FAISS index and clear the answer cache
    for its company. Both are best-effort — a cache miss must never break an
    otherwise successful upload."""
    if not company_id:
        return
    if has_embeddings:
        try:
            from operations_agent.vector_store import mark_index_dirty
            mark_index_dirty(company_id)
        except Exception:
            logger.exception("Operations: failed to mark FAISS index dirty")
    try:
        from operations_agent.agents.knowledge_qa_agent import invalidate_answer_cache_for_company
        invalidate_answer_cache_for_company(company_id)
    except Exception:
        logger.exception("Operations: failed to invalidate answer cache")


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
            from core.api_key_service import KeyServiceError
            if isinstance(e, KeyServiceError):
                raise
            logger.error(f'{self.agent_name} error: {e}', exc_info=True)
            return {'success': False, 'error': str(e)}

    # ------------------------------------------------------------------
    # File processing pipeline
    # ------------------------------------------------------------------
    def _process_file(self, file_path: str, original_filename: str,
                      company_id: int, uploaded_by_id: int,
                      title: str = '', tags: str = '',
                      existing_doc_id: int = None) -> Dict:
        """Full pipeline: validate → extract → classify → entities → chunk → save.

        When ``existing_doc_id`` is given (async upload flow), that placeholder
        row is stamped ``processing`` and updated in place instead of creating a
        new one; failures stamp it ``failed`` so the status poll can report them.
        """
        from operations_agent.models import OperationsDocument, OperationsDocumentChunk
        from core.models import Company, CompanyUser

        def _fail(doc_row, message):
            """Stamp a placeholder row failed (async flow) and return an error."""
            if doc_row is not None:
                try:
                    doc_row.processing_status = 'failed'
                    doc_row.processing_error = str(message)[:2000]
                    doc_row.save(update_fields=['processing_status', 'processing_error', 'updated_at'])
                except Exception:
                    logger.exception("Operations: failed to stamp doc %s as failed", getattr(doc_row, 'id', '?'))
            return {'success': False, 'error': message}

        placeholder = None
        if existing_doc_id:
            placeholder = OperationsDocument.objects.filter(id=existing_doc_id).first()
            if placeholder is None:
                # Deleted before the work started: nothing to make (it used to fall through to a brand-new entry).
                return _deleted_meanwhile(file_path)
            placeholder.processing_status = 'processing'
            placeholder.save(update_fields=['processing_status', 'updated_at'])

        # 1. Validate
        ext = Path(original_filename).suffix.lower()
        file_type = self.SUPPORTED_EXTENSIONS.get(ext)
        if not file_type:
            return _fail(placeholder, f'Unsupported file type: {ext}. Supported: {", ".join(self.SUPPORTED_EXTENSIONS.keys())}')

        file_size = os.path.getsize(file_path)
        if file_size > self.MAX_FILE_SIZE:
            return _fail(placeholder, f'File too large ({file_size / 1024 / 1024:.1f} MB). Max: 50 MB')

        # 2. Extract text
        success, extracted_text, page_count, error = self._extract_text(file_path, file_type)
        if not success:
            return _fail(placeholder, error)

        if not extracted_text or not extracted_text.strip():
            return _fail(placeholder, no_text_message(file_type))

        # 3. Auto-classify document type via LLM
        doc_type = self._classify_document(text=extracted_text[:3000])

        # 4. Extract entities via LLM
        entities = self._extract_entities(text=extracted_text)

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
        if getattr(self, 'read_note', ''):
            metadata['partly_read'] = self.read_note      # shown on the document's page (CO-216)
        if getattr(self, 'page_starts', None):
            metadata['page_starts'] = self.page_starts    # each passage's real page, also when re-indexed (CO-278)

        # 6. Save OperationsDocument
        company = Company.objects.get(pk=company_id)
        uploaded_by = CompanyUser.objects.get(pk=uploaded_by_id) if uploaded_by_id else None

        resolved_doc_type = doc_type.get('document_type', 'other') if isinstance(doc_type, dict) else 'other'
        # `is_processed` stays False until the row is durably 'ready' — it is a
        # derived mirror of processing_status, not a second source of truth, so
        # the two never disagree mid-pipeline.
        doc_fields = dict(
            company=company,
            uploaded_by=uploaded_by,
            title=title or Path(original_filename).stem,
            original_filename=original_filename,
            file=file_path,
            file_type=file_type,
            document_type=resolved_doc_type,
            file_size=file_size,
            page_count=page_count,
            parsed_text=extracted_text,
            summary=summary,
            key_insights=key_insights,
            metadata=metadata,
            entities=entities.get('entities', {}) if isinstance(entities, dict) else {},
            tags=tags,
            is_processed=False,
            processed_at=timezone.now(),
            processing_status='processing',
        )
        if placeholder is not None:
            # Async flow: fill in the pre-created placeholder row. Only an update: a plain save re-created an entry
            # deleted during the AI steps, under the same id, searchable and with its 'is ready' alert (CO-172).
            for k, v in doc_fields.items():
                setattr(placeholder, k, v)
            try:
                with transaction.atomic():          # its own savepoint, so a refused update leaves nothing broken
                    placeholder.save(force_update=True)
            except DatabaseError:
                return _deleted_meanwhile(file_path)
            doc = placeholder
        else:
            doc = OperationsDocument.objects.create(**doc_fields)

        # 7-8. Chunk + embed and stamp 'ready' in ONE transaction. If anything
        #      here fails or the process dies, the row stays 'processing' with
        #      its file intact and the chunks roll back — recoverable, never a
        #      half-ready doc.
        try:
            with transaction.atomic():
                chunk_count, embedded, embed_model = self._chunk_embed_and_store(
                    doc, extracted_text, page_count, resolved_doc_type,
                )
                doc.chunks_total = chunk_count
                doc.chunks_processed = chunk_count
                doc.is_indexed = embedded
                doc.embedding_model = embed_model or ''
                doc.processing_status = 'ready'
                doc.is_processed = True
                doc.save(update_fields=[
                    'chunks_total', 'chunks_processed', 'is_indexed',
                    'embedding_model', 'processing_status', 'is_processed', 'updated_at',
                ])
        except DatabaseError:
            if not OperationsDocument.objects.filter(pk=doc.pk).exists():
                return _deleted_meanwhile(file_path)     # deleted while its passages were being stored
            raise

        # 9. Only NOW that the row is durably 'ready' is it safe to drop the
        #    source file — a crash before this point leaves the file reusable.
        try:
            src = Path(file_path)
            if src.exists():
                src.unlink()
            OperationsDocument.objects.filter(pk=doc.pk).update(file='')
            doc.file = ''
        except OSError:
            logger.warning("Operations: could not delete source file %s", file_path)

        _invalidate_operations_indexes(doc.company_id, embedded)

        self.log_action('process_file', {
            'document_id': doc.id,
            'filename': original_filename,
            'chunks': chunk_count,
            'embedded': embedded,
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
                'chunks_created': chunk_count,
                'entities': doc.entities,
                'summary': summary,
                'key_insights': key_insights,
            },
        }

    # ------------------------------------------------------------------
    # Text extraction
    # ------------------------------------------------------------------
    def _extract_text(self, file_path: str, file_type: str) -> Tuple[bool, str, int, Optional[str]]:
        """Returns (success, text, page_count, error). ``self.read_note`` says when only part of the file was read.

        Nothing limited what a file could expand to (CO-216): a Word, Excel or PowerPoint file is a zip and was
        unpacked whole in the web process, a spreadsheet was printed whole, and the text had no ceiling, so one file
        could become thousands of passages and hundreds of summary calls. The unpacked size is checked first, PDF
        pages and spreadsheet rows are capped, and the text is cut at MAX_TEXT_CHARS, each with a note the user sees.
        """
        self.read_note = ''
        self.page_starts = None
        if file_type in ('docx', 'xlsx', 'pptx'):
            import zipfile
            try:
                with zipfile.ZipFile(file_path) as archive:
                    unpacked = sum(info.file_size for info in archive.infolist())
            except (zipfile.BadZipFile, OSError):
                return False, '', 0, ("We couldn't read this file. It may be corrupted or saved in an older format "
                                      "(.doc, .xls, .ppt are not read): please save it again as .docx, .xlsx or .pptx.")
            if unpacked > MAX_UNPACKED_BYTES:
                return False, '', 0, (f'This file unpacks to {unpacked / 1024 / 1024:.0f} MB, more than the '
                                      f'{MAX_UNPACKED_BYTES // 1024 // 1024} MB that can be read. Please split it '
                                      'into smaller files.')
        success, text, page_count, error = self._extract_by_type(file_path, file_type)
        if success and file_type == 'pptx':
            # A slide is a deck's page: where each one starts (slides with no text are not in the text).
            self.page_starts = [[m.start(), int(m.group(1))]
                                for m in re.finditer(r'^--- Slide (\d+) ---$', text or '', re.M)] or None
        notes = re.findall(r'\[Only the first [^\]]+\]', text or '')
        if success and text and len(text) > MAX_TEXT_CHARS:
            notes.append(f'[Only the first {MAX_TEXT_CHARS:,} characters of {len(text):,} were read: the file is '
                         'too long to read whole. Split it to have the rest read.]')
            text = text[:MAX_TEXT_CHARS]
        self.read_note = ' '.join(n.strip('[]') for n in notes)
        return success, text, page_count, error

    def _extract_by_type(self, file_path: str, file_type: str) -> Tuple[bool, str, int, Optional[str]]:
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
                return False, '', 0, (
                    f"This file type (.{file_type}) isn't supported. "
                    "Please upload a PDF, Word, Excel, CSV, PowerPoint, or text file."
                )
        except Exception as e:
            logger.error(f'Text extraction failed for {file_path}: {e}', exc_info=True)
            return False, '', 0, (
                "We couldn't read this file. It may be corrupted or in an unsupported format — "
                "please check it opens correctly and re-upload."
            )

    def _join_pages(self, pages_text, total):
        """The pages joined, with where each starts kept in ``self.page_starts`` as [offset, page number]."""
        starts, pos = [], 0
        for number, text in enumerate(pages_text, 1):
            starts.append([pos, number])
            pos += len(text) + 2
        self.page_starts = starts
        if total > len(pages_text):
            pages_text = pages_text + [f'[Only the first {len(pages_text):,} pages of {total:,} were read.]']
        return '\n\n'.join(pages_text)

    def _extract_pdf(self, file_path: str) -> Tuple[bool, str, int, Optional[str]]:
        try:
            import pdfplumber
            pages_text = []
            with pdfplumber.open(file_path) as pdf:
                total = len(pdf.pages)
                for page in pdf.pages[:MAX_PDF_PAGES]:
                    text = page.extract_text() or ''
                    pages_text.append(text)
                    getattr(page, 'flush_cache', lambda: None)()    # keep memory flat on long files
            return True, self._join_pages(pages_text, total), len(pages_text), None
        except ImportError:
            try:
                from PyPDF2 import PdfReader
                reader = PdfReader(file_path)
                pages_text = [p.extract_text() or '' for p in reader.pages[:MAX_PDF_PAGES]]
                return True, self._join_pages(pages_text, len(reader.pages)), len(pages_text), None
            except ImportError:
                return False, '', 0, 'The server is missing a required library to read PDF files. Please contact support.'
        except Exception as e:
            logger.error('PDF extraction failed for %s: %s', file_path, e, exc_info=True)
            return False, '', 0, (
                "We couldn't read this PDF. It may be corrupted, password-protected, or a scanned image — "
                "please check it opens correctly and re-upload."
            )

    @staticmethod
    def _extract_docx(file_path: str) -> Tuple[bool, str, int, Optional[str]]:
        """The body in order, tables included row by row, then headers, footers and text boxes.

        Only the body's paragraphs were read: a fee schedule or a price list in a table, and anything in a header,
        footer or text box, was left out of the text, the summary and the search, with no warning (CO-177)."""
        try:
            from docx import Document
            from docx.oxml.ns import qn
            from docx.table import Table
            from docx.text.paragraph import Paragraph
            doc = Document(file_path)

            def table_lines(table):
                lines = []
                for row in table.rows:
                    cells, seen = [], set()
                    for cell in row.cells:
                        if id(cell._tc) in seen:       # a merged cell is listed once per column it spans
                            continue
                        seen.add(id(cell._tc))
                        text = ' '.join(cell.text.split())
                        if text:
                            cells.append(text)
                    if cells:
                        lines.append(' | '.join(cells))
                return lines

            blocks = []
            for child in doc.element.body.iterchildren():
                tag = child.tag.rsplit('}', 1)[-1]
                if tag == 'p':
                    text = Paragraph(child, doc).text
                    if text.strip():
                        blocks.append(text)
                elif tag == 'tbl':
                    lines = table_lines(Table(child, doc))
                    if lines:
                        blocks.append('\n'.join(lines))
            extra = []
            for section in doc.sections:
                for part in (section.header, section.footer):
                    try:
                        text = '\n'.join(p.text for p in part.paragraphs if p.text.strip())
                    except Exception:
                        text = ''
                    if text and text not in extra:
                        extra.append(text)
            for box in doc.element.body.iter(qn('w:txbxContent')):
                text = ' '.join(''.join(t.text or '' for t in box.iter(qn('w:t'))).split())
                if text and text not in extra:
                    extra.append(text)
            page_count = max(1, len(blocks) // 40)  # ~40 paragraphs per page estimate
            return True, '\n\n'.join(blocks + extra), page_count, None
        except ImportError:
            return False, '', 0, 'The server is missing a required library to read Word files. Please contact support.'
        except Exception as e:
            logger.error('DOCX extraction failed for %s: %s', file_path, e, exc_info=True)
            return False, '', 0, (
                "We couldn't read this Word document. It may be corrupted or in an older/unsupported format — "
                "please check it opens correctly and re-upload."
            )

    @staticmethod
    def _extract_xlsx(file_path: str) -> Tuple[bool, str, int, Optional[str]]:
        try:
            import pandas as pd
            xls = pd.ExcelFile(file_path)
            all_text = []
            for sheet_name in xls.sheet_names:
                df = pd.read_excel(xls, sheet_name=sheet_name, nrows=MAX_SHEET_ROWS + 1)
                all_text.append(f'--- Sheet: {sheet_name} ---')
                all_text.append(rows_as_lines(df.head(MAX_SHEET_ROWS), sheet_name))
                if len(df) > MAX_SHEET_ROWS:
                    all_text.append(f'[Only the first {MAX_SHEET_ROWS:,} rows of the sheet "{sheet_name}" were read.]')
            return True, '\n\n'.join(all_text), len(xls.sheet_names), None
        except ImportError:
            return False, '', 0, 'The server is missing a required library to read Excel files. Please contact support.'
        except Exception as e:
            logger.error('Excel extraction failed for %s: %s', file_path, e, exc_info=True)
            return False, '', 0, (
                "We couldn't read this Excel file. It may be corrupted or password-protected — "
                "please check it opens correctly and re-upload."
            )

    @staticmethod
    def _extract_csv(file_path: str) -> Tuple[bool, str, int, Optional[str]]:
        try:
            import pandas as pd
            try:
                df = pd.read_csv(file_path, nrows=MAX_SHEET_ROWS + 1)
            except pd.errors.ParserError:
                # Ragged rows (uneven column counts) are the most common cause of
                # a "failed" CSV. Retry tolerantly by skipping the bad lines so a
                # slightly-malformed file still imports instead of hard-failing.
                logger.warning('CSV %s had malformed rows; retrying with on_bad_lines=skip', file_path)
                df = pd.read_csv(file_path, on_bad_lines='skip', engine='python', nrows=MAX_SHEET_ROWS + 1)
            if df.empty:
                return False, '', 0, (
                    "This CSV appears to be empty or has no readable rows. "
                    "Please check the file has a header row and at least one data row, then re-upload."
                )
            text = rows_as_lines(df.head(MAX_SHEET_ROWS))
            if len(df) > MAX_SHEET_ROWS:
                text += f'\n[Only the first {MAX_SHEET_ROWS:,} rows were read.]'
            return True, text, 1, None
        except ImportError:
            return False, '', 0, 'The server is missing a required library to read CSV files. Please contact support.'
        except UnicodeDecodeError:
            return False, '', 0, (
                "We couldn't read this CSV — it may use an unsupported text encoding. "
                "Try re-saving it as UTF-8 CSV and upload again."
            )
        except Exception as e:
            logger.error('CSV extraction failed for %s: %s', file_path, e, exc_info=True)
            return False, '', 0, (
                "We couldn't read this CSV file. It looks malformed — please make sure every row has the "
                "same number of columns (no extra commas), then re-upload."
            )

    @staticmethod
    def _extract_pptx(file_path: str) -> Tuple[bool, str, int, Optional[str]]:
        try:
            from pptx import Presentation
            from pptx.enum.shapes import MSO_SHAPE_TYPE
            prs = Presentation(file_path)

            def shape_texts(shape):
                # Tables, shapes inside groups and the speaker notes were skipped (CO-177).
                try:
                    is_group = shape.shape_type == MSO_SHAPE_TYPE.GROUP
                except Exception:
                    is_group = False
                if is_group:
                    for inner in shape.shapes:
                        yield from shape_texts(inner)
                elif getattr(shape, 'has_table', False):
                    for row in shape.table.rows:
                        cells = [' '.join(c.text.split()) for c in row.cells]
                        cells = [c for c in cells if c]
                        if cells:
                            yield ' | '.join(cells)
                elif getattr(shape, 'has_text_frame', False) and shape.text_frame.text.strip():
                    yield shape.text_frame.text

            slides_text = []
            for i, slide in enumerate(prs.slides, 1):
                texts = [t for shape in slide.shapes for t in shape_texts(shape)]
                try:
                    notes = slide.notes_slide.notes_text_frame.text.strip() if slide.has_notes_slide else ''
                except Exception:
                    notes = ''
                if notes:
                    texts.append(f'Speaker notes: {notes}')
                if texts:
                    slides_text.append(f'--- Slide {i} ---\n' + '\n'.join(texts))
            return True, '\n\n'.join(slides_text), len(prs.slides), None
        except ImportError:
            return False, '', 0, 'The server is missing a required library to read PowerPoint files. Please contact support.'
        except Exception as e:
            logger.error('PPTX extraction failed for %s: %s', file_path, e, exc_info=True)
            return False, '', 0, (
                "We couldn't read this PowerPoint file. It may be corrupted or in an unsupported format — "
                "please check it opens correctly and re-upload."
            )

    @staticmethod
    def _extract_txt(file_path: str) -> Tuple[bool, str, int, Optional[str]]:
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
            page_count = max(1, len(text) // 3000)
            return True, text, page_count, None
        except Exception as e:
            logger.error('Text extraction failed for %s: %s', file_path, e, exc_info=True)
            return False, '', 0, (
                "We couldn't read this text file. It may be corrupted or use an unsupported encoding — "
                "please re-save it as UTF-8 and upload again."
            )

    # ------------------------------------------------------------------
    # Chunking + embedding (RAG)
    # ------------------------------------------------------------------
    def _chunk_embed_and_store(self, doc, text: str, page_count: int,
                               document_type: str, owner_kind: str = 'document', page_starts=None):
        """Chunk (section-aware, TOC filtered), embed in batches, and persist.

        ``owner_kind`` is 'document' or 'summary' — the chunk rows link to the
        matching FK so both surfaces share one retrieval pipeline.

        Returns ``(chunk_count, embedded_bool, embedding_model)``. Falls back to
        no-embedding storage when the embedding provider is unavailable, so the
        keyword retrieval path still works. Mirrors the HR/Frontline pipeline.
        """
        from operations_agent.models import OperationsDocumentChunk

        if page_starts is None and owner_kind == 'document':
            page_starts = (getattr(doc, 'metadata', None) or {}).get('page_starts')
        chunk_pairs = self._chunk_pairs(text, page_count, document_type, page_starts)
        if not chunk_pairs:
            return 0, False, ''

        # Embedding is optional — the retriever falls back to keyword search
        # when a chunk has no vector. The provider prefers an env key but falls
        # back to this company's own key (BYOK → managed → platform), the same
        # resolution the LLM calls use. Without the tenant, a company with a
        # perfectly good operations_agent key still indexed every chunk with no
        # vector and QA silently degraded to keyword-only matching.
        embedding_service = None
        has_embeddings = False
        embed_model = ''
        try:
            embedding_service = build_embedding_service(
                getattr(doc, 'company_id', None))
            has_embeddings = bool(embedding_service) and embedding_service.is_available()
            embed_model = getattr(embedding_service, 'embedding_model', '') or ''
        except Exception:
            logger.warning("Operations: embedding service unavailable; storing chunks without vectors")

        texts = [c for c, _h, _p in chunk_pairs]
        embeddings = [None] * len(texts)
        if has_embeddings:
            batch_size = 20
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                try:
                    batch_vecs = embedding_service.generate_embeddings_batch(batch)
                except Exception as exc:
                    logger.warning("Operations embedding batch failed: %s", exc)
                    batch_vecs = [None] * len(batch)
                for j, v in enumerate(batch_vecs or []):
                    embeddings[i + j] = v

        rows = []
        any_vector = False
        for i, (content, heading, page) in enumerate(chunk_pairs):
            emb = embeddings[i]
            if emb:
                any_vector = True
            rows.append(OperationsDocumentChunk(
                document=doc if owner_kind == 'document' else None,
                summary=doc if owner_kind == 'summary' else None,
                chunk_index=i,
                content=content,
                section_heading=(heading or '')[:300],
                page_number=page,
                token_count=len(content.split()),
                embedding=emb,
            ))
        # In batches: one insert of thousands of rows (with their vectors) was what failed on large files (CO-178).
        OperationsDocumentChunk.objects.bulk_create(rows, batch_size=200)
        return len(rows), any_vector, (embed_model if any_vector else '')

    def _chunk_pairs(self, text: str, page_count: int, document_type: str, page_starts=None):
        """Return a list of ``(content, heading, page_number)`` tuples.

        Section-aware doc types use the heading-aware chunker (which also drops
        TOC/index junk); everything else uses a fixed-window chunker that still
        skips junk chunks.

        A passage's page is the real one: where it starts, looked up in ``page_starts`` ([offset, page] for each PDF
        page or slide). It was its position in the text times the page count, right only if every page held the
        same amount of text; Word files got a "page" per 40 paragraphs and text files one per 3,000 characters, and
        a passage that could not be found was stamped page 1 (CO-278). A file type with no pages gets none.
        """
        import bisect
        from operations_agent.chunking import (
            chunk_with_headings, looks_like_toc_or_index, SECTION_AWARE_TYPES,
        )

        starts = [int(p[0]) for p in page_starts] if page_starts else []

        def _page_for(offset):
            if not starts or offset is None or offset < 0:
                return None
            return int(page_starts[max(0, bisect.bisect_right(starts, offset) - 1)][1])

        pairs = []
        if document_type in SECTION_AWARE_TYPES:
            searched_from = 0
            for content, heading in chunk_with_headings(
                text, max_chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP,
            ):
                # Where the passage starts: searched onward from the last one, so a repeated line is not taken for an
                # earlier page.
                off = text.find(content[:60], searched_from) if content else -1
                if off < 0 and content:
                    off = text.find(content[:60])
                if off >= 0:
                    searched_from = off
                pairs.append((content, heading, _page_for(off if off >= 0 else None)))
            if pairs:
                return pairs

        # Fixed-window fallback (also used when section chunking yielded nothing)
        idx_start = 0
        step = max(1, CHUNK_SIZE - CHUNK_OVERLAP)
        while idx_start < len(text):
            content = text[idx_start:idx_start + CHUNK_SIZE].strip()
            if content and not looks_like_toc_or_index(content):
                pairs.append((content, '', _page_for(idx_start)))
            idx_start += step
        return pairs

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
            from core.api_key_service import KeyServiceError
            if isinstance(e, KeyServiceError):
                raise
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
{_entity_excerpt(text)}
\"\"\"

Return ONLY valid JSON. No explanation."""

            result = self._call_llm_for_reasoning(prompt, temperature=0.1, max_tokens=500)

            import json
            # Try to parse JSON from response
            cleaned = result.strip()
            if cleaned.startswith('```'):
                cleaned = cleaned.split('\n', 1)[-1].rsplit('```', 1)[0]
            entities = clean_entities(json.loads(cleaned))
            return {'entities': entities}
        except Exception as e:
            from core.api_key_service import KeyServiceError
            if isinstance(e, KeyServiceError):
                raise
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
            if not isinstance(parsed, dict):
                return {'summary': '', 'key_insights': []}
            return {
                'summary': _as_text(parsed.get('summary', ''))[:3000],
                'key_insights': clean_items(parsed.get('key_insights', []), items=8),
            }
        except Exception as e:
            from core.api_key_service import KeyServiceError
            if isinstance(e, KeyServiceError):
                raise
            logger.warning(f'Summary generation failed: {e}')
            return {'summary': '', 'key_insights': []}
