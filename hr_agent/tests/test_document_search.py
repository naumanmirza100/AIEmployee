"""HR and Frontline say when document search can only match words, and fix parts saved without vectors (CO-70).

When no embedding provider worked, or a batch call failed, chunks were stored without vectors, the document was still
marked ready and the upload pop-up said "N chunk(s) embedded"; no screen told the company search was matching words.
"""
import json
from types import SimpleNamespace
from unittest import mock

from django.core.cache import cache

from api.views import document_search as views
from api.views import hr_agent as hr_views
from core import document_search
from core.Frontline_agent.embedding_service import EmbeddingService
from Frontline_agent.models import Document, DocumentChunk
from hr_agent.models import HRDocument, HRDocumentChunk

from .base import HRTestCase


class FakeService:
    """Stands in for the embedding service: a working provider that gives every text a 3-number vector."""
    embedding_model = 'fake-model'
    recommended_batch_size = 2

    def __init__(self, *args, **kwargs):
        pass

    def is_available(self):
        return True

    def generate_embeddings_batch(self, texts):
        return [[0.1, 0.2, 0.3] for _ in texts]


class DocumentSearchTests(HRTestCase):

    def setUp(self):
        super().setUp()
        cache.clear()
        self.doc = HRDocument.objects.create(company=self.company, title='Leave policy', document_type='policy',
                                            processing_status='ready', is_indexed=True, chunks_total=3)
        HRDocumentChunk.objects.create(document=self.doc, chunk_index=0, chunk_text='Annual leave is 18 days.',
                                       embedding=json.dumps([0.1, 0.2, 0.3]))
        for i in (1, 2):
            HRDocumentChunk.objects.create(document=self.doc, chunk_index=i, chunk_text=f'Part {i}.', embedding=None)

    def provider(self, works):
        return mock.patch.object(document_search, 'provider_available', return_value=works)

    def test_words_only_when_no_provider_works(self):
        with self.provider(False):
            self.assertEqual(document_search.status(self.company.id, 'hr_agent')['mode'], 'words')

    def test_partly_when_some_parts_have_no_vector(self):
        with self.provider(True):
            info = document_search.status(self.company.id, 'hr_agent')
        self.assertEqual((info['mode'], info['chunks'], info['chunks_without_vectors']), ('partly', 3, 2))

    def test_filling_gives_every_part_a_vector(self):
        with mock.patch('core.Frontline_agent.embedding_service.EmbeddingService', FakeService), \
                mock.patch('hr_agent.vector_store.mark_index_dirty') as dirty:
            filled = document_search.fill_missing_vectors(self.company.id, 'hr_agent')
        self.assertEqual(filled, 2)
        self.assertFalse(HRDocumentChunk.objects.filter(embedding__isnull=True).exists())
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.embedding_model, 'fake-model')
        dirty.assert_called_once_with(self.company.id)
        with self.provider(True):
            self.assertEqual(document_search.status(self.company.id, 'hr_agent')['mode'], 'meaning')

    def test_another_companys_parts_are_left_alone(self):
        other = HRDocument.objects.create(company=self.rival, title='Rival policy', document_type='policy')
        HRDocumentChunk.objects.create(document=other, chunk_index=0, chunk_text='Rival text.', embedding=None)
        with mock.patch('core.Frontline_agent.embedding_service.EmbeddingService', FakeService), \
                mock.patch('hr_agent.vector_store.mark_index_dirty'):
            document_search.fill_missing_vectors(self.company.id, 'hr_agent')
        self.assertTrue(HRDocumentChunk.objects.filter(document=other, embedding__isnull=True).exists())

    def test_an_hr_member_cannot_fix_and_is_told_why(self):
        with self.provider(True):
            code, body = self.call(views.document_search_status, self.member, {'agent': 'hr_agent'})
            self.assertEqual(code, 403)
            self.assertIn('Only an HR admin can do this', body['message'])
            code, body = self.call(views.document_search_status, self.member, {'agent': 'hr_agent'}, method='get')
        self.assertEqual(body['data']['mode'], 'partly')
        self.assertFalse(body['data']['can_fix'])

    def test_an_admin_fixes_it_inline_when_no_queue(self):
        with self.provider(True), \
                mock.patch('api.views.frontline_agent._celery_broker_ready', return_value=False), \
                mock.patch('core.Frontline_agent.embedding_service.EmbeddingService', FakeService), \
                mock.patch('hr_agent.vector_store.mark_index_dirty'):
            code, body = self.call(views.document_search_status, self.admin, {'agent': 'hr_agent'})
        self.assertEqual(code, 200, body)
        self.assertEqual(body['data'], {'queued': False, 'filled': 2})

    def test_nothing_to_fix_with_when_no_provider(self):
        with self.provider(False):
            code, body = self.call(views.document_search_status, self.admin, {'agent': 'hr_agent'})
        self.assertEqual(code, 409)
        self.assertIn('Searching by meaning is off', body['message'])

    def test_an_agent_the_company_lacks_is_refused(self):
        code, _ = self.call(views.document_search_status, self.admin, {'agent': 'frontline_agent'})
        self.assertEqual(code, 400)

    def test_frontline_parts_are_counted_too(self):
        self.buy_module(self.company, 'frontline_agent')
        doc = Document.objects.create(company=self.company, title='FAQ', file_path='x', uploaded_by=self.admin_emp.user)
        DocumentChunk.objects.create(document=doc, chunk_index=0, chunk_text='Refunds take 5 days.', embedding='')
        with self.provider(True):
            code, body = self.call(views.document_search_status, self.member, {'agent': 'frontline_agent'},
                                   method='get')
        self.assertEqual((body['data']['chunks'], body['data']['chunks_without_vectors']), (1, 1))
        self.assertTrue(body['data']['can_fix'])

    def test_the_upload_status_says_how_many_parts_have_vectors(self):
        code, body = self.call(hr_views.get_hr_document_status, self.admin, method='get', document_id=self.doc.id)
        self.assertEqual(code, 200)
        self.assertEqual((body['data']['chunks_with_vectors'], body['data']['chunks_total']), (1, 3))


class EmbeddingUsageTests(HRTestCase):

    def test_tokens_count_when_the_companys_key_pays(self):
        service = EmbeddingService.__new__(EmbeddingService)
        service.company_id = self.company.id
        service._key_ctx = SimpleNamespace(mode='platform', quota_id=1, provider='openai')
        with mock.patch('core.api_key_service.record_usage') as record:
            service._record_usage(SimpleNamespace(usage=SimpleNamespace(total_tokens=120)))
        record.assert_called_once_with(service._key_ctx, 120)
        service._key_ctx = None
        with mock.patch('core.api_key_service.record_usage') as record:
            service._record_usage(SimpleNamespace(usage=SimpleNamespace(total_tokens=120)))
        record.assert_not_called()
