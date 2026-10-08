"""Suggested deadlines in the Project Pilot review form.

The review form pre-fills a deadline for the project and for every task. These
tests pin the arithmetic, and one thing above all: a suggested date must never
be one the task service then refuses (a task due outside its project's dates).
"""

from datetime import date, timedelta

from django.test import SimpleTestCase

from api.views import pm_agent
from core.models import Task
from project_manager_agent import drafts

from .base import PMTestCase

# A Monday, so working-day arithmetic is easy to read in the assertions.
MONDAY = date(2026, 10, 5)


def _project(name='Rebuild', **extra):
    return dict({'action': 'create_project', 'project_name': name}, **extra)


def _task(title, **extra):
    return dict({'action': 'create_task', 'task_title': title}, **extra)


class TimelineTests(SimpleTestCase):

    def test_without_a_deadline_the_tasks_run_end_to_end(self):
        plan = drafts.timeline([_project(), _task('A'), _task('B'), _task('C')], today=MONDAY)
        # Starts the next working day; three tasks at the default three days.
        self.assertEqual(plan['start'], '2026-10-06')
        self.assertTrue(plan['deadline_suggested'])
        dues = [plan['tasks'][i]['suggested'] for i in (1, 2, 3)]
        self.assertEqual(dues, sorted(dues))
        self.assertEqual(dues[-1], plan['deadline'])

    def test_a_given_deadline_is_kept_and_the_tasks_fit_inside_it(self):
        plan = drafts.timeline(
            [_project(deadline='2026-12-31'), _task('A'), _task('B')], today=MONDAY)
        self.assertEqual(plan['deadline'], '2026-12-31')
        self.assertFalse(plan['deadline_suggested'])
        for i in (1, 2):
            self.assertLessEqual(plan['tasks'][i]['suggested'], '2026-12-31')
            self.assertGreaterEqual(plan['tasks'][i]['suggested'], plan['start'])

    def test_bigger_tasks_get_more_of_the_window(self):
        plan = drafts.timeline(
            [_project(deadline='2026-11-30'),
             _task('Small', estimated_hours=6), _task('Large', estimated_hours=60)],
            today=MONDAY)
        self.assertLess(plan['tasks'][1]['weight'], 0.2)
        self.assertEqual(plan['tasks'][2]['weight'], 1.0)

    def test_no_suggested_date_falls_on_a_weekend(self):
        plan = drafts.timeline(
            [_project()] + [_task(str(i), estimated_hours=h)
                            for i, h in enumerate((1, 7, 13, 20, 4, 30, 9))],
            today=MONDAY)
        for entry in plan['tasks'].values():
            self.assertLess(date.fromisoformat(entry['suggested']).weekday(), 5, entry)

    def test_an_agent_dated_task_is_never_left_outside_the_project(self):
        # From a real reply: the agent dated one task far out but gave the
        # project no deadline. The suggestion must reach that far.
        plan = drafts.timeline(
            [_project(), _task('A'), _task('Deploy', due_date='2027-03-29')], today=MONDAY)
        self.assertGreaterEqual(plan['deadline'], '2027-03-29')

    def test_deadline_days_becomes_a_date(self):
        plan = drafts.timeline([_project(deadline_days=30), _task('A')], today=MONDAY)
        self.assertEqual(plan['deadline'], (MONDAY + timedelta(days=30)).isoformat())
        self.assertFalse(plan['deadline_suggested'])

    def test_an_existing_project_bounds_the_tasks_and_is_not_editable(self):
        class Existing:
            id = 7
            start_date = date(2026, 10, 12)
            effective_deadline = date(2026, 11, 13)
        plan = drafts.timeline([_task('A', project_id=7), _task('B')], today=MONDAY,
                               project=Existing())
        self.assertFalse(plan['deadline_editable'])
        self.assertEqual((plan['start'], plan['deadline']), ('2026-10-12', '2026-11-13'))
        self.assertEqual(set(plan['tasks']), {0, 1})

    def test_tasks_that_name_their_project_are_held_to_that_project(self):
        # "Create a task in ShopKart for Ahmed": the project is on the task, not chosen in the picker.
        named = [_task('A', project_id=7), _task('B', project_id='7')]
        self.assertEqual(drafts.only_project_id(named), 7)
        # Without it the card made up a deadline a week away and called it the project's.
        made_up = drafts.timeline(named, today=MONDAY)
        self.assertEqual((made_up['tasks'], made_up['deadline_suggested']), ({}, True))

    def test_only_when_they_all_name_the_same_existing_project(self):
        self.assertIsNone(drafts.only_project_id([_task('A', project_id=7), _task('B', project_id=8)]))
        self.assertIsNone(drafts.only_project_id([_task('A', project_id=7), _task('B')]))       # one has none
        self.assertIsNone(drafts.only_project_id([_task('A', project_id='new-1')]))             # not a stored project
        self.assertIsNone(drafts.only_project_id([{'action': 'create_project', 'name': 'P'}, _task('A', project_id=7)]))
        self.assertIsNone(drafts.only_project_id([{'action': 'update_task', 'task_id': 3}]))

    def test_a_task_for_some_other_project_is_left_alone(self):
        class Existing:
            id = 7
            start_date = date(2026, 10, 12)
            effective_deadline = date(2026, 11, 13)
        plan = drafts.timeline([_task('Elsewhere', project_id=99)], today=MONDAY,
                               project=Existing())
        self.assertEqual(plan['tasks'], {})


