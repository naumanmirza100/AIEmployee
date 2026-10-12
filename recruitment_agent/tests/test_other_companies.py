"""One company's login cannot write on another company's candidate.

'qualify' and 'enrich' take CV data from the request. Each screening step looked
inside that data for a candidate number and saved its result onto that candidate
without asking whose it was, so a login at one company could set the decision,
score and reasoning on any other company's candidate.
"""
import json
from unittest import mock

from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from api.views import recruitment_agent as views
from core.models import Company, CompanyModulePurchase, CompanyUser
from recruitment_agent.models import CVRecord, JobDescription

PARSED = {'name': 'Mallory', 'email': 'm@mail.test', 'skills': ['python', 'django'],
          'experience': [{'title': 'Engineer', 'company': 'X', 'start_date': '2019', 'end_date': '2024'}]}
INSIGHTS = {'total_experience_years': 5, 'role_fit_score': 99, 'summary': 'Strong'}


def with_a_key():
    """Screening needs the company to have an AI key; these two steps make no AI call."""
    return mock.patch('core.api_key_service.resolve_for_call',
                      return_value=mock.Mock(api_key='test-key', mode='platform'))


class TwoCompaniesTestCase(TestCase):

    def setUp(self):
        self.acme = Company.objects.create(name='Acme', email='acme@test.local')
        self.rival = Company.objects.create(name='Rival', email='rival@test.local')
        for company in (self.acme, self.rival):
            CompanyModulePurchase.objects.create(company=company, module_name='recruitment_agent',
                                                 status='active', is_complimentary=True)
        self.ann = self.login(self.acme, 'ann@acme.test', 'Ann')
        self.rita = self.login(self.rival, 'rita@rival.test', 'Rita')
        self.job = JobDescription.objects.create(title='Designer', description='Design things well ' * 3,
                                                 company=self.acme, company_user=self.ann)
        self.cv = CVRecord.objects.create(
            file_name='cara.pdf', job_description=self.job,
            parsed_json=json.dumps({'name': 'Cara', 'skills': ['figma']}),
            insights_json=json.dumps({'total_experience_years': 3}),
            qualification_decision='HOLD', qualification_confidence=50, qualification_priority='MEDIUM',
            qualification_json=json.dumps({'decision': 'HOLD', 'reasoning': 'Acme wrote this'}),
            enriched_json=json.dumps({'primary_role': 'Designer'}))

    def login(self, company, email, name):
        return CompanyUser.objects.create(company=company, email=email, full_name=name, role='admin',
                                          password_hash='x', is_active=True)

    def call(self, view, actor, data, method='post', **kwargs):
        request = getattr(APIRequestFactory(), method)('/', data, format='json')
        force_authenticate(request, user=actor)
        with with_a_key():
            response = view(request, **kwargs)
        if hasattr(response, 'render'):
            response.render()
        return response.status_code, getattr(response, 'data', None)

    def stored(self):
        cv = CVRecord.objects.get(pk=self.cv.pk)
        return (cv.qualification_decision, cv.qualification_confidence, cv.qualification_priority,
                cv.qualification_json, cv.enriched_json)


class ScreeningResultTests(TwoCompaniesTestCase):

    def test_a_candidate_number_in_the_request_does_not_change_that_candidate(self):
        before = self.stored()
        for where in ('parsed_json', 'insights_json'):
            body = {'parsed_json': dict(PARSED), 'insights_json': dict(INSIGHTS), 'job_keywords': ['python']}
            body[where]['record_id'] = self.cv.id
            code, reply = self.call(views.api_cv_qualify, self.rita, body)
            self.assertEqual(code, 200, reply)
            self.assertIn('decision', reply['qualification'])
            self.assertEqual(self.stored(), before, where)

            code, reply = self.call(views.api_cv_enrich, self.rita, body)
            self.assertEqual(code, 200, reply)
            self.assertEqual(self.stored(), before, where)

    def test_not_even_on_the_callers_own_candidate(self):
        # These two addresses answer a question; they are not a way to save.
        before = self.stored()
        body = {'parsed_json': dict(PARSED, record_id=self.cv.id), 'insights_json': dict(INSIGHTS)}
        self.assertEqual(self.call(views.api_cv_qualify, self.ann, body)[0], 200)
        self.assertEqual(self.call(views.api_cv_enrich, self.ann, body)[0], 200)
        self.assertEqual(self.stored(), before)

    def test_another_companys_candidate_cannot_be_named_either(self):
        code, _ = self.call(views.api_cv_qualify, self.rita, {'cv_record_id': self.cv.id})
        self.assertEqual(code, 404)
        code, _ = self.call(views.api_cv_enrich, self.rita, {'cv_record_id': self.cv.id})
        self.assertEqual(code, 404)

    def test_the_steps_handed_out_have_no_way_to_save(self):
        with with_a_key():
            agents = views._make_agents(self.acme)
        self.assertIsNone(agents['enrich_agent'].sql_repository)
        self.assertIsNone(agents['qualify_agent'].sql_repository)

    def test_sent_data_loses_its_candidate_number_and_nothing_else(self):
        self.assertEqual(views._own_data_only({'record_id': 7, 'name': 'A'}), {'name': 'A'})
        self.assertEqual(views._own_data_only({'name': 'A'}), {'name': 'A'})
        self.assertEqual(views._own_data_only('not a dict'), 'not a dict')
        sent = {'record_id': 7}
        views._own_data_only(sent)
        self.assertEqual(sent, {'record_id': 7})        # the caller's own dict is left alone
