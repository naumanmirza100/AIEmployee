"""A job stays with the company that made it.

'Update job' let the caller change which company a job belongs to. Create fixed
the company to the caller's own; update did not. The job then showed among the
other company's jobs, was advertised under that company's name on the public
careers page, and its applications landed in that company's list.
"""
from unittest import mock

from api.serializers.career import JobDescriptionSerializer
from api.views import company_jobs
from recruitment_agent.models import JobDescription
from recruitment_agent.tests.test_other_companies import TwoCompaniesTestCase


class JobStaysWithItsCompanyTests(TwoCompaniesTestCase):

    def update(self, actor, data):
        with mock.patch.object(company_jobs, '_company_has_recruitment_agent', return_value=False):
            return self.call(company_jobs.update_company_job, actor, data, method='put', id=self.job.id)

    def test_an_update_cannot_move_a_job_to_another_company(self):
        code, reply = self.update(self.ann, {'title': 'Senior Designer', 'company': self.rival.id})
        self.assertEqual(code, 200, reply)
        job = JobDescription.objects.get(pk=self.job.pk)
        self.assertEqual((job.title, job.company_id), ('Senior Designer', self.acme.id))
        self.assertEqual(reply['data']['company'], self.acme.id)

    def test_a_new_job_is_filed_under_the_callers_company_whatever_is_sent(self):
        body = {'title': 'Engineer', 'description': 'Builds the things we sell to people ' * 2,
                'company': self.acme.id, 'parse_keywords': False}
        code, reply = self.call(company_jobs.create_company_job, self.rita, body)
        self.assertEqual(code, 201, reply)
        job = JobDescription.objects.get(pk=reply['data']['id'])
        self.assertEqual((job.company_id, job.company_user_id), (self.rival.id, self.rita.id))

    def test_the_serializer_shows_the_company_but_does_not_take_it(self):
        self.assertEqual(JobDescriptionSerializer(self.job).data['company'], self.acme.id)
        serializer = JobDescriptionSerializer(self.job, data={'company': self.rival.id}, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertNotIn('company', serializer.validated_data)
