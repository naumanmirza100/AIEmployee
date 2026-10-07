"""A new hire gets a login on the HR record they already have, and HR hears if
Recruitment changes its mind.

Recruitment hands a new starter to HR with the address they applied from. A
login made later at a company address matched no HR record, so HR made a
second record for the same person and started their onboarding again. HR could
not edit the address, link the login or merge the two. And changing an
interview's outcome away from Hired told HR nothing.
"""
from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory, force_authenticate

from api.views import company_users
from api.views.recruitment_agent import update_interview
from core.models import CompanyModulePurchase, CompanyUser, UserProfile
from hr_agent.models import Employee, HRWorkflow, HRWorkflowExecution
from project_manager_agent.models import PMNotification

from . import test_hr_handoff as base

User = get_user_model()
PASSWORD = 'Made-up-pass1!'            # not a real credential


class NewHireLoginTests(base.HiredToHRTests):
    # Only this file's tests: the parent's run where they are defined.
    locals().update({name: None for name in dir(base.HiredToHRTests) if name.startswith('test_')})

    def setUp(self):
        super().setUp()
        HRWorkflow.objects.create(company=self.company, name='Onboard', is_active=True,
                                  trigger_conditions={'on': 'employee_hired'},
                                  steps=[{'type': 'update_employee', 'fields': {'job_title': 'New starter'}}])
        code, body = self.hire()
        assert code == 201, body
        self.cara = Employee.objects.get(full_name='Cara Candidate')
        self.member = CompanyUser.objects.create(company=self.company, email='mo@test.local', full_name='Mo Member',
                                                 role='company_user', password_hash='x', is_active=True)

    def create_login(self, actor=None, **data):
        payload = {'email': 'cara@acme.test', 'password': PASSWORD, 'role': 'team_member', **data}
        if 'employee_id' not in data:
            payload['employee_id'] = self.cara.id
        request = APIRequestFactory().post('/', payload, format='json')
        force_authenticate(request, user=actor or self.recruiter)
        response = company_users.create_user(request)
        response.render()
        return response.status_code, response.data

    def records(self):
        return Employee.objects.filter(company=self.company).count()

    # ---- one person, one record ---------------------------------------------------

    def test_a_login_made_from_the_record_belongs_to_that_record(self):
        before, runs = self.records(), HRWorkflowExecution.objects.count()
        code, body = self.create_login()
        self.assertEqual(code, 201, body)
        self.cara.refresh_from_db()
        login = User.objects.get(email='cara@acme.test')
        self.assertEqual((self.cara.user_id, self.cara.work_email, self.cara.personal_email),
                         (login.id, 'cara@acme.test', 'cara@mail.test'))
        self.assertEqual(body['data']['employee_id'], self.cara.id)
        self.assertEqual(self.records(), before)                              # still one Cara
        self.assertEqual(HRWorkflowExecution.objects.count(), runs)           # and onboarding did not start again
        profile = UserProfile.objects.get(user=login)
        self.assertEqual((profile.company_id, profile.created_by_company_user_id, profile.phone_number),
                         (self.company.id, self.recruiter.id, '+92 300 0000000'))
        self.assertEqual((login.first_name, login.last_name), ('Cara', 'Candidate'))
        self.assertTrue(login.check_password(PASSWORD))

    def test_the_name_and_number_hr_holds_are_used_as_they_are(self):
        Employee.objects.filter(pk=self.cara.pk).update(full_name='Zoë O’Neil 3rd', phone='')
        code, body = self.create_login()
        self.assertEqual(code, 201, body)                                     # a name the Add User form would refuse
        self.assertEqual(User.objects.get(email='cara@acme.test').first_name, 'Zoë')
        self.assertEqual(self.records(), 2)                                   # Cara and her manager

    def test_a_login_at_the_address_the_record_already_has_is_fine(self):
        code, body = self.create_login(email='cara@mail.test')
        self.assertEqual(code, 201, body)
        self.cara.refresh_from_db()
        self.assertEqual((self.cara.work_email, self.cara.user.email), ('cara@mail.test', 'cara@mail.test'))

    def test_it_is_made_in_the_name_hr_has_whatever_is_sent(self):
        self.create_login(fullName='Someone Else')
        login = User.objects.get(email='cara@acme.test')
        self.assertEqual(login.get_full_name(), 'Cara Candidate')

    def test_a_number_typed_in_is_still_checked(self):
        code, body = self.create_login(phoneNumber='12')
        self.assertEqual(code, 400)
        self.assertIn('valid phone number', body['message'])
        self.assertFalse(User.objects.filter(email='cara@acme.test').exists())

    # ---- what is refused ----------------------------------------------------------------

    def refused(self, expected, text, **kwargs):
        code, body = self.create_login(**kwargs)
        self.assertEqual(code, expected, body)
        self.assertIn(text, body['message'])
        self.assertFalse(User.objects.filter(email='cara@acme.test').exists())
        self.cara.refresh_from_db()
        self.assertEqual((self.cara.user_id, self.cara.work_email), (None, 'cara@mail.test'))

    def test_only_an_hr_admin_can(self):
        self.refused(403, 'Only an HR admin', actor=self.member)

    def test_not_for_a_record_that_is_not_theirs_or_is_not_there(self):
        from core.models import Company
        rival = Company.objects.create(name='Rival', email='rival@test.local')
        theirs = Employee.objects.create(company=rival, full_name='Their Hire', work_email='t@rival.test',
                                         employment_status='candidate')
        self.refused(404, 'HR record not found', employee_id=theirs.id)
        self.refused(404, 'HR record not found', employee_id='abc')
        theirs.refresh_from_db()
        self.assertIsNone(theirs.user_id)

    def test_not_for_someone_who_has_left(self):
        Employee.objects.filter(pk=self.cara.pk).update(employment_status='offboarded')
        self.refused(400, 'has left')

    def test_not_at_an_address_another_record_already_has(self):
        self.refused(400, 'Another HR record already uses meg@acme.test: Meg Manager', email='meg@acme.test')

    def test_not_twice(self):
        self.assertEqual(self.create_login()[0], 201)
        code, body = self.create_login(email='cara2@acme.test')
        self.assertEqual(code, 400)
        self.assertIn('already has a login', body['message'])
        self.assertFalse(User.objects.filter(email='cara2@acme.test').exists())

    def test_adding_a_user_the_old_way_is_unchanged(self):
        code, body = self.create_login(employee_id='', email='new@acme.test', fullName='New Person')
        self.assertEqual((code, body['message']), (400, 'Phone number is required'))
        code, body = self.create_login(employee_id='', email='new@acme.test', fullName='New Person 2',
                                       phoneNumber='+44 20 7946 0000')
        self.assertEqual((code, body['message']), (400, 'Full name must not contain numbers.'))
        code, body = self.create_login(actor=self.member, employee_id='', email='new@acme.test',
                                       fullName='New Person', phoneNumber='+44 20 7946 0000')
        self.assertEqual((code, body['data']['employee_id']), (201, None))    # any login may, as before

    # ---- HR hears when Recruitment changes its mind ------------------------------------

    def change(self, **data):
        request = APIRequestFactory().patch('/', data, format='json')
        force_authenticate(request, user=self.recruiter)
        response = update_interview(request, interview_id=self.interview.id)
        response.render()
        return response.status_code

    def told(self):
        return list(PMNotification.objects.filter(title__startswith='No longer hired').order_by('id'))

    def test_hr_is_told_when_a_hire_is_no_longer_hired(self):
        PMNotification.objects.all().delete()
        self.assertEqual(self.change(outcome='REJECTED'), 200)
        [alert] = self.told()
        self.assertEqual((alert.company_user_id, alert.title), (self.recruiter.id, 'No longer hired: Cara Candidate'))
        self.assertIn('from Hired to Rejected', alert.message)
        self.assertIn('Changed by Rae Recruiter', alert.message)
        self.assertIn('HR record is still there', alert.message)
        self.assertEqual(alert.data['link'], '/hr/dashboard?tab=employees')

    def test_and_when_the_decision_is_cleared(self):
        self.change(outcome='')
        self.assertIn('from Hired to no decision', self.told()[0].message)

    def test_not_for_any_other_change(self):
        PMNotification.objects.all().delete()
        self.change(status='COMPLETED')                       # still Hired
        self.change(outcome='HIRED')
        self.assertEqual(self.told(), [])
        self.change(outcome='REJECTED')
        self.change(outcome='PASSED')                         # it was no longer Hired: nothing new to say
        self.assertEqual(len(self.told()), 1)

    def test_not_for_someone_hr_was_never_given(self):
        from recruitment_agent.models import Interview
        Interview.objects.filter(pk=self.interview.pk).update(hr_employee=None)
        self.assertEqual(self.change(outcome='REJECTED'), 200)
        self.assertEqual(self.told(), [])

    def test_not_once_the_company_no_longer_has_hr(self):
        CompanyModulePurchase.objects.filter(company=self.company, module_name='hr_agent').update(status='cancelled')
        self.change(outcome='REJECTED')
        self.assertEqual(self.told(), [])
