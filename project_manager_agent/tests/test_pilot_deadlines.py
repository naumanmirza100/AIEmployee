"""A deadline the user states in Project Pilot is kept to, and moving one is a review card.

From the client test of 25 Oct 2026 (MDS/02-Log/issues/2026-10-25_PM-Client-Test.md):
  E2  "create this project from pdf ... keep its deadline of completion only 10 days from now" got a
      proposal ending 7 December: gpt-4o-mini planned from the size of the brief.
  E3  "change the deadline of this project to 10 days instead, and also change the deadlines of the
      tasks accordingly" got a plain-text question, and "yes it is confirmed" changed nothing.
"""
from datetime import date, timedelta
from unittest import mock

from django.utils import timezone

from api.views import pm_agent
from core.models import Project, Task
from project_manager_agent import pilot_deadlines
from project_manager_agent.ai_agents.project_pilot_agent import ProjectPilotAgent
from project_manager_agent.project_pilot_pipeline import run_project_pilot_pipeline

from .base import PMTestCase

TODAY = date(2026, 10, 25)


class StatedDeadlineTests(PMTestCase):

    def test_the_meeting_wordings_all_mean_four_november(self):
        for text in ('create this project, from pdf and assign tasks to developer users, and also keep its '
                     'deadline of completion only 10 days from now',
                     'make its deadline in 10 days at max, of whole project',
                     'can you change the deadline of this project to 10 days instead'):
            self.assertEqual(pilot_deadlines.stated_deadline(text, TODAY), date(2026, 11, 4), text)

    def test_other_ways_of_saying_it(self):
        cases = {'finish within two weeks': date(2026, 11, 8),
                 'deliver in 10 working days': date(2026, 11, 6),
                 'make it done in a month': date(2026, 11, 25),
                 'deadline: 2026-11-20': date(2026, 11, 20),
                 'complete it by 15 Nov': date(2026, 11, 15),
                 'due by November 3rd': date(2026, 11, 3),
                 'deadline 04/11/2026': date(2026, 11, 4),          # day first, as the card shows dates
                 'it must be ready by 5 jan': date(2027, 1, 5),     # no year: the next 5 January
                 'first demo in 2 weeks, launch in 3 months': date(2027, 1, 25),   # the project ends at the last
                 # From the live chat: the date after "from" is the one being replaced.
                 'now change the deadlines from next 10 days, to extended 20 days, now the dead line of project '
                 'is upto next 20 days': date(2026, 11, 14),
                 'change the deadline from 20 days to 10 days': date(2026, 11, 4),
                 'move the deadline from 15 Nov to 30 Nov': date(2026, 11, 30)}
        for text, expected in cases.items():
            self.assertEqual(pilot_deadlines.stated_deadline(text, TODAY), expected, text)

    def test_a_length_that_is_not_the_deadline_is_left_alone(self):
        for text in ('each task should take 3 days', 'create a project for a 3 day workshop',
                     'plan a sprint of 2 weeks', 'create a project from this brief'):
            self.assertIsNone(pilot_deadlines.stated_deadline(text, TODAY), text)


class FitNewProjectTests(PMTestCase):

    def proposal(self):
        # What gpt-4o-mini proposed for the Zaiqa brief: start 26 Oct, the last task and the project 7 Dec.
        return [{'action': 'create_project', 'project_name': 'Zaiqa Foods Online Ordering',
                 'start_date': '2026-10-26', 'deadline': '2026-12-07'},
                *({'action': 'create_task', 'task_title': f'Step {n}', 'project_id': None, 'due_date': due}
                  for n, due in enumerate(['2026-11-01', '2026-11-10', '2026-11-20', '2026-12-07'], start=1))]

    def test_the_project_gets_the_stated_deadline_and_the_tasks_fit_inside_in_order(self):
        actions = self.proposal()
        self.assertTrue(pilot_deadlines.fit_new_project(actions, date(2026, 11, 4), TODAY))
        self.assertEqual(actions[0]['deadline'], '2026-11-04')
        dues = [a['due_date'] for a in actions[1:]]
        self.assertEqual(dues, sorted(dues))
        self.assertTrue(all('2026-10-26' <= d <= '2026-11-04' for d in dues), dues)
        self.assertEqual(dues[-1], '2026-11-04')
        self.assertTrue(all(date.fromisoformat(d).weekday() < 5 for d in dues), dues)

    def test_tasks_already_inside_the_deadline_keep_their_dates(self):
        actions = self.proposal()
        pilot_deadlines.fit_new_project(actions, date(2026, 12, 31), TODAY)
        self.assertEqual(actions[0]['deadline'], '2026-12-31')
        self.assertEqual([a['due_date'] for a in actions[1:]],
                         ['2026-11-01', '2026-11-10', '2026-11-20', '2026-12-07'])

    def test_nothing_to_fit_without_a_new_project(self):
        actions = [{'action': 'create_task', 'task_title': 'x', 'project_id': 5, 'due_date': '2026-12-07'}]
        self.assertFalse(pilot_deadlines.fit_new_project(actions, date(2026, 11, 4), TODAY))
        self.assertEqual(actions[0]['due_date'], '2026-12-07')


