"""A company can add dashboard logins and give them roles.

A company's first login was made an admin and that was the end of it: no
screen could change a role, and since the sign-up page stopped asking for an
email, a second dashboard login could not be created at all. So every
admin-only action, and every alert "to the admins", came down to one login.
"""
from django.contrib.auth.hashers import check_password
from django.core import mail
from django.test import Client

from api.views import company_logins as views
from core.models import CompanyUser, CompanyUserToken
from hr_agent import alerts as hr_alerts
from hr_agent.models import Employee
from hr_agent.tests.base import HRTestCase
from project_manager_agent.models import PMNotification


class CompanyLoginsTests(HRTestCase):

    def page(self, actor=None):
        code, body = self.call(views.company_logins, actor or self.admin, method='get')
        self.assertEqual(code, 200, body)
        return body['data']

    def add(self, actor=None, **data):
        data.setdefault('email', 'Nia@Test.Local')
        data.setdefault('full_name', 'Nia New')
        return self.call(views.company_logins, actor or self.admin, data)

    def change(self, target, actor=None, **data):
        return self.call(views.company_login, actor or self.admin, data, method='patch', login_id=target.id)

    def role(self, login):
        return CompanyUser.objects.get(pk=login.pk).role

    # ---- seeing them -------------------------------------------------------

    def test_everyone_sees_their_own_companys_logins_and_only_admins_can_manage(self):
        page = self.page(self.member)
        self.assertEqual(sorted(l['email'] for l in page['logins']), ['dana@test.local', 'mo@test.local'])
        self.assertFalse(page['can_manage'])
        self.assertTrue(self.page(self.admin)['can_manage'])
        me = [l for l in page['logins'] if l['is_you']]
        self.assertEqual([l['email'] for l in me], ['mo@test.local'])
        self.assertEqual([r['key'] for r in page['roles']],
                         ['admin', 'hr_agent', 'frontline_agent', 'manager', 'company_user'])

    # ---- adding one --------------------------------------------------------

    def test_an_admin_adds_a_login_and_the_person_is_told_how_to_set_a_password(self):
        code, body = self.add(role='frontline_agent')
        self.assertEqual((code, body['invited']), (201, True), body)
        nia = CompanyUser.objects.get(email='nia@test.local')
        self.assertEqual((nia.company_id, nia.role, nia.is_active, nia.full_name),
                         (self.company.id, 'frontline_agent', True, 'Nia New'))
        invitation, = mail.outbox
        self.assertEqual(invitation.to, ['nia@test.local'])
        self.assertIn('Forgot password', invitation.body)
        self.assertIn('Dana Admin', invitation.body)
        self.assertIn('nia@test.local', [l['email'] for l in body['data']['logins']])

    def test_the_new_login_has_no_password_until_they_set_one(self):
        self.add()
        nia = CompanyUser.objects.get(email='nia@test.local')
        for guess in ('', 'password', 'nia@test.local', nia.password_hash):
            self.assertFalse(check_password(guess, nia.password_hash), guess)
        response = Client().post('/api/company/login', {'email': 'nia@test.local', 'password': 'anything'},
                                 content_type='application/json')
        self.assertEqual(response.status_code, 401)
        # ... and "Forgot password" is open to them: it emails a code to their own address.
        Client().post('/api/company/forgot-password', {'email': 'nia@test.local'}, content_type='application/json')
        nia.refresh_from_db()
        self.assertTrue(nia.reset_otp)

    def test_a_member_cannot_add_a_login(self):
        code, _ = self.add(self.member)
        self.assertEqual((code, CompanyUser.objects.filter(email='nia@test.local').exists()), (403, False))

    def test_what_is_refused(self):
        cases = {
            'not an address': dict(email='nia'),
            'no name': dict(full_name='  '),
            'a role that is not offered': dict(role='owner'),
            'an address that already has a login here': dict(email='MO@test.local'),
            'or in another company': dict(email='rhea@test.local'),
        }
        before = CompanyUser.objects.count()
        for name, data in cases.items():
            code, body = self.add(**data)
            self.assertEqual(code, 400, name)
        self.assertEqual((CompanyUser.objects.count(), len(mail.outbox)), (before, 0))

    # ---- changing a role -----------------------------------------------------

    def test_an_admin_changes_a_role_and_the_person_is_told(self):
        code, body = self.change(self.member, role='hr_agent')
        self.assertEqual((code, body['changed'], self.role(self.member)), (200, True, 'hr_agent'))
        note = PMNotification.objects.get(company_user=self.member)
        self.assertEqual(note.title, 'Your role is now HR admin')
        self.assertIn('Dana Admin changed it from Member', note.message)

    def test_setting_the_role_it_already_has_changes_nothing(self):
        code, body = self.change(self.member, role='company_user')
        self.assertEqual((code, body['changed']), (200, False))
        self.assertFalse(PMNotification.objects.filter(company_user=self.member).exists())

    def test_a_member_cannot_change_roles_not_even_their_own(self):
        for target in (self.member, self.admin):
            code, _ = self.change(target, actor=self.member, role='admin')
            self.assertEqual(code, 403)
        self.assertEqual((self.role(self.member), self.role(self.admin)), ('company_user', 'admin'))

    def test_another_companys_login_cannot_be_touched(self):
        code, _ = self.change(self.rival_admin, role='company_user')
        self.assertEqual((code, self.role(self.rival_admin)), (404, 'admin'))

    def test_a_role_this_screen_does_not_offer_is_refused(self):
        code, _ = self.change(self.member, role='owner')
        self.assertEqual((code, self.role(self.member)), (400, 'company_user'))

    # ---- never without an admin ----------------------------------------------

    def test_an_admin_cannot_demote_or_switch_off_themselves(self):
        self.change(self.member, role='admin')                  # so they are not the only one
        for data in (dict(role='company_user'), dict(is_active=False)):
            code, body = self.change(self.admin, **data)
            self.assertEqual(code, 400, data)
            self.assertIn('yourself', body['message'])
        self.assertEqual(self.role(self.admin), 'admin')

    def test_the_only_admin_cannot_be_demoted_or_switched_off_by_anyone(self):
        other = self.login(self.company, 'ola@test.local', 'Ola Other', 'admin')
        CompanyUser.objects.filter(pk=self.admin.pk).update(is_active=False)     # Ola is now the only active admin
        for data in (dict(role='company_user'), dict(is_active=False)):
            self.assertEqual(self.change(other, actor=other, **data)[0], 400, data)
        CompanyUser.objects.filter(pk=self.admin.pk).update(is_active=True)
        code, _ = self.change(other, role='company_user')       # with Dana back, Ola can step down
        self.assertEqual((code, self.role(other)), (200, 'company_user'))

    def test_two_admins_removing_each_other_at_once_cannot_leave_none(self):
        # The second request was let in while its sender was still an admin;
        # by the time it runs, the first has already taken that away.
        ola = self.login(self.company, 'ola@test.local', 'Ola Other', 'admin')
        for already_done_to_ola in (dict(role='company_user'), dict(is_active=False)):
            CompanyUser.objects.filter(pk=ola.pk).update(role='admin', is_active=True)
            ola_as_let_in = CompanyUser.objects.get(pk=ola.pk)
            CompanyUser.objects.filter(pk=ola.pk).update(**already_done_to_ola)
            code, body = self.change(self.admin, actor=ola_as_let_in, role='company_user')
            self.assertEqual(code, 400, already_done_to_ola)
            self.assertIn('only admin', body['message'])
            self.assertEqual(self.role(self.admin), 'admin')

    # ---- switching a login off and on -----------------------------------------

    def test_switching_a_login_off_signs_it_out_everywhere(self):
        CompanyUserToken.objects.get_or_create(company_user=self.member)
        code, _ = self.change(self.member, is_active=False)
        self.member.refresh_from_db()
        self.assertEqual((code, self.member.is_active), (200, False))
        self.assertFalse(CompanyUserToken.objects.filter(company_user=self.member).exists())
        code, _ = self.change(self.member, is_active=True)
        self.member.refresh_from_db()
        self.assertTrue(self.member.is_active)

    def test_it_works_over_http(self):
        client = self.http(self.admin)
        code, body = self.send(client, 'post', '/api/company/logins',
                               {'email': 'nia@test.local', 'full_name': 'Nia New', 'role': 'manager'})
        self.assertEqual(code, 201, body)
        nia = CompanyUser.objects.get(email='nia@test.local')
        code, body = self.send(client, 'patch', f'/api/company/logins/{nia.id}', {'role': 'admin'})
        self.assertEqual((code, self.role(nia)), (200, 'admin'), body)
        self.assertIn(Client().get('/api/company/logins').status_code, (401, 403))


class WhoHearsTests(HRTestCase):
    """The leave alert reaches the manager's login even though nothing links it."""

    def test_a_leave_request_reaches_the_managers_login_found_by_their_work_address(self):
        from hr_agent.leave_helpers import resolve_approver_for_leave
        boss_login = self.login(self.company, 'bea@test.local', 'Bea Boss', 'company_user')
        boss = Employee.objects.create(company=self.company, full_name='Bea Boss', work_email='BEA@test.local',
                                       employment_status='active')          # no link to the login
        Employee.objects.filter(pk=self.member_emp.pk).update(manager=boss)
        self.member_emp.refresh_from_db()
        # As the leave form does: the manager is named to decide it, being able to.
        approver = resolve_approver_for_leave(self.member_emp, self.company)
        self.assertEqual(approver, boss)
        hr_alerts.leave_request_submitted(self.leave_request(approver=approver))
        self.assertTrue(PMNotification.objects.filter(company_user=boss_login).exists())
        self.assertTrue(PMNotification.objects.filter(company_user=self.admin).exists())       # HR admins still do
        self.assertFalse(PMNotification.objects.filter(company_user=self.member).exists())     # not whoever asked
