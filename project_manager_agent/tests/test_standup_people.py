"""The Daily Standup lists each person once, with their tasks.

Seen while rehearsing the PM demo (25 Oct 2026): tasks were matched by login ("bilal.ahmed") against the team's
names ("Bilal Ahmed"), so each person appeared twice, once by name with no tasks and once by login with them.
"""
from unittest import mock

from django.test import SimpleTestCase

from project_manager_agent.ai_agents.daily_standup_agent import DailyStandupAgent

TEAM = [{'id': 7, 'username': 'bilal.ahmed', 'name': 'Bilal Ahmed'},
        {'id': 8, 'username': 'ayesha.malik', 'name': 'Ayesha Malik'}]


def task(title, status='todo'):
    return {'title': title, 'status': status, 'assignee_id': 7, 'assignee_username': 'bilal.ahmed',
            'assignee_name': 'Bilal Ahmed'}


class StandupPeopleTests(SimpleTestCase):

    def standup(self, tasks):
        with mock.patch.object(DailyStandupAgent, '_call_llm', return_value='report') as call:
            result = DailyStandupAgent().generate_standup(tasks, TEAM)
        return result, call.call_args.args[0]

    def test_each_person_once_with_their_tasks(self):
        result, prompt = self.standup([task('Schema'), task('Login', 'in_progress')])
        self.assertEqual(set(result['member_details']), {'Bilal Ahmed', 'Ayesha Malik'})
        self.assertEqual(result['member_details']['Bilal Ahmed']['total_assigned'], 2)
        self.assertNotIn('bilal.ahmed', prompt)

    def test_active_means_someone_moved_work(self):
        result, _ = self.standup([task('Schema')])
        self.assertEqual((result['summary']['active_members'], result['summary']['inactive_members']),
                         (0, ['Bilal Ahmed']))
        result, _ = self.standup([task('Schema', 'in_progress')])
        self.assertEqual((result['summary']['active_members'], result['summary']['inactive_members']), (1, []))
