"""HR documents are split into pieces of HR's own size, not Frontline's.

The sizes used to fall back to Frontline's settings, whose default is 4000
characters, so a short handbook became one piece. Its match with any single
question was then too weak, and HR answered "I don't have verified
information" about the learning budget written in the middle of it.
"""
import shutil
import tempfile
from pathlib import Path
from unittest import mock

from django.test import override_settings

from hr_agent import tasks
from hr_agent.models import HRDocument, HRDocumentChunk

from .base import HRTestCase

HANDBOOK = ' '.join([
    'Office hours are 9:30 to 18:30, Monday to Friday, and teams may work from home two days a week.',
    'New employees serve a probation of three months, and interns of two months.',
    'Medical insurance covers you, your spouse and up to three children.',
    'The learning budget is PKR 50,000 a year for courses, books and certifications, approved by your manager.',
    'Claim work expenses within 30 days, with receipts; anything above PKR 25,000 needs approval first.',
] * 6)


class HRChunkSizeTests(HRTestCase):

    def setUp(self):
        super().setUp()
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)

    def test_the_sizes_are_hrs_own_whatever_frontline_uses(self):
        with override_settings(FRONTLINE_CHUNK_SIZE=4000, FRONTLINE_CHUNK_OVERLAP=200):
            self.assertEqual(tasks.hr_chunk_sizes(), (1200, 150))
        with override_settings(HR_CHUNK_SIZE=800, HR_CHUNK_OVERLAP=100):
            self.assertEqual(tasks.hr_chunk_sizes(), (800, 100))

    def test_a_short_handbook_is_more_than_one_piece(self):
        path = Path(self.media) / 'handbook.txt'
        path.write_text(HANDBOOK, encoding='utf-8')
        doc = HRDocument.objects.create(company=self.company, title='Handbook', document_type='handbook',
                                        file_path=str(path), file_format='txt')
        with override_settings(MEDIA_ROOT=self.media, FRONTLINE_CHUNK_SIZE=4000), \
                mock.patch('core.Frontline_agent.embedding_service.EmbeddingService.is_available', return_value=False):
            tasks.process_hr_document.apply(args=[doc.id])
        chunks = list(HRDocumentChunk.objects.filter(document=doc).order_by('chunk_index'))
        self.assertGreaterEqual(len(chunks), 3, [len(c.chunk_text) for c in chunks])
        self.assertTrue(all(len(c.chunk_text) <= 1200 for c in chunks))
        self.assertTrue(any('learning budget' in c.chunk_text for c in chunks))
