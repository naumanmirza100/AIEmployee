"""Project Pilot gives work to the role asked for: "only to the developers", "to all team members".

On the live site (26 Oct 2026) "assign the tasks to all developers" also gave work to a designer and a team member,
and "developers only, no designers" gave a task to the project manager.
"""
from unittest import mock

from api.views import pm_agent
from project_manager_agent import pilot_roles
from project_manager_agent.ai_agents.project_pilot_agent import ProjectPilotAgent

from .base import PMTestCase

PEOPLE = [
    {'id': 1, 'name': 'Bilal Ahmed', 'role': 'developer'},
    {'id': 2, 'name': 'Hira Siddiqui', 'role': 'developer'},
    {'id': 3, 'name': 'Sana Javed', 'role': 'designer'},
    {'id': 4, 'name': 'Kamran Akhtar', 'role': 'team_member'},
    {'id': 5, 'name': 'Ayesha Malik', 'role': 'project_manager'},
]


class ReadingTheRoleTests(PMTestCase):

    def test_the_ways_people_ask(self):
        for words, keep, drop in (
            ("Create a project with 6 tasks and assign them only to the developers", {'developer'}, set()),
            ('assign the tasks to all developers', {'developer'}, set()),
            ('to all team members only', {'team_member'}, set()),
            ('give them to the Team-Members', {'team_member'}, set()),
            ('sirf developers ko de do', {'developer'}, set()),
            ('4 tasks, developers only, no designers', {'developer'}, {'designer'}),
            ('split it between our designers', {'designer'}, set()),
            ('assign to everyone except the designers', set(), {'designer'}),
            ("don't give anything to the designers, give it to developers", {'developer'}, {'designer'}),
            ("don't assign to anyone except the developers", {'developer'}, set()),
            ('nobody other than the team members', {'team_member'}, set()),
            ('give the reviews to the project managers', {'project_manager'}, set()),
            ('interns ko testing de do', {'internee'}, set()),
        ):
            self.assertEqual(pilot_roles.asked(words), (keep, drop), words)

    def test_a_role_word_that_is_not_an_instruction(self):
        for words in ("Create a project 'Developer Portal' with 5 tasks", 'add a task to deploy to the dev server',
                      "Create a project for the designers' portfolio site", 'how many developers do we have?',
                      'move the developer onboarding task to next Friday'):
            self.assertEqual(pilot_roles.asked(words), (set(), set()), words)

    def test_who_may_have_the_work(self):
        ids = lambda words: [p['id'] for p in pilot_roles.limit(PEOPLE, words)]
        self.assertEqual(ids('assign the tasks to all developers'), [1, 2])
        self.assertEqual(ids('to all team members only'), [4])
        self.assertEqual(ids('assign to everyone except the designers'), [1, 2, 4, 5])
        self.assertEqual(ids('give the menu to Sana and the rest to the developers'), [1, 2, 3])
        self.assertEqual(ids('make 5 tasks'), [1, 2, 3, 4, 5])

    def test_a_role_nobody_has_is_said_so_when_the_request_insists(self):
        for words in ('give the testing tasks only to the interns', 'interns only', 'sirf interns ko de do',
                      'nobody except the interns'):
            self.assertEqual(pilot_roles.nobody(PEOPLE, words),
                             "Nobody in your team has the role Internee, so nothing was changed. Set people's roles "
                             "under Users (the pencil on their row), or name the people who should do it.", words)
        self.assertIsNone(pilot_roles.nobody(PEOPLE, 'only to the developers'))
        self.assertIsNone(pilot_roles.nobody(PEOPLE, 'give it to Sana and only the interns'))

    def test_used_loosely_a_role_nobody_has_means_everyone_as_before(self):
        words = 'create this project and assign tasks to the interns, deadline only 10 days from now'
        self.assertIsNone(pilot_roles.nobody(PEOPLE, words))
        self.assertEqual(len(pilot_roles.limit(PEOPLE, words)), 5)

    def test_a_task_given_to_someone_else_goes_to_the_role(self):
        actions = [{'action': 'create_project', 'project_name': 'Loyalty app'},
                   {'action': 'create_task', 'task_title': 'a', 'assignee_id': 1},
                   {'action': 'create_task', 'task_title': 'b', 'assignee_id': 3},
                   {'action': 'create_task', 'task_title': 'c', 'assignee_id': 5},
                   {'action': 'create_task', 'task_title': 'd', 'assignee_id': None},
                   {'action': 'update_task', 'task_id': 9, 'updates': {'assignee_id': 4}},
                   {'action': 'update_task', 'task_id': 8, 'updates': {'status': 'done'}}]
        pilot_roles.keep_to(actions, 'developers only, no designers', PEOPLE)
        given = [a.get('assignee_id', (a.get('updates') or {}).get('assignee_id')) for a in actions[1:]]
        self.assertEqual(given, [1, 2, 1, 2, 1, None])    # whoever has the fewest: Hira, Bilal, Hira, Bilal
        self.assertEqual(actions[0], {'action': 'create_project', 'project_name': 'Loyalty app'})

    def test_no_role_asked_leaves_the_proposal_alone(self):
        actions = [{'action': 'create_task', 'task_title': 'a', 'assignee_id': 3}]
        self.assertEqual(pilot_roles.keep_to(actions, 'make the tasks', PEOPLE), [
            {'action': 'create_task', 'task_title': 'a', 'assignee_id': 3}])


