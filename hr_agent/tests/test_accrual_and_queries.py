"""Accrual safety and query counts (HR-DATA-1, -2, HR-PERF-1, -2, -3)."""
from decimal import Decimal

from hr_agent.models import (
    LeaveAccrualPolicy, LeaveAccrualRun, LeaveBalance, leave_year_start,
)
from hr_agent.tasks import _accrual_period_key, accrue_leave_balances

from .base import HRTestCase


class AccrualIdempotencyTests(HRTestCase):
    """HR-DATA-1 — a redelivered task used to credit everyone twice."""

    def setUp(self):
        super().setUp()
        self.policy = LeaveAccrualPolicy.objects.create(
            company=self.company, leave_type='vacation', period='monthly',
            days_per_period=Decimal('2.5'), is_active=True,
        )

    def _accrued(self, employee):
        row = LeaveBalance.objects.filter(
            employee=employee, leave_type='vacation', period_start=leave_year_start()
        ).first()
        return float(row.accrued_days) if row else None

    def test_one_run_credits_everyone_once(self):
        result = accrue_leave_balances()
        self.assertEqual(result['policies_run'], 1, result)
        self.assertEqual(self._accrued(self.member_emp), 2.5)
        self.assertEqual(self._accrued(self.admin_emp), 2.5)

    def test_a_second_run_in_the_same_period_credits_nothing(self):
        accrue_leave_balances()
        result = accrue_leave_balances()
        self.assertEqual(result['policies_run'], 0, result)
        self.assertEqual(self._accrued(self.member_emp), 2.5)

    def test_a_redelivered_run_credits_nothing(self):
        """The claim row is what stops it — not `last_run_at`, which the old
        code only stamped after the loop it might not finish."""
        accrue_leave_balances()
        LeaveAccrualPolicy.objects.filter(pk=self.policy.pk).update(last_run_at=None)

        result = accrue_leave_balances()

        self.assertEqual(result['policies_run'], 0, result)
        self.assertEqual(self._accrued(self.member_emp), 2.5)

    def test_the_run_is_recorded(self):
        accrue_leave_balances()
        run = LeaveAccrualRun.objects.get(policy=self.policy)
        self.assertEqual(run.period_key, _accrual_period_key('monthly', self.now()))
        self.assertIsNotNone(run.completed_at)
        self.assertEqual(run.employees_credited, 2)

    def test_another_companys_employees_are_not_credited(self):
        accrue_leave_balances()
        self.assertIsNone(self._accrued(self.rival_emp))

    def test_credits_land_on_the_leave_year_row(self):
        """HR-DATA-3 — accrual used to write the period_start=NULL row."""
        accrue_leave_balances()
        rows = LeaveBalance.objects.filter(employee=self.member_emp, leave_type='vacation')
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.first().period_start, leave_year_start())


class AccrualCapTests(HRTestCase):
    """HR-DATA-2 — the cap is applied by the database now, not read-modify-write."""

    def test_the_cap_is_respected(self):
        LeaveAccrualPolicy.objects.create(
            company=self.company, leave_type='vacation', period='monthly',
            days_per_period=Decimal('5'), max_balance=Decimal('6'), is_active=True,
        )
        self.balance(employee=self.member_emp, accrued_days=Decimal('4'))
        accrue_leave_balances()
        row = LeaveBalance.objects.get(employee=self.member_emp, leave_type='vacation',
                                       period_start=leave_year_start())
        self.assertEqual(float(row.accrued_days), 6.0)

    def test_the_cap_counts_carryover(self):
        LeaveAccrualPolicy.objects.create(
            company=self.company, leave_type='vacation', period='monthly',
            days_per_period=Decimal('5'), max_balance=Decimal('10'), is_active=True,
        )
        self.balance(employee=self.member_emp, accrued_days=Decimal('4'),
                     carried_over_days=Decimal('4'))
        accrue_leave_balances()
        row = LeaveBalance.objects.get(employee=self.member_emp, leave_type='vacation',
                                       period_start=leave_year_start())
        self.assertEqual(float(row.accrued_days), 6.0)  # 6 + 4 carried = the 10 cap

    def test_a_balance_already_over_the_cap_is_left_alone(self):
        LeaveAccrualPolicy.objects.create(
            company=self.company, leave_type='vacation', period='monthly',
            days_per_period=Decimal('5'), max_balance=Decimal('10'), is_active=True,
        )
        self.balance(employee=self.member_emp, accrued_days=Decimal('15'))
        accrue_leave_balances()
        row = LeaveBalance.objects.get(employee=self.member_emp, leave_type='vacation',
                                       period_start=leave_year_start())
        self.assertEqual(float(row.accrued_days), 15.0)


class PeriodKeyTests(HRTestCase):
    def test_monthly_and_annual_keys(self):
        from datetime import datetime
        when = datetime(2026, 9, 23)
        self.assertEqual(_accrual_period_key('monthly', when), '2026-09')
        self.assertEqual(_accrual_period_key('annual', when), '2026')

    def test_biweekly_buckets_two_weeks_together(self):
        from datetime import datetime
        first = _accrual_period_key('biweekly', datetime(2026, 9, 21))
        same_fortnight = _accrual_period_key('biweekly', datetime(2026, 9, 28))
        later = _accrual_period_key('biweekly', datetime(2026, 10, 12))
        self.assertEqual(first, same_fortnight)
        self.assertNotEqual(first, later)


class EmployeeListQueryTests(HRTestCase):
    """HR-PERF-1 and -2 — the list ran a per-person backfill and an N+1."""

    def setUp(self):
        super().setUp()
        for i in range(6):
            cu = self.login(self.company, f'extra{i}@test.local', f'Extra {i}', 'company_user')
            self.employee(cu, f'Extra {i}')

    def test_the_query_count_does_not_grow_with_headcount(self):
        from api.views import hr_agent as views
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        def count():
            with CaptureQueriesContext(connection) as ctx:
                code, _ = self.call(views.list_employees, self.admin, method='get')
                self.assertEqual(code, 200)
            return len(ctx)

        before = count()
        cu = self.login(self.company, 'onemore@test.local', 'One More', 'company_user')
        self.employee(cu, 'One More')
        self.assertEqual(count(), before)

    def test_listing_does_not_write(self):
        """It used to create Employee rows during a GET."""
        from api.views import hr_agent as views
        from hr_agent.models import Employee
        before = Employee.objects.count()
        self.call(views.list_employees, self.admin, method='get')
        self.assertEqual(Employee.objects.count(), before)
