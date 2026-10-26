"""Leave allowances for the whole company, balances held to them, and a new starter's workflows run on their whole record.

Found preparing the HR demo (26 Oct 2026):
- a new company's employees had no leave balance at all, and the only ways to give one were an accrual policy with no
  screen, or HR's Adjust button, one person and one leave type at a time;
- nothing checked a balance: people could ask for, and be given, more days than they had;
- the "employee hired" workflows ran the moment the HR record was made, before the Excel import saved the start date
  and manager, so the welcome email said "first day to be confirmed" and the meetings with the manager failed.
"""
from datetime import date, timedelta
from unittest import mock

from api.views import hr_agent as views
from hr_agent import allowances
from hr_agent.models import Employee, LeaveAccrualRun, LeaveBalance, leave_year_start
from hr_agent.tasks import accrue_leave_balances

from .base import HRTestCase


class AllowanceTests(HRTestCase):

    def balance_of(self, employee, leave_type='vacation'):
        return LeaveBalance.objects.get(employee=employee, leave_type=leave_type, period_start=leave_year_start())

    def test_applying_gives_everyone_this_years_balance_and_keeps_what_they_used(self):
        self.balance(self.member_emp, accrued_days=3, used_days=2)
        self.assertEqual(allowances.apply(self.company, {'vacation': 20, 'sick': 10}), 2)
        self.assertEqual((float(self.balance_of(self.member_emp).accrued_days),
                          float(self.balance_of(self.member_emp).used_days)), (20.0, 2.0))
        self.assertEqual(float(self.balance_of(self.admin_emp, 'sick').accrued_days), 10.0)
        self.assertFalse(LeaveBalance.objects.filter(employee=self.rival_emp).exists())

    def test_the_yearly_job_does_not_credit_this_year_again(self):
        allowances.apply(self.company, {'vacation': 20})
        self.assertTrue(LeaveAccrualRun.objects.filter(period_key=str(leave_year_start().year)).exists())
        accrue_leave_balances()
        self.assertEqual(float(self.balance_of(self.member_emp).accrued_days), 20.0)

    def test_zero_switches_a_type_off(self):
        allowances.apply(self.company, {'vacation': 20, 'unpaid': 0})
        self.assertEqual(allowances.current(self.company), {'vacation': 20.0})

    def test_someone_new_gets_theirs(self):
        allowances.apply(self.company, {'vacation': 18})
        with self.captureOnCommitCallbacks(execute=True):
            nina = Employee.objects.create(company=self.company, full_name='Nina New', work_email='nina@test.local',
                                           employment_status='active')
        self.assertEqual(float(self.balance_of(nina).accrued_days), 18.0)

    def test_the_screen(self):
        code, body = self.call(views.leave_allowances, self.admin, {'allowances': {'vacation': 20, 'sick': '10'}})
        self.assertEqual(code, 200, body)
        days = {a['leave_type']: a['days'] for a in body['data']['allowances']}
        self.assertEqual((days['vacation'], days['sick'], days['unpaid']), (20.0, 10.0, 0))
        self.assertEqual(body['data']['employees'], 2)
        code, _ = self.call(views.leave_allowances, self.member, {'allowances': {'vacation': 99}})
        self.assertEqual(code, 403)
        code, body = self.call(views.leave_allowances, self.member, method='get')
        self.assertEqual((code, body['data']['allowances'][0]['days']), (200, 20.0))


class BalanceCheckTests(HRTestCase):

    def ask(self, days, leave_type='vacation'):
        start = date.today() + timedelta(days=30)
        while start.weekday() != 0:
            start += timedelta(days=1)
        return views.make_leave_request(self.member_emp, self.company, {
            'leave_type': leave_type, 'start_date': start.isoformat(),
            'end_date': (start + timedelta(days=days - 1)).isoformat()})

    def test_more_than_is_left_is_refused_with_the_numbers(self):
        allowances.apply(self.company, {'vacation': 3})
        request, refused = self.ask(5)
        self.assertIsNone(request)
        self.assertEqual(refused.data['message'], 'Only 3 days of Vacation / PTO left this year (after requests '
                                                  'still waiting), and this request is 5. Ask for fewer days, or for '
                                                  'Unpaid leave for the rest.')

    def test_requests_still_waiting_count(self):
        allowances.apply(self.company, {'vacation': 4})
        self.assertIsNotNone(self.ask(3)[0])
        self.assertIsNone(self.ask(2)[0])

    def test_unpaid_and_a_company_without_allowances_are_not_held(self):
        allowances.apply(self.company, {'vacation': 1})
        self.assertIsNotNone(self.ask(5, 'unpaid')[0])
        self.assertIsNotNone(self.ask(5, 'sick')[0])        # no sick allowance set: no balance kept


class NewStarterTests(HRTestCase):

    def test_the_hired_workflows_see_the_start_date_and_manager_the_import_saved(self):
        seen = []
        with mock.patch('hr_agent.signals._run_matching_workflows', side_effect=lambda **kw: seen.append(kw)):
            with self.captureOnCommitCallbacks(execute=True):
                nina = Employee.objects.create(company=self.company, full_name='Nina New',
                                               work_email='nina@test.local', employment_status='active')
                # What the import does next, in the same transaction.
                Employee.objects.filter(pk=nina.pk).update(manager=self.admin_emp, job_title='Designer')
        [hired] = [kw for kw in seen if kw['event'] == 'employee_hired']
        self.assertEqual((hired['context']['manager_id'], hired['context']['job_title']),
                         (self.admin_emp.id, 'Designer'))
