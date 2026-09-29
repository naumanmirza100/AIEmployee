"""The missing-detail check, and the endpoint that applies a confirmed proposal.

Two things are under test:

  * `project_manager_agent.drafts` — pure logic, no database. What counts as a
    gap, and how form answers merge back onto a proposal.
  * `project_pilot_confirm` — creates what the user reviewed, and nothing else.
"""

from datetime import timedelta

from django.utils import timezone

from api.views import pm_agent
from core.models import Project, Task
from project_manager_agent import drafts

from .base import PMTestCase


# ---------------------------------------------------------------- pure logic

class InspectTests(PMTestCase):
    """What `drafts.inspect` calls a gap."""

    users = [{'id': 1, 'username': 'pat', 'name': 'Pat Tester', 'role': 'dev'}]

    def test_a_complete_task_has_no_gaps(self):
        report = drafts.inspect(
            [{'action': 'create_task', 'task_title': 'Ship it',
              'assignee_id': 1, 'due_date': '2026-10-01'}],
            self.users)
        self.assertFalse(report['needs_input'])
        self.assertEqual(report['items'], [])

    def test_missing_assignee_and_due_date_are_both_reported(self):
        report = drafts.inspect(
            [{'action': 'create_task', 'task_title': 'Ship it'}], self.users)
        self.assertTrue(report['needs_input'])
        fields = [g['field'] for g in report['items'][0]['gaps']]
        self.assertEqual(fields, ['assignee_id', 'due_date'])

    def test_the_assignee_gap_carries_the_choices(self):
        report = drafts.inspect(
            [{'action': 'create_task', 'task_title': 'Ship it', 'due_date': '2026-10-01'}],
            self.users)
        gap = report['items'][0]['gaps'][0]
        self.assertEqual(gap['input'], 'user')
        self.assertEqual(gap['options'], self.users)
        self.assertFalse(gap['no_options'])

    def test_no_users_is_flagged_rather_than_offering_an_empty_dropdown(self):
        report = drafts.inspect([{'action': 'create_task', 'task_title': 'Ship it'}], [])
        self.assertTrue(report['no_users'])
        self.assertTrue(report['items'][0]['gaps'][0]['no_options'])

    def test_no_users_is_not_flagged_when_nothing_is_missing(self):
        report = drafts.inspect(
            [{'action': 'create_task', 'task_title': 'x', 'assignee_id': 1,
              'due_date': '2026-10-01'}], [])
        self.assertFalse(report['needs_input'])
        self.assertFalse(report['no_users'])

    def test_a_project_needs_a_deadline(self):
        report = drafts.inspect([{'action': 'create_project', 'project_name': 'Rebuild'}],
                                self.users)
        self.assertEqual([g['field'] for g in report['items'][0]['gaps']], ['deadline'])

    def test_end_date_counts_as_the_deadline(self):
        report = drafts.inspect(
            [{'action': 'create_project', 'project_name': 'Rebuild', 'end_date': '2026-12-01'}],
            self.users)
        self.assertFalse(report['needs_input'])

    def test_the_words_an_llm_uses_for_i_dont_know_count_as_blank(self):
        for empty in (None, '', '  ', 'null', 'None', 'N/A', 'TBD', 'unknown'):
            with self.subTest(value=empty):
                report = drafts.inspect(
                    [{'action': 'create_task', 'task_title': 'x',
                      'assignee_id': empty, 'due_date': '2026-10-01'}],
                    self.users)
                self.assertTrue(report['needs_input'], f'{empty!r} should read as missing')

    def test_actions_we_do_not_gate_are_left_alone(self):
        report = drafts.inspect([{'action': 'update_task', 'task_id': 3}], self.users)
        self.assertFalse(report['needs_input'])
        self.assertEqual(report['summary'][0]['action'], 'update_task')

    def test_every_action_appears_in_the_summary(self):
        report = drafts.inspect(
            [{'action': 'create_project', 'project_name': 'Rebuild'},
             {'action': 'create_task', 'task_title': 'Ship it'}], self.users)
        self.assertEqual([s['title'] for s in report['summary']], ['Rebuild', 'Ship it'])


