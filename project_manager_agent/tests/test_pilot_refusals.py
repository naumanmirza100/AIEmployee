"""Pilot turns down, in words, what the AI's reading would do that nobody asked for.

Found by asking wrong things on the live site (25 Oct 2026): "give the cart and checkout task to Zubair", with no
Zubair in the company, came back as a card taking the task from Sana and leaving it with nobody; "move the project
deadline to yesterday" came back as a card for a deadline in the past.
"""
from datetime import timedelta
from unittest import mock

from django.utils import timezone

from api.views import pm_agent
from project_manager_agent.ai_agents.project_pilot_agent import ProjectPilotAgent

from .base import PMTestCase


class PilotRefusalTests(PMTestCase):

    def setUp(self):
        super().setUp()
        self.panel = self.task(title='Admin panel', assignee=self.dev)

    def ask(self, question, actions):
        with mock.patch.object(ProjectPilotAgent, 'process', return_value={'answer': '', 'actions': actions}):
            code, body = self.call(pm_agent.project_pilot, self.dash, {'question': question,
                                                                       'project_id': self.project.id})
        return body

    def reassign(self, user_id):
        return [{'action': 'update_task', 'task_id': self.panel.id, 'updates': {'assignee_id': user_id}}]

    def test_someone_not_in_the_team_is_said_so_not_left_with_nobody(self):
        body = self.ask('give the admin panel to Zubair', self.reassign(None))
        self.assertEqual(body['status'], 'success', body)
        self.assertTrue(body['data']['answer'].startswith("I couldn't find Zubair in your team"))

    def test_nor_swapped_for_someone_who_is(self):
        body = self.ask('Zubair ko admin panel de do', self.reassign(self.pm.id))
        self.assertTrue(body['data']['answer'].startswith("I couldn't find Zubair in your team"), body)

    def test_a_name_the_ai_could_not_place_leaves_the_task_alone(self):
        body = self.ask('zubair ko admin panel de do', self.reassign(None))
        self.assertTrue(body['data']['answer'].startswith("I couldn't tell who should have it"), body)

    def test_people_in_the_team_and_unassigning_still_get_the_card(self):
        for question, user_id in (('give the admin panel to Pat', self.pm.id), ('Pat ko admin panel de do', self.pm.id),
                                  ('assign Testing to Pat', self.pm.id), ('unassign the admin panel', None)):
            body = self.ask(question, self.reassign(user_id))
            self.assertEqual(body['status'], 'needs_input', (question, body))

    def test_a_deadline_that_has_passed_is_not_offered(self):
        yesterday = timezone.localdate() - timedelta(days=1)
        body = self.ask('move the project deadline to yesterday', [
            {'action': 'update_project', 'project_id': self.project.id, 'updates': {'deadline': yesterday.isoformat()}}])
        self.assertEqual(body['status'], 'success', body)
        self.assertEqual(body['data']['answer'], f'{yesterday.day} {yesterday:%B %Y} has already passed, so the '
                                                 'deadline was not moved. A deadline is today or later: say another date.')

    def test_moving_a_task_to_monday_is_not_taken_for_a_person(self):
        body = self.ask('move the admin panel to Monday', [
            {'action': 'update_task', 'task_id': self.panel.id,
             'updates': {'due_date': (timezone.localdate() + timedelta(days=9)).isoformat()}}])
        self.assertEqual(body['status'], 'needs_input', body)
