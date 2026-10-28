"""The rest of Executive Meeting's open gaps, fixed before its demo (28 Oct 2026).

CO-163 the People window's ids, CO-164 long transcripts, CO-166/CO-276 the weekly plan, CO-167 minutes,
CO-168 the overview's figures, CO-171 changes told, CO-209 seats on Team and roles, CO-255 another company's ids,
CO-258 notes made again, CO-261 text in emails.
"""
from datetime import timedelta
import json
from unittest import mock

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from api.views import company_logins
from api.views import meeting_agent as views
from core.models import Company, CompanyModulePurchase, CompanyUser
from meeting_agent import tests_time_and_answers as base
from meeting_agent.ai_agents.calendar_planner_agent import CalendarPlannerAgent
from meeting_agent.ai_agents.meeting_notetaker_agent import MeetingNotetakerAgent, PIECE_CHARS
from meeting_agent.models import ExecNotification, ExecutiveTask, MeetingActionItem, MeetingNote


class GapTests(base.ExecCase):

    def setUp(self):
        super().setUp()
        self.omar = CompanyUser.objects.create(company=self.company, email='omar@margalla.test', full_name='Omar Farooq',
                                               role='company_user', password_hash='x', is_active=True)
        other = Company.objects.create(name='Rival', email='rival@test.local')
        self.stranger = CompanyUser.objects.create(company=other, email='x@rival.test', full_name='X', role='owner',
                                                   password_hash='x', is_active=True)
        self.board = self.meeting(base.typed(timezone.now() + timedelta(days=1)))

    def test_another_companys_person_or_meeting_is_refused(self):                         # CO-255
        item = MeetingActionItem.objects.create(meeting=self.board, title='Send the notice')
        code, _ = self.call(views.action_item_detail, self.nadia, method='patch', item_id=item.id,
                            data={'assignee_id': self.stranger.id})
        self.assertEqual(code, 404)
        code, _ = self.call(views.action_item_detail, self.nadia, method='patch', item_id=item.id,
                            data={'status': 'whatever'})
        self.assertEqual(code, 400)
        theirs = self.meeting(base.typed(timezone.now()), title='Theirs')
        theirs.organizer = self.stranger
        theirs.save()
        code, _ = self.call(views.task_list, self.nadia, data={'title': 'Prep', 'linked_meeting_id': theirs.id})
        self.assertEqual(code, 400)

    def test_notes_made_again_keep_the_old_items_when_the_answer_is_wrong(self):           # CO-258
        MeetingActionItem.objects.create(meeting=self.board, title='Kept')
        with mock.patch.object(views, '_get_agent') as agent:
            agent.return_value.process_full_transcript.return_value = {
                'summary': 'S', 'key_decisions': ['Renew'], 'action_items': ['not a dict', {'title': 'New one'}]}
            code, body = self.call(views.meeting_notes, self.nadia, meeting_id=self.board.id,
                                   data={'transcript': 'We agreed to renew.'})
        self.assertEqual(code, 200, body)
        self.assertEqual(list(self.board.action_items.values_list('title', flat=True)), ['New one'])
        with mock.patch.object(views, '_get_agent') as agent, \
                mock.patch.object(views.MeetingActionItem, 'save', side_effect=ValueError('bad')):
            agent.return_value.process_full_transcript.return_value = {'summary': 'S2', 'action_items': [{'title': 'X'}]}
            self.call(views.meeting_notes, self.nadia, meeting_id=self.board.id, data={'transcript': 'Again.'})
        self.assertEqual(list(self.board.action_items.values_list('title', flat=True)), ['New one'])
        self.assertEqual(MeetingNote.objects.get(meeting=self.board).ai_summary, 'S')

    def test_a_long_transcript_is_read_whole_in_pieces(self):                            # CO-164
        agent = MeetingNotetakerAgent(company_id=self.company.id)
        answers = [json.dumps({'points': [f'part {i}'], 'action_items': [{'title': f'Item {i}'}],
                               'decisions': [f'Decision {i}']}) for i in (1, 2, 3)] + ['- the whole meeting']
        with mock.patch.object(agent, '_call_llm', side_effect=answers) as llm:
            result = agent.process_full_transcript('word ' * (PIECE_CHARS // 2), 'Board')
        self.assertEqual(llm.call_count, 4)                                    # three pieces and the summary
        self.assertEqual([i['title'] for i in result['action_items']], ['Item 1', 'Item 2', 'Item 3'])
        self.assertEqual(result['chars_read'], result['chars_total'])

    def test_the_weekly_plan_places_every_task(self):                                    # CO-166
        agent = CalendarPlannerAgent(company_id=self.company.id)
        tasks = [{'id': i, 'title': f'Task {i}', 'due_date': None} for i in range(30)]
        with mock.patch.object(agent, '_call_llm', return_value='{"weekly_summary": "", "recommendations": []}'):
            plan = agent.plan_week([], tasks, '2026-11-02')
        placed = sum(len(day.get('suggested_task_slots', [])) for day in plan.get('daily_plans', []))
        self.assertEqual(placed + len(plan.get('unscheduled_tasks', [])), 30)

    def test_minutes_keep_the_meetings_own_decisions_and_items(self):                    # CO-167
        MeetingNote.objects.create(meeting=self.board, ai_summary='Lease renewal.', key_decisions=['Renew for two years'])
        MeetingActionItem.objects.create(meeting=self.board, title='Send the notice', owner_name='Sana Iqbal')
        with mock.patch.object(views, '_get_agent') as agent:
            agent.return_value.write_minutes.return_value = 'Minutes'
            self.call(views.document_draft, self.nadia, data={'doc_type': 'minutes', 'meeting_id': self.board.id,
                                                              'summary': 'Typed summary'})
        args = agent.return_value.write_minutes.call_args[0]
        self.assertEqual(args[5], ['Renew for two years'])
        self.assertEqual(args[4][0]['assignee_hint'], 'Sana Iqbal')
        agent.return_value.extract_decisions_and_actions.assert_not_called()

    def test_the_overview_counts_past_twenty(self):                                      # CO-168
        for i in range(25):
            ExecutiveTask.objects.create(company_user=self.nadia, title=f'T{i}', status='todo',
                                         due_date=timezone.now().date() - timedelta(days=3))
        code, body = self.call(views.exec_stats, self.nadia, method='get')
        self.assertEqual(code, 200, body)
        self.assertEqual((body['stats']['total_tasks'], body['stats']['overdue_tasks'], body['stats']['upcoming_meetings']),
                         (25, 25, 1))

    def test_the_people_on_a_task_are_told_what_changed(self):                           # CO-171
        task = ExecutiveTask.objects.create(company_user=self.nadia, title='Send the notice', status='todo')
        task.assignees.add(self.omar)
        self.emails.reset_mock()
        code, _ = self.call(views.task_detail, self.nadia, method='patch', task_id=task.id,
                            data={'due_date': '2026-11-02', 'status': 'in_progress'})
        self.assertEqual(code, 200)
        subject = self.emails.call_args[0][2]
        self.assertEqual((self.emails.call_args[0][0], subject), (self.omar, 'Task changed: Send the notice'))
        self.assertIn('02 Nov 2026', self.emails.call_args[0][3])

    def test_email_text_is_escaped_and_a_link_must_be_a_web_address(self):                # CO-261
        self.board.title = '<b>Board</b>'
        self.board.save()
        views._send_meeting_update_email(self.omar, self.board, 'Nadia <Rehman>', ['title'])
        _, _, subject, html = self.emails.call_args[0]
        self.assertEqual(subject, 'Meeting Updated: <b>Board</b>')                  # a subject is plain text
        self.assertIn('&lt;b&gt;Board&lt;/b&gt;', html)
        self.assertNotIn('<b>Board</b>', html)
        code, _ = self.call(views.meeting_list, self.nadia, data={'title': 'X', 'scheduled_at': '2026-11-03T11:00:00',
                                                                  'meeting_link': 'javascript:alert(1)'})
        self.assertEqual(code, 400)


class SeatTests(base.EmployeeCase):

    def test_a_seat_is_not_a_login_on_team_and_roles(self):                              # CO-209
        listed = company_logins._page(self.nadia)['logins']
        self.assertNotIn(self.seat_login.id, [row['id'] for row in listed])
        request = APIRequestFactory().patch('/', {'is_active': True}, format='json')
        force_authenticate(request, user=self.nadia)
        response = company_logins.company_login(request, login_id=self.seat_login.id)
        self.assertEqual(response.status_code, 400)
        self.seat_login.refresh_from_db()
        self.assertFalse(self.seat_login.is_active)

    def test_adding_the_employee_as_a_login_keeps_their_meetings(self):
        request = APIRequestFactory().post('/', {'email': self.seat_login.email, 'full_name': 'Sana Iqbal',
                                                'role': 'company_user'}, format='json')
        force_authenticate(request, user=self.nadia)
        with mock.patch.object(company_logins, '_invite', return_value=True):
            response = company_logins.company_logins(request)
        self.assertEqual(response.status_code, 201)
        self.seat_login.refresh_from_db()
        self.assertTrue(self.seat_login.is_active)
        self.assertTrue(self.board.participants.filter(company_user=self.seat_login).exists())

    def test_the_people_window_knows_an_employee_from_a_login(self):                     # CO-163
        code, body = self.call(views.meeting_participants, self.nadia, method='get', meeting_id=self.board.id)
        row = body['participants'][0]
        self.assertEqual((row['user_type'], row['user_id']), ('profile', self.seat_login.id))
        self.assertTrue(row['member_id'])
