"""An employee uses HR from their own login, in My Space.

Every HR address took dashboard logins only. An employee could not see their leave
balance, ask for leave or ask HR a question; somebody with a dashboard login had to
do it for them, and My Space's Profile page sent them to a page they could not open.
"""
import json
from datetime import date, timedelta
from unittest import mock

from django.test import Client
from rest_framework.authtoken.models import Token

from core.models import CompanyModulePurchase
from hr_agent.models import LeaveBalance, LeaveRequest
from project_manager_agent.models import PMNotification

from .base import HRTestCase


def next_monday():
    today = date.today()
    return today + timedelta(days=7 - today.weekday())


class MySpaceHRTests(HRTestCase):

    def setUp(self):
        super().setUp()
        self.sara = self.employee_with_login('sara', 'Sara Iqbal', self.company, self.admin)
        self.sara.manager = self.admin_emp
        self.sara.save(update_fields=['manager'])
        self.client_sara = Client(HTTP_AUTHORIZATION=f'Token {Token.objects.create(user=self.sara.user).key}')
        start = date(date.today().year, 1, 1)
        LeaveBalance.objects.create(employee=self.sara, leave_type='vacation', accrued_days=14, carried_over_days=2,
                                    used_days=3, period_start=start)

    def get(self, client=None):
        response = (client or self.client_sara).get('/api/user/hr')
        return response.status_code, json.loads(response.content)

    def post(self, url, payload, client=None):
        response = (client or self.client_sara).post(url, json.dumps(payload), content_type='application/json')
        return response.status_code, json.loads(response.content)

    def ask_for_leave(self, **changed):
        monday = next_monday()
        payload = {'leave_type': 'vacation', 'start_date': (monday + timedelta(days=3)).isoformat(),
                   'end_date': (monday + timedelta(days=4)).isoformat(), 'reason': 'Family wedding', **changed}
        return self.post('/api/user/hr/leave', payload)

    def test_she_sees_her_own_record_balance_and_leave(self):
        self.leave_request(employee=self.sara)
        self.leave_request(employee=self.member_emp)                       # someone else's
        code, body = self.get()
        self.assertEqual(code, 200, body)
        data = body['data']
        self.assertEqual((data['employee']['full_name'], data['employee']['manager']), ('Sara Iqbal', 'Dana Admin'))
        [balance] = data['balances']
        self.assertEqual((balance['label'], balance['remaining']), ('Vacation / PTO', 13.0))
        self.assertEqual(len(data['leave_requests']), 1)

    def test_she_asks_for_two_days_and_her_approver_is_told(self):
        code, body = self.ask_for_leave()
        self.assertEqual(code, 201, body)
        lr = LeaveRequest.objects.get(pk=body['data']['id'])
        self.assertEqual((lr.employee_id, lr.status, float(lr.days_requested), lr.approver_id),
                         (self.sara.id, 'pending', 2.0, self.admin_emp.id))
        self.assertTrue(PMNotification.objects.filter(company_user=self.admin,
                                                      title='Leave request from Sara Iqbal').exists())

    def test_she_cannot_file_or_cancel_anyone_else_s_leave(self):
        code, body = self.ask_for_leave(employee_id=self.member_emp.id)    # ignored: the login decides who
        self.assertEqual(LeaveRequest.objects.get(pk=body['data']['id']).employee_id, self.sara.id)
        theirs = self.leave_request(employee=self.member_emp)
        self.assertEqual(self.post(f'/api/user/hr/leave/{theirs.id}/cancel', {})[0], 404)
        theirs.refresh_from_db()
        self.assertEqual(theirs.status, 'pending')

    def test_she_cancels_her_own_while_it_waits_but_not_after_a_decision(self):
        mine = self.leave_request(employee=self.sara)
        self.assertEqual(self.post(f'/api/user/hr/leave/{mine.id}/cancel', {})[0], 200)
        mine.refresh_from_db()
        self.assertEqual(mine.status, 'cancelled')
        decided = self.leave_request(employee=self.sara, status='approved')
        self.assertEqual(self.post(f'/api/user/hr/leave/{decided.id}/cancel', {})[0], 400)

    def test_wrong_dates_and_kinds_are_refused_with_the_reason(self):
        monday = next_monday()
        code, body = self.ask_for_leave(start_date=monday.isoformat(), end_date=(monday - timedelta(days=1)).isoformat())
        self.assertEqual((code, body['message']), (400, 'end_date must be on or after start_date'))
        self.assertEqual(self.ask_for_leave(leave_type='holiday-on-the-moon')[0], 400)

    def test_her_question_is_answered_as_an_employee_s_from_her_own_record(self):
        answer = {'answer': 'You have 13 days left, and may carry 5 into next year.', 'has_verified_info': True,
                  'citations': [{'title': 'Leave Policy 2026', 'document_id': None}] * 2}
        with mock.patch('core.HR_agent.hr_agent.HRAgent.answer_question', return_value=answer) as ask:
            code, body = self.post('/api/user/hr/ask', {'question': 'How many days of annual leave do I have left?'})
        self.assertEqual(code, 200, body)
        self.assertEqual(body['data']['sources'], [{'title': 'Leave Policy 2026'}])
        self.assertEqual(ask.call_args.kwargs, {'asker_role': 'employee', 'asker_employee': self.sara,
                                                'search_query': None, 'wants_everything': None})

    def test_without_the_hr_agent_or_an_hr_record_the_page_says_so(self):
        CompanyModulePurchase.objects.filter(company=self.company).update(status='cancelled')
        code, body = self.get()
        self.assertEqual((code, body['data']['available']), (200, False))
        self.assertEqual(self.ask_for_leave()[0], 400)      # not 403: My Space signs a person out on a 403

    def test_when_the_company_s_ai_cannot_be_used_she_is_told_politely(self):
        from core.api_key_service import QuotaExhausted
        with mock.patch('core.HR_agent.hr_agent.HRAgent.answer_question', side_effect=QuotaExhausted()):
            code, body = self.post('/api/user/hr/ask', {'question': 'How many days do I have?'})
        self.assertEqual(code, 503)
        self.assertNotIn('token', body['message'].lower())

    def test_a_dashboard_login_s_token_is_not_taken(self):
        from core.models import CompanyUserToken
        key = CompanyUserToken.objects.get_or_create(company_user=self.admin)[0].key
        self.assertEqual(self.get(Client(HTTP_AUTHORIZATION=f'Token {key}'))[0], 401)

    def test_the_decision_reaches_her_with_a_link_to_her_leave(self):
        from hr_agent import alerts
        from core.models import Notification
        lr = self.leave_request(employee=self.sara)
        lr.status = 'approved'
        lr.save(update_fields=['status'])
        alerts.leave_decided(lr, decided_by=self.admin)
        note = Notification.objects.filter(user=self.sara.user).latest('id')
        self.assertIn('Leave approved', note.title)
        self.assertEqual(note.link, '/me/hr')
