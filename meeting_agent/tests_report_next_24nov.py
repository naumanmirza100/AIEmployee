"""The Executive Meeting items from the test report's "Next" and "Later" lists (24 Nov 2026).

1  Bad typed values: server errors, or saved and taking the meeting off the calendar.
2  One person invited twice: their dashboard login and their employee record.
3  "End of next week" put on the wrong day.
4  The AI scheduler endpoint made meetings with nobody invited (decision D18: it books nothing).
5  A subtask moved past its parent; a cancelled meeting accepted; the email link answering on a plain GET; invitations
   for a meeting in the past (D19); another company's meeting's document.
6  Write-ups: the briefing's invented department and pasted prompt; a held meeting's agenda; the week plan's summary;
   the digest's overdue count.
7  The empty plain-text part of the emails; invitees reading the notes (D20).
"""
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.utils import timezone

from api.views import meeting_agent as views
from core.models import CompanyUser
from meeting_agent.models import (
    ExecutiveMeeting, ExecutiveMeetingParticipant, ExecutiveTask, MeetingActionItem, MeetingNote,
)

from . import tests_time_and_answers as base


def later(days=3, hour=11):
    return base.typed(timezone.now().astimezone(base.KARACHI).replace(hour=hour, minute=0, second=0, microsecond=0)
                      + timedelta(days=days))


class TypedValues(base.ExecCase):

    def create(self, **data):
        data.setdefault('title', 'Q4 planning')
        data.setdefault('scheduled_at', later().isoformat())
        return self.call(views.meeting_list, self.nadia, data=data)

    def test_a_length_that_is_not_whole_minutes_is_refused(self):
        for bad in ('abc', -30, 0, 30.5, 10_000):
            code, body = self.create(duration_minutes=bad)
            self.assertEqual(code, 400, (bad, body))
            self.assertIn('whole number of minutes', body['message'])
        self.assertEqual(self.create(duration_minutes='45')[0], 201)
        self.assertEqual(ExecutiveMeeting.objects.get().duration_minutes, 45)

    def test_a_bad_status_recurrence_or_length_on_edit_is_refused_and_nothing_changes(self):
        meeting = self.meeting(later())
        for data in ({'status': 'banana'}, {'recurrence': 'hourly-ish'}, {'duration_minutes': 'abc'},
                     {'scheduled_at': 'soon'}):
            code, body = self.call(views.meeting_detail, self.nadia, method='patch', data=data, meeting_id=meeting.id)
            self.assertEqual(code, 400, (data, body))
        meeting.refresh_from_db()
        self.assertEqual((meeting.status, meeting.recurrence, meeting.duration_minutes), ('scheduled', 'none', 60))
        code, _ = self.call(views.meeting_detail, self.nadia, method='patch', data={'duration_minutes': 30},
                            meeting_id=meeting.id)
        meeting.refresh_from_db()
        self.assertEqual((code, meeting.duration_minutes), (200, 30))

    def test_dates_and_hours_that_are_not_real_are_refused(self):
        for due in ('next friday', '2026-02-30'):
            code, body = self.call(views.task_list, self.nadia, data={'title': f'Task {due}', 'due_date': due})
            self.assertEqual(code, 400, body)
        task = ExecutiveTask.objects.create(company_user=self.nadia, title='Budget')
        code, _ = self.call(views.task_detail, self.nadia, method='patch', data={'estimated_hours': 'lots'},
                            task_id=task.id)
        self.assertEqual(code, 400)
        code, _ = self.call(views.task_detail, self.nadia, method='patch', data={'estimated_hours': '2.5'},
                            task_id=task.id)
        task.refresh_from_db()
        self.assertEqual((code, task.estimated_hours), (200, Decimal('2.5')))
        item = MeetingActionItem.objects.create(meeting=self.meeting(later()), title='Send the deck')
        code, _ = self.call(views.action_item_detail, self.nadia, method='patch', data={'due_date': 'next week'},
                            item_id=item.id)
        self.assertEqual(code, 400)

    def test_a_subtask_cant_be_moved_past_its_parent(self):
        parent = ExecutiveTask.objects.create(company_user=self.nadia, title='Launch', due_date=date(2026, 12, 4))
        sub = ExecutiveTask.objects.create(company_user=self.nadia, title='Brief', parent_task=parent,
                                           due_date=date(2026, 12, 1))
        code, body = self.call(views.task_detail, self.nadia, method='patch', data={'due_date': '2026-12-20'},
                               task_id=sub.id)
        self.assertEqual(code, 400, body)
        code, _ = self.call(views.task_detail, self.nadia, method='patch',
                            data={'due_date': '2026-12-20', 'allow_after_parent': True}, task_id=sub.id)
        self.assertEqual(code, 200)

    def test_the_week_planner_refuses_a_week_or_hours_it_cant_read(self):
        with mock.patch.object(views, '_get_agent', side_effect=AssertionError('no AI for a bad request')):
            for data in ({'week_start': 'soon'}, {'work_start_hour': 25}, {'work_start_hour': 17, 'work_end_hour': 9}):
                code, body = self.call(views.calendar_plan_week, self.nadia, data=data)
                self.assertEqual(code, 400, (data, body))


