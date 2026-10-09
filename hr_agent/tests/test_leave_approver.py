"""A leave request goes to someone who can decide it.

Deciding leave takes a dashboard login. A request used to be sent to the
employee's manager even when that manager had only a My Space login: the
manager saw nothing, the request was on nobody's My work list, and the alert
the HR admins got opened a view of the leave screen it was not on.
"""
from importlib import import_module

from django.apps import apps

from api.views import hr_agent as views
from core import my_work
from hr_agent.leave_helpers import can_decide_leave, resolve_approver_for_leave
from hr_agent.models import Employee, LeaveRequest
from project_manager_agent.models import PMNotification

from .base import HRTestCase

free_stuck = import_module('hr_agent.migrations.0020_free_stuck_leave_requests').free_stuck


def bell_links(company_user):
    return [n.data['link'] for n in PMNotification.objects.filter(company_user=company_user)]


class ApproverTests(HRTestCase):

    def setUp(self):
        super().setUp()
        # Meg manages Mo and has a dashboard login. Lee manages Sam and has only a My Space login.
        self.meg_login = self.login(self.company, 'meg@test.local', 'Meg Manager', 'manager')
        self.meg = self.employee(self.meg_login, 'Meg Manager')
        self.lee = self.employee_with_login('lee', 'Lee Lead', self.company, self.admin)
        self.sam = self.employee_with_login('sam', 'Sam Staff', self.company, self.admin)
        self.member_emp.manager = self.meg
        self.member_emp.save()
        self.sam.manager = self.lee
        self.sam.save()

    def ask(self, employee):
        code, body = self.call(views.submit_leave_request, self.admin, {
            'employee_id': employee.id, 'start_date': '2027-03-01', 'end_date': '2027-03-02'})
        self.assertEqual(code, 201, body)
        return LeaveRequest.objects.get(pk=body['data']['id'])

    # ---- who it is sent to ----------------------------------------------------------

    def test_a_manager_with_a_dashboard_login_is_the_approver(self):
        self.assertTrue(can_decide_leave(self.meg))
        self.assertEqual(self.ask(self.member_emp).approver, self.meg)

    def test_a_manager_with_only_a_my_space_login_is_passed_over(self):
        self.assertFalse(can_decide_leave(self.lee))
        self.assertIsNone(self.ask(self.sam).approver)

    def test_a_manager_whose_dashboard_login_is_switched_off_is_passed_over(self):
        self.meg_login.is_active = False
        self.meg_login.save()
        self.meg.refresh_from_db()
        self.assertIsNone(resolve_approver_for_leave(self.member_emp, self.company))

    def test_a_dashboard_login_is_found_by_the_work_address_when_nothing_links_it(self):
        Employee.objects.filter(pk=self.meg.pk).update(company_user=None)
        self.meg.refresh_from_db()
        self.assertTrue(can_decide_leave(self.meg))
        # ...but only one that is switched on, and only one of the same company.
        self.meg_login.is_active = False
        self.meg_login.save()
        self.assertFalse(can_decide_leave(self.meg))
        self.login(self.rival, 'lee@test.local', 'Lee Elsewhere', 'admin')
        self.assertFalse(can_decide_leave(self.lee))

    def test_with_no_manager_nobody_is_named(self):
        # It used to fall back to "any login that has an HR record", who need be neither a manager nor in HR.
        self.assertIsNone(self.sam.manager.manager_id)
        self.assertIsNone(resolve_approver_for_leave(self.lee, self.company))
        self.assertIsNone(resolve_approver_for_leave(self.admin_emp, self.company))

    # ---- so it is on somebody's list ------------------------------------------------

    def test_a_request_with_nobody_named_is_on_the_hr_admins_my_work(self):
        self.ask(self.sam)
        [item] = [i for i in my_work.for_company_user(self.admin) if i['kind'] == 'leave']
        self.assertEqual((item['title'], item['link']),
                         ('Leave request from Sam Staff', '/hr/dashboard?tab=leave&view=all'))

    def test_the_alert_opens_the_view_the_request_is_on(self):
        self.ask(self.member_emp)                                   # Meg is named
        self.assertEqual(bell_links(self.meg_login), ['/hr/dashboard?tab=leave'])
        # An HR admin who is not the approver finds it under "All", not "Pending for me".
        self.assertEqual(bell_links(self.admin), ['/hr/dashboard?tab=leave&view=all'])

    def test_an_hr_admin_who_is_the_approver_is_told_once(self):
        self.sam.manager = self.admin_emp
        self.sam.save()
        self.ask(self.sam)
        self.assertEqual(bell_links(self.admin), ['/hr/dashboard?tab=leave'])

    def test_nobody_is_told_about_their_own_request(self):
        self.meg.manager = self.meg                                 # a record that names itself
        self.meg.save()
        self.leave_request(self.meg, approver=self.meg)
        self.assertEqual(bell_links(self.meg_login), [])
        self.assertEqual(len(bell_links(self.admin)), 1)            # the HR admin still hears

    # ---- the ones already stuck -----------------------------------------------------

    def test_requests_already_waiting_on_someone_who_cannot_decide_are_freed(self):
        stuck = self.leave_request(self.sam, approver=self.lee)
        fine = self.leave_request(self.member_emp, approver=self.meg)
        decided = self.leave_request(self.sam, approver=self.lee, status='approved')
        free_stuck(apps, None)
        for lr in (stuck, fine, decided):
            lr.refresh_from_db()
        self.assertIsNone(stuck.approver)
        self.assertEqual(fine.approver, self.meg)
        self.assertEqual(decided.approver, self.lee)                # a decided request keeps its history

    def test_freeing_reads_a_login_by_link_or_by_address_and_only_if_switched_on(self):
        by_address = Employee.objects.create(company=self.company, full_name='Ann Address',
                                             work_email='MEG@test.local')
        off_login = self.login(self.company, 'off@test.local', 'Olly Off', 'manager')
        off = self.employee(off_login, 'Olly Off')
        off_login.is_active = False
        off_login.save()
        elsewhere = Employee.objects.create(company=self.company, full_name='Rhea Namesake',
                                            work_email='rhea@test.local')    # a login of the other company
        requests = {e.full_name: self.leave_request(self.sam, approver=e) for e in (by_address, off, elsewhere)}
        free_stuck(apps, None)
        left = {name: LeaveRequest.objects.get(pk=lr.pk).approver_id for name, lr in requests.items()}
        self.assertEqual(left, {'Ann Address': by_address.id, 'Olly Off': None, 'Rhea Namesake': None})
