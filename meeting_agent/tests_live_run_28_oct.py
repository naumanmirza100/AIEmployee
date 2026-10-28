"""Found in Executive Meeting's live run on 28 Oct 2026: "Create with AI" drafted anything it was given.

"What's the weather in Islamabad today?" became a meeting called Weather Inquiry, "Delete all my meetings" a meeting
of that name, "Tell me a joke" and "Show me the salaries of everyone" tasks. A name that is nobody in the company was
dropped without a word, and "yesterday at 9am" drafted a meeting in the past.
"""
from unittest import mock

from api.views import meeting_agent as views
from meeting_agent import tests_time_and_answers as base


class DraftTests(base.ExecCase):

    def draft(self, view, answer, prompt='x'):
        with mock.patch.object(views, '_get_agent') as agent:
            agent.return_value.parse_meeting_request.return_value = answer
            agent.return_value.parse_task_request.return_value = answer
            return self.call(view, self.nadia, data={'prompt': prompt})

    def test_a_message_that_is_not_a_meeting_drafts_nothing(self):
        code, body = self.draft(views.meeting_ai_parse, {'title': 'Weather Inquiry', 'kind': 'other'})
        self.assertEqual(code, 422)
        self.assertIn('does not ask for a meeting', body['message'])

    def test_private_records_are_refused(self):
        code, body = self.draft(views.task_ai_parse, {'title': 'Retrieve Employee Salaries', 'kind': 'not_allowed'})
        self.assertEqual(code, 422)
        self.assertIn("Sorry, I can't help with that", body['message'])
        code, body = self.draft(views.task_ai_parse, {'title': 'Tell a joke', 'kind': 'other'})
        self.assertEqual((code, 'does not describe a task' in body['message']), (422, True))

    def test_a_name_that_is_nobody_and_a_time_that_passed_are_said(self):
        code, body = self.draft(views.meeting_ai_parse, {
            'title': 'Meeting with Elon Musk', 'kind': 'meeting', 'participant_hints': ['Elon Musk'],
            'scheduled_at': '2026-10-27T09:00:00', 'time_problem': 'there is no 25:00'})
        self.assertEqual(code, 200, body)
        said = ' '.join(body['warnings'])
        self.assertIn('No one called Elon Musk', said)
        self.assertIn('there is no 25:00', said)
        self.assertIn('already passed', said)

    def test_answer_buttons_point_at_the_servers_real_address(self):
        # The live site sets BACKEND_URL only; the buttons went to http://localhost:8000, in PM's invitations too.
        from django.test import override_settings
        from api.views.notification import build_meeting_email_action_url
        with override_settings(BACKEND_URL='https://api.example.test', BACKEND_PUBLIC_URL=None, PUBLIC_BACKEND_URL=None):
            seat = mock.Mock(id=7)
            self.assertTrue(views.answer_link(seat, 'accepted').startswith('https://api.example.test/api/meetings/'))
            self.assertTrue(build_meeting_email_action_url(3, 4, 'accepted').startswith('https://api.example.test/'))

    def test_a_briefing_for_a_meeting_is_written_from_it(self):
        from django.utils import timezone
        from meeting_agent.models import MeetingActionItem, MeetingNote
        board = self.meeting(timezone.now(), title='Board review')
        MeetingNote.objects.create(meeting=board, ai_summary='FinEdge renewal agreed.', key_decisions=['Renew for a year'])
        MeetingActionItem.objects.create(meeting=board, title='Send the acceptance', owner_name='Usman Tariq')
        with mock.patch.object(views, '_get_agent') as agent:
            agent.return_value.create_briefing.return_value = '# Briefing'
            self.call(views.document_draft, self.nadia, data={'doc_type': 'briefing', 'meeting_id': board.id})
        context = agent.return_value.create_briefing.call_args[0][1]
        for said in ('Board review', 'Renew for a year', 'Send the acceptance (Usman Tariq)', 'Prepared by: Nadia Rehman'):
            self.assertIn(said, context)

    def test_an_answer_in_a_list_is_read_and_an_unreadable_one_drafts_nothing(self):
        # The film's board review failed with a server error: the AI had put its one answer in a list (29 Oct 2026).
        from meeting_agent.ai_agents.meeting_scheduling_agent import MeetingSchedulingAgent
        from meeting_agent.ai_agents.task_prioritization_agent import TaskPrioritizationAgent
        for agent in (MeetingSchedulingAgent, TaskPrioritizationAgent):
            self.assertEqual(agent._extract_json('```json\n[{"title": "Board review"}]\n```'), {'title': 'Board review'})
            self.assertEqual(agent._extract_json('["Board review"]'), {})
        for answer in ({}, ['Board review']):
            code, body = self.draft(views.meeting_ai_parse, answer)
            self.assertEqual(code, 422, body)
            self.assertIn('could not be read', body['message'])

    def test_minutes_do_not_print_none_for_an_item_with_no_date(self):
        # "Update pipeline sheet ... | Owner: Bilal Ahmed | Due: None" in the film's minutes (29 Oct 2026).
        from meeting_agent.ai_agents.document_authoring_agent import DocumentAuthoringAgent
        agent = DocumentAuthoringAgent.__new__(DocumentAuthoringAgent)
        agent.log_action = lambda *a, **k: None
        agent.system_prompt = ''
        with mock.patch.object(DocumentAuthoringAgent, '_call_llm', create=True, return_value='# Minutes') as llm:
            agent.write_minutes('Board review', '29 Oct 2026', ['Bilal Ahmed'], 'Summary', [
                {'title': 'Update the pipeline sheet', 'assignee_hint': 'Bilal Ahmed', 'due_date': None},
                {'title': 'Book the movers', 'assignee_hint': None}], ['Renew FinEdge'])
        prompt = llm.call_args[0][0]
        self.assertIn('Owner: Bilal Ahmed | Due: no date set', prompt)
        self.assertIn('Book the movers | Owner: not named | Due: no date set', prompt)
        self.assertNotIn('None', prompt)

    def test_the_digest_gives_a_meeting_its_time_as_typed_not_as_utc(self):
        # "a Quick FinEdge check-in with Bilal at 03:25 UTC", of a meeting at 03:25 in Karachi (film, 29 Oct 2026).
        from datetime import datetime
        from meeting_agent import clock
        from meeting_agent.ai_agents.proactive_notification_agent import ProactiveNotificationAgent
        from meeting_agent.tests_time_and_answers import typed
        today = clock.today(self.company)
        self.meeting(typed(datetime(today.year, today.month, today.day, 3, 25)), title='Quick FinEdge check-in')
        agent = ProactiveNotificationAgent.__new__(ProactiveNotificationAgent)
        agent.log_action = lambda *a, **k: None
        agent.system_prompt = ''
        with mock.patch.object(ProactiveNotificationAgent, '_call_llm', create=True, return_value='{}') as llm:
            agent.generate_daily_digest(self.nadia.id, 'Nadia')
        prompt = llm.call_args[0][0]
        self.assertIn('"time": "03:25"', prompt)
        self.assertNotIn('+00:00', prompt)

    def test_a_meeting_request_without_a_kind_is_still_drafted(self):
        code, body = self.draft(views.meeting_ai_parse, {'title': 'Board review', 'scheduled_at': '2099-01-05T11:00:00'})
        self.assertEqual(code, 200, body)
        self.assertEqual((body['data']['title'], body['warnings']), ('Board review', []))


