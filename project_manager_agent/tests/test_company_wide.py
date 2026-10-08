"""Project Manager shows a dashboard login its company's projects and people.

Its screens and AI helpers used to show a login only the projects that same
login had created, and offer only the employees it had created. A second
dashboard login found Project Manager empty, and a project made by an employee
with the project-manager role appeared on no dashboard login's screens at all,
the founder's included.
"""
import re
from pathlib import Path

from django.contrib.auth.models import User
from django.http import Http404
from rest_framework.parsers import JSONParser
from rest_framework.request import Request

from api.views import company_dashboard, company_user_tasks, pm_agent
from core.models import Project, UserProfile
from project_manager_agent.ai_agents import analytics_dashboard_agent
from project_manager_agent.project_pilot_pipeline import run_project_pilot_pipeline

from .base import PMTestCase

ROOT = Path(__file__).resolve().parents[2]


class CompanyWideTests(PMTestCase):

    def setUp(self):
        super().setUp()
        # Made by an employee project manager: no dashboard login is behind it.
        self.pats = Project.objects.create(name="Pat's project", company=self.company,
                                           owner=self.pm, project_manager=self.pm)
        # An old upload, saved with no company: only its creator can reach it.
        self.orphan = Project.objects.create(name='Old upload', created_by_company_user=self.dash, owner=self.pm)
        self.t_mine = self.task(title='Mine', assignee=self.dev)
        self.t_colleague = self.task(title="Colleague's", project=self.colleague_project, assignee=self.pm)
        self.t_pats = self.task(title="Pat's", project=self.pats, assignee=self.other_pm)
        self.t_rival = self.task(title='Theirs', project=self.rival_project, assignee=self.rival_pm)
        # People who must never be offered work.
        gone = self.employee('gone')
        User.objects.filter(pk=gone.pk).update(is_active=False)
        root = self.employee('root')
        User.objects.filter(pk=root.pk).update(is_superuser=True)
        # Attached to the company directly, by nobody in particular.
        self.joined = User.objects.create_user(username='jo', password='x', first_name='Jo')
        UserProfile.objects.update_or_create(user=self.joined, defaults={'company': self.company, 'role': 'team_member'})

    def company_names(self):
        return sorted(['Website rebuild', 'Colleague project', "Pat's project"])

    def drf(self, actor, data):
        request = Request(self.factory.post('/', data, format='json'), parsers=[JSONParser()])
        request.user = actor
        return request

    # ---- projects -----------------------------------------------------------------

    def test_a_second_login_sees_the_companys_projects_on_the_dashboard(self):
        code, body = self.call(company_dashboard.project_manager_dashboard, self.dash_colleague, method='get')
        self.assertEqual(code, 200, body)
        self.assertEqual(sorted(p['name'] for p in body['data']['projects']), self.company_names())
        self.assertEqual((body['data']['stats']['total_projects'], body['data']['stats']['total_tasks']), (3, 3))

    def test_so_does_every_project_list(self):
        for view in (company_dashboard.get_company_user_projects, company_dashboard.get_company_user_projects_list):
            code, body = self.call(view, self.dash_colleague, method='get')
            self.assertEqual(code, 200, (view.__name__, body))
            self.assertEqual(sorted(p['name'] for p in body['data']), self.company_names(), view.__name__)

    def test_the_founder_sees_what_an_employee_project_manager_made(self):
        _, body = self.call(company_dashboard.project_manager_dashboard, self.dash, method='get')
        names = [p['name'] for p in body['data']['projects']]
        self.assertIn("Pat's project", names)
        self.assertIn('Old upload', names)                       # and still its own company-less upload
        self.assertNotIn('Their project', names)

    def test_another_companys_projects_never_show(self):
        _, body = self.call(company_dashboard.project_manager_dashboard, self.rival_dash, method='get')
        self.assertEqual([p['name'] for p in body['data']['projects']], ['Their project'])

    # ---- the AI helpers read from the same scope ---------------------------------------

    def test_the_question_helper_answers_about_a_colleagues_project(self):
        for project in (self.colleague_project, self.pats):
            error, inputs = pm_agent._knowledge_qa_inputs(
                self.drf(self.dash_colleague, {'question': 'How is it going?', 'project_id': project.id}))
            self.assertIsNone(error)
            self.assertEqual(inputs['context']['project']['name'], project.name)
        with self.assertRaises(Http404):
            pm_agent._knowledge_qa_inputs(
                self.drf(self.dash_colleague, {'question': 'And theirs?', 'project_id': self.rival_project.id}))

    def test_the_charts_count_the_whole_company(self):
        data = pm_agent._pm_build_analytics_data(self.dash_colleague)
        self.assertEqual((data['projects_total'], data['tasks_total']), (3, 3))
        self.assertEqual(pm_agent._pm_build_analytics_data(self.rival_dash)['projects_total'], 1)

    def test_the_analytics_helper_finds_a_colleagues_project(self):
        find = analytics_dashboard_agent._projects_of
        self.assertEqual(sorted(find(self.dash_colleague).values_list('name', flat=True)), self.company_names())
        self.assertFalse(find(self.dash_colleague).filter(pk=self.rival_project.pk).exists())

    def test_pilot_reaches_a_colleagues_project_and_never_another_companys(self):
        from unittest import mock
        seen = {}

        class Pilot:
            def process(self, **kwargs):
                seen.update(kwargs)
                return {'success': True, 'answer': 'ok', 'actions': []}

        def run(project):
            seen.clear()
            with mock.patch('project_manager_agent.project_pilot_pipeline.AgentRegistry.get_agent',
                            return_value=Pilot()):
                run_project_pilot_pipeline(company_user=self.dash_colleague, extracted_text='Plan.',
                                           file_name='plan.txt', user_prompt='Add it', project_id=project.id)
            return (seen.get('context') or {}).get('project') or {}

        self.assertEqual(run(self.pats).get('name'), "Pat's project")
        with self.assertRaises(Http404):
            run(self.rival_project)

    # ---- people ---------------------------------------------------------------------

    def test_a_second_login_is_offered_every_employee(self):
        code, body = self.call(pm_agent.get_available_users, self.dash_colleague, method='get')
        self.assertEqual(code, 200, body)
        self.assertEqual(sorted(u['username'] for u in body['data']), ['dev', 'jo', 'pat', 'pia'])
        roles = {u['username']: u['role'] for u in body['data']}
        self.assertEqual((roles['pat'], roles['dev']), ('project_manager', 'team_member'))

    def test_never_another_companys_or_someone_who_left(self):
        _, body = self.call(pm_agent.get_available_users, self.rival_dash, method='get')
        self.assertEqual([u['username'] for u in body['data']], ['rob'])

    def test_the_question_helper_knows_the_same_people(self):
        _, inputs = pm_agent._knowledge_qa_inputs(self.drf(self.dash_colleague, {'question': 'Who is busy?'}))
        self.assertEqual(sorted(u['username'] for u in inputs['available_users']), ['dev', 'jo', 'pat', 'pia'])

    def test_a_second_login_sees_the_teams_tasks(self):
        code, body = self.call(company_user_tasks.get_all_users_tasks, self.dash_colleague, method='get')
        self.assertEqual(code, 200, body)
        self.assertEqual(sorted(t['title'] for t in body['data']), ["Colleague's", 'Mine', "Pat's"])

    # ---- and it stays that way ---------------------------------------------------------

    def test_no_screen_filters_projects_by_the_login_that_made_them(self):
        pattern = re.compile(r'created_by_company_user\s*=\s*company_user\b|\["created_by_company_user"\]')
        # The one place it is right: a login with no company at all sees what it made.
        allowed = {('api/views/pm_agent.py', 'projects = base_qs.filter(created_by_company_user=company_user)')}
        found = set()
        for path in ('api/views/pm_agent.py', 'api/views/company_dashboard.py', 'api/views/company_user_tasks.py',
                     'project_manager_agent/project_pilot_pipeline.py',
                     'project_manager_agent/ai_agents/analytics_dashboard_agent.py'):
            for line in (ROOT / path).read_text(encoding='utf-8').splitlines():
                if pattern.search(line) and not line.strip().startswith(('#', '(a)')):
                    found.add((path, line.strip()))
        self.assertEqual(found, allowed)