class PilotKeepsToTheRoleTests(PMTestCase):
    """Through the Pilot endpoint, with the AI's answer given. In the base company Pat and Pia are project managers
    and Dev a team member."""

    def ask(self, question, actions):
        seen = {}

        def process(agent, **kwargs):
            seen['people'] = sorted(p['username'] for p in kwargs['available_users'])
            return {'answer': '', 'actions': actions}

        with mock.patch.object(ProjectPilotAgent, 'process', autospec=True, side_effect=process):
            _, body = self.call(pm_agent.project_pilot, self.dash, {'question': question,
                                                                    'project_id': self.project.id})
        return body, seen.get('people')

    def task_for(self, user):
        return {'action': 'create_task', 'project_id': self.project.id, 'task_title': 'Write the tests',
                'assignee_id': user.id, 'due_date': None}

    def test_the_ai_is_offered_only_the_role_and_its_slip_is_moved(self):
        body, offered = self.ask('add a task for the tests and give it only to the project managers',
                                 [self.task_for(self.dev)])
        self.assertEqual(offered, ['pat', 'pia'])
        self.assertEqual(body['status'], 'needs_input', body)
        self.assertIn(body['data']['actions'][0]['assignee_id'], (self.pm.id, self.other_pm.id))

    def test_all_team_members_means_team_members(self):
        body, offered = self.ask('add a task for the tests and assign to all team members', [self.task_for(self.pm)])
        self.assertNotIn('pat', offered)
        self.assertNotIn(body['data']['actions'][0]['assignee_id'], (self.pm.id, self.other_pm.id))

    def test_insisting_on_a_role_nobody_has_changes_nothing(self):
        body, offered = self.ask('add a task for the tests and give it only to the designers', [self.task_for(self.dev)])
        self.assertIsNone(offered)
        self.assertEqual(body['status'], 'success', body)
        self.assertTrue(body['data']['answer'].startswith('Nobody in your team has the role Designer'))

    def test_a_role_nobody_has_used_loosely_offers_everyone(self):
        body, offered = self.ask('add a task for the tests and give it to the designers', [self.task_for(self.dev)])
        self.assertEqual(offered, ['dev', 'pat', 'pia'])
        self.assertEqual(body['data']['actions'][0]['assignee_id'], self.dev.id)

    def test_a_role_in_capitals_is_not_taken_for_a_missing_person(self):
        body, _ = self.ask('give the task to Project Managers', [self.task_for(self.pm)])
        self.assertEqual(body['status'], 'needs_input', body)
