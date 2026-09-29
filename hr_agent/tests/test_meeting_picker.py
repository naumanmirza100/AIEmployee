"""The HR meeting scheduler's date picker, answered without a second model call.

Same bug as the Project Manager scheduler (see project_manager_agent/tests/
test_meeting_picker.py) plus one of its own: the picker's summary sentence
said e.g. "Wed", and HR's relative-date correction (HR-BUG-07) — which exists
to fix the *model's* reading of words like "next Friday" — could move a picked
date to the following Wednesday. A picked time is not a reading of anything,
so it must be used exactly.
"""

from datetime import timedelta
from unittest import mock

from django.utils import timezone

from api.views import hr_agent as views
from hr_agent.models import HRMeeting

from .base import HRTestCase


def _no_model(*args, **kwargs):
    raise AssertionError('the picker path must not call the model')


class HRMeetingPickerTests(HRTestCase):

    def setUp(self):
        super().setUp()
        # Only employees with an employee login can be invited, and the picker
        # path must still apply that rule — so the invitee needs a real one:
        # an auth user whose profile belongs to this company.
        self.ali = self.employee_with_login('ali', 'Ali Staff', self.company, self.admin)
        self.rival_ali = self.employee_with_login(
            'rali', 'Rival Ali', self.rival, self.rival_admin)

        # A Wednesday *two weeks* out, at 10:00 UTC. The correction resolves
        # "Wed" to the upcoming Wednesday, so if it ran on a picked time it
        # would pull this one a week earlier — visibly. (The upcoming
        # Wednesday itself would be left alone and hide the bug.)
        now = timezone.now()
        days = (2 - now.weekday()) % 7 or 7
        self.when = (now + timedelta(days=days + 7)).replace(
            hour=10, minute=0, second=0, microsecond=0)

    @staticmethod
    def employee_with_login(username, full_name, company, created_by):
        from django.contrib.auth import get_user_model
        from core.models import UserProfile
        from hr_agent.models import Employee
        user = get_user_model().objects.create_user(
            username=username, password='x', email=f'{username}@test.local')
        UserProfile.objects.update_or_create(user=user, defaults={
            'company': company, 'created_by_company_user': created_by, 'role': 'team_member'})
        # hr_agent.signals creates the Employee row for a new employee login;
        # take that one rather than colliding with it.
        employee, _ = Employee.objects.update_or_create(
            company=company, work_email=f'{username}@test.local',
            defaults={'user': user, 'full_name': full_name, 'employment_status': 'active'})
        return employee

    def post(self, participant, name):
        with mock.patch('api.views.hr_agent.HRAgent._call_llm', side_effect=_no_model):
            return self.call(views.hr_meeting_schedule, self.admin, {
                'message': f'Schedule the meeting with {name} on Wed, '
                           f'{self.when:%d %b %Y} for 45 minutes.',
                'pending_intent': {
                    'title': 'Catch-up',
                    'meeting_type': 'one_on_one',
                    'duration_minutes': 45,
                    'participant_ids': [participant.id],
                    'participant_names': [name],
                },
                'proposed_time': self.when.isoformat(),
            })

    def test_the_meeting_lands_on_the_picked_day_not_a_week_later(self):
        code, body = self.post(self.ali, 'Ali Staff')
        self.assertEqual(code, 200, body)
        self.assertEqual(body['data']['action'], 'scheduled', body['data'].get('reply'))
        meeting = HRMeeting.objects.get(company=self.company, title='Catch-up')
        self.assertEqual(meeting.scheduled_at, self.when)
        self.assertEqual(meeting.duration_minutes, 45)
        self.assertIn(self.ali, meeting.participants.all())

    def test_a_participant_from_another_company_is_not_invited(self):
        self.post(self.rival_ali, 'Rival Ali')
        self.assertFalse(
            HRMeeting.objects.filter(participants=self.rival_ali).exists())

    def test_the_login_rule_still_applies(self):
        # Mo has no employee login. The picker path skips the model, not the
        # business rules: this must still be refused, as on the normal path.
        code, body = self.post(self.member_emp, 'Mo Member')
        self.assertEqual(body['data']['action'], 'no_login')
        self.assertFalse(HRMeeting.objects.exists())

    def test_an_unreadable_time_is_refused_plainly(self):
        with mock.patch('api.views.hr_agent.HRAgent._call_llm', side_effect=_no_model):
            code, body = self.call(views.hr_meeting_schedule, self.admin, {
                'message': 'Schedule it.',
                'pending_intent': {'participant_ids': [self.ali.id]},
                'proposed_time': 'not a time',
            })
        self.assertEqual(code, 200)
        self.assertEqual(body['data']['action'], 'error')
        self.assertFalse(HRMeeting.objects.exists())
