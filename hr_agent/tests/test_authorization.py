"""Who may see and change whose HR record (HR-SEC-1 … HR-SEC-5)."""
from api.views import hr_agent as views

from .base import HRTestCase


class HrAdminRoleTests(HRTestCase):
    """HR-SEC-1 — `company_user` used to count as HR admin, so every colleague
    could read everyone's salary."""

    def test_the_default_role_is_not_an_hr_admin(self):
        self.assertFalse(views._is_hr_admin(self.member))

    def test_admin_and_owner_are(self):
        self.assertTrue(views._is_hr_admin(self.admin))
        self.rival_admin.role = 'owner'
        self.assertTrue(views._is_hr_admin(self.rival_admin))

    def test_member_cannot_read_compensation(self):
        code, _ = self.call(views.list_compensation_history, self.member, method='get',
                            employee_id=self.admin_emp.id)
        self.assertEqual(code, 403)

    def test_admin_can_read_compensation(self):
        code, body = self.call(views.list_compensation_history, self.admin, method='get',
                               employee_id=self.member_emp.id)
        self.assertEqual(code, 200, body)

    def test_member_cannot_adjust_a_leave_balance(self):
        code, _ = self.call(views.adjust_leave_balance, self.member,
                            {'leave_type': 'vacation', 'set_accrued_days': 99,
                             'reason': 'giving myself a holiday'},
                            employee_id=self.member_emp.id)
        self.assertEqual(code, 403)

    def test_member_cannot_export_a_colleague(self):
        code, _ = self.call(views.export_employee_data, self.member, method='get',
                            employee_id=self.admin_emp.id)
        self.assertEqual(code, 403)

    def test_member_can_still_export_themselves(self):
        code, _ = self.call(views.export_employee_data, self.member, method='get',
                            employee_id=self.member_emp.id)
        self.assertEqual(code, 200)

    def test_member_cannot_read_the_audit_log(self):
        code, _ = self.call(views.list_hr_audit_log, self.member, method='get')
        self.assertEqual(code, 403)

    def test_member_cannot_approve_their_own_leave(self):
        """Self-approval followed from the same role list."""
        lr = self.leave_request(employee=self.member_emp)
        code, _ = self.call(views.decide_leave_request, self.member, {'action': 'approve'},
                            request_id=lr.id)
        self.assertEqual(code, 403)
        lr.refresh_from_db()
        self.assertEqual(lr.status, 'pending')

    def test_the_assigned_approver_can_still_decide(self):
        lr = self.leave_request(employee=self.member_emp, approver=self.admin_emp)
        code, body = self.call(views.decide_leave_request, self.admin, {'action': 'approve'},
                               request_id=lr.id)
        self.assertEqual(code, 200, body)


class LeaveListScopeTests(HRTestCase):
    """HR-SEC-2 — the list returned every employee's reason to everyone."""

    def setUp(self):
        super().setUp()
        self.mine = self.leave_request(employee=self.member_emp, reason='dentist')
        self.theirs = self.leave_request(employee=self.admin_emp, reason='chemotherapy')

    def test_a_member_sees_only_their_own(self):
        code, body = self.call(views.list_leave_requests, self.member, method='get')
        self.assertEqual(code, 200, body)
        ids = {row['id'] for row in body['data']}
        self.assertIn(self.mine.id, ids)
        self.assertNotIn(self.theirs.id, ids)

    def test_a_member_does_not_see_a_colleagues_reason(self):
        _, body = self.call(views.list_leave_requests, self.member, method='get')
        self.assertNotIn('chemotherapy', json_dump(body))

    def test_a_member_sees_requests_they_approve(self):
        assigned = self.leave_request(employee=self.admin_emp, approver=self.member_emp,
                                      reason='conference')
        _, body = self.call(views.list_leave_requests, self.member, method='get')
        self.assertIn(assigned.id, {row['id'] for row in body['data']})

    def test_an_hr_admin_sees_the_whole_company(self):
        code, body = self.call(views.list_leave_requests, self.admin, method='get')
        self.assertEqual(code, 200, body)
        ids = {row['id'] for row in body['data']}
        self.assertTrue({self.mine.id, self.theirs.id} <= ids)

    def test_another_companys_requests_never_appear(self):
        theirs = self.leave_request(employee=self.rival_emp, reason='rival business')
        _, body = self.call(views.list_leave_requests, self.admin, method='get')
        self.assertNotIn(theirs.id, {row['id'] for row in body['data']})

    def test_the_list_reports_its_window(self):
        _, body = self.call(views.list_leave_requests, self.admin, method='get')
        self.assertEqual(set(body['pagination']),
                         {'limit', 'offset', 'total', 'returned', 'has_more'})