class OnePlacePerPerson(base.EmployeeCase):
    """Sana has a dashboard login as well as her employee login, linked on her HR record."""

    def setUp(self):
        super().setUp()
        from hr_agent.models import Employee
        self.sana_login = CompanyUser.objects.create(company=self.company, email='member@margalla.test',
                                                     full_name='Sana Iqbal', role='company_user', password_hash='x',
                                                     is_active=True)
        Employee.objects.update_or_create(company=self.company, work_email='sana@margalla.test',
                                          defaults={'user': self.sana, 'company_user': self.sana_login,
                                                    'full_name': 'Sana Iqbal', 'employment_status': 'active'})

    def test_picked_both_ways_she_is_invited_once_as_her_login(self):
        from core.models import UserProfile
        profile = UserProfile.objects.get(user=self.sana)
        with mock.patch.object(views, '_invite_all') as invited:
            code, body = self.call(views.meeting_list, self.nadia, data={
                'title': 'Catch-up', 'scheduled_at': later(5).isoformat(),
                'participants': [{'user_id': profile.id, 'user_type': 'profile'},
                                 {'user_id': self.sana_login.id, 'user_type': 'company_user'}]})
        self.assertEqual(code, 201, body)
        self.assertEqual(invited.call_args[0][0], [self.sana_login])
        meeting = ExecutiveMeeting.objects.get(title='Catch-up')
        self.assertEqual(list(meeting.participants.values_list('company_user_id', flat=True)), [self.sana_login.id])

    def test_the_draft_lists_her_once(self):
        names = [m['full_name'] for m in views._all_company_members(self.nadia)]
        self.assertEqual(names.count('Sana Iqbal'), 1)

    def test_an_unlinked_namesake_record_is_one_chip_too(self):
        members = [{'id': 7, 'full_name': 'Sana Iqbal', 'email': 'sana@x.test', 'user_type': 'profile'},
                   {'id': 3, 'full_name': 'Sana Iqbal', 'email': 'member@x.test', 'user_type': 'company_user'},
                   {'id': 4, 'full_name': 'Usman Tariq', 'email': 'usman@x.test', 'user_type': 'company_user'}]
        matched = views._match_members_by_hints(members, ['Sana', 'Usman'])
        self.assertEqual([(m['full_name'], m['user_type']) for m in matched],
                         [('Sana Iqbal', 'company_user'), ('Usman Tariq', 'company_user')])


