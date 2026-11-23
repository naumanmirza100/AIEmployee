"""Leave balances, from Mahnoor's all-agents test (20 Nov 2026).

- HR 1: any caller could set a leave's day count: 10 working days booked as 0.5, a sick day of -5 that added days.
- HR 9: editing a pending request skipped the balance check and took the day count from the caller.
- HR 10: withdrawing a leave under way gave back every day.
"""
from datetime import date, timedelta
from decimal import Decimal

from api.views import hr_agent as views
from hr_agent.leave_helpers import working_days_between
from hr_agent.models import LeaveBalance, LeaveRequest

from .base import HRTestCase


def next_monday(after_days=14):
    day = date.today() + timedelta(days=after_days)
    return day + timedelta(days=(7 - day.weekday()) % 7)


class DayCounts(HRTestCase):

    def setUp(self):
        super().setUp()
        self.balance(employee=self.member_emp, accrued_days=Decimal('20'))
        self.start = next_monday()
        self.end = self.start + timedelta(days=11)            # Monday to the next Friday: 10 working days
        self.days = float(working_days_between(self.start, self.end, self.company))

    def ask(self, actor, days=None, **extra):
        data = {'employee_id': self.member_emp.id, 'leave_type': 'vacation',
                'start_date': self.start.isoformat(), 'end_date': self.end.isoformat(), **extra}
        if days is not None:
            data['days_requested'] = days
        return self.call(views.submit_leave_request, actor, data)

    def test_a_member_gets_the_working_days_whatever_they_send(self):
        for days in (0.5, -5):
            with self.subTest(days=days):
                code, body = self.ask(self.member, days)
                self.assertEqual(code, 201, body)
                self.assertEqual(body['data']['days_requested'], self.days)
                LeaveRequest.objects.filter(pk=body['data']['id']).delete()

    def test_an_hr_admin_corrects_within_the_dates(self):
        code, body = self.ask(self.admin, 1)
        self.assertEqual((code, body['data']['days_requested']), (201, 1.0), body)
        for days in (-5, self.days + 1):
            with self.subTest(days=days):
                code, body = self.ask(self.admin, days)
                self.assertEqual(code, 400, body)
                self.assertIn('days_requested must be between 0 and', body['message'])

    def test_an_edit_takes_the_days_from_the_dates_and_is_held_to_the_balance(self):
        code, body = self.call(views.submit_leave_request, self.member, {
            'employee_id': self.member_emp.id, 'leave_type': 'vacation',
            'start_date': self.start.isoformat(), 'end_date': self.start.isoformat()})
        self.assertEqual((code, body['data']['days_requested']), (201, 1.0), body)
        lr_id = body['data']['id']
        far = self.start + timedelta(days=32)                 # five weeks of working days: over the 20
        code, body = self.call(views.update_leave_request, self.member,
                               {'end_date': far.isoformat(), 'days_requested': 0.5}, method='patch',
                               request_id=lr_id)
        self.assertEqual(code, 400, body)
        self.assertIn('left this year', body['message'])
        self.assertEqual(float(LeaveRequest.objects.get(pk=lr_id).days_requested), 1.0)
        code, body = self.call(views.update_leave_request, self.member,
                               {'end_date': self.end.isoformat(), 'days_requested': 0.5}, method='patch',
                               request_id=lr_id)
        self.assertEqual((code, body['data']['days_requested']), (200, self.days), body)


class WithdrawingALeaveUnderWay(HRTestCase):

    def setUp(self):
        super().setUp()
        today = date.today()
        self.start, self.end = today - timedelta(days=6), today + timedelta(days=7)
        self.days = float(working_days_between(self.start, self.end, self.company))
        self.taken = float(working_days_between(self.start, today - timedelta(days=1), self.company))
        self.balance(employee=self.member_emp, accrued_days=Decimal('20'), used_days=Decimal(str(self.days)))
        self.lr = self.leave_request(start_date=self.start, end_date=self.end, days_requested=self.days,
                                     status='approved')

    def used(self):
        return float(LeaveBalance.objects.get(employee=self.member_emp, leave_type='vacation').used_days)

    def test_the_person_ends_it_yesterday_and_gets_back_only_the_days_left(self):
        code, body = self.call(views.withdraw_leave_request, self.member, {'reason': 'back early'},
                               request_id=self.lr.id)
        self.assertEqual(code, 200, body)
        self.assertTrue(body['data']['ended_early'])
        self.lr.refresh_from_db()
        self.assertEqual((self.lr.status, self.lr.end_date), ('approved', date.today() - timedelta(days=1)))
        self.assertEqual(float(self.lr.days_requested), self.taken)
        self.assertEqual(body['data']['days_restored'], self.days - self.taken)
        self.assertEqual(self.used(), self.taken)

    def test_an_hr_admin_can_still_give_back_every_day(self):
        code, body = self.call(views.withdraw_leave_request, self.admin, {'reason': 'correction'},
                               request_id=self.lr.id)
        self.assertEqual(code, 200, body)
        self.lr.refresh_from_db()
        self.assertEqual((self.lr.status, self.used()), ('withdrawn', 0.0))
