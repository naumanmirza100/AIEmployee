"""The Users tab covers the company's employee logins, whoever added them.

It listed only the employee logins the signed-in dashboard login had created
itself, and refused to show, edit, deactivate or reactivate anyone else's,
admins included. Every agent's people lists were company-wide, so a
colleague's employees appeared in HR and Recruitment but nobody else could
manage their login.
"""
from django.contrib.auth import get_user_model

from api.views import company_users as views
from core.models import UserProfile
from hr_agent.tests.base import HRTestCase

User = get_user_model()


class UsersTabScopeTests(HRTestCase):

    def setUp(self):
        super().setUp()
        self.by_member = self.employee_login('mel', self.member)
        self.by_admin = self.employee_login('abe', self.admin)
        self.rivals = self.employee_login('rob', self.rival_admin)

    def employee_login(self, username, created_by, **fields):
        user = User.objects.create_user(username=username, email=f'{username}@test.local', password='x', **fields)
        UserProfile.objects.update_or_create(user=user, defaults={
            'company': created_by.company, 'created_by_company_user': created_by, 'role': 'team_member'})
        return user

    def listed(self, actor):
        code, body = self.call(views.list_users, actor, method='get')
        self.assertEqual(code, 200, body)
        return sorted(u['email'] for u in body['data']), body['pagination']['total']

    def email_of(self, user):
        return User.objects.get(pk=user.pk).email

    # ---- seeing --------------------------------------------------------------

    def test_every_dashboard_login_sees_all_of_the_companys_employee_logins(self):
        for actor in (self.member, self.admin):
            self.assertEqual(self.listed(actor), (['abe@test.local', 'mel@test.local'], 2))
        self.assertEqual(self.listed(self.rival_admin), (['rob@test.local'], 1))

    def test_a_switched_off_login_is_still_listed_so_it_can_be_switched_back_on(self):
        User.objects.filter(pk=self.by_admin.pk).update(is_active=False)
        self.assertEqual(self.listed(self.member)[1], 2)

    def test_dashboard_logins_own_records_and_platform_staff_are_not_employees(self):
        # HR gives each dashboard login a user record of its own; even when that record
        # carries the company on its profile, it is not an employee login.
        self.admin.refresh_from_db()
        UserProfile.objects.update_or_create(user=self.admin.login_user, defaults={'company': self.company})
        self.employee_login('root', self.admin, is_staff=True)
        emails, total = self.listed(self.admin)
        self.assertEqual((emails, total), (['abe@test.local', 'mel@test.local'], 2))

    def test_one_can_be_opened_by_a_colleague_but_not_by_another_company(self):
        self.assertEqual(self.call(views.get_user, self.member, method='get', userId=self.by_admin.id)[0], 200)
        self.assertEqual(self.call(views.get_user, self.member, method='get', userId=self.rivals.id)[0], 404)

    # ---- changing ------------------------------------------------------------

    def test_an_admin_can_change_a_login_a_colleague_created(self):
        code, body = self.call(views.update_user, self.admin, {'email': 'mel.new@test.local'}, method='patch',
                               userId=self.by_member.id)
        self.assertEqual((code, self.email_of(self.by_member)), (200, 'mel.new@test.local'), body)

    def test_whoever_created_it_still_can(self):
        code, _ = self.call(views.update_user, self.member, {'email': 'mel.new@test.local'}, method='patch',
                            userId=self.by_member.id)
        self.assertEqual((code, self.email_of(self.by_member)), (200, 'mel.new@test.local'))

    def test_a_member_cannot_change_a_login_someone_else_created(self):
        code, body = self.call(views.update_user, self.member, {'email': 'taken.over@test.local'}, method='patch',
                               userId=self.by_admin.id)
        self.assertEqual(code, 403, body)
        self.assertIn('owner or admin', body['message'])
        self.assertEqual(self.email_of(self.by_admin), 'abe@test.local')
        for view, method in ((views.delete_user, 'delete'), (views.reactivate_user, 'post')):
            self.assertEqual(self.call(view, self.member, method=method, userId=self.by_admin.id)[0], 403)
        self.assertTrue(User.objects.get(pk=self.by_admin.pk).is_active)

    def test_an_admin_can_switch_a_colleagues_login_off_and_on(self):
        self.assertEqual(self.call(views.delete_user, self.admin, method='delete', userId=self.by_member.id)[0], 200)
        self.assertFalse(User.objects.get(pk=self.by_member.pk).is_active)
        self.assertEqual(self.call(views.reactivate_user, self.admin, userId=self.by_member.id)[0], 200)
        self.assertTrue(User.objects.get(pk=self.by_member.pk).is_active)

    def test_nobody_reaches_into_another_company(self):
        for view, method, data in ((views.update_user, 'patch', {'email': 'x@test.local'}),
                                   (views.delete_user, 'delete', None), (views.reactivate_user, 'post', None)):
            self.assertEqual(self.call(view, self.admin, data, method=method, userId=self.rivals.id)[0], 404)
        rob = User.objects.get(pk=self.rivals.pk)
        self.assertEqual((rob.email, rob.is_active), ('rob@test.local', True))
