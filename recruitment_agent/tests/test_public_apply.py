"""What the public 'apply for this job' address accepts.

Anyone on the internet can call it. It stored the file as sent, of any type and
any size; it did not check the email or the link boxes; and it could be called
as often as anyone liked, each call emailing whatever address was typed. An
older careers address did the same with even less checking.
"""
import shutil
import tempfile
from unittest import mock

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings

from core.models import Company, CompanyUser
from recruitment_agent import public_apply
from recruitment_agent.models import CVRecord, JobApplication, JobDescription

MEDIA = tempfile.mkdtemp(prefix='public-apply-tests-')
PDF = b'%PDF-1.4\n%synthetic\n'
DOCX = b'PK\x03\x04' + b'\x00' * 40


def tearDownModule():
    shutil.rmtree(MEDIA, ignore_errors=True)


@override_settings(MEDIA_ROOT=MEDIA)
class PublicApplyTestCase(TestCase):

    def setUp(self):
        company = Company.objects.create(name='Acme', email='acme@test.local')
        owner = CompanyUser.objects.create(company=company, email='rae@acme.test', full_name='Rae', role='admin',
                                           password_hash='x', is_active=True)
        self.job = JobDescription.objects.create(title='Designer', description='Design things well ' * 3,
                                                 company=company, company_user=owner, is_active=True)
        self.n = 0

    def details(self, **changed):
        self.n += 1
        details = {'first_name': 'Cara', 'last_name': 'Khan', 'email': f'cara{self.n}@mail.test',
                   'phone': f'0300 55501{self.n:02d}', 'education': 'BA Design, Karachi University'}
        details.update(changed)
        return details

    def apply(self, cv=('cara.pdf', PDF), **changed):
        data = self.details(**changed)
        if cv is not None:
            data['cv_file'] = SimpleUploadedFile(cv[0], cv[1])
        response = Client().post(f'/api/public/jobs/{self.job.id}/apply/', data)
        return response.status_code, response.json()

    def stored(self):
        return JobApplication.objects.filter(job=self.job).count()


class TheFileTests(PublicApplyTestCase):

    def test_a_pdf_or_a_word_document_is_taken(self):
        self.assertEqual(self.apply()[0], 201)
        self.assertEqual(self.apply(cv=('cara.DOCX', DOCX))[0], 201)
        self.assertEqual(self.stored(), 2)

    def test_any_other_kind_of_file_is_refused_and_nothing_is_stored(self):
        for name in ('run.exe', 'cara.pdf.exe', 'cara.doc', 'cara.html', 'cara'):
            code, reply = self.apply(cv=(name, PDF))
            self.assertEqual((code, reply.get('code')), (400, 'BAD_CV_FILE'), name)
        self.assertEqual((self.stored(), len(mail.outbox)), (0, 0))

    def test_a_file_that_only_has_the_right_name_is_refused(self):
        code, reply = self.apply(cv=('cara.pdf', b'MZ\x90\x00 this is a program'))
        self.assertEqual((code, reply['code']), (400, 'BAD_CV_FILE'))
        self.assertIn('not a real PDF', reply['message'])
        self.assertEqual(self.apply(cv=('cara.docx', PDF))[0], 400)
        self.assertEqual(self.stored(), 0)

    def test_a_file_over_ten_megabytes_is_refused(self):
        with mock.patch.object(public_apply, 'MAX_CV_BYTES', 100):
            code, reply = self.apply(cv=('cara.pdf', PDF + b'x' * 200))
            self.assertEqual((code, reply['code']), (400, 'BAD_CV_FILE'))
            self.assertIn('larger than 10 MB', reply['message'])
            self.assertEqual(self.apply(cv=('cara.pdf', PDF + b'x' * 50))[0], 201)
        self.assertEqual(public_apply.MAX_CV_BYTES, 10 * 1024 * 1024)

    def test_an_empty_file_is_refused(self):
        self.assertEqual(self.apply(cv=('cara.pdf', b''))[0], 400)

    def test_the_file_is_checked_before_anything_is_written(self):
        with mock.patch('django.core.files.storage.FileSystemStorage._save') as write:
            self.apply(cv=('run.exe', PDF))
        write.assert_not_called()


