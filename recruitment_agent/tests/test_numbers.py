"""Recruitment's numbers are worked out from all the data, the right way.

CO-104  rank was the place in one upload or the order of applying; the best candidate was "rank 1" of the wrong list
CO-105  the job pickers got only the nine newest jobs
CO-106  the dashboard's cards stopped at 9 jobs and 10 interviews
CO-107  'Conversion Rate' fell to 0% as interviews were held; 'Interviewed' counted unanswered invitations
"""
import json

from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from api.views import recruitment_agent as views
from core.models import Company, CompanyModulePurchase, CompanyUser
from recruitment_agent.models import CVRecord, Interview, JobDescription
from recruitment_agent.ranking import ranks_for


class NumbersTests(TestCase):

    def setUp(self):
        self.company = Company.objects.create(name='Acme', email='acme@test.local')
        CompanyModulePurchase.objects.create(company=self.company, module_name='recruitment_agent',
                                             status='active', is_complimentary=True)
        self.rae = CompanyUser.objects.create(company=self.company, email='rae@acme.test', full_name='Rae Recruiter',
                                              role='admin', password_hash='x', is_active=True)
        self.job = self.make_job('Designer')

    def make_job(self, title, active=True):
        return JobDescription.objects.create(title=title, description=f'{title} wanted.', company=self.company,
                                             company_user=self.rae, is_active=active)

    def cv(self, name, score, decision='INTERVIEW', job=None, confidence=50):
        return CVRecord.objects.create(file_name=f'{name}.pdf', job_description=job or self.job, role_fit_score=score,
                                       qualification_decision=decision, qualification_confidence=confidence,
                                       rank=1, parsed_json=json.dumps({'name': name, 'email': f'{name}@mail.test'}))

    def get(self, view, **params):
        request = APIRequestFactory().get('/x', params)
        force_authenticate(request, user=self.rae)
        response = view(request)
        return response.data

    def test_rank_is_the_place_by_score_within_the_job(self):
        weak, strong, middle = self.cv('weak', 40), self.cv('strong', 90), self.cv('middle', 70)
        other = self.cv('other', 10, job=self.make_job('Writer'))
        self.assertEqual(ranks_for([weak, strong, middle, other]),
                         {strong.id: 1, middle.id: 2, weak.id: 3, other.id: 1})
        listed = self.get(views.list_cv_records, job_id=self.job.id)['data']
        self.assertEqual([(r['file_name'], r['rank']) for r in listed if r['file_name'] != 'other.pdf'],
                         [('strong.pdf', 1), ('middle.pdf', 2), ('weak.pdf', 3)])

    def test_the_pickers_get_every_job(self):
        for n in range(12):
            self.make_job(f'Job {n}')
        body = self.get(views.list_job_descriptions, picker='1')
        self.assertEqual(len(body['data']), 13)
        self.assertNotIn('description', body['data'][0])
        self.assertEqual(len(self.get(views.list_job_descriptions)['data']), 9)        # the Jobs screen pages

    def test_the_dashboard_counts_everything(self):
        for n in range(11):
            self.make_job(f'Job {n}')
        for n in range(12):
            Interview.objects.create(candidate_name=f'P{n}', candidate_email=f'p{n}@mail.test', job_role='Designer',
                                     cv_record=self.cv(f'p{n}', 60), company_user=self.rae, status='PENDING')
        overview = self.get(views.recruitment_analytics, overview='1')['data']['overview']
        self.assertEqual(overview, {'total_cvs': 12, 'total_interviews': 12, 'active_jobs': 12,
                                    'pending_interviews': 12})

    def test_conversion_counts_held_interviews_and_each_candidate_once(self):
        held = self.cv('held', 80)
        Interview.objects.create(candidate_name='Held', candidate_email='held@mail.test', job_role='Designer',
                                 cv_record=held, company_user=self.rae, status='COMPLETED')
        Interview.objects.create(candidate_name='Held', candidate_email='held@mail.test', job_role='Designer',
                                 cv_record=held, company_user=self.rae, status='SCHEDULED')
        Interview.objects.create(candidate_name='Quiet', candidate_email='quiet@mail.test', job_role='Designer',
                                 cv_record=self.cv('quiet', 70), company_user=self.rae, status='PENDING')
        self.cv('no', 20, decision='REJECT')
        self.cv('maybe', 50, decision='HOLD')
        data = self.get(views.recruitment_analytics)['data']
        self.assertEqual(data['overview']['conversion_rate'], 25.0)        # 1 of 4 screened
        interviewed = next(s for s in data['funnel'] if s['stage'] == 'Interviewed')
        self.assertEqual(interviewed['count'], 1)
