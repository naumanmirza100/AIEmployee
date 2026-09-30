"""Hired in Recruitment → a new starter in HR, which starts HR's onboarding.

Marking an interview Hired used to stop there; someone retyped the person
into HR, and onboarding waited until they did.
"""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from api.views.recruitment_agent import interview_hr_handoff
from core.models import Company, CompanyModulePurchase, CompanyUser
from hr_agent.models import Employee, HRWorkflow, HRWorkflowExecution
from hr_agent.workflow_templates import get_template
from project_manager_agent.models import PMNotification
from recruitment_agent.models import CVRecord, Interview, JobDescription


class HiredToHRTests(TestCase):

    def setUp(self):
        self.company = Company.objects.create(name='Acme', email='acme@test.local')
        self.recruiter = CompanyUser.objects.create(
            company=self.company, email='rae@test.local', full_name='Rae Recruiter',
            role='admin', password_hash='x', is_active=True)
        CompanyModulePurchase.objects.create(company=self.company, module_name='hr_agent',
                                             status='active', is_complimentary=True)
        job = JobDescription.objects.create(
            title='Backend engineer', description='Build things', company=self.company,
            company_user=self.recruiter, department='Engineering', type='Contract')
        cv = CVRecord.objects.create(file_name='cara.pdf', parsed_json='{}', job_description=job)
        self.interview = Interview.objects.create(
            candidate_name='Cara Candidate', candidate_email='cara@mail.test', candidate_phone='+92 300 0000000',
            job_role='Backend engineer', available_slots_json='[]', company_user=self.recruiter,
            cv_record=cv, status='COMPLETED', outcome='HIRED')
        self.manager = Employee.objects.create(company=self.company, full_name='Meg Manager',
                                               work_email='meg@acme.test', employment_status='active')
        self.start = (timezone.localdate() + timedelta(days=21)).isoformat()

    def call(self, method='get', data=None, interview=None, actor=None):
        request = getattr(APIRequestFactory(), method)('/', data or {}, format='json')
        force_authenticate(request, user=actor or self.recruiter)
        response = interview_hr_handoff(request, interview_id=(interview or self.interview).id)
        response.render()
        return response.status_code, response.data

    def hire(self, **overrides):
        form = self.call()[1]['data']['prefill']
        form.update({'start_date': self.start, 'manager_id': self.manager.id, **overrides})
        return self.call('post', form)

    # ---- the review form ----------------------------------------------------

    def test_the_form_is_filled_in_from_the_interview_and_the_job(self):
        code, body = self.call()
        self.assertEqual(code, 200)
        data = body['data']
        self.assertTrue(data['hr_available'])
        self.assertEqual(data['prefill']['full_name'], 'Cara Candidate')
        self.assertEqual(data['prefill']['work_email'], 'cara@mail.test')
        self.assertEqual(data['prefill']['job_title'], 'Backend engineer')
        self.assertEqual(data['prefill']['department'], 'Engineering')
        self.assertEqual(data['prefill']['employment_type'], 'contract')
        self.assertEqual(data['prefill']['start_date'],
                         (timezone.localdate() + timedelta(days=14)).isoformat())
        self.assertIn('Meg Manager', [m['full_name'] for m in data['managers']])

    # ---- creating the new starter -------------------------------------------

    def test_confirming_creates_a_candidate_in_hr_linked_to_the_interview(self):
        code, body = self.hire()
        self.assertEqual(code, 201, body)
        employee = Employee.objects.get(full_name='Cara Candidate')
        self.assertEqual(employee.employment_status, 'candidate')
        self.assertEqual(employee.start_date.isoformat(), self.start)
        self.assertEqual(employee.manager, self.manager)
        self.assertEqual(employee.department_obj.name, 'Engineering')
        self.assertEqual(employee.personal_email, 'cara@mail.test')
        self.interview.refresh_from_db()
        self.assertEqual(self.interview.hr_employee, employee)

    def test_it_starts_hrs_onboarding(self):
        spec = get_template('new_hire_onboarding')
        workflow = HRWorkflow.objects.create(company=self.company, name=spec['name'],
                                             trigger_conditions=spec['trigger_conditions'],
                                             steps=spec['steps'], is_active=True)
        code, body = self.hire()
        self.assertEqual(body['data']['onboarding_workflows'], ['New hire onboarding'])
        employee = Employee.objects.get(full_name='Cara Candidate')
        self.assertTrue(HRWorkflowExecution.objects.filter(workflow=workflow, employee_id=employee.id).exists())

    def test_hr_admins_are_told(self):
        hr_admin = CompanyUser.objects.create(company=self.company, email='hana@test.local',
                                              full_name='Hana HR', role='hr_agent',
                                              password_hash='x', is_active=True)
        self.hire()
        [alert] = PMNotification.objects.filter(company_user=hr_admin)
        self.assertEqual(alert.title, 'New hire from Recruitment: Cara Candidate')
        self.assertIn('Rae Recruiter', alert.message)
        self.assertEqual(alert.data['link'], '/hr/dashboard?tab=employees')

    def test_the_same_hire_cannot_be_added_twice(self):
        self.hire()
        code, body = self.hire(work_email='cara2@mail.test')
        self.assertEqual((code, body['code']), (409, 'already_in_hr'))
        self.assertEqual(Employee.objects.filter(full_name='Cara Candidate').count(), 1)

    def test_a_start_date_is_required(self):
        code, body = self.hire(start_date='')
        self.assertEqual(code, 400)
        self.assertIn('start_date', body['errors'])
        self.assertFalse(Employee.objects.filter(full_name='Cara Candidate').exists())

    # ---- someone already in HR --------------------------------------------------

    def test_an_email_already_in_hr_is_offered_for_linking_not_duplicated(self):
        known = Employee.objects.create(company=self.company, full_name='Cara C.',
                                        work_email='cara@mail.test', employment_status='offboarded')
        self.assertEqual(self.call()[1]['data']['existing']['id'], known.id)
        code, body = self.hire()
        self.assertEqual(code, 400)
        self.assertIn('work_email', body['errors'])

        code, body = self.call('post', {'link_existing': True})
        self.assertEqual(code, 200, body)
        self.interview.refresh_from_db()
        self.assertEqual(self.interview.hr_employee, known)
        self.assertEqual(Employee.objects.filter(company=self.company).count(), 2)   # Meg and Cara C.

    # ---- when it doesn't apply -------------------------------------------------

    def test_only_for_hired_candidates(self):
        self.interview.outcome = 'PASSED'
        self.interview.save()
        code, _ = self.hire()
        self.assertEqual(code, 400)

    def test_not_without_the_hr_agent(self):
        CompanyModulePurchase.objects.filter(company=self.company).delete()
        self.assertFalse(self.call()[1]['data']['hr_available'])
        code, body = self.hire()
        self.assertEqual((code, body['code']), (403, 'no_hr'))

    def test_another_recruiters_interview_is_not_found(self):
        other = CompanyUser.objects.create(company=self.company, email='ola@test.local',
                                           full_name='Ola', role='company_user',
                                           password_hash='x', is_active=True)
        code, _ = self.call(actor=other)
        self.assertEqual(code, 404)
