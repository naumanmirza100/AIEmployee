"""Process CVs in the background (24 Nov 2026, the test report's Recruitment 5).

Three CVs took 7½ minutes on screen, all inside one request, while the live server ends a request after 60 seconds.
The upload is answered at once (202) with a batch; the work runs on the Celery worker (25 Nov 2026; on its own thread
when the worker cannot be reached); the screen follows the batch.
"""
from datetime import timedelta
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from api.views import recruitment_agent as views
from core.models import Company, CompanyUser
from recruitment_agent import cv_batches
from recruitment_agent.models import CVBatch, CVRecord

from .test_invitations_go_by_themselves import screening
from . import test_uploads as _uploads     # the module: its class would run here again
from .test_uploads import MEDIA, reader


class Instant:
    """threading.Thread that runs its target at once."""

    def __init__(self, target=None, name=None, daemon=None, **kwargs):
        self.target = target

    def start(self):
        self.target()


@override_settings(MEDIA_ROOT=MEDIA, CELERY_TASK_ALWAYS_EAGER=False)
class InTheBackground(_uploads.UploadTests):

    def post(self, names, people, worker=None, seen=None):
        """Upload; the worker (by default, the task run at once) gets the batch when the request commits. `seen` is
        called with the batch's folder before the worker reads it."""
        agents, _ = screening(['HOLD'] * len(people), [])
        agents['cv_agent'] = mock.Mock(parse_file=reader(people))
        files = [SimpleUploadedFile(n, b'%PDF-1.4 text', content_type='application/pdf') for n in names]
        request = APIRequestFactory().post('/x', {'files': files, 'job_description_id': str(self.job.id)},
                                           format='multipart')
        force_authenticate(request, user=self.rae)
        with mock.patch.object(views, '_make_agents', return_value=agents), \
                mock.patch('recruitment_agent.tasks.process_cv_batch.delay',
                           side_effect=worker or cv_batches.process) as self.delay, \
                mock.patch('recruitment_agent.cv_batches.threading.Thread', Instant), \
                mock.patch('time.sleep'), \
                mock.patch('core.notification_utils.notify_company_users') as told, \
                mock.patch('recruitment_agent.cv_batches.connection'):
            with self.captureOnCommitCallbacks() as on_commit:
                response = views.process_cvs(request)
            if seen and response.status_code == 202:
                seen(cv_batches.batch_folder(response.data['batch']['id']))
            for callback in on_commit:
                callback()
        return response, told

    def read(self, batch_id, actor=None):
        request = APIRequestFactory().get('/x')
        force_authenticate(request, user=actor or self.rae)
        response = views.cv_batch_detail(request, batch_id=batch_id)
        return response.status_code, response.data

    def test_the_upload_is_answered_at_once_and_the_batch_ends_with_the_results(self):
        response, told = self.post(['cara.pdf', 'old.doc'], [{'name': 'Cara Khan', 'email': 'cara@mail.test'}])
        self.assertEqual(response.status_code, 202, response.data)
        batch_id = response.data['batch']['id']
        code, body = self.read(batch_id)
        self.assertEqual((code, body['data']['status']), (200, 'done'))
        states = {f['name']: f['state'] for f in body['data']['files']}
        self.assertEqual(states, {'cara.pdf': 'done', 'old.doc': 'failed'})
        result = body['data']['result']
        self.assertEqual((result['total'], result['failed_files'][0]['file_name']), (1, 'old.doc'))
        self.assertEqual(CVRecord.objects.count(), 1)
        self.assertIn('1 CV(s) scored for Designer', told.call_args.kwargs['title'])    # the bell, when done

    def test_the_worker_reads_the_files_from_the_shared_media_folder_and_clears_it(self):
        waiting = []
        response, _ = self.post(['cara.pdf'], [{'name': 'Cara Khan', 'email': 'cara@mail.test'}],
                                seen=lambda folder: waiting.extend(p.name for p in folder.iterdir()))
        batch_id = response.data['batch']['id']
        self.assertEqual(waiting, ['0.pdf'])                       # on the volume the worker sees, until it is read
        self.delay.assert_called_once_with(batch_id)
        self.assertFalse(cv_batches.batch_folder(batch_id).exists())
        self.assertNotIn('paths', str(response.data))              # the server's paths are not handed out
        self.assertEqual(self.read(batch_id)[1]['data']['status'], 'done')

    def test_when_the_worker_cannot_be_reached_it_runs_here_as_before(self):
        response, told = self.post(['cara.pdf'], [{'name': 'Cara Khan', 'email': 'cara@mail.test'}],
                                   worker=ConnectionError('redis is down'))
        self.assertEqual(self.read(response.data['batch']['id'])[1]['data']['status'], 'done')
        self.assertEqual(CVRecord.objects.count(), 1)
        told.assert_called_once()

    def test_the_same_task_delivered_twice_reads_the_cvs_once(self):
        response, _ = self.post(['cara.pdf'], [{'name': 'Cara Khan', 'email': 'cara@mail.test'}])
        self.assertIsNone(cv_batches.process(response.data['batch']['id']))
        self.assertEqual(CVRecord.objects.count(), 1)

    def test_a_run_that_stopped_with_the_server_is_said_to_have_failed(self):
        batch = CVBatch.objects.create(company=self.company, company_user=self.rae, job_description=self.job,
                                       status='running', files=[{'name': 'a.pdf', 'state': 'reading'}])
        CVBatch.objects.filter(pk=batch.pk).update(created_at=batch.created_at - timedelta(hours=2))
        folder = cv_batches.batch_folder(batch.id)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / '0.pdf').write_bytes(b'%PDF')
        code, body = self.read(batch.id)
        self.assertEqual(body['data']['status'], 'failed')
        self.assertIn('server restarted', body['data']['error'])
        self.assertFalse(folder.exists())                          # its files are not left behind

    def test_another_company_cannot_read_it(self):
        batch = CVBatch.objects.create(company=self.company, company_user=self.rae, job_description=self.job)
        rival = Company.objects.create(name='Rival', email='rival@test.local')
        other = CompanyUser.objects.create(company=rival, email='o@rival.test', full_name='O', role='admin',
                                           password_hash='x', is_active=True)
        self.assertEqual(self.read(batch.id, other)[0], 404)


# The upload tests themselves are not run a second time from here.
for _name in [n for n in dir(_uploads.UploadTests) if n.startswith('test_')]:
    setattr(InTheBackground, _name, None)
