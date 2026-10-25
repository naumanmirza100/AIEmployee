"""Meeting Notes → Project record: a project's decisions and work, on a page or two, in date order.

Asked for after the client test of 25 Oct 2026: for the chosen project, the decisions, actions and due dates,
risks, the project made and the tasks handed out. A summary, not a log of every event.
"""
from datetime import timedelta

from django.utils import timezone

from api.views import pm_tool_results
from core.models import ProjectRisk, Task
from project_manager_agent import project_record
from project_manager_agent import services as pm_services
from project_manager_agent.models import PMAuditLog, ProjectToolResult

from .base import PMTestCase


class ProjectRecordTests(PMTestCase):

    def setUp(self):
        super().setUp()
        actor = pm_services.DashboardActor(self.dash)
        today = timezone.localdate()
        self.design = pm_services.create_task(actor, {'project_id': self.project.id, 'title': 'Design',
                                                      'assignee_id': self.dev.id, 'due_date': self.inside})
        self.build_task = pm_services.create_task(actor, {'project_id': self.project.id, 'title': 'Build',
                                                          'assignee_id': self.pm.id, 'due_date': self.inside})
        self.copy = pm_services.create_task(actor, {'project_id': self.project.id, 'title': 'Copy'})
        pm_services.update_project(actor, self.project.id, {'deadline': (today + timedelta(days=45)).isoformat()})
        pm_services.update_task(actor, self.design.id, {'status': 'in_progress'})
        pm_services.update_task(actor, self.design.id, {'status': 'done'})
        pm_services.update_task(actor, self.build_task.id, {'assignee_id': self.dev.id})
        # Late: due yesterday, still open (set directly, as the service refuses dates before the start).
        Task.objects.filter(pk=self.copy.pk).update(due_date=timezone.now() - timedelta(days=1))
        ProjectToolResult.objects.create(project=self.project, kind='meeting_notes', key='1', data={
            'topic': 'Kick-off', 'date': today.isoformat(), 'result': {
                'key_decisions': [{'decision': 'Launch with three menu pages'}],
                'action_items': [{'action': 'Send the logo files', 'owner': 'Dev', 'deadline': 'Friday'}],
                'risks_mentioned': [{'risk': 'Payment gateway approval may be slow', 'severity': 'high'}],
            }})
        ProjectRisk.objects.create(project=self.project, title='Designer on leave next week', description='-',
                                   severity='medium')
        self.record = project_record.build(self.project)
        self.lines = [item['text'] for day in self.record['timeline'] for item in day['items']]

    def test_the_timeline_tells_the_story_in_a_few_bullets(self):
        self.assertTrue(self.lines[0].startswith('Project created by Dana Dash'), self.lines)
        joined = '\n'.join(self.lines)
        self.assertIn('3 tasks added: “Design”, “Build”, “Copy” — assigned to Dev Tester (1), Pat Tester (1); '
                      '1 without an owner', joined)
        self.assertIn(f'Deadline moved from {self.deadline.day} {self.deadline:%b %Y}', joined)
        self.assertIn('Handed over: “Build” to Dev Tester', joined)
        self.assertIn('Completed: “Design”', joined)
        self.assertIn('Meeting “Kick-off”: decided Launch with three menu pages, 1 action item, 1 risk raised', joined)
        self.assertIn('Risk logged: Designer on leave next week (Medium)', joined)
        # A summary: status steps on the way to done are not listed one by one.
        self.assertNotIn('in progress', joined.lower())

    def test_decisions_due_dates_risks_and_people(self):
        decisions = [d['text'] for d in self.record['decisions']]
        self.assertIn('Launch with three menu pages', decisions)
        self.assertTrue(any(d.startswith('Deadline moved') for d in decisions), decisions)
        self.assertEqual([t['title'] for t in self.record['due']['late']], ['Copy'])
        risks = [r['text'] for r in self.record['risks']]
        self.assertEqual(risks[0], '1 task past due: “Copy”')
        self.assertIn('Payment gateway approval may be slow', risks)
        self.assertIn('Designer on leave next week', risks)
        team = {p['name']: (p['open'], p['done']) for p in self.record['team']}
        self.assertEqual(team, {'Dev Tester': (1, 1), 'No owner': (1, 0)})
        self.assertEqual(self.record['project']['done'], 1)
        self.assertEqual(self.record['meeting_actions'][0]['action'], 'Send the logo files')
        self.assertTrue(any('owner' in s for s in self.record['next_steps']), self.record['next_steps'])

    def test_an_edit_keeps_what_it_changed_from_and_to(self):
        entry = PMAuditLog.objects.filter(action='task_updated', object_id=self.build_task.id).latest('created_at')
        self.assertEqual(entry.details['from'], {'assignee': 'Pat Tester'})
        self.assertEqual(entry.details['to'], {'assignee': 'Dev Tester'})
        self.assertEqual(entry.details['project_id'], self.project.id)

    def test_the_endpoint_is_scoped_to_the_company(self):
        code, body = self.call(pm_tool_results.project_record, self.dash, method='get', project_id=self.project.id)
        self.assertEqual(code, 200, body)
        self.assertEqual(body['data']['project']['name'], 'Website rebuild')
        code, body = self.call(pm_tool_results.project_record, self.rival_dash, method='get',
                               project_id=self.project.id)
        self.assertEqual(code, 404)


class UntitledMeetingTests(PMTestCase):

    def test_notes_with_no_topic_are_a_meeting_not_meeting_meeting(self):
        ProjectToolResult.objects.create(project=self.project, kind='meeting_notes', key='2', data={
            'topic': '', 'date': timezone.localdate().isoformat(),
            'result': {'key_decisions': [{'decision': 'Cash on delivery at launch'}]}})
        record = project_record.build(self.project)
        lines = [item['text'] for day in record['timeline'] for item in day['items']]
        self.assertTrue(any(line.startswith('Meeting: decided Cash on delivery at launch') for line in lines), lines)
        self.assertEqual(record['decisions'][-1]['source'], 'Meeting')
