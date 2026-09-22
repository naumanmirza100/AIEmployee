"""Who may reach the PM API at all: the module-purchase gate, the two login
kinds, and the lists of people a task may be assigned to.

These go through the real URLs so the middleware, the authentication classes
and the permissions are all exercised (SEC-1, SEC-2, DATA-3).
"""
from django.contrib.auth.models import User

from api.views import pm_agent as dashboard
from api.views import user_project_manager as employee

from .base import PMTestCase

CREATE_PROJECT_A = '/api/project-manager/projects/create'
CREATE_PROJECT_C = '/api/user/project-manager/projects/create'


class ModulePurchaseGateTests(PMTestCase):
    """SEC-2 — the gate used to cover only one of the three families."""

    def test_a_company_without_the_module_is_refused(self):
        code, _ = self.send(self.http(self.rival_dash), 'post', CREATE_PROJECT_A, {'name': 'x'})
        self.assertEqual(code, 403)

    def test_a_company_with_the_module_is_allowed(self):
        code, body = self.send(self.http(self.dash), 'post', CREATE_PROJECT_A, {'name': 'Allowed'})
        self.assertEqual(code, 201, body)

    def test_the_gate_covers_the_company_family(self):
        code, _ = self.send(self.http(self.rival_dash), 'put',
                            f'/api/company/projects/{self.rival_project.id}/update',
                            {'name': 'x'})
        self.assertEqual(code, 403)

    def test_the_gate_covers_the_employee_family(self):
        code, _ = self.send(self.http(self.rival_pm), 'post', CREATE_PROJECT_C, {'name': 'x'})
        self.assertEqual(code, 403)


class AuthenticationTests(PMTestCase):
    """DATA-3 — the employee endpoints say which login they expect."""

    def test_a_dashboard_token_on_an_employee_endpoint_explains_itself(self):
        code, body = self.send(self.http(self.dash), 'post', CREATE_PROJECT_C, {'name': 'x'})
        self.assertEqual(code, 401)
        self.assertIn('dashboard login', body['detail'])

    def test_an_employee_token_on_a_dashboard_endpoint_is_refused(self):
        code, _ = self.send(self.http(self.pm), 'post', CREATE_PROJECT_A, {'name': 'x'})
        self.assertIn(code, (401, 403))

    def test_an_unknown_token_is_still_just_invalid(self):
        from django.test import Client
        client = Client(HTTP_AUTHORIZATION='Token nonsense')
        code, body = self.send(client, 'post', CREATE_PROJECT_C, {'name': 'x'})
        self.assertEqual(code, 401)
        self.assertIn('Invalid token', body['detail'])

    def test_no_token_at_all_is_refused(self):
        from django.test import Client
        code, _ = self.send(Client(), 'post', CREATE_PROJECT_C, {'name': 'x'})
        self.assertIn(code, (401, 403))


class AssignableUserTests(PMTestCase):
    """SEC-1 and audit bug 5 — the dropdowns must match what assignment allows."""

    def test_dashboard_list_excludes_other_companies(self):
        code, body = self.call(dashboard.get_available_users, self.dash, method='get')
        self.assertEqual(code, 200, body)
        ids = {user['id'] for user in body['data']}
        self.assertIn(self.dev.id, ids)
        self.assertNotIn(self.rival_pm.id, ids)

    def test_dashboard_list_excludes_deactivated_people(self):
        User.objects.filter(pk=self.dev.pk).update(is_active=False)
        _, body = self.call(dashboard.get_available_users, self.dash, method='get')
        self.assertNotIn(self.dev.id, {user['id'] for user in body['data']})

    def test_employee_list_covers_the_whole_company(self):
        """Colleagues linked through their creating dashboard login were missing."""
        code, body = self.call(employee.get_company_users_for_pm, self.pm, method='get')
        self.assertEqual(code, 200, body)
        ids = {user['id'] for user in body['data']}
        self.assertTrue({self.pm.id, self.other_pm.id, self.dev.id} <= ids)
        self.assertNotIn(self.rival_pm.id, ids)

    def test_employee_list_excludes_deactivated_people(self):
        User.objects.filter(pk=self.dev.pk).update(is_active=False)
        _, body = self.call(employee.get_company_users_for_pm, self.pm, method='get')
        self.assertNotIn(self.dev.id, {user['id'] for user in body['data']})
