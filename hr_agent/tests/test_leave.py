"""The leave engine: balances must never double-spend or leak days
(HR-DATA-3, plus the locking behaviour that was already correct)."""
from datetime import date, timedelta
from decimal import Decimal

from api.views import hr_agent as views
from hr_agent.models import LeaveBalance, LeaveRequest, leave_year_start

from .base import HRTestCase


class BalanceKeyTests(HRTestCase):
    """HR-DATA-3 — accrual wrote one row and approval another, so accrued days
    and used days never met."""

    def test_every_writer_uses_the_leave_year_row(self):
        lr = self.leave_request(employee=self.member_emp, approver=self.admin_emp,
                                days_requested=2)
        self.call(views.decide_leave_request, self.admin, {'action': 'approve'},
                  request_id=lr.id)

        self.call(views.adjust_leave_balance, self.admin,
                  {'leave_type': 'vacation', 'set_accrued_days': 25, 'reason': 'annual grant'},
                  employee_id=self.member_emp.id)

        rows = LeaveBalance.objects.filter(employee=self.member_emp, leave_type='vacation')
        self.assertEqual(rows.count(), 1, 'accrual, approval and adjustment must share one row')
        row = rows.first()
        self.assertEqual(row.period_start, leave_year_start())
        self.assertEqual(float(row.accrued_days), 25.0)
        self.assertEqual(float(row.used_days), 2.0)
        self.assertEqual(row.remaining, 23.0)


class ApprovalTests(HRTestCase):
    """Behaviour that was already right — pinned so the fixes around it can't
    break it."""

    def setUp(self):
        super().setUp()
        self.balance(employee=self.member_emp, accrued_days=Decimal('20'))
        self.lr = self.leave_request(employee=self.member_emp, approver=self.admin_emp,
                                     days_requested=3)

    def test_approval_deducts_once(self):
        code, body = self.call(views.decide_leave_request, self.admin, {'action': 'approve'},
                               request_id=self.lr.id)
        self.assertEqual(code, 200, body)
        row = LeaveBalance.objects.get(employee=self.member_emp, leave_type='vacation',
                                       period_start=leave_year_start())
        self.assertEqual(float(row.used_days), 3.0)

    def test_a_second_approval_is_refused_and_does_not_double_deduct(self):
        self.call(views.decide_leave_request, self.admin, {'action': 'approve'},
                  request_id=self.lr.id)
        code, _ = self.call(views.decide_leave_request, self.admin, {'action': 'approve'},
                            request_id=self.lr.id)
        self.assertEqual(code, 400)
        row = LeaveBalance.objects.get(employee=self.member_emp, leave_type='vacation',
                                       period_start=leave_year_start())
        self.assertEqual(float(row.used_days), 3.0)

    def test_rejection_deducts_nothing(self):
        self.call(views.decide_leave_request, self.admin, {'action': 'reject'},
                  request_id=self.lr.id)
        row = LeaveBalance.objects.get(employee=self.member_emp, leave_type='vacation',
                                       period_start=leave_year_start())
        self.assertEqual(float(row.used_days), 0.0)


class WithdrawTests(HRTestCase):
    """Withdrawal returns the days exactly once and never goes negative."""

    def setUp(self):
        super().setUp()
        self.balance(employee=self.member_emp, accrued_days=Decimal('20'))
        self.lr = self.leave_request(employee=self.member_emp, approver=self.admin_emp,
                                     days_requested=3)
        self.call(views.decide_leave_request, self.admin, {'action': 'approve'},
                  request_id=self.lr.id)

    def _row(self):
        return LeaveBalance.objects.get(employee=self.member_emp, leave_type='vacation',
                                        period_start=leave_year_start())

    def test_withdraw_restores_the_days(self):
        code, body = self.call(views.withdraw_leave_request, self.member,
                               {'reason': 'trip cancelled'}, request_id=self.lr.id)
        self.assertEqual(code, 200, body)
        self.assertEqual(float(self._row().used_days), 0.0)

    def test_withdraw_twice_restores_once(self):
        self.call(views.withdraw_leave_request, self.member, {'reason': 'cancelled'},
                  request_id=self.lr.id)
        code, _ = self.call(views.withdraw_leave_request, self.member, {'reason': 'again'},
                            request_id=self.lr.id)
        self.assertEqual(code, 400)
        self.assertEqual(float(self._row().used_days), 0.0)

    def test_withdraw_needs_a_reason(self):
        code, _ = self.call(views.withdraw_leave_request, self.member, {},
                            request_id=self.lr.id)
        self.assertEqual(code, 400)

    def test_used_days_never_go_negative(self):
        LeaveBalance.objects.filter(employee=self.member_emp).update(used_days=Decimal('1'))
        self.call(views.withdraw_leave_request, self.member, {'reason': 'cancelled'},
                  request_id=self.lr.id)
        self.assertGreaterEqual(float(self._row().used_days), 0.0)

    def test_an_employee_cannot_withdraw_a_past_leave(self):
        LeaveRequest.objects.filter(pk=self.lr.pk).update(
            start_date=date.today() - timedelta(days=10),
            end_date=date.today() - timedelta(days=5))
        code, _ = self.call(views.withdraw_leave_request, self.member, {'reason': 'oops'},
                            request_id=self.lr.id)
        self.assertEqual(code, 400)

    def test_an_hr_admin_can_correct_a_past_leave(self):
        LeaveRequest.objects.filter(pk=self.lr.pk).update(
            start_date=date.today() - timedelta(days=10),
            end_date=date.today() - timedelta(days=5))
        code, body = self.call(views.withdraw_leave_request, self.admin,
                               {'reason': 'data correction'}, request_id=self.lr.id)
        self.assertEqual(code, 200, body)


class CancelTests(HRTestCase):
    """Cancel is for pending requests only, so no balance is involved."""

    def test_cancel_a_pending_request(self):
        lr = self.leave_request(employee=self.member_emp)
        code, body = self.call(views.cancel_leave_request, self.member, {},
                               request_id=lr.id)
        self.assertEqual(code, 200, body)
        lr.refresh_from_db()
        self.assertEqual(lr.status, 'cancelled')

    def test_an_approved_request_cannot_be_cancelled(self):
        self.balance(employee=self.member_emp, accrued_days=Decimal('20'))
        lr = self.leave_request(employee=self.member_emp, approver=self.admin_emp)
        self.call(views.decide_leave_request, self.admin, {'action': 'approve'},
                  request_id=lr.id)
        code, _ = self.call(views.cancel_leave_request, self.member, {}, request_id=lr.id)
        self.assertEqual(code, 400)

    def test_a_colleague_cannot_cancel_someone_elses_request(self):
        lr = self.leave_request(employee=self.admin_emp)
        code, _ = self.call(views.cancel_leave_request, self.member, {}, request_id=lr.id)
        self.assertEqual(code, 403)