class TheDetailsTests(PublicApplyTestCase):

    def refused(self, **changed):
        code, reply = self.apply(**changed)
        self.assertEqual((code, reply.get('code')), (400, 'BAD_DETAILS'), changed)
        return reply['message']

    def test_an_address_that_is_not_an_email_is_refused_and_not_mailed(self):
        for address in ('not-an-address', 'cara@', 'two@mail.test, other@mail.test'):
            self.assertIn('Email', self.refused(email=address))
        self.assertEqual((self.stored(), len(mail.outbox)), (0, 0))

    def test_a_link_that_is_not_a_web_address_is_refused(self):
        for box in ('linkedin_url', 'github_url'):
            for typed in ('javascript:alert(1)', 'ftp://files.example/cv', 'just words', 'data:text/html,x'):
                self.refused(**{box: typed})
        self.assertEqual(self.stored(), 0)

    def test_a_proper_link_is_kept(self):
        self.assertEqual(self.apply(linkedin_url='https://www.linkedin.com/in/cara', github_url='http://github.com/c')[0],
                         201)
        application = JobApplication.objects.get()
        self.assertEqual(application.linkedin_url, 'https://www.linkedin.com/in/cara')

    def test_over_long_values_are_refused_with_a_message_not_a_server_error(self):
        self.assertIn('First name', self.refused(first_name='A' * 101))
        self.assertIn('Phone', self.refused(phone='0' * 31))
        self.assertIn('Cover letter', self.refused(cover_letter='x' * 10001))
        self.assertIn('Education', self.refused(education='x' * 5001))
        self.assertEqual(self.stored(), 0)

    def test_an_ordinary_application_goes_through_and_is_confirmed_by_email(self):
        code, reply = self.apply(cover_letter='I would like this job.')
        self.assertEqual(code, 201, reply)
        application = JobApplication.objects.get()
        self.assertRegex(application.cv_file.name, r'cara\w*\.pdf$')        # storage may add a suffix to the name
        self.assertEqual((application.cv_file_name, len(application.access_token) > 20), ('cara.pdf', True))
        self.assertEqual(mail.outbox[0].to, [application.email])

    def test_the_same_email_or_phone_twice_is_still_told_so(self):
        self.apply(email='cara@mail.test', phone='0300 1')
        code, reply = self.apply(email='cara@mail.test', phone='0300 2')
        self.assertEqual((code, reply['code'], reply['duplicate_fields']), (400, 'ALREADY_APPLIED', ['email']))


class HowManyTests(PublicApplyTestCase):

    @override_settings(PUBLIC_APPLY_MAX_WAITING_PER_JOB=3)
    def test_a_job_takes_only_so_many_applications_waiting_to_be_screened(self):
        for _ in range(3):
            self.assertEqual(self.apply()[0], 201)
        code, reply = self.apply()
        self.assertEqual((code, reply['code']), (429, 'TOO_MANY_WAITING'))
        self.assertEqual(self.stored(), 3)

        # Screening one takes it off the count.
        CVRecord.objects.create(file_name='cara.pdf', job_description=self.job,
                                job_application=JobApplication.objects.first())
        self.assertEqual(self.apply()[0], 201)

    @override_settings(PUBLIC_APPLY_MAX_WAITING_PER_JOB=1)
    def test_one_full_job_does_not_close_another(self):
        self.apply()
        other = JobDescription.objects.create(title='Writer', description='Write things well ' * 3,
                                              company=self.job.company, company_user=self.job.company_user,
                                              is_active=True)
        response = Client().post(f'/api/public/jobs/{other.id}/apply/',
                                 dict(self.details(), cv_file=SimpleUploadedFile('c.pdf', PDF)))
        self.assertEqual(response.status_code, 201)

    def test_the_default_is_five_hundred(self):
        self.assertEqual(public_apply.waiting_cap(), 500)

    def test_one_caller_address_can_only_apply_so_often(self):
        from django.core.cache import cache
        cache.clear()
        with mock.patch.object(public_apply.PublicApplyThrottle, 'get_rate', return_value='2/hour'):
            codes = [self.apply()[0] for _ in range(3)]
        self.assertEqual(codes, [201, 201, 429])
        self.assertEqual(self.stored(), 2)
        cache.clear()

    def test_the_view_carries_the_limit_and_the_limit_has_a_rate(self):
        from django.conf import settings
        from api.views import public_jobs
        self.assertIn(public_apply.PublicApplyThrottle, public_jobs.public_job_apply.cls.throttle_classes)
        import project_manager_ai.settings as real
        self.assertEqual(real.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['public_apply'], '60/hour')
        self.assertIn('public_apply', settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'])


class TheOldCareersAddressTests(TestCase):

    def test_it_no_longer_takes_applications(self):
        response = Client().post('/api/careers/applications', {
            'email': 'x@mail.test', 'resume': SimpleUploadedFile('run.exe', b'MZ')})
        self.assertEqual(response.status_code, 404)

    def test_the_job_list_beside_it_still_answers(self):
        self.assertEqual(Client().get('/api/careers/positions').status_code, 200)