class AnsweringAndInviting(base.EmployeeCase):

    def test_a_cancelled_meeting_cant_be_accepted_in_the_agent(self):
        usman = CompanyUser.objects.create(company=self.company, email='usman@margalla.test', full_name='Usman Tariq',
                                           role='company_user', password_hash='x', is_active=True)
        ExecutiveMeetingParticipant.objects.create(meeting=self.board, company_user=usman)
        ExecutiveMeeting.objects.filter(pk=self.board.pk).update(status='cancelled')
        code, body = self.call(views.meeting_respond, usman, data={'response': 'accepted'}, meeting_id=self.board.id)
        self.assertEqual(code, 400, body)
        self.assertIn('cancelled', body['message'])

    def test_a_meeting_in_the_past_is_kept_and_nobody_is_invited(self):
        from core.models import UserProfile
        profile = UserProfile.objects.get(user=self.sana)
        with mock.patch.object(views, '_invite_all') as invited:
            code, body = self.call(views.meeting_list, self.nadia, data={
                'title': 'Product sync', 'scheduled_at': later(-3).isoformat(),
                'participants': [{'user_id': profile.id, 'user_type': 'profile'}]})
        self.assertEqual(code, 201, body)
        self.assertIn('without inviting anyone', body['note'])
        invited.assert_not_called()

    def test_the_plain_text_part_of_an_invitation_has_its_words_and_links(self):
        views._send_meeting_invite_email(self.seat_login, self.board, 'Nadia Rehman')
        text = views._plain_from_html(self.emails.call_args[0][3])
        self.assertIn('Board review', text)
        self.assertIn('Accept: http', text)
        self.assertNotIn('<', text)

    def test_an_invitee_reads_the_notes_but_doesnt_write_them(self):
        usman = CompanyUser.objects.create(company=self.company, email='usman@margalla.test', full_name='Usman Tariq',
                                           role='company_user', password_hash='x', is_active=True)
        ExecutiveMeetingParticipant.objects.create(meeting=self.board, company_user=usman)
        MeetingNote.objects.create(meeting=self.board, ai_summary='Renewal agreed.')
        code, body = self.call(views.meeting_notes, usman, method='get', meeting_id=self.board.id)
        self.assertEqual((code, body['notes']['ai_summary']), (200, 'Renewal agreed.'))
        code, _ = self.call(views.meeting_notes, usman, data={'transcript': 'x'}, meeting_id=self.board.id)
        self.assertEqual(code, 403)


class TheProjectManagersEmailLinkToo(base.ExecCase):

    def test_opening_the_link_shows_a_button_and_only_pressing_it_answers(self):
        from api.views import notification
        from project_manager_agent.models import MeetingParticipant, ScheduledMeeting
        ali = get_user_model().objects.create_user('ali', email='ali@margalla.test', password='x')
        meeting = ScheduledMeeting.objects.create(organizer=self.nadia, invitee=ali, title='Planning',
                                                  proposed_time=timezone.now() + timedelta(days=2))
        MeetingParticipant.objects.create(meeting=meeting, user=ali, status='pending')
        token = notification.build_meeting_email_action_url(meeting.id, ali.id, 'accepted').rstrip('/').rsplit('/', 1)[1]
        page = notification.meeting_email_action(RequestFactory().get('/'), 'accepted', token).content.decode()
        self.assertIn('<form method="post">', page)
        self.assertEqual(MeetingParticipant.objects.get(meeting=meeting).status, 'pending')
        with mock.patch('api.views.notification.ensure_free'):
            notification.meeting_email_action(RequestFactory().post('/'), 'accepted', token)
        self.assertEqual(MeetingParticipant.objects.get(meeting=meeting).status, 'accepted')


class OtherCompaniesAndTheAIScheduler(base.ExecCase):

    def test_another_companys_meeting_has_no_document(self):
        from core.models import Company
        rival = Company.objects.create(name='Rival', email='rival@test.local')
        theirs = CompanyUser.objects.create(company=rival, email='r@rival.test', full_name='R', role='owner',
                                            password_hash='x', is_active=True)
        meeting = ExecutiveMeeting.objects.create(organizer=theirs, title='Their board', scheduled_at=later(),
                                                  duration_minutes=60)
        with mock.patch.object(views, '_get_agent'):
            code, _ = self.call(views.document_draft, self.nadia, data={'doc_type': 'agenda', 'meeting_id': meeting.id})
        self.assertEqual(code, 404)

    def test_the_ai_scheduler_books_nothing(self):
        agent = mock.Mock()
        agent.parse_meeting_request.return_value = {'title': 'Check-in', 'scheduled_at': later().isoformat(),
                                                    'duration_minutes': 30}
        agent.check_conflicts.return_value = []
        with mock.patch.object(views, '_get_agent', return_value=agent):
            code, body = self.call(views.schedule_meeting_ai, self.nadia, data={'message': 'check-in', 'create': True})
        self.assertEqual(code, 200, body)
        self.assertIn('Nothing was booked', body['message'])
        self.assertFalse(ExecutiveMeeting.objects.exists())