class OwnerTests(base.EmployeeCase):

    def test_an_employee_named_in_the_notes_is_the_owner(self):
        # Matched to logins only, an employee's action item, and the task made from it, went to nobody.
        self.assertEqual(views._member_named(self.company, 'Sana Iqbal'), self.seat_login)
        self.assertEqual(views._member_named(self.company, 'sana'), self.seat_login)
        self.assertEqual(views._member_named(self.company, 'Nadia Rehman'), self.nadia)
        self.assertIsNone(views._member_named(self.company, 'Nobody Here'))

    def test_an_employees_action_item_becomes_their_task_and_they_hear_of_it(self):
        # Clean run, 29 Oct: the seat is never an active login, so the task made from Usman's item went to nobody,
        # and an employee given a task got nothing in their bell.
        from core.models import Notification
        from meeting_agent.models import MeetingActionItem
        item = MeetingActionItem.objects.create(meeting=self.board, title='Send the acceptance', assignee=self.seat_login,
                                                due_date='2026-11-06')
        code, body = self.call(views.action_item_convert_to_task, self.nadia, item_id=item.id)
        self.assertEqual(code, 201, body)
        self.assertEqual([a['id'] for a in body['task']['assignees']], [self.seat_login.id])
        told = Notification.objects.get(user=self.sana, type='exec_task_assigned')
        self.assertIn('06 Nov 2026', told.message)

    def test_a_new_task_for_an_employee_reaches_their_bell(self):
        from core.models import Notification
        code, body = self.call(views.task_list, self.nadia, data={
            'title': 'Hiring plan', 'due_date': '2026-11-04',
            'assignees': [{'id': self.seat_login.id, 'user_type': 'company_user'}]})
        self.assertEqual(code, 201, body)
        self.assertTrue(Notification.objects.filter(user=self.sana, type='exec_task_assigned').exists())
