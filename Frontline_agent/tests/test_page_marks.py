"""Page marks are taken out of every stored passage, the first page's too.

Live (27 Oct 2026) a source under a Knowledge Q&A answer read "__PAGE_1__ Client Support Guide …": the extracted
text is stripped, which takes the first page's form feed with it, and the chunkers (Frontline's and HR's) only knew the
mark with one.
"""
from unittest import mock

from Frontline_agent.document_processor import PAGE_MARKER_RE
from Frontline_agent.models import Document, DocumentChunk
from Frontline_agent.tasks import process_document

from .base import FrontlineTestCase

TEXT = '__PAGE_1__\nSupport hours are 9 to 6.\n\x0c__PAGE_2__\nBackups are kept for 30 days.'


class PageMarkTests(FrontlineTestCase):

    def test_the_mark_is_known_with_or_without_its_form_feed(self):
        self.assertEqual([m.group(1) for m in PAGE_MARKER_RE.finditer(TEXT)], ['1', '2'])
        self.assertNotIn('__PAGE_', PAGE_MARKER_RE.sub('', TEXT))

    def test_no_stored_passage_keeps_a_page_mark(self):
        doc = Document.objects.create(company=self.company, title='Guide', file_path='guide.pdf',
                                      uploaded_by=self.admin_user, file_format='pdf')
        extracted = {'success': True, 'extracted_text': TEXT, 'file_hash': 'x'}
        with mock.patch('Frontline_agent.document_processor.DocumentProcessor.process_document',
                        return_value=extracted), \
                mock.patch('core.Frontline_agent.embedding_service.EmbeddingService.is_available',
                           return_value=False):
            process_document.apply(args=[doc.id])
        texts = list(DocumentChunk.objects.filter(document=doc).values_list('chunk_text', flat=True))
        self.assertTrue(texts)
        self.assertFalse([t for t in texts if '__PAGE_' in t], texts)
        self.assertIn('Backups are kept for 30 days.', ''.join(texts))