class PilotKeepsTheStatedDeadlineTests(PMTestCase):
    """E2: the model's own dates lose to the user's."""

    def model_proposes(self):
        today = timezone.localdate()
        late = (today + timedelta(days=43)).isoformat()
        return mock.patch.object(ProjectPilotAgent, 'process', return_value={'answer': '', 'actions': [
            {'action': 'create_project', 'project_name': 'Zaiqa Foods', 'start_date': today.isoformat(),
             'deadline': late},
            {'action': 'create_task', 'task_title': 'Menu pages', 'assignee_id': self.dev.id,
             'due_date': (today + timedelta(days=20)).isoformat()},
            {'action': 'create_task', 'task_title': 'Launch', 'assignee_id': self.dev.id, 'due_date': late},
        ]})

    def check(self, rows):
        deadline = (timezone.localdate() + timedelta(days=10)).isoformat()
        project_row = next(r for r in rows if r['action'] == 'create_project')
        self.assertEqual(project_row['deadline'], deadline)
        self.assertFalse(project_row['suggested'])
        self.assertTrue(all(r['due_date'] <= deadline for r in rows if r['action'] == 'create_task'), rows)

    def test_a_typed_request(self):
        with self.model_proposes():
            code, body = self.call(pm_agent.project_pilot, self.dash, {
                'question': 'create the Zaiqa project and keep its deadline of completion only 10 days from now'})
        self.assertEqual((code, body['status']), (200, 'needs_input'), body)
        self.check(body['data']['rows'])

    def test_a_request_with_a_file_reads_the_typed_words_not_the_document(self):
        with self.model_proposes():
            result = run_project_pilot_pipeline(
                company_user=self.dash, file_name='Zaiqa_Foods_Project_Brief.pdf',
                extracted_text='Zaiqa Foods brief. Deadline: 31 December 2026.',
                user_prompt='create this project, from pdf and assign tasks to developer users, and also keep '
                            'its deadline of completion only 10 days from now')
        self.check(result['draft']['rows'])

    def test_the_review_card_names_the_new_project(self):
        with self.model_proposes():
            code, body = self.call(pm_agent.project_pilot, self.dash, {'question': 'create the Zaiqa project'})
        self.assertIn('project "Zaiqa Foods"', body['data']['answer'])


