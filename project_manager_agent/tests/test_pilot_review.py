"""Project Pilot changes nothing until its proposal has been reviewed.

It used to apply its actions the moment they arrived unless a new task was
missing an assignee or deadline — so updates, deletes and complete creates
("delete all projects except Website") ran with nobody looking, and confirming
a mixed proposal silently dropped its updates and deletes.
"""
from datetime import timedelta
from unittest import mock

from django.utils import timezone

from api.views import pm_agent
from core.models import Project, Subtask, Task
from project_manager_agent import pilot_review
from project_manager_agent.ai_agents.project_pilot_agent import ProjectPilotAgent
from project_manager_agent.services import DashboardActor

from .base import PMTestCase


class PilotReviewTests(PMTestCase):

    def propose(self, *actions, question='Do it'):
        with mock.patch.object(ProjectPilotAgent, 'process',
                               return_value={'answer': '', 'actions': list(actions)}):
            return self.call(pm_agent.project_pilot, self.dash, {'question': question})

    def test_a_complete_create_is_reviewed_not_made(self):
        due = (timezone.localdate() + timedelta(days=10)).isoformat()
        code, body = self.propose({'action': 'create_task', 'task_title': 'Ship it',
                                   'project_id': self.project.id, 'assignee_id': self.pm.id, 'due_date': due})
        self.assertEqual((code, body['status']), (200, 'needs_input'))
        self.assertFalse(Task.objects.filter(title='Ship it').exists())
        self.assertEqual(body['data']['items'], [])                        # nothing missing…
        self.assertIn('nothing changes until you confirm', body['data']['answer'])   # …still reviewed

    def test_an_update_shows_what_changes_from_what(self):
        task = self.task(title='Build header', status='todo', priority='low')
        code, body = self.propose({'action': 'update_task', 'task_id': task.id,
                                   'updates': {'status': 'done', 'priority': 'low', 'assignee_id': self.dev.id}})
        self.assertEqual(body['status'], 'needs_input')
        [change] = body['data']['changes']
        self.assertEqual((change['kind'], change['title']), ('update', 'Build header'))
        self.assertEqual([(l['label'], l['before'], l['after']) for l in change['lines']],
                         [('Status', 'To Do', 'Done'), ('Assigned to', '—', 'Dev Tester')])  # unchanged priority left out
        task.refresh_from_db()
        self.assertEqual(task.status, 'todo')

    def test_a_delete_says_what_else_goes_with_it(self):
        task = self.task(title='Doomed')
        Subtask.objects.create(task=task, title='Part')
        code, body = self.propose({'action': 'delete_project', 'project_id': self.project.id})
        [change] = body['data']['changes']
        self.assertEqual(change['kind'], 'delete')
        self.assertEqual(change['effect'], 'Also deletes its 1 task and 1 subtask.')
        self.assertTrue(Project.objects.filter(pk=self.project.pk).exists())

    def test_targets_outside_the_company_are_shown_as_not_found(self):
        code, body = self.propose({'action': 'delete_project', 'project_id': self.rival_project.id})
        [change] = body['data']['changes']
        self.assertIn("wasn't found", change['problem'])

    def test_a_proposed_assignee_outside_the_company_becomes_a_question(self):
        code, body = self.propose({'action': 'create_task', 'task_title': 'Sneaky', 'project_id': self.project.id,
                                   'assignee_id': self.rival_pm.id})
        [row] = [r for r in body['data']['rows'] if r['action'] == 'create_task']
        self.assertIsNone(row['assignee_id'])
        self.assertIn('assignee_id', row['missing'])

    def test_an_answer_with_nothing_to_change_is_just_an_answer(self):
        with mock.patch.object(ProjectPilotAgent, 'process', return_value={'answer': 'You have 2 projects.'}):
            code, body = self.call(pm_agent.project_pilot, self.dash, {'question': 'How many projects?'})
        self.assertEqual((body['status'], body['data']['answer']), ('success', 'You have 2 projects.'))


class ApplyTests(PMTestCase):

    def apply(self, *actions, skip=()):
        return pilot_review.apply(list(actions), DashboardActor(self.dash), skip=skip)

    def test_a_new_project_is_made_first_so_its_tasks_can_join_it(self):
        results, project_id = self.apply(
            {'action': 'create_task', 'task_title': 'First task'},
            {'action': 'create_project', 'project_name': 'Rebuild', 'project_description': 'All of it',
             'project_status': 'Active', 'project_priority': 'High'})
        self.assertTrue(all(r['success'] for r in results), results)
        project = Project.objects.get(pk=project_id)
        self.assertEqual((project.description, project.status, project.priority), ('All of it', 'active', 'high'))
        self.assertEqual(Task.objects.get(title='First task').project, project)

    def test_the_services_rules_still_apply(self):
        results, _ = self.apply({'action': 'update_task', 'task_id': self.task(title='T').id,
                                 'updates': {'assignee_id': self.rival_pm.id}})
        self.assertFalse(results[0]['success'])
        self.assertIn('Invalid assignee', results[0]['error'])

    def test_a_refused_change_does_not_stop_the_rest(self):
        keeper = self.task(title='Stays')
        results, _ = self.apply({'action': 'delete_project', 'project_id': self.rival_project.id},
                                {'action': 'update_task', 'task_id': keeper.id, 'updates': {'priority': 'high'}})
        self.assertEqual([r['success'] for r in results], [False, True])
        self.assertTrue(Project.objects.filter(pk=self.rival_project.pk).exists())
        keeper.refresh_from_db()
        self.assertEqual(keeper.priority, 'high')


class AddToExistingProjectTests(PMTestCase):
    """"Create a task in project X" used to take Pilot's 200-token text path:
    its prompt says "DO NOT ask for clarification", and the code treated any
    prompt containing "clarification" as a clarifying question — so the JSON
    came back cut off and nothing could be proposed."""

    def test_it_gets_room_for_its_actions(self):
        agent = ProjectPilotAgent()
        context = {'all_projects': [{'id': self.project.id, 'name': self.project.name, 'status': 'planning',
                                     'priority': 'medium', 'tasks_count': 0, 'description': ''}],
                   'tasks': [], 'user_assignments': []}
        with mock.patch.object(ProjectPilotAgent, '_call_llm', return_value='[]') as llm:
            agent.process(question=f'Create a task called "Write copy" in the {self.project.name} project.',
                          context=context, available_users=[])
        self.assertGreater(llm.call_args.kwargs.get('max_tokens', 0), 200)