class ConfidentialityRoleTests(HRTestCase):
    """HR-SEC-3 — the default role mapped to the top confidentiality rung."""

    def test_the_default_role_reads_as_an_employee(self):
        self.assertEqual(views._resolve_asker_role(self.member), 'employee')

    def test_an_hr_admin_reads_as_hr(self):
        self.assertEqual(views._resolve_asker_role(self.admin), 'hr')

    def test_a_manager_reads_as_a_manager(self):
        self.member.role = 'manager'
        self.assertEqual(views._resolve_asker_role(self.member), 'manager')

    def test_an_unknown_role_falls_to_the_lowest_rung(self):
        self.member.role = 'something_new'
        self.assertEqual(views._resolve_asker_role(self.member), 'employee')

    def test_employees_cannot_reach_hr_only_documents(self):
        from core.HR_agent.services import _allowed_confidentialities
        self.assertNotIn('hr_only', _allowed_confidentialities('employee'))
        self.assertNotIn('hr_only', _allowed_confidentialities('manager'))
        self.assertIn('hr_only', _allowed_confidentialities('hr'))


class RoleAdministrationTests(HRTestCase):
    """HR-SEC-4 — the role ladder had to become reachable."""

    def test_an_admin_can_promote_someone(self):
        code, body = self.call(views.set_company_user_role, self.admin, {'role': 'hr_agent'},
                               method='patch', company_user_id=self.member.id)
        self.assertEqual(code, 200, body)
        self.member.refresh_from_db()
        self.assertEqual(self.member.role, 'hr_agent')
        self.assertTrue(views._is_hr_admin(self.member))

    def test_a_member_cannot_promote_themselves(self):
        code, _ = self.call(views.set_company_user_role, self.member, {'role': 'admin'},
                            method='patch', company_user_id=self.member.id)
        self.assertEqual(code, 403)
        self.member.refresh_from_db()
        self.assertEqual(self.member.role, 'company_user')

    def test_an_unknown_role_is_refused(self):
        code, _ = self.call(views.set_company_user_role, self.admin, {'role': 'wizard'},
                            method='patch', company_user_id=self.member.id)
        self.assertEqual(code, 400)

    def test_the_last_admin_cannot_be_demoted(self):
        code, body = self.call(views.set_company_user_role, self.admin, {'role': 'employee'},
                               method='patch', company_user_id=self.admin.id)
        self.assertEqual(code, 400, body)
        self.admin.refresh_from_db()
        self.assertTrue(views._is_hr_admin(self.admin))

    def test_another_companys_login_cannot_be_touched(self):
        code, _ = self.call(views.set_company_user_role, self.admin, {'role': 'admin'},
                            method='patch', company_user_id=self.rival_admin.id)
        self.assertEqual(code, 404)


class ShadowUserIdentityTests(HRTestCase):
    """HR-SEC-5 — the login was matched by email across every company."""

    def test_the_same_email_in_two_companies_gets_two_logins(self):
        shared = 'shared@example.test'
        a = self.login(self.company, shared, 'Person A', 'company_user')
        b = self.login(self.rival, shared, 'Person B', 'company_user')

        user_a = views._hr_get_or_create_user_for_company_user(a)
        user_b = views._hr_get_or_create_user_for_company_user(b)

        self.assertIsNotNone(user_a)
        self.assertIsNotNone(user_b)
        self.assertNotEqual(user_a.pk, user_b.pk)

    def test_the_link_is_stable_across_calls(self):
        first = views._hr_get_or_create_user_for_company_user(self.member)
        second = views._hr_get_or_create_user_for_company_user(self.member)
        self.assertEqual(first.pk, second.pk)
        self.member.refresh_from_db()
        self.assertEqual(self.member.login_user_id, first.pk)


def json_dump(obj):
    import json as _json
    return _json.dumps(obj, default=str)