class ApplyAnswersTests(PMTestCase):
    """Merging the form's answers back onto the proposal."""

    def test_answers_land_on_the_right_action(self):
        actions = [{'action': 'create_task', 'task_title': 'A'},
                   {'action': 'create_task', 'task_title': 'B'}]
        merged = drafts.apply_answers(actions, {'1': {'assignee_id': 7}})
        self.assertIsNone(merged[0].get('assignee_id'))
        self.assertEqual(merged[1]['assignee_id'], 7)

    def test_the_original_actions_are_not_modified(self):
        actions = [{'action': 'create_task', 'task_title': 'A'}]
        drafts.apply_answers(actions, {'0': {'assignee_id': 7}})
        self.assertNotIn('assignee_id', actions[0])

    def test_a_blank_answer_leaves_the_gap_blank(self):
        merged = drafts.apply_answers(
            [{'action': 'create_task', 'task_title': 'A'}], {'0': {'assignee_id': ''}})
        self.assertNotIn('assignee_id', merged[0])

    def test_only_fields_we_asked_about_can_be_set(self):
        # A crafted payload must not be able to rewrite the action itself.
        merged = drafts.apply_answers(
            [{'action': 'create_task', 'task_title': 'A'}],
            {'0': {'action': 'delete_project', 'project_id': 1, 'assignee_id': 7}})
        self.assertEqual(merged[0]['action'], 'create_task')
        self.assertNotIn('project_id', merged[0])
        self.assertEqual(merged[0]['assignee_id'], 7)

    def test_nonsense_indices_are_ignored(self):
        actions = [{'action': 'create_task', 'task_title': 'A'}]
        for bad in ('x', '9', '-1', None):
            with self.subTest(index=bad):
                merged = drafts.apply_answers(actions, {bad: {'assignee_id': 7}})
                self.assertEqual(len(merged), 1)


# ------------------------------------------------------------- the endpoint

class ConfirmEndpointTests(PMTestCase):
    """`project_pilot_confirm` creates what was reviewed."""

    def setUp(self):
        super().setUp()
        self.due = (timezone.now().date() + timedelta(days=10)).isoformat()

    def test_it_creates_a_project_and_its_tasks(self):
        code, body = self.call(pm_agent.project_pilot_confirm, self.dash, {
            'actions': [
                {'action': 'create_project', 'project_name': 'Rebuild',
                 'deadline': self.due},
                {'action': 'create_task', 'task_title': 'Ship it'},
            ],
            'answers': {'1': {'assignee_id': self.pm.id, 'due_date': self.due}},
        })
        self.assertEqual(code, 200)
        self.assertTrue(Project.objects.filter(name='Rebuild', company=self.company).exists())
        task = Task.objects.get(title='Ship it')
        self.assertEqual(task.assignee_id, self.pm.id)
        self.assertEqual(task.project.name, 'Rebuild')
        self.assertTrue(all(r['success'] for r in body['data']['action_results']))

    def test_a_task_with_no_project_joins_the_one_just_created(self):
        self.call(pm_agent.project_pilot_confirm, self.dash, {
            'actions': [
                {'action': 'create_project', 'project_name': 'Fresh', 'deadline': self.due},
                {'action': 'create_task', 'task_title': 'Orphan'},
            ],
            'answers': {},
        })
        self.assertEqual(Task.objects.get(title='Orphan').project.name, 'Fresh')

    def test_a_gap_left_blank_is_honoured(self):
        # The user was asked, chose not to answer, and confirmed anyway.
        code, _ = self.call(pm_agent.project_pilot_confirm, self.dash, {
            'actions': [{'action': 'create_task', 'task_title': 'Loose end',
                         'project_id': self.project.id}],
            'answers': {},
        })
        self.assertEqual(code, 200)
        task = Task.objects.get(title='Loose end')
        self.assertIsNone(task.assignee_id)
        self.assertIsNone(task.due_date)

    def test_actions_other_than_creates_are_ignored(self):
        victim = self.task(title='Keep me')
        code, body = self.call(pm_agent.project_pilot_confirm, self.dash, {
            'actions': [{'action': 'delete_task', 'task_id': victim.id}],
            'answers': {},
        })
        self.assertEqual(code, 200)
        self.assertTrue(Task.objects.filter(pk=victim.pk).exists())
        self.assertEqual(body['data']['action_results'], [])

    def test_it_will_not_reach_into_another_company(self):
        code, body = self.call(pm_agent.project_pilot_confirm, self.dash, {
            'actions': [{'action': 'create_task', 'task_title': 'Trespass',
                         'project_id': self.rival_project.id}],
            'answers': {},
        })
        self.assertEqual(code, 200)
        self.assertFalse(Task.objects.filter(title='Trespass').exists())
        self.assertFalse(body['data']['action_results'][0]['success'])

    def test_one_bad_action_does_not_stop_the_others(self):
        code, body = self.call(pm_agent.project_pilot_confirm, self.dash, {
            'actions': [
                {'action': 'create_task', 'task_title': '', 'project_id': self.project.id},
                {'action': 'create_task', 'task_title': 'Good one',
                 'project_id': self.project.id},
            ],
            'answers': {},
        })
        self.assertEqual(code, 200)
        results = body['data']['action_results']
        self.assertFalse(results[0]['success'])
        self.assertTrue(results[1]['success'])
        self.assertTrue(Task.objects.filter(title='Good one').exists())

    def test_an_empty_proposal_is_rejected(self):
        code, _ = self.call(pm_agent.project_pilot_confirm, self.dash, {'actions': []})
        self.assertEqual(code, 400)
