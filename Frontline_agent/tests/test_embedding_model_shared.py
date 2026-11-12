"""The local embedding model is loaded once per process and shared (12 Nov 2026).

Every EmbeddingService used to load its own copy of the sentence-transformers model, about 0.5 GB with torch, and a
service is made per request and per test. In the server image, where the model really loads, the test suite grew past
6 GB and was killed. sentence_transformers is a fake here, so the test runs on any machine."""
import sys
import types
from unittest import mock

from django.test import SimpleTestCase, override_settings

from core.Frontline_agent import embedding_service


class FakeModel:
    made = 0

    def __init__(self, name, device='cpu'):
        FakeModel.made += 1
        self.name, self.device = name, device


@override_settings(EMBEDDING_PROVIDER='local', LOCAL_EMBEDDING_MODEL='BAAI/bge-small-en-v1.5', LOCAL_EMBEDDING_DEVICE='cpu')
class TheLocalModelIsShared(SimpleTestCase):

    def setUp(self):
        FakeModel.made = 0
        fake = types.ModuleType('sentence_transformers')
        fake.SentenceTransformer = FakeModel
        for patcher in (mock.patch.dict(sys.modules, {'sentence_transformers': fake}),
                        mock.patch.object(embedding_service, '_LOCAL_IMPORT_FAILED', None),
                        mock.patch.object(embedding_service, '_LOCAL_MODELS', {})):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_many_services_load_the_model_once(self):
        services = [embedding_service.EmbeddingService(company_id=n) for n in range(5)]
        self.assertEqual(FakeModel.made, 1)
        self.assertEqual({s.provider for s in services}, {'local'})
        self.assertTrue(all(s.client is services[0].client for s in services))

    def test_another_model_or_device_is_its_own_copy(self):
        embedding_service.EmbeddingService()
        with override_settings(LOCAL_EMBEDDING_DEVICE='cuda'):
            embedding_service.EmbeddingService()
        self.assertEqual(FakeModel.made, 2)
