"""Removing a person is one switch, wherever it is pressed.

There were two, and neither knew about the other. Deactivating someone under
Company, Users switched their employee login off, moved no work and left their
HR record active. HR's Deactivate marked the record offboarded. And the form
that hands a leaver's work to somebody else could only be reached through the
HR agent, so a company without HR had no way to pass that work on.
"""
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.authtoken.models import Token

from api.views import company_users as users
from api.views import hr_agent as hr
from core.models import CompanyModulePurchase, CompanyUser, Project, Task
from hr_agent.models import Employee, HRAuditLog
from hr_agent.tests.base import HRTestCase

User = get_user_model()


class OneSwitchTests(HRTestCase):

    def setUp(self):
        super().setUp()
        self.sam = self.employee_with_login('sam', 'Sam Staff', self.company, self.member)   # Mo added Sam
        self.tom = self.employee_with_login('tom', 'Tom Taker', self.company, self.admin)
        Token.objects.create(user=self.sam.user)

    def deactivate(self, employee=None, actor=None):
        return self.call(users.delete_user, actor or self.admin, method='delete',
                         userId=(employee or self.sam).user_id)

    def reactivate(self, employee=None, actor=None):
        return self.call(users.reactivate_user, actor or self.admin, userId=(employee or self.sam).user_id)

    def state(self, employee=None):
        employee = Employee.objects.get(pk=(employee or self.sam).pk)
        return employee.employment_status, User.objects.get(pk=employee.user_id).is_active

    # ---- Company, Users: Deactivate ------------------------------------------------

    def test_deactivating_a_user_offboards_them_in_hr_too(self):
        code, body = self.deactivate()
        self.assertEqual(code, 200, body)
        self.assertEqual(self.state(), ('offboarded', False))
        self.assertFalse(Token.objects.filter(user=self.sam.user).exists())        # their open session ends
        self.assertEqual((body['data']['employee_id'], body['data']['access']['employee_login_off']),
                         (self.sam.id, True))
        entry = HRAuditLog.objects.filter(action='employee.deactivate').latest('id')
        self.assertEqual((entry.target_id, entry.diff['after']['from'], entry.diff['after']['previous_status']),
                         (self.sam.id, 'users_tab', 'active'))

    def test_their_dashboard_login_goes_off_with_it(self):
        both = self.login(self.company, 'sam.dash@test.local', 'Sam Staff', 'company_user')
        Employee.objects.filter(pk=self.sam.pk).update(company_user=both)
        code, body = self.deactivate()
        self.assertEqual((code, body['data']['access']['dashboard_login_off']), (200, True))
        self.assertFalse(CompanyUser.objects.get(pk=both.pk).is_active)

    def test_whoever_added_the_user_can_still_do_it_and_nobody_else_can(self):
        self.assertEqual(self.deactivate(actor=self.member)[0], 200)             # Mo added Sam
        self.assertEqual(self.state(), ('offboarded', False))
        self.assertEqual(self.deactivate(self.tom, actor=self.member)[0], 403)  # Dana added Tom
        self.assertEqual(self.state(self.tom), ('active', True))

    def test_nobody_deactivates_the_login_they_are_using(self):
        Employee.objects.filter(pk=self.admin_emp.pk).update(company_user=None)
        Employee.objects.filter(pk=self.tom.pk).update(company_user=self.admin)   # Tom's record is Dana's own
        code, body = self.deactivate(self.tom)
        self.assertEqual(code, 400)
        self.assertIn('your own employee login', body['message'])
        self.assertEqual(self.state(self.tom), ('active', True))
        self.assertTrue(CompanyUser.objects.get(pk=self.admin.pk).is_active)

    def test_a_login_from_before_every_login_had_an_hr_record_is_given_one(self):
        Employee.objects.filter(pk=self.sam.pk).delete()
        code, body = self.call(users.delete_user, self.admin, method='delete', userId=self.sam.user_id)
        self.assertEqual(code, 200, body)
        record = Employee.objects.get(user_id=self.sam.user_id)
        self.assertEqual((record.employment_status, body['data']['employee_id']), ('offboarded', record.id))
        self.assertFalse(User.objects.get(pk=self.sam.user_id).is_active)

    def test_a_record_left_under_another_company_is_brought_home_first(self):
        Employee.objects.filter(pk=self.sam.pk).update(company=self.rival)        # stale: Sam works at Acme
        self.assertEqual(self.deactivate()[0], 200)
        record = Employee.objects.get(pk=self.sam.pk)
        self.assertEqual((record.company_id, record.employment_status), (self.company.id, 'offboarded'))

    # ---- the two switches agree ------------------------------------------------------

    def test_someone_deactivated_before_the_two_were_joined_can_be_reactivated(self):
        # The old Users tab switched the login off and told HR nothing.
        User.objects.filter(pk=self.sam.user_id).update(is_active=False)
        self.assertEqual(self.state(), ('active', False))
        self.assertEqual(self.reactivate()[0], 200)
        self.assertEqual(self.state(), ('active', True))

    def test_hr_can_reactivate_someone_the_users_tab_deactivated(self):
        self.deactivate()
        code, body = self.call(hr.reactivate_employee, self.admin, employee_id=self.sam.id)
        self.assertEqual((code, body['data']['logins_restored']), (200, True))
        self.assertEqual(self.state(), ('active', True))

    def test_the_users_tab_can_reactivate_someone_hr_deactivated(self):
        self.assertEqual(self.call(hr.deactivate_employee, self.admin, employee_id=self.sam.id)[0], 200)
        self.assertEqual(self.state(), ('offboarded', False))
        code, body = self.reactivate()
        self.assertEqual(code, 200, body)
        self.assertEqual(self.state(), ('active', True))
        self.assertEqual(Employee.objects.get(pk=self.sam.pk).access_ended, {})
        entry = HRAuditLog.objects.filter(action='employee.reactivate').latest('id')
        self.assertEqual((entry.target_id, entry.diff['after']['from']), (self.sam.id, 'users_tab'))

    def test_reactivating_brings_back_the_dashboard_login_that_went_off(self):
        both = self.login(self.company, 'sam.dash@test.local', 'Sam Staff', 'company_user')
        Employee.objects.filter(pk=self.sam.pk).update(company_user=both)
        self.deactivate()
        self.reactivate()
        self.assertTrue(CompanyUser.objects.get(pk=both.pk).is_active)

    def test_someone_whose_record_was_anonymised_stays_off(self):
        self.deactivate()
        Employee.objects.filter(pk=self.sam.pk).update(anonymized_at=timezone.now())
        code, body = self.reactivate()
        self.assertEqual(code, 400)
        self.assertIn('anonymised', body['message'])
        self.assertEqual(self.state(), ('offboarded', False))

    def test_reactivating_someone_who_is_active_is_still_refused(self):
        code, body = self.reactivate()
        self.assertEqual((code, body['message']), (400, 'User is already active'))

    # ---- handing their work over, with or without HR -----------------------------------

    def work(self):
        project = Project.objects.create(name='Website', company=self.company, owner=self.sam.user,
                                         project_manager=self.sam.user, created_by_company_user=self.admin)
        task = Task.objects.create(project=project, title='Write the copy', assignee=self.sam.user, status='todo')
        Employee.objects.filter(pk=self.tom.pk).update(manager=self.sam)       # Tom reports to Sam
        return task

    def without_hr(self):
        CompanyModulePurchase.objects.filter(company=self.company, module_name='hr_agent').update(status='cancelled')

    def groups(self, client=None):
        code, body = self.send(client or self.http(self.admin), 'get', f'/api/company/users/{self.sam.user_id}/handover')
        self.assertEqual(code, 200, body)
        return [g['key'] for g in body['data']['groups']]

    def test_a_company_without_hr_can_hand_a_leavers_work_over(self):
        task = self.work()
        self.without_hr()
        client = self.http(self.admin)
        self.assertEqual(self.send(client, 'get', f'/api/hr/employees/{self.sam.id}/handover')[0], 403)   # HR is locked
        self.assertEqual(self.groups(client), ['tasks', 'projects'])                  # no HR groups without HR
        code, body = self.send(client, 'post', f'/api/company/users/{self.sam.user_id}/handover',
                               {'assignments': {'tasks': self.tom.user_id}})
        self.assertEqual(code, 200, body)
        task.refresh_from_db()
        self.assertEqual((task.assignee_id, body['data']['results']['tasks']['moved']), (self.tom.user_id, 1))
        self.assertEqual([g['key'] for g in body['data']['remaining']['groups']], ['projects'])
        entry = HRAuditLog.objects.filter(action='employee.handover').latest('id')
        self.assertEqual((entry.target_id, entry.diff['after']['tasks']['moved']), (self.sam.id, 1))

    def test_hrs_own_groups_are_handed_over_in_hr(self):
        self.work()
        self.assertEqual(self.groups(), ['tasks', 'projects', 'reports'])            # with HR, they are all there
        self.without_hr()
        code, body = self.send(self.http(self.admin), 'post', f'/api/company/users/{self.sam.user_id}/handover',
                               {'assignments': {'reports': self.admin_emp.id}})
        self.assertEqual(code, 400)
        self.assertIn('handed over in HR', body['message'])
        self.assertEqual(Employee.objects.get(pk=self.tom.pk).manager_id, self.sam.id)

    def test_only_an_owner_or_admin_and_only_their_own_company(self):
        self.work()
        url = f'/api/company/users/{self.sam.user_id}/handover'
        self.assertEqual(self.send(self.http(self.member), 'get', url)[0], 403)
        self.assertEqual(self.send(self.http(self.rival_admin), 'get', url)[0], 404)
        code, _ = self.send(self.http(self.rival_admin), 'post', url, {'assignments': {'tasks': self.tom.user_id}})
        self.assertEqual(code, 404)
        self.assertEqual(self.send(self.http(self.admin), 'post', url, {'assignments': {}})[0], 400)