class WriteUps(base.ExecCase):

    def test_end_of_next_week_is_worked_out_in_code(self):
        from meeting_agent.ai_agents.meeting_notetaker_agent import MeetingNotetakerAgent
        self.assertIn('end of next week = Friday 2026-11-27', MeetingNotetakerAgent._dates_hint(date(2026, 11, 17)))
        self.assertIn('end of next week = Friday 2026-12-04', MeetingNotetakerAgent._dates_hint(date(2026, 11, 25)))

    def test_the_briefing_header_is_filled_in_and_the_facts_are_not_its_background(self):
        from meeting_agent.ai_agents.document_authoring_agent import DocumentAuthoringAgent as Agent
        agent = Agent.__new__(Agent)
        agent.system_prompt, agent.log_action = '', lambda *a, **k: None
        with mock.patch.object(Agent, '_call_llm', return_value='# B', create=True) as llm:
            agent.create_briefing('Board review', 'Meeting: Board review.\nNotes: Renewal agreed.',
                                  prepared_by='Nadia Rehman', date='24 Nov 2026')
        prompt = llm.call_args[0][0]
        self.assertIn('**Prepared by:** Nadia Rehman', prompt)
        self.assertIn('**Date:** 24 Nov 2026', prompt)
        self.assertIn('<facts>', prompt)
        background = prompt.split('## Background / Context', 1)[1].split('##', 1)[0]
        self.assertNotIn('Notes: Renewal agreed.', background)

    def test_a_held_meetings_agenda_is_built_from_its_notes(self):
        meeting = self.meeting(later(-2))
        MeetingNote.objects.create(meeting=meeting, ai_summary='Renewal agreed.', key_decisions=['Renew FinEdge'])
        MeetingActionItem.objects.create(meeting=meeting, title='Send the acceptance')
        with mock.patch.object(views, '_get_agent') as agent:
            agent.return_value.draft_agenda.return_value = '# Agenda'
            self.call(views.document_draft, self.nadia, data={'doc_type': 'agenda', 'meeting_id': meeting.id})
        self.assertEqual(agent.return_value.draft_agenda.call_args[0][2], ['Renew FinEdge', 'Send the acceptance'])

    def test_the_week_plan_keeps_tasks_off_the_weekend_and_gives_the_ai_the_figures(self):
        from meeting_agent.ai_agents.calendar_planner_agent import CalendarPlannerAgent
        agent = CalendarPlannerAgent.__new__(CalendarPlannerAgent)
        agent.company_id, agent.system_prompt, agent.log_action = None, '', lambda *a, **k: None
        monday = date(2026, 11, 23)
        meetings = [{'id': 1, 'title': 'Stand-up', 'date': monday.isoformat(), 'time': '10:00',
                     'scheduled_at': f'{monday}T10:00:00', 'duration_minutes': 30}]
        tasks = [{'id': 9, 'title': 'Weekend report', 'due_date': (monday + timedelta(days=5)).isoformat()}]
        with mock.patch.object(CalendarPlannerAgent, '_call_llm', return_value='{}', create=True) as llm:
            plan = agent.plan_week(meetings, tasks, monday.isoformat())
        placed = {d['day_name']: [s['task'] for s in d['suggested_task_slots']] for d in plan['daily_plans']}
        self.assertEqual((placed['Friday'], placed['Saturday']), (['Weekend report'], []))
        prompt = llm.call_args[0][0]
        self.assertIn('1 meeting(s), 30 minutes in all', prompt)
        self.assertIn('Saturday and Sunday are not working days', prompt)

    def test_the_digest_counts_overdue_action_items(self):
        from meeting_agent.ai_agents.proactive_notification_agent import ProactiveNotificationAgent
        meeting = self.meeting(later(-10))
        MeetingActionItem.objects.create(meeting=meeting, title='Post the job', status='open',
                                         due_date=timezone.now().date() - timedelta(days=5))
        agent = ProactiveNotificationAgent.__new__(ProactiveNotificationAgent)
        agent.system_prompt, agent.log_action = '', lambda *a, **k: None
        with mock.patch.object(ProactiveNotificationAgent, '_call_llm', return_value='{}', create=True) as llm:
            digest = agent.generate_daily_digest(self.nadia.id, 'Nadia')
        self.assertEqual(digest['stats']['overdue_action_items'], 1)
        self.assertIn('Overdue action items: 1', llm.call_args[0][0])
        self.assertTrue(digest['pending_action_items'][0]['overdue'])
