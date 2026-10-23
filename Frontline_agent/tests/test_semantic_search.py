"""Frontline's search by meaning runs, and keeps to the documents it may use.

Its FAISS branch filtered the hits with `doc_ids`, a name that exists only in
the caller. Every question raised NameError, which was logged as "Semantic
search failed" and swallowed, so only keyword search ran: on a 245-page
prospectus Frontline answered from the wrong pages.
"""
from unittest import mock

from core.Frontline_agent import services
from core.Frontline_agent.services import KnowledgeService
from Frontline_agent import vector_store
from Frontline_agent.models import Document, DocumentChunk

from .base import FrontlineTestCase


class FakeStore:
    def __init__(self, hits):
        self.hits = hits

    def search(self, query_vec, k=25, **kwargs):
        return self.hits


DEGREE = ('Students shall qualify for the award of the undergraduate degree if they earn a minimum CGPA of 2.0 '
          'and have no compulsory subject outstanding with a W, WF, I or F grade in any semester. ') * 3
OUR_REFUNDS = ('Customers may return any product within thirty days of delivery for a full refund, provided the '
               'item is unused and in its original packaging, with the receipt. ') * 3
THEIR_REFUNDS = ('Customers may return a product within seven days of delivery for store credit only, and opened '
                 'items cannot be returned at all, whatever their condition. ') * 3


class SemanticSearchTests(FrontlineTestCase):

    def setUp(self):
        super().setUp()
        # The junk verdicts are cached by chunk id, and ids are reused between tests.
        services._CHUNK_JUNK_CACHE.clear()

    def chunk(self, company, user, text):
        document = Document.objects.create(title=f'{company.name} rules', file_path='x.pdf', company=company,
                                           uploaded_by=user, processing_status='ready')
        return document, DocumentChunk.objects.create(document=document, chunk_index=0, chunk_text=text,
                                                      page_number=214)

    def search(self, hits, allowed):
        service = KnowledgeService(company_id=self.company.id)
        with mock.patch.object(vector_store, 'FAISS_AVAILABLE', True), \
                mock.patch.object(vector_store, 'get_store', return_value=FakeStore(hits)):
            return service._semantic_search(query_embedding=[0.1, 0.2], company_id=self.company.id,
                                            allowed_doc_ids=allowed,
                                            all_chunks=DocumentChunk.objects.filter(document_id__in=allowed))

    def test_the_nearest_passage_is_found(self):
        document, ours = self.chunk(self.company, self.admin_user, DEGREE)
        found = self.search([(ours.id, 0.83)], [document.id])
        self.assertEqual([(r['chunk_id'], r['score']) for r in found], [(ours.id, 0.83)])
        self.assertIn('p.214', found[0]['title'])

    def test_a_hit_outside_the_allowed_documents_is_dropped(self):
        document, ours = self.chunk(self.company, self.admin_user, OUR_REFUNDS)
        _, theirs = self.chunk(self.rival, self.rival_user, THEIR_REFUNDS)
        found = self.search([(theirs.id, 0.95), (ours.id, 0.71)], [document.id])
        self.assertEqual([r['chunk_id'] for r in found], [ours.id])
