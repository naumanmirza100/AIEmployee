"""Project Pilot from a document changes nothing until its proposal is reviewed.

An upload with a clear instruction ("create a project from this") and no
similar project used to create every project and task straight away; the
floating chat didn't even show what it made. It now comes back as the same
review card as a typed Pilot request.
"""
import shutil
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest import mock

from django.test import override_settings
from django.utils import timezone

from api.views import pm_agent
from core.models import Project, Task
from project_manager_agent.ai_agents.project_pilot_agent import ProjectPilotAgent
from project_manager_agent.models import ProjectPilotJob
from project_manager_agent.project_pilot_pipeline import run_project_pilot_pipeline
from project_manager_agent.tasks import run_project_pilot_job

from .base import PMTestCase


class PilotFromFileTests(PMTestCase):

    def setUp(self):
        super().setUp()
        due = (timezone.localdate() + timedelta(days=10)).isoformat()
        self.actions = [
            {'action': 'create_project', 'project_name': 'Launch'},
            {'action': 'create_task', 'task_title': 'Write copy', 'project_name': 'Launch',
             'assignee_id': self.pm.id, 'due_date': due},
        ]

    def proposing(self, actions=None):
        return mock.patch.object(ProjectPilotAgent, 'process',
                                 return_value={'answer': '', 'actions': list(actions or self.actions)})

    def run_pipeline(self, prompt='Create a project from this plan'):
        with self.proposing():
            return run_project_pilot_pipeline(company_user=self.dash, extracted_text='Plan: launch the site.',
                                              file_name='plan.txt', user_prompt=prompt)

    def test_a_clear_instruction_is_reviewed_not_made(self):
        result = self.run_pipeline()
        self.assertEqual(result['action_results'], [])
        draft = result['draft']
        self.assertTrue(draft['review'])
        self.assertEqual([a['action'] for a in draft['actions']], ['create_project', 'create_task'])
        self.assertFalse(Project.objects.filter(name='Launch').exists())
        self.assertFalse(Task.objects.filter(title='Write copy').exists())

    def test_confirming_the_card_makes_exactly_that(self):
        draft = self.run_pipeline()['draft']
        code, body = self.call(pm_agent.project_pilot_confirm, self.dash, {'actions': draft['actions']})
        self.assertEqual(code, 200, body)
        project = Project.objects.get(name='Launch')
        self.assertEqual(Task.objects.get(title='Write copy').project, project)

    def test_an_upload_without_an_instruction_still_asks_first(self):
        result = self.run_pipeline(prompt='')
        self.assertTrue(result['confirmation_required']['needs_confirmation'])
        self.assertNotIn('draft', result)
        self.assertFalse(Project.objects.filter(name='Launch').exists())

    def test_a_document_with_nothing_to_do_is_just_an_answer(self):
        with mock.patch.object(ProjectPilotAgent, 'process', return_value={'answer': 'It is a meeting summary.'}):
            result = run_project_pilot_pipeline(company_user=self.dash, extracted_text='Notes.',
                                                file_name='notes.txt', user_prompt='What is this?')
        self.assertEqual((result['answer'], result['action_results']), ('It is a meeting summary.', []))
        self.assertNotIn('draft', result)


class PilotFileJobTests(PMTestCase):

    def setUp(self):
        super().setUp()
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)

    def test_the_job_hands_the_review_card_to_the_browser(self):
        with override_settings(MEDIA_ROOT=self.media):
            folder = Path(self.media) / 'project_pilot_uploads' / 'x'
            folder.mkdir(parents=True)
            (folder / 'plan.txt').write_text('Plan: launch the site.', encoding='utf-8')
            job = ProjectPilotJob.objects.create(
                company_user=self.dash, company_id=self.company.id, user_prompt='Create a project from this plan',
                file_path='project_pilot_uploads/x/plan.txt', file_name='plan.txt', status='queued')
            with mock.patch.object(ProjectPilotAgent, 'process', return_value={
                    'answer': '', 'actions': [{'action': 'create_project', 'project_name': 'Launch'}]}):
                run_project_pilot_job(job.id)
        code, body = self.call(pm_agent.project_pilot_job_status, self.dash, method='get', job_id=job.id)
        self.assertEqual(code, 200, body)
        data = body['data']
        self.assertEqual(data['processing_status'], 'ready')
        self.assertTrue(data['draft']['review'])
        self.assertEqual(data['action_results'], [])
        self.assertNotIn('_draft', data['timing_ms'])
        self.assertFalse(Project.objects.filter(name='Launch').exists())
