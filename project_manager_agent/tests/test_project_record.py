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


class CompanyRecordTests(PMTestCase):
    """"All projects" in the box: what was added, changed, removed and confirmed across every project, each line
    under its project, with the team's and the meetings' news, and where each project stands. Asked for on
    26 Oct 2026."""

    def setUp(self):
        super().setUp()
        from hr_agent.models import Employee, HRAuditLog
        from project_manager_agent.models import MeetingParticipant, MeetingResponse, ScheduledMeeting
        actor = pm_services.DashboardActor(self.dash)
        pm_services.create_task(actor, {'project_id': self.project.id, 'title': 'Design', 'assignee_id': self.dev.id,
                                        'due_date': self.inside})
        late = pm_services.create_task(actor, {'project_id': self.colleague_project.id, 'title': 'Brochure',
                                               'assignee_id': self.pm.id})
        Task.objects.filter(pk=late.pk).update(due_date=timezone.now() - timedelta(days=2))
        old = pm_services.create_project(actor, {'name': 'Old site'})
        pm_services.delete_project(actor, old['id'] if isinstance(old, dict) else old.id)
        pm_services.create_task(pm_services.DashboardActor(self.rival_dash),
                                {'project_id': self.rival_project.id, 'title': 'Their secret task'})
        meeting = ScheduledMeeting.objects.create(
            organizer=self.dash, invitee=self.dev, title='Kick-off', duration_minutes=30, timezone_name='Asia/Karachi',
            proposed_time=timezone.now() + timedelta(days=2), status='accepted')
        MeetingParticipant.objects.create(meeting=meeting, user=self.dev, status='accepted')
        MeetingResponse.objects.create(meeting=meeting, responded_by='invitee', action='accepted', responder=self.dev)
        gone = self.employee('gus')
        record = Employee.objects.get(user=gone)            # every employee login has an HR record
        HRAuditLog.objects.create(company=self.company, actor=self.dash, action='employee.deactivate',
                                  target_type='employee', target_id=record.id, diff={})
        self.record = project_record.build_company(self.dash)
        self.groups = {g['label']: [i['text'] for i in g['items']]
                       for day in self.record['timeline'] for g in day['groups']}
        self.everything = '\n'.join(t for texts in self.groups.values() for t in texts)

    def test_each_line_is_under_its_project_and_the_company_news_has_its_own(self):
        self.assertIn('1 task added: “Design” — assigned to Dev Tester (1)', self.groups['Website rebuild'])
        self.assertTrue(any(t.startswith('1 task added: “Brochure”') for t in self.groups['Colleague project']))
        self.assertIn('Project removed: “Old site” (by Dana Dash)', self.groups['Projects'])
        self.assertTrue(any(t.startswith('Joined the team: ') and 'Dev Tester (Team Member)' in t
                            for t in self.groups['Team']), self.groups['Team'])
        self.assertTrue(any(t.startswith('Confirmed, everyone accepted: “Kick-off”') for t in self.groups['Meetings']),
                        self.groups['Meetings'])
        self.assertTrue(any(t.startswith('1 meeting booked: “Kick-off”') and 'with Dev Tester' in t
                            for t in self.groups['Meetings']))
        self.assertIn('Left the team: Gus Tester', self.groups['Team'])

    def test_someone_who_left_with_open_work_is_named(self):
        from django.contrib.auth.models import User
        User.objects.filter(pk=self.pm.pk).update(is_active=False)          # Pat has "Brochure", late
        record = project_record.build_company(self.dash)
        self.assertTrue(next(m for m in record['team'] if m['name'] == 'Pat Tester')['left'])
        self.assertIn('Pat Tester has left the team but still has 1 open task: hand them over (Users → their row).',
                      record['next_steps'])

    def test_another_companys_work_never_shows(self):
        self.assertNotIn('Their secret task', self.everything)
        self.assertNotIn('Their project', [p['name'] for p in self.record['projects']])
        self.assertNotIn('Their project', self.groups)

    def test_where_every_project_stands_late_first(self):
        names = [p['name'] for p in self.record['projects']]
        self.assertEqual(names[0], 'Colleague project')           # the one with late work
        self.assertEqual(sorted(names), ['Colleague project', 'Website rebuild'])
        overview = self.record['overview']
        self.assertEqual((overview['projects'], overview['tasks'], overview['late']), (2, 2, 1))
        self.assertEqual([(t['title'], t['project']) for t in self.record['due']['late']],
                         [('Brochure', 'Colleague project')])
        self.assertTrue(any(s.startswith('Colleague project: 1 task late') for s in self.record['next_steps']),
                        self.record['next_steps'])
        team = {m['name']: (m['open'], m['projects']) for m in self.record['team']}
        self.assertEqual(team['Dev Tester'], (1, 1))
        self.assertEqual(team['Pat Tester'], (1, 1))

    def test_the_newest_day_comes_first(self):
        dates = [day['date'] for day in self.record['timeline']]
        self.assertEqual(dates, sorted(dates, reverse=True))

    def test_days_are_on_the_companys_clock(self):
        # Seen live, 26 Oct 2026: a task made at 1:50 am in Lahore was listed under the day before (UTC).
        from datetime import datetime, timezone as tz
        made = pm_services.create_task(pm_services.DashboardActor(self.dash),
                                       {'project_id': self.project.id, 'title': 'Late-night task'})
        PMAuditLog.objects.filter(model_name='Task', object_id=made.id).update(
            created_at=datetime(2026, 10, 25, 20, 50, tzinfo=tz.utc))          # 1:50 am on 26 Oct in Lahore

        def day_of_late_night_task():
            _, body = self.call(pm_tool_results.company_record, self.dash, method='get')
            return next(day['date'] for day in body['data']['timeline'] for g in day['groups'] for i in g['items']
                        if 'Late-night task' in i['text'])

        self.assertEqual(day_of_late_night_task(), '2026-10-25')                # no time zone set: UTC, as before
        self.company.timezone_name = 'Asia/Karachi'
        self.company.save(update_fields=['timezone_name'])
        self.assertEqual(day_of_late_night_task(), '2026-10-26')

    def test_one_task_with_no_owner_has(self):
        Task.objects.create(project=self.project, title='Nobody yet')
        record = project_record.build_company(self.dash)
        self.assertIn('1 open task in 1 project has no owner yet.', record['next_steps'])

    def test_the_endpoint(self):
        code, body = self.call(pm_tool_results.company_record, self.dash, method='get')
        self.assertEqual(code, 200, body)
        self.assertEqual(body['data']['scope'], 'all')
        _, theirs = self.call(pm_tool_results.company_record, self.rival_dash, method='get')
        self.assertEqual([p['name'] for p in theirs['data']['projects']], ['Their project'])


class UntitledMeetingTests(PMTestCase):

    def test_notes_with_no_topic_are_a_meeting_not_meeting_meeting(self):
        ProjectToolResult.objects.create(project=self.project, kind='meeting_notes', key='2', data={
            'topic': '', 'date': timezone.localdate().isoformat(),
            'result': {'key_decisions': [{'decision': 'Cash on delivery at launch'}]}})
        record = project_record.build(self.project)
        lines = [item['text'] for day in record['timeline'] for item in day['items']]
        self.assertTrue(any(line.startswith('Meeting: decided Cash on delivery at launch') for line in lines), lines)
        self.assertEqual(record['decisions'][-1]['source'], 'Meeting')
