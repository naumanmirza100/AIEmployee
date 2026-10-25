"""A company can have the PM chat make new work at once, without the review card.

Asked for after the client test of 25 Oct 2026: an admin chooses, on the Company profile page, whether projects,
tasks and meetings asked for in the PM chat are made straight away or shown for review first. Changes to what
exists, and deletions, are always reviewed.
"""
from unittest import mock

from django.utils import timezone

from api.views import company_auth, pm_agent
from core.models import Project, Task
from project_manager_agent.ai_agents.project_pilot_agent import ProjectPilotAgent

from .base import PMTestCase


class PilotAutoConfirmTests(PMTestCase):

    def switch(self, on):
        self.company.pm_auto_confirm = on
        self.company.save(update_fields=['pm_auto_confirm'])

    def propose(self, *actions):
        with mock.patch.object(ProjectPilotAgent, 'process', return_value={'answer': '', 'actions': list(actions)}):
            return self.call(pm_agent.project_pilot, self.dash, {'question': 'Make it'})

    def new_project(self):
        return ({'action': 'create_project', 'project_name': 'Online ordering', 'project_description': 'Shop'},
                {'action': 'create_task', 'task_title': 'Build the cart', 'assignee_id': self.dev.id})

    def test_off_it_is_shown_for_review_as_before(self):
        code, body = self.propose(*self.new_project())
        self.assertEqual(body['status'], 'needs_input')
        self.assertFalse(Project.objects.filter(name='Online ordering').exists())

    def test_on_new_work_is_made_at_once_with_the_suggested_dates(self):
        self.switch(True)
        code, body = self.propose(*self.new_project())
        self.assertEqual((code, body['status']), (200, 'success'))
        self.assertTrue(body['data']['auto_confirmed'])
        self.assertEqual(body['data']['answer'], 'Created 1 project and 1 task.')
        project = Project.objects.get(name='Online ordering')
        task = Task.objects.get(title='Build the cart')
        self.assertEqual((task.project, task.assignee), (project, self.dev))
        self.assertIsNotNone(project.deadline)                       # the deadline the card would have suggested
        self.assertIsNotNone(task.due_date)
        self.assertGreaterEqual(task.due_date.date() if hasattr(task.due_date, 'date') else task.due_date,
                                timezone.localdate())

    def test_on_a_deletion_is_still_reviewed(self):
        self.switch(True)
        code, body = self.propose({'action': 'delete_project', 'project_id': self.project.id})
        self.assertEqual(body['status'], 'needs_input')
        self.assertTrue(Project.objects.filter(pk=self.project.pk).exists())


class AutoConfirmSettingTests(PMTestCase):

    def save(self, actor, on):
        return self.call(company_auth.update_company_profile, actor, {'pmAutoConfirm': on}, method='patch')

    def test_an_admin_switches_it_on_and_the_profile_shows_it(self):
        self.dash.role = 'admin'
        self.dash.save(update_fields=['role'])
        code, body = self.save(self.dash, True)
        self.assertEqual(code, 200, body)
        self.assertTrue(body['data']['company']['pmAutoConfirm'])
        self.company.refresh_from_db()
        self.assertTrue(self.company.pm_auto_confirm)

    def test_anyone_else_is_refused(self):
        code, body = self.save(self.dash, True)            # role 'company_user'
        self.assertEqual(code, 403, body)
        self.company.refresh_from_db()
        self.assertFalse(self.company.pm_auto_confirm)
