"""Action items from a meeting's notes carry dates from the meeting's own week.

The note-taker was never told when the meeting was held, so "by Friday" came back
as a Friday in 2023, and the action items showed dates two years old.
"""
import json
from datetime import datetime, timedelta, timezone as dt_timezone
from unittest import mock
from zoneinfo import ZoneInfo

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from api.views import meeting_agent as views
from core.models import Company, CompanyUser
from meeting_agent.ai_agents.meeting_notetaker_agent import MeetingNotetakerAgent
from meeting_agent.clock import held_on
from meeting_agent.models import ExecutiveMeeting


class NoteDatesTests(TestCase):

    def setUp(self):
        self.company = Company.objects.create(name='Acme', email='acme@test.local', timezone_name='Asia/Karachi')
        self.hamza = CompanyUser.objects.create(company=self.company, email='hamza@test.local', full_name='Hamza',
                                                role='owner', password_hash='x', is_active=True)

    def meeting(self, typed):
        # The agent keeps a time as typed: 23:30 in Karachi is stored as 23:30 UTC.
        return ExecutiveMeeting.objects.create(organizer=self.hamza, title='FinEdge account review',
                                               scheduled_at=typed.replace(tzinfo=dt_timezone.utc))

    def test_the_meeting_day_is_the_day_typed_on_the_company_clock(self):
        yesterday_late = (timezone.now() - timedelta(days=1)).replace(hour=23, minute=30, tzinfo=None)
        self.assertEqual(held_on(self.meeting(yesterday_late)), yesterday_late.date())
        later = self.meeting((timezone.now() + timedelta(days=5)).replace(tzinfo=None))
        today = timezone.now().astimezone(ZoneInfo('Asia/Karachi')).date()
        self.assertEqual(held_on(later), today)          # notes written before the day count as today

    def test_the_note_taker_is_told_the_day(self):
        agent = MeetingNotetakerAgent()
        with mock.patch.object(agent, '_call_llm', return_value='[]') as llm:
            agent.extract_action_items('We agreed Omar sends the figures by Friday.', ['Omar'],
                                       held_on=datetime(2026, 10, 15).date())
        prompt = llm.call_args[0][0]
        self.assertIn('Thursday, 2026-10-15', prompt)
        self.assertIn("'Friday' is the first Friday after it", prompt)

    def test_a_due_date_before_the_meeting_is_not_kept(self):
        typed = (timezone.now() - timedelta(days=2)).replace(hour=11, minute=0, second=0, microsecond=0, tzinfo=None)
        meeting = self.meeting(typed)
        day = typed.date()
        fake = mock.Mock()
        fake.process_full_transcript.return_value = {
            'summary': 'Reviewed sprint 3.', 'key_decisions': ['Renew for a year'], 'followup_email': '',
            'action_items': [
                {'title': 'Send support response times', 'due_date': '2023-10-20', 'priority': 'high'},
                {'title': 'Share load test results', 'due_date': (day + timedelta(days=3)).isoformat()},
                {'title': 'Book the renewal call', 'due_date': 'null'},
            ]}
        request = APIRequestFactory().post('/', {'transcript': 'Hamza: ... Omar: ...'}, format='json')
        force_authenticate(request, user=self.hamza)
        with mock.patch.object(views, '_get_agent', return_value=fake):
            response = views.meeting_notes(request, meeting_id=meeting.id)
        response.render()
        self.assertEqual(response.status_code, 200, json.loads(response.content))
        self.assertEqual(fake.process_full_transcript.call_args.kwargs['held_on'], day)
        dates = dict(meeting.action_items.values_list('title', 'due_date'))
        self.assertEqual(dates, {'Send support response times': None,
                                 'Share load test results': day + timedelta(days=3),
                                 'Book the renewal call': None})
