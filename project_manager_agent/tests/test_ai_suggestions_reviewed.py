"""Task Prioritization and subtask generation suggest; the user decides.

"Analyze" used to write the AI's priority onto every task the moment it came
back, and "Generate subtasks" saved subtasks for every task in the project —
both before anyone had seen them.
"""
from unittest import mock

from api.views import pm_agent
from core.models import Subtask, Task
from project_manager_agent.ai_agents.subtask_generation_agent import SubtaskGenerationAgent
from project_manager_agent.ai_agents.task_prioritization_agent import TaskPrioritizationAgent

from .base import PMTestCase


class PrioritySuggestionTests(PMTestCase):

    def setUp(self):
        super().setUp()
        self.header = self.task(title='Header', priority='low')
        self.footer = self.task(title='Footer', priority='high')

    def analyse(self):
        suggested = {'success': True, 'tasks': [
            {'id': self.header.id, 'title': 'Header', 'ai_priority': 'high', 'status': 'done'},
            {'id': self.footer.id, 'title': 'Footer', 'ai_priority': 'high'},
        ]}
        with mock.patch.object(TaskPrioritizationAgent, 'process', return_value=suggested):
            code, body = self.call(pm_agent.task_prioritization, self.dash,
                                   {'action': 'prioritize_and_order', 'project_id': self.project.id})
        self.assertEqual(code, 200, body)
        return body['data']

    def test_the_analysis_suggests_and_changes_nothing(self):
        data = self.analyse()
        self.header.refresh_from_db()
        self.assertEqual((self.header.priority, self.header.status), ('low', 'todo'))
        self.assertEqual([(c['title'], c['from_label'], c['to_label']) for c in data['priority_changes']],
                         [('Header', 'Low', 'High')])                     # Footer is already high

    def test_the_ticked_changes_are_made(self):
        code, body = self.call(pm_agent.apply_task_priorities, self.dash,
                               {'changes': [{'task_id': self.header.id, 'priority': 'high'},
                                            {'task_id': self.footer.id, 'priority': 'urgent!'}]})
        self.assertEqual(code, 200)
        self.assertEqual(body['data']['updated'], [self.header.id])
        self.assertEqual(len(body['data']['failed']), 1)
        self.header.refresh_from_db()
        self.assertEqual(self.header.priority, 'high')

    def test_never_another_companys_task(self):
        theirs = Task.objects.create(project=self.rival_project, title='Theirs', priority='low')
        code, body = self.call(pm_agent.apply_task_priorities, self.dash,
                               {'changes': [{'task_id': theirs.id, 'priority': 'high'}]})
        self.assertEqual(body['data']['updated'], [])
        theirs.refresh_from_db()
        self.assertEqual(theirs.priority, 'low')


class SubtaskProposalTests(PMTestCase):

    def setUp(self):
        super().setUp()
        self.header = self.task(title='Header')

    def generate(self):
        proposed = {'success': True, 'subtasks_by_task': {str(self.header.id): {
            'subtasks': [{'title': 'Sketch it', 'description': 'On paper'}, 'Build it', ''],
            'task_reasoning': 'Design before code.'}}}
        with mock.patch.object(SubtaskGenerationAgent, 'process', return_value=proposed):
            code, body = self.call(pm_agent.generate_subtasks, self.dash, {'project_id': self.project.id})
        self.assertEqual(code, 200, body)
        return body['data']

    def test_generating_proposes_and_saves_nothing(self):
        data = self.generate()
        self.assertFalse(Subtask.objects.exists())
        [proposal] = data['proposals']
        self.assertEqual((proposal['task_title'], [s['title'] for s in proposal['subtasks']]),
                         ('Header', ['Sketch it', 'Build it']))               # the blank one dropped
        self.assertEqual(data['proposed_count'], 2)

    def test_the_kept_ones_are_saved_once(self):
        proposal = dict(self.generate()['proposals'][0])
        proposal['subtasks'] = proposal['subtasks'][:1]                       # the user unticked one
        code, body = self.call(pm_agent.save_generated_subtasks, self.dash, {'proposals': [proposal]})
        self.assertEqual((code, body['data']['saved_count']), (200, 1))
        self.assertEqual(list(Subtask.objects.values_list('title', flat=True)), ['Sketch it'])
        self.header.refresh_from_db()
        self.assertIn('Design before code.', self.header.ai_reasoning)
        # Saving again adds nothing: the task has subtasks now.
        code, body = self.call(pm_agent.save_generated_subtasks, self.dash, {'proposals': [proposal]})
        self.assertEqual(body['data']['saved_count'], 0)
        self.assertEqual(Subtask.objects.count(), 1)

    def test_never_another_companys_task(self):
        theirs = Task.objects.create(project=self.rival_project, title='Theirs')
        code, body = self.call(pm_agent.save_generated_subtasks, self.dash, {'proposals': [
            {'task_id': theirs.id, 'subtasks': [{'title': 'Sneak in'}]}]})
        self.assertEqual(body['data']['saved_count'], 0)
        self.assertFalse(Subtask.objects.exists())