class ReviewRowsTests(SimpleTestCase):
    users = [{'id': 4, 'username': 'pat', 'name': 'Pat', 'role': 'dev'}]

    def test_every_create_gets_a_row_with_a_starting_value(self):
        report = drafts.inspect(
            [_project(), _task('A', assignee_id=4), _task('B', due_date='2026-10-20')],
            self.users, today=MONDAY)
        project, a, b = report['rows']
        self.assertEqual(project['deadline'], report['timeline']['deadline'])
        self.assertTrue(project['suggested'])
        self.assertEqual(a['assignee_id'], 4)
        self.assertTrue(a['suggested'])          # its date is ours
        self.assertEqual(b['due_date'], '2026-10-20')
        self.assertFalse(b['suggested'])         # its date is the agent's
        self.assertEqual(b['missing'], ['assignee_id'])

    def test_clearing_a_field_removes_it_including_its_aliases(self):
        merged = drafts.apply_answers(
            [_project(end_date='2026-12-01', deadline_days=40), _task('A', due_date='2026-10-20')],
            {'0': {'deadline': ''}, '1': {'due_date': ''}})
        for key in ('deadline', 'end_date', 'deadline_days'):
            self.assertNotIn(key, merged[0])
        self.assertNotIn('due_date', merged[1])


class SuggestionsAreAcceptedEndToEnd(PMTestCase):
    """Create exactly what the form pre-fills, and nothing may be refused."""

    def test_every_pre_filled_value_is_accepted_by_the_service(self):
        actions = [_project('Launch'),
                   _task('Plan', estimated_hours=10), _task('Build', estimated_hours=40),
                   _task('Ship', due_date=(date.today() + timedelta(days=90)).isoformat())]
        report = drafts.inspect(actions, [], today=date.today())

        # What the form would submit untouched: every field at its start value.
        answers = {}
        for row in report['rows']:
            if row['action'] == 'create_project':
                answers[str(row['index'])] = {'deadline': row['deadline']}
            else:
                answers[str(row['index'])] = {'due_date': row['due_date'],
                                              'assignee_id': row['assignee_id'] or ''}

        code, body = self.call(pm_agent.project_pilot_confirm, self.dash,
                               {'actions': actions, 'answers': answers})
        self.assertEqual(code, 200)
        failures = [r for r in body['data']['action_results'] if not r['success']]
        self.assertEqual(failures, [])
        self.assertEqual(Task.objects.filter(project__name='Launch').count(), 3)
