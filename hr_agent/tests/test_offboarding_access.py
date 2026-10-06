"""Offboarding someone in HR switches their logins off.

Deactivate said "access is revoked" and changed one status field. The person
could still sign in both ways, and still appeared when tasks, tickets, meetings
and interviews were assigned. Now their logins follow the HR status, whichever
way it changes, and come back (exactly those, nothing more) if they return.
"""
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token

from api.views import hr_agent as views
from core.models import CompanyUser, CompanyUserToken
from core.tenancy import members_of
from hr_agent.models import Employee, HRWorkflow

from .base import HRTestCase


class OffboardingAccessTests(HRTestCase):

    def setUp(self):
        super().setUp()
        # Someone with only an employee (My Space) login, with a session open.
        self.lee = self.employee_with_login('lee', 'Lee Leaver', self.company, self.admin)
        self.lee_token = Token.objects.create(user=self.lee.user)
        # A second company admin, so admins can be offboarded without locking the company out.
        self.second_admin = self.login(self.company, 'sam@test.local', 'Sam Second', 'admin')

    def deactivate(self, employee, actor=None):
        return self.call(views.deactivate_employee, actor or self.admin, {'reason': 'left'}, employee_id=employee.id)

    def reactivate(self, employee):
        return self.call(views.reactivate_employee, self.admin, {}, employee_id=employee.id)

    @staticmethod
    def fresh(obj):
        obj.refresh_from_db()
        return obj

    # ---- switching off ---------------------------------------------------------

    def test_an_employee_login_stops_working_and_they_leave_every_picker(self):
        self.assertIn(self.lee.user, members_of(self.company))
        code, body = self.deactivate(self.lee)
        self.assertEqual(code, 200, body)
        self.assertEqual(body['data']['access'], {'employee_login_off': True, 'dashboard_login_off': False, 'kept': ''})
        self.assertFalse(self.fresh(self.lee.user).is_active)
        self.assertFalse(Token.objects.filter(user=self.lee.user).exists())     # the open session ends too
        self.assertNotIn(self.lee.user, members_of(self.company))

    def test_a_dashboard_login_stops_working_too(self):
        client = self.http(self.member)                                          # Mo is signed in
        self.assertEqual(client.get('/api/company/my-work').status_code, 200)
        code, body = self.deactivate(self.member_emp)
        self.assertEqual(code, 200, body)
        self.assertTrue(body['data']['access']['dashboard_login_off'])
        self.assertFalse(self.fresh(self.member).is_active)
        self.assertFalse(CompanyUserToken.objects.filter(company_user=self.member).exists())
        self.assertFalse(self.fresh(self.member_emp.user).is_active)             # the user it acts as
        self.assertIn(client.get('/api/company/my-work').status_code, (401, 403))

    def test_a_dashboard_login_is_found_by_its_email_when_nothing_links_it(self):
        login = self.login(self.company, 'lee@test.local', 'Lee Leaver', 'company_user')
        self.deactivate(self.lee)
        self.assertFalse(self.fresh(login).is_active)

    def test_the_companys_last_admin_is_never_locked_out(self):
        CompanyUser.objects.filter(pk=self.second_admin.pk).update(is_active=False)   # Dana is now the only admin
        hr_lead = self.login(self.company, 'hana@test.local', 'Hana HR', 'hr_agent')
        code, body = self.deactivate(self.admin_emp, actor=hr_lead)
        self.assertEqual(code, 200, body)
        self.assertEqual(body['data']['access']['kept'], 'last_admin')
        self.assertTrue(self.fresh(self.admin).is_active)
        self.assertTrue(self.fresh(self.admin_emp.user).is_active)
        self.assertEqual(self.fresh(self.admin_emp).employment_status, 'offboarded')

    def test_an_admin_is_switched_off_when_another_admin_remains(self):
        code, body = self.deactivate(self.admin_emp, actor=self.second_admin)
        self.assertEqual((code, body['data']['access']['dashboard_login_off']), (200, True), body)
        self.assertFalse(self.fresh(self.admin).is_active)

    def test_you_cannot_deactivate_your_own_record(self):
        code, body = self.deactivate(self.admin_emp, actor=self.admin)
        self.assertEqual(code, 400, body)
        code, body = self.call(views.update_employee, self.admin, {'employment_status': 'offboarded'},
                               method='patch', employee_id=self.admin_emp.id)
        self.assertEqual(code, 400, body)
        self.assertEqual(self.fresh(self.admin_emp).employment_status, 'active')
        self.assertTrue(self.fresh(self.admin).is_active)

    def test_platform_staff_are_not_a_companys_to_switch_off(self):
        get_user_model().objects.filter(pk=self.lee.user_id).update(is_staff=True)
        self.deactivate(self.lee)
        self.assertTrue(self.fresh(self.lee.user).is_active)

    # ---- every way the status can change -----------------------------------------

    def test_an_edit_that_sets_the_status_switches_them_off(self):
        code, body = self.call(views.update_employee, self.admin, {'employment_status': 'offboarded'},
                               method='patch', employee_id=self.lee.id)
        self.assertEqual(code, 200, body)
        self.assertFalse(self.fresh(self.lee.user).is_active)

    def test_a_workflow_step_that_offboards_someone_switches_them_off(self):
        workflow = HRWorkflow.objects.create(company=self.company, name='Leaver', steps=[
            {'type': 'update_employee', 'fields': {'employment_status': 'offboarded'}}])
        code, body = self.call(views.execute_hr_workflow, self.admin, {'context': {'employee_id': self.lee.id}},
                               workflow_id=workflow.id)
        self.assertEqual((code, body['data']['status']), (200, 'completed'), body)
        self.assertFalse(self.fresh(self.lee.user).is_active)

    def test_erasing_someone_also_ends_their_access(self):
        login = self.login(self.company, 'lee@test.local', 'Lee Leaver', 'company_user')
        code, body = self.call(views.anonymize_employee, self.admin, {}, employee_id=self.lee.id)
        self.assertEqual(code, 200, body)
        self.assertFalse(self.fresh(self.lee.user).is_active)
        self.assertFalse(self.fresh(login).is_active)                            # found before the email was scrubbed

    # ---- coming back ---------------------------------------------------------------

    def test_reactivating_brings_their_logins_back(self):
        self.deactivate(self.lee)
        self.deactivate(self.member_emp)
        code, body = self.reactivate(self.lee)
        self.assertEqual((code, body['data']['logins_restored']), (200, True), body)
        self.reactivate(self.member_emp)
        self.assertTrue(self.fresh(self.lee.user).is_active)
        self.assertTrue(self.fresh(self.member).is_active)
        self.assertTrue(self.fresh(self.member_emp.user).is_active)
        self.assertEqual(self.fresh(self.lee).access_ended, {})

    def test_a_login_that_was_already_off_stays_off(self):
        get_user_model().objects.filter(pk=self.lee.user_id).update(is_active=False)    # switched off earlier, in Users
        code, body = self.deactivate(self.lee)
        self.assertFalse(body['data']['access']['employee_login_off'])
        code, body = self.reactivate(self.lee)
        self.assertFalse(body['data']['logins_restored'])
        self.assertFalse(self.fresh(self.lee.user).is_active)

    def test_a_meeting_seat_is_not_turned_into_a_login(self):
        # The stand-in an executive meeting makes for an employee: same email, never a login.
        seat = CompanyUser.objects.create(company=self.company, email='lee@test.local', full_name='Lee Leaver',
                                          role='team_member', password_hash='x', is_active=False)
        self.deactivate(self.lee)
        self.reactivate(self.lee)
        self.assertFalse(self.fresh(seat).is_active)
        self.assertTrue(self.fresh(self.lee.user).is_active)

    def test_a_later_edit_does_not_switch_off_a_login_someone_turned_back_on(self):
        self.deactivate(self.lee)
        get_user_model().objects.filter(pk=self.lee.user_id).update(is_active=True)     # a deliberate exception
        lee = Employee.objects.get(pk=self.lee.pk)
        lee.job_title = 'Alumni'
        lee.save(update_fields=['job_title', 'updated_at'])
        self.assertTrue(self.fresh(self.lee.user).is_active)

    def test_someone_who_was_never_offboarded_is_left_alone(self):
        lee = Employee.objects.get(pk=self.lee.pk)
        lee.job_title = 'Designer'
        lee.save(update_fields=['job_title', 'updated_at'])
        self.assertTrue(self.fresh(self.lee.user).is_active)
        self.assertEqual(self.fresh(self.lee).access_ended, {})