class MovingAProjectDeadlineTests(PMTestCase):
    """E3: a review card with the project's new deadline and every task's new date, without the AI."""

    QUESTION = ('can you change the deadline of this project to 10 days instead, and also change the deadlines '
                'of the tasks accordingly')

    def setUp(self):
        super().setUp()
        today = timezone.localdate()
        self.project.start_date = today
        self.project.save(update_fields=['start_date'])
        self.first = self.task(title='Design', due_date=timezone.now() + timedelta(days=20))
        self.second = self.task(title='Build', due_date=timezone.now() + timedelta(days=40))
        self.last = self.task(title='Launch', due_date=timezone.now() + timedelta(days=60))
        self.finished = self.task(title='Kick-off', status='done', due_date=timezone.now() + timedelta(days=30))
        self.history = [
            {'role': 'user', 'content': 'create this project, from pdf\n\n📎 Attached: Website_Rebuild_Brief.pdf'},
            {'role': 'assistant', 'content': "Here's the plan: create 1 project and 3 tasks. Check it below."},
        ]

    def ask(self, question=None, history=None, **extra):
        with mock.patch.object(ProjectPilotAgent, 'process', side_effect=AssertionError('the AI was asked')):
            return self.call(pm_agent.project_pilot, self.dash,
                             {'question': question or self.QUESTION,
                              'chat_history': self.history if history is None else history, **extra})

    def test_this_project_is_found_from_the_chat_and_shown_for_review(self):
        code, body = self.ask()
        self.assertEqual((code, body['status']), (200, 'needs_input'), body)
        data = body['data']
        deadline = (timezone.localdate() + timedelta(days=10)).isoformat()
        self.assertEqual(data['actions'][0], {
            'action': 'update_project', 'project_id': self.project.id, 'project_name': 'Website rebuild',
            'updates': {'deadline': deadline}, 'reasoning': f'Deadline moved to {deadline}, as asked.'})
        moved = {a['task_id']: a['updates']['due_date'] for a in data['actions'][1:]}
        self.assertEqual(set(moved), {self.first.id, self.second.id, self.last.id})   # not the finished one
        self.assertEqual(moved[self.last.id] <= deadline, True)
        self.assertLessEqual(moved[self.first.id], moved[self.second.id])
        self.assertLessEqual(moved[self.second.id], moved[self.last.id])
        self.assertIn('**Website rebuild** finishes on', data['answer'])
        rows = {r['title']: r for r in data['changes']}
        self.assertEqual(rows['Website rebuild']['lines'][0]['label'], 'Deadline')
        self.assertEqual(rows['Launch']['lines'][0]['after'], moved[self.last.id])
        # Nothing has changed yet.
        self.project.refresh_from_db()
        self.assertEqual(self.project.deadline, self.deadline)

    def test_confirming_the_card_moves_the_dates(self):
        code, body = self.ask()
        code, done = self.call(pm_agent.project_pilot_confirm, self.dash, {'actions': body['data']['actions']})
        self.assertEqual(code, 200, done)
        self.assertTrue(all(r['success'] for r in done['data']['action_results']), done)
        deadline = timezone.localdate() + timedelta(days=10)
        self.project.refresh_from_db()
        self.assertEqual(self.project.deadline, deadline)
        for task in (self.first, self.second, self.last):
            task.refresh_from_db()
            self.assertLessEqual(task.due_date.date(), deadline)
        self.finished.refresh_from_db()
        self.assertEqual(self.finished.due_date.date(), (timezone.now() + timedelta(days=30)).date())

    def test_the_chats_project_is_meant_even_without_saying_this_project(self):
        code, body = self.ask('okay now change the deadlines from next 10 days to extended 20 days, so change the '
                              'deadline of all tasks accordingly')
        self.assertEqual(body['status'], 'needs_input', body)
        deadline = (timezone.localdate() + timedelta(days=20)).isoformat()
        self.assertEqual(body['data']['actions'][0]['updates'], {'deadline': deadline})

    def test_the_project_picked_in_the_box_needs_no_history(self):
        code, body = self.ask('change the project deadline to 15 Nov', history=[], project_id=self.project.id)
        self.assertEqual(body['status'], 'needs_input', body)
        self.assertEqual(body['data']['actions'][0]['project_id'], self.project.id)

    def test_extending_without_mentioning_tasks_moves_only_the_project(self):
        later = (timezone.localdate() + timedelta(days=90)).strftime('%Y-%m-%d')
        code, body = self.ask(f'extend the deadline of Website rebuild to {later}', history=[])
        self.assertEqual([a['action'] for a in body['data']['actions']], ['update_project'])

    def test_when_the_project_cant_be_told_it_asks_which(self):
        code, body = self.ask(history=[])
        self.assertEqual((code, body['status']), (200, 'success'))
        self.assertIn("Which project's deadline", body['data']['answer'])

    def test_a_yes_after_a_question_in_words_acts_on_the_request(self):
        history = self.history + [
            {'role': 'user', 'content': self.QUESTION},
            {'role': 'assistant', 'content': 'Do you want me to update the project and all its tasks?'},
        ]
        code, body = self.ask('yes it is confirmed, do it', history=history)
        self.assertEqual(body['status'], 'needs_input', body)
        self.assertEqual(body['data']['actions'][0]['action'], 'update_project')


class ConfirmedInWordsTests(PMTestCase):

    def test_only_a_yes_to_a_question_brings_the_request_back(self):
        history = [{'role': 'user', 'content': 'move the deadline of Website rebuild to 15 Nov'},
                   {'role': 'assistant', 'content': 'Shall I move the tasks too?'}]
        self.assertEqual(pm_agent._with_request_confirmed('yes please', history),
                         'move the deadline of Website rebuild to 15 Nov\n\nyes please')
        self.assertEqual(pm_agent._with_request_confirmed('yesterday we agreed', history), 'yesterday we agreed')
        answered = history[:1] + [{'role': 'assistant', 'content': 'Done.'}]
        self.assertEqual(pm_agent._with_request_confirmed('yes', answered), 'yes')
