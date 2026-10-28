"""Recruitment's Workflow / SOP Runner (docx item 7): steps that run by themselves on hiring events."""
import json
from unittest import mock

from django.core import mail
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from api.views import recruitment_workflows as views
from core.models import Company, CompanyModulePurchase, CompanyUser
from project_manager_agent.models import PMNotification
from recruitment_agent import workflows
from recruitment_agent.models import (CVRecord, Interview, JobDescription, RecruitmentWorkflow,
                                      RecruitmentWorkflowRun)


class WorkflowTests(TestCase):

    def setUp(self):
        self.company = Company.objects.create(name='Margalla Software', email='hello@margalla.test')
        CompanyModulePurchase.objects.create(company=self.company, module_name='recruitment_agent',
                                             status='active', is_complimentary=True)
        self.owner = self.login('sana', 'Sana Owner', 'owner')
        self.member = self.login('omar', 'Omar Member', 'company_user')
        self.job = JobDescription.objects.create(title='Backend Engineer', description='Django.', company=self.company,
                                                 company_user=self.owner)
        self.cv = CVRecord.objects.create(file_name='cara.pdf', job_description=self.job, qualification_decision='INTERVIEW',
                                          role_fit_score=86,
                                          parsed_json=json.dumps({'name': 'Cara Khan', 'email': 'cara@mail.test'}))

    def login(self, name, full_name, role):
        return CompanyUser.objects.create(company=self.company, email=f'{name}@margalla.test', full_name=full_name,
                                          role=role, password_hash='x', is_active=True)

    def call(self, view, actor, method='get', data=None, **kwargs):
        request = getattr(APIRequestFactory(), method)('/x', data or {}, format='json')
        force_authenticate(request, user=actor)
        return view(request, **kwargs)

    def make(self, key):
        response = self.call(views.workflow_from_template, self.owner, 'post', {'template_key': key})
        self.assertEqual(response.status_code, 201, response.data)
        return RecruitmentWorkflow.objects.get(pk=response.data['data']['id'])

    def test_a_strong_candidate_reaches_the_admins_once(self):
        self.make('strong_candidate')
        workflows.run_for_event('candidate_screened', cv_record=self.cv, detail='INTERVIEW')
        workflows.run_for_event('candidate_screened', cv_record=self.cv, detail='INTERVIEW')   # the same event again
        alerts = PMNotification.objects.filter(company_user=self.owner)
        self.assertEqual([a.title for a in alerts], ['Strong candidate: Cara Khan'])
        self.assertEqual(RecruitmentWorkflowRun.objects.get().status, 'completed')

    def test_a_weak_candidate_takes_the_other_branch(self):
        self.make('strong_candidate')
        self.cv.role_fit_score = 40
        self.cv.save()
        workflows.run_for_event('candidate_screened', cv_record=self.cv, detail='HOLD')
        self.assertFalse(PMNotification.objects.exists())

    def test_the_thank_you_goes_in_the_companys_name(self):
        self.make('thank_applicant')
        workflows.run_for_event('application_received', cv_record=self.cv)
        [sent] = mail.outbox
        self.assertEqual(sent.to, ['cara@mail.test'])
        self.assertIn('Margalla Software', sent.subject)
        self.assertIn('Margalla Software via Pay Per Project', sent.from_email)

    def test_a_hire_reaches_hr_admins(self):
        self.make('hired_to_hr')
        hr = self.login('hina', 'Hina HR', 'hr_agent')
        interview = Interview.objects.create(candidate_name='Cara Khan', candidate_email='cara@mail.test',
                                             job_role='Backend Engineer', cv_record=self.cv, available_slots_json='[]',
                                             company_user=self.owner, status='COMPLETED', outcome='HIRED')
        workflows.run_for_event('interview_outcome', interview=interview, detail='HIRED')
        self.assertTrue(PMNotification.objects.filter(company_user=hr, title='New hire: Cara Khan').exists())

    def test_a_failing_step_tells_the_recruiter_and_never_raises(self):
        RecruitmentWorkflow.objects.create(company=self.company, name='Email nobody', trigger_event='candidate_screened',
                                           steps=[{'type': 'send_email', 'to': 'nobody', 'subject': 's', 'body': 'b'}])
        workflows.run_for_event('candidate_screened', cv_record=self.cv, detail='X')
        self.assertEqual(RecruitmentWorkflowRun.objects.get().status, 'failed')
        self.assertTrue(PMNotification.objects.filter(company_user=self.owner, title__contains='stopped').exists())

    def test_only_the_owner_or_an_admin_sets_them_up_and_steps_are_checked(self):
        response = self.call(views.workflow_from_template, self.member, 'post', {'template_key': 'thank_applicant'})
        self.assertEqual(response.status_code, 403)
        self.assertIn("Only the company's owner or an admin", response.data['message'])
        response = self.call(views.workflow_list, self.owner, 'post', {
            'name': 'Wait then email', 'trigger_event': 'interview_booked',
            'steps': [{'type': 'wait', 'seconds': 60}]})
        self.assertEqual(response.status_code, 400)
        self.assertIn('waiting steps are not available', response.data['message'])

    def test_a_test_run_sends_nothing(self):
        wf = self.make('thank_applicant')
        response = self.call(views.workflow_test, self.member, 'post', {}, workflow_id=wf.id)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['data']['candidate'], 'Cara Khan')
        self.assertTrue(all(step.get('simulated') for step in response.data['data']['results']['results']))
        self.assertEqual(mail.outbox, [])
