"""Process CVs in the background (24 Nov 2026, the test report's Recruitment 5).

Three CVs took 7½ minutes on screen, all inside one request, while the live server ends a request after 60 seconds.
The upload is answered at once (202) with a batch; the work runs on its own thread; the screen follows the batch.
"""
from datetime import timedelta
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from api.views import recruitment_agent as views
from core.models import Company, CompanyUser
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

    def post(self, names, people):
        agents, _ = screening(['HOLD'] * len(people), [])
        agents['cv_agent'] = mock.Mock(parse_file=reader(people))
        files = [SimpleUploadedFile(n, b'%PDF-1.4 text', content_type='application/pdf') for n in names]
        request = APIRequestFactory().post('/x', {'files': files, 'job_description_id': str(self.job.id)},
                                           format='multipart')
        force_authenticate(request, user=self.rae)
        with mock.patch.object(views, '_make_agents', return_value=agents), \
                mock.patch('recruitment_agent.cv_batches.threading.Thread', Instant), \
                mock.patch('time.sleep'), \
                mock.patch('core.notification_utils.notify_company_users') as told, \
                mock.patch('recruitment_agent.cv_batches.connection'), \
                self.captureOnCommitCallbacks(execute=True):
            response = views.process_cvs(request)
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

    def test_a_run_that_stopped_with_the_server_is_said_to_have_failed(self):
        batch = CVBatch.objects.create(company=self.company, company_user=self.rae, job_description=self.job,
                                       status='running', files=[{'name': 'a.pdf', 'state': 'reading'}])
        CVBatch.objects.filter(pk=batch.pk).update(created_at=batch.created_at - timedelta(hours=2))
        code, body = self.read(batch.id)
        self.assertEqual(body['data']['status'], 'failed')
        self.assertIn('server restarted', body['data']['error'])

    def test_another_company_cannot_read_it(self):
        batch = CVBatch.objects.create(company=self.company, company_user=self.rae, job_description=self.job)
        rival = Company.objects.create(name='Rival', email='rival@test.local')
        other = CompanyUser.objects.create(company=rival, email='o@rival.test', full_name='O', role='admin',
                                           password_hash='x', is_active=True)
        self.assertEqual(self.read(batch.id, other)[0], 404)


# The upload tests themselves are not run a second time from here.
for _name in [n for n in dir(_uploads.UploadTests) if n.startswith('test_')]:
    setattr(InTheBackground, _name, None)
