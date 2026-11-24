"""Recruitment roles (24 Nov 2026): recruiter, hiring manager, interviewer.

Recruitment is the company's since CO-13, and every login saw and changed everything in it. Now a recruiter (the role
of everyone not given another, and always of owners and admins) still does; a hiring manager works on the jobs they
posted or are named on; an interviewer sees their interviews and gives feedback.
"""
import json

from django.contrib.auth import get_user_model
from django.test import Client

from core.models import CompanyUserToken, UserProfile
from recruitment_agent.models import CVRecord, Interview, JobDescription, RecruitmentRole

from .test_sharing import SharingTestCase, quietly


class RolesTestCase(SharingTestCase):

    def setUp(self):
        super().setUp()
        # A second job and candidate, Ben's to manage.
        self.job2 = JobDescription.objects.create(title='Engineer', description='Build things ' * 3,
                                                  company=self.company, company_user=self.ann)
        self.cv2 = CVRecord.objects.create(file_name='dan.pdf', job_description=self.job2,
                                           parsed_json='{"name": "Dan", "email": "dan@mail.test"}')
        self.job2.hiring_managers.add(self.ben)
        self.ivy = self.login(self.company, 'ivy@test.local', 'Ivy Interviewer', 'company_user')

    def give(self, who, role):
        RecruitmentRole.objects.update_or_create(company_user=who, defaults={'role': role})

    def http(self, who):
        key = CompanyUserToken.objects.get_or_create(company_user=who)[0].key
        return Client(HTTP_AUTHORIZATION=f'Token {key}')


class WhatEachSees(RolesTestCase):

    def ids(self, view, who):
        return sorted(r['id'] for r in self.call(view, who)[1]['data'])

    def test_a_recruiter_sees_everything_as_before(self):
        from api.views import recruitment_agent as views
        self.assertEqual(self.ids(views.list_job_descriptions, self.ben), sorted([self.job.id, self.job2.id]))

    def test_a_hiring_manager_sees_only_their_jobs_and_candidates(self):
        from api.views import recruitment_agent as views
        self.give(self.ben, 'hiring_manager')
        self.assertEqual(self.ids(views.list_job_descriptions, self.ben), [self.job2.id])
        self.assertEqual(self.ids(views.list_cv_records, self.ben), [self.cv2.id])
        self.assertEqual(self.call(views.get_cv_record_detail, self.ben, record_id=self.cv.id)[0], 404)
        self.assertEqual(self.call(views.list_job_descriptions, self.ben)[1]['my_role'], 'hiring_manager')

    def test_an_interviewer_sees_only_the_interviews_they_sit_in(self):
        from api.views import recruitment_agent as views
        self.give(self.ivy, 'interviewer')
        self.assertEqual(self.ids(views.list_interviews, self.ivy), [])
        employee = get_user_model().objects.create_user('ivy', email='ivy@test.local', password='x')
        UserProfile.objects.update_or_create(user=employee, defaults={'company': self.company, 'role': 'team_member'})
        with quietly():
            self.interview.interviewers.add(employee)
        self.assertEqual(self.ids(views.list_interviews, self.ivy), [self.interview.id])
        self.assertEqual(self.ids(views.list_cv_records, self.ivy), [self.cv.id])

    def test_an_admin_is_always_a_recruiter(self):
        from recruitment_agent import sharing
        self.give(self.ann, 'interviewer')
        self.ann._recruitment_role = None
        self.assertEqual(sharing.role(self.ann), 'recruiter')


class WhatEachMayChange(RolesTestCase):

    def test_an_interviewer_gives_feedback_and_nothing_else(self):
        self.give(self.ivy, 'interviewer')
        client = self.http(self.ivy)
        refused = client.post('/api/recruitment/cv-records/bulk-update',
                              json.dumps({'ids': [self.cv.id], 'decision': 'REJECT'}), content_type='application/json')
        self.assertEqual((refused.status_code, refused.json()['code']), (403, 'recruitment_role'))
        self.assertEqual(client.post('/api/recruitment/job-descriptions/create', '{}',
                                     content_type='application/json').status_code, 403)
        allowed = client.post(f'/api/recruitment/interviews/{self.interview.id}/feedback',
                              json.dumps({'feedback': 'Good'}), content_type='application/json')
        self.assertNotEqual(allowed.json().get('code'), 'recruitment_role')     # the view decides, not the role
        self.assertEqual(client.get('/api/recruitment/interviews').status_code, 200)

    def test_a_hiring_manager_may_not_touch_workflows_or_roles(self):
        self.give(self.ben, 'hiring_manager')
        client = self.http(self.ben)
        self.assertEqual(client.post('/api/recruitment/workflows/from-template', '{}',
                                     content_type='application/json').status_code, 403)
        response = client.post(f'/api/recruitment/job-descriptions/{self.job2.id}/hiring-managers',
                               json.dumps({'company_user_ids': [self.ben.id]}), content_type='application/json')
        self.assertEqual(response.status_code, 403)

    def test_owners_and_admins_set_roles_and_an_admin_stays_a_recruiter(self):
        from api.views import recruitment_agent as views
        code, body = self.call(views.recruitment_roles, self.ann, 'post',
                               {'company_user_id': self.ben.id, 'role': 'interviewer'})
        self.assertEqual(code, 200, body)
        self.assertEqual({r['name']: r['role'] for r in body['data']['logins']}['Ben Colleague'], 'interviewer')
        self.assertEqual(self.call(views.recruitment_roles, self.ann, 'post',
                                   {'company_user_id': self.ann.id, 'role': 'interviewer'})[0], 400)
        self.assertEqual(self.call(views.recruitment_roles, self.ivy, 'post',
                                   {'company_user_id': self.ben.id, 'role': 'recruiter'})[0], 403)

    def test_a_recruiter_names_a_jobs_hiring_managers(self):
        from api.views import recruitment_agent as views
        code, body = self.call(views.job_hiring_managers, self.ann, 'post',
                               {'company_user_ids': [self.ben.id, self.ivy.id]}, job_description_id=self.job.id)
        self.assertEqual(code, 200, body)
        self.assertEqual(sorted(self.job.hiring_managers.values_list('id', flat=True)), sorted([self.ben.id, self.ivy.id]))
        self.assertEqual(self.call(views.job_hiring_managers, self.ann, 'post',
                                   {'company_user_ids': [self.rita.id]}, job_description_id=self.job.id)[0], 400)
