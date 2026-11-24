"""The workflow step builder's choices (24 Nov 2026): the steps were typed as JSON."""
from api.views import hr_agent as views
from core.models import Project
from hr_agent.models import HRNotificationTemplate

from .base import HRTestCase


class BuilderOptions(HRTestCase):

    def project(self, name, company):
        from django.contrib.auth.models import User
        owner = User.objects.get_or_create(username='pm-owner')[0]
        return Project.objects.create(name=name, company=company, owner=owner)

    def test_an_hr_admin_gets_the_templates_projects_and_employees(self):
        HRNotificationTemplate.objects.create(company=self.company, name='Welcome', subject='Hi', body='Hello')
        self.buy_module(self.company, 'project_manager_agent')
        self.project('Onboarding', self.company)
        self.project('Theirs', self.rival)
        code, body = self.call(views.hr_workflow_builder_options, self.admin, method='get')
        self.assertEqual(code, 200, body)
        data = body['data']
        self.assertEqual([t['name'] for t in data['templates']], ['Welcome'])
        self.assertEqual([p['name'] for p in data['projects']], ['Onboarding'])
        self.assertTrue(data['has_project_manager'])
        self.assertIn('Mo Member', [e['full_name'] for e in data['employees']])

    def test_without_project_manager_no_projects_are_offered(self):
        self.project('Onboarding', self.company)
        body = self.call(views.hr_workflow_builder_options, self.admin, method='get')[1]
        self.assertEqual((body['data']['projects'], body['data']['has_project_manager']), ([], False))

    def test_only_hr_admins(self):
        self.assertEqual(self.call(views.hr_workflow_builder_options, self.member, method='get')[0], 403)
