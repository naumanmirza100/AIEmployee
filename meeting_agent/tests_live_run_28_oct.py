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
