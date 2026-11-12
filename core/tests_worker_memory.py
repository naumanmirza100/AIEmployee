"""A worker process that ends a task above a memory ceiling is replaced (CELERY_WORKER_MAX_MEMORY_PER_CHILD).

Live on 12 Nov 2026, after reading a 9.3 MB PDF one Celery process held 1.9 GB against about 400 MB at rest. Python
keeps what a task took, four processes run on a 7.6 GB server, and the server had run out of memory that morning.
"""
from django.conf import settings
from django.test import SimpleTestCase


class WorkerMemoryCeilingTests(SimpleTestCase):

    def test_the_ceiling_reaches_celery(self):
        from project_manager_ai.celery import app
        self.assertEqual(app.conf.worker_max_memory_per_child, settings.CELERY_WORKER_MAX_MEMORY_PER_CHILD)

    def test_it_sits_above_a_process_at_rest_and_well_below_a_grown_one(self):
        # KiB: about 400,000 at rest, 1,946,372 after the PDF.
        self.assertGreaterEqual(settings.CELERY_WORKER_MAX_MEMORY_PER_CHILD, 450_000)
        self.assertLessEqual(settings.CELERY_WORKER_MAX_MEMORY_PER_CHILD, 1_000_000)
