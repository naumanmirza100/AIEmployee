"""When an agent's free AI allowance runs out, people are told so plainly, and PM spends less of it.

In the client test of 25 Oct 2026 the company used up the Project Manager agent's 100,000 free tokens, and
re-creating a project failed with a red error that looked like a crash (E1 in
MDS/02-Log/issues/2026-10-25_PM-Client-Test.md). A request with a file said only "QuotaExhausted: ".
"""
import json
import shutil
import tempfile
from pathlib import Path
from unittest import mock

from django.test import override_settings

from api.views import pm_agent
from core.api_key_service import QuotaExhausted, resolve_for_call
from core.models import Agent, AgentTokenQuota
from core.notification_utils import notify_company_quota
from project_manager_agent.ai_agents.project_pilot_agent import ProjectPilotAgent
from project_manager_agent.ai_agents.task_prioritization_agent import TaskPrioritizationAgent
from project_manager_agent.models import PMNotification, ProjectPilotJob
from project_manager_agent.tasks import run_project_pilot_job

from .base import PMTestCase

USED_UP = QuotaExhausted('project_manager_agent', 100_000)


class AllowanceUsedUpMessageTests(PMTestCase):

    def setUp(self):
        super().setUp()
        Agent.objects.update_or_create(slug='project_manager_agent', defaults={
            'name': 'Project Manager Agent', 'default_provider': 'openai'})

    def test_the_message_names_the_agent_the_allowance_and_what_to_do(self):
        AgentTokenQuota.objects.create(company=self.company, agent_name='project_manager_agent',
                                       included_tokens=100_000, used_tokens=100_137)
        with self.assertRaises(QuotaExhausted) as caught:
            resolve_for_call(self.company, 'project_manager_agent')
        self.assertEqual(caught.exception.user_message,
                         'Your Project Manager Agent has used all of its free AI allowance (100,000 tokens). To '
                         'carry on, add your own OpenAI or Groq key in Settings → API Keys, or ask us for more.')

    def test_a_typed_request_gets_it_with_402(self):
        with mock.patch.object(ProjectPilotAgent, 'process', side_effect=USED_UP):
            code, body = self.call(pm_agent.project_pilot, self.dash, {'question': 'create a project for the shop'})
        self.assertEqual(code, 402)
        self.assertEqual((body['code'], body['message']), ('quota_exhausted', USED_UP.user_message))

    def test_a_request_with_a_file_says_it_too_not_quota_exhausted_colon(self):
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)
        with override_settings(MEDIA_ROOT=media):
            folder = Path(media) / 'project_pilot_uploads' / 'x'
            folder.mkdir(parents=True)
            (folder / 'brief.txt').write_text('Afar: a delivery app.', encoding='utf-8')
            job = ProjectPilotJob.objects.create(
                company_user=self.dash, company_id=self.company.id, user_prompt='Create this project',
                file_path='project_pilot_uploads/x/brief.txt', file_name='brief.txt', status='queued')
            with mock.patch.object(ProjectPilotAgent, 'process', side_effect=USED_UP):
                run_project_pilot_job(job.id)
        code, body = self.call(pm_agent.project_pilot_job_status, self.dash, method='get', job_id=job.id)
        data = body['data']
        self.assertEqual(data['processing_status'], 'failed')
        self.assertEqual((data['error'], data['error_code']), (USED_UP.user_message, 'quota_exhausted'))
        self.assertNotIn('_error_code', data['timing_ms'])

    def test_the_bell_notice_opens_api_keys(self):
        notify_company_quota(self.company, 'Project Manager Agent', 90, actual_pct=91.2)
        notice = PMNotification.objects.filter(company_user=self.dash).latest('id')
        self.assertEqual(notice.title, 'Token quota at 91.2% — Project Manager Agent')
        self.assertEqual(notice.data['link'], '/company/settings/api-keys')
        code, body = self.call(pm_agent.list_notifications, self.dash, method='get')
        self.assertEqual(body['data']['notifications'][0]['link'], '/company/settings/api-keys')


class PrioritizeReasoningInOneCallTests(PMTestCase):
    """Prioritize wrote each task's reasoning with its own AI call: 13 tasks, 13 calls."""

    def test_the_reasonings_come_from_one_call_whatever_the_number_of_tasks(self):
        tasks = [{'id': n, 'title': f'Task {n}', 'status': 'todo', 'priority': 'medium', 'ai_priority': 'high',
                  'ai_reasoning': 'Needed early.', 'dependencies': [n - 1] if n > 1 else []} for n in range(1, 9)]
        plan = {'execution_plan': [{'id': n, 'execution_order': n, 'reasoning': 'Comes next.'} for n in range(1, 9)],
                'summary': {'total_sequential_days': 8}}
        written = {str(n): f'Task {n} goes at position {n}.' for n in range(1, 8)}      # one missing

        def answer(prompt, *args, **kwargs):
            if 'execution_plan' in prompt and 'Return ONLY a JSON object mapping' not in prompt:
                return json.dumps(plan)
            if 'Return ONLY a JSON object mapping each Task ID' in prompt:
                return json.dumps(written)
            return json.dumps({'overall_reasoning': 'Foundations first.'})

        agent = TaskPrioritizationAgent()
        with mock.patch.object(agent, '_call_llm', side_effect=answer) as llm:
            result = agent.suggest_task_order(tasks)
        self.assertEqual(llm.call_count, 3)                     # the plan, the reasonings, the overall summary
        by_id = {t['id']: t['ai_reasoning'] for t in result['tasks']}
        self.assertEqual(by_id[3], 'Task 3 goes at position 3.')
        self.assertEqual(by_id[8], 'Needed early. Comes next.')    # left out of the answer: the old merge
