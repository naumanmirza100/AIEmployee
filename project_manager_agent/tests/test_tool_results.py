"""What Project Manager's AI tools make is kept, and can become tasks.

Workflow & SOP's checklists, Meeting Notes and Calendar & Schedule's plan were shown once and lost on the next click:
ticks were forgotten, action items stayed text, and the plan could not go into anyone's calendar.
"""
from datetime import timedelta
from unittest import mock

from django.utils import timezone

from api.views import pm_agent as views
from api.views import pm_tool_results as saved
from core.models import Task
from project_manager_agent.models import ProjectToolResult

from .base import PMTestCase

CHECKLIST = {'success': True, 'checklist': [
    {'item': 'Set up CI', 'priority': 'high', 'category': 'setup'},
    {'item': 'Write the API spec', 'priority': 'medium'},
    'Agree the code review rules'], 'tips': ['Keep it short']}


def ai_returns(result):
    agent = mock.Mock()
    agent.process.return_value = result
    return mock.patch.object(views.AgentRegistry, 'get_agent', return_value=agent)


class ChecklistTests(PMTestCase):

    def make(self, result=CHECKLIST, phase='development'):
        with ai_returns(result):
            return self.call(views.workflow_suggest, self.dash,
                             {'project_id': self.project.id, 'action': 'checklist', 'phase': phase})

    def test_a_checklist_is_kept_and_ticks_survive_making_it_again(self):
        code, body = self.make()
        self.assertEqual(code, 200, body)
        kept = body['data']['saved']
        self.assertEqual([i['text'] for i in kept['items']],
                         ['Set up CI', 'Write the API spec', 'Agree the code review rules'])

        code, body = self.call(saved.tick_checklist_item, self.dash, {'done': True}, result_id=kept['id'], index=0)
        self.assertEqual((code, body['data']['items'][0]['done']), (200, True))

        self.make({**CHECKLIST, 'checklist': ['Set up CI', 'Book the load test']})
        code, body = self.call(saved.saved_checklist, self.dash, method='get', project_id=self.project.id,
                               phase='development')
        self.assertEqual([(i['text'], i['done']) for i in body['data']['items']],
                         [('Set up CI', True), ('Book the load test', False)])
        self.assertEqual(ProjectToolResult.objects.filter(project=self.project).count(), 1)

    def test_each_phase_has_its_own(self):
        self.make(phase='planning')
        self.make(phase='testing')
        self.assertEqual(set(ProjectToolResult.objects.values_list('key', flat=True)), {'planning', 'testing'})

    def test_suggestions_and_validations_are_not_kept(self):
        with ai_returns({'success': True, 'phases': []}):
            self.call(views.workflow_suggest, self.dash, {'project_id': self.project.id, 'action': 'suggest'})
        self.assertFalse(ProjectToolResult.objects.exists())

    def test_another_companys_checklist_cannot_be_ticked_or_read(self):
        self.make()
        row = ProjectToolResult.objects.get()
        code, _ = self.call(saved.tick_checklist_item, self.rival_dash, {'done': True}, result_id=row.id, index=0)
        self.assertEqual(code, 404)
        code, _ = self.call(saved.saved_checklist, self.rival_dash, method='get', project_id=self.project.id,
                            phase='development')
        self.assertEqual(code, 404)


class TasksFromSuggestionsTests(PMTestCase):

    def create(self, items, actor=None, project=None):
        return self.call(saved.tasks_from_suggestions, actor or self.dash, {'items': items},
                         project_id=(project or self.project).id)

    def test_items_become_tasks_with_owners_matched_by_name(self):
        code, body = self.create([
            {'title': 'Set up CI', 'priority': 'high', 'assignee_name': 'Dev Tester', 'due': self.inside},
            {'title': 'Send the minutes', 'assignee_name': 'pat'},
            {'title': 'Ask legal', 'assignee_name': 'Tester'},              # three people are called Tester
            {'title': 'Book the room', 'assignee_name': 'TBD', 'due': 'Friday'},
        ])
        self.assertEqual(code, 201, body)
        tasks = {t.title: t for t in Task.objects.filter(project=self.project)}
        self.assertEqual((tasks['Set up CI'].assignee, tasks['Set up CI'].priority), (self.dev, 'high'))
        self.assertEqual(tasks['Set up CI'].due_date.date().isoformat(), self.inside)
        self.assertEqual(tasks['Send the minutes'].assignee, self.pm)
        self.assertIsNone(tasks['Ask legal'].assignee)
        self.assertIsNone(tasks['Book the room'].due_date)

    def test_a_date_outside_the_project_is_left_out_not_refused(self):
        code, body = self.create([{'title': 'Launch party', 'due': self.after_deadline}])
        self.assertEqual(code, 201, body)
        self.assertIsNone(Task.objects.get(title='Launch party').due_date)

    def test_nothing_chosen_is_refused(self):
        code, _ = self.create([{'title': '  '}])
        self.assertEqual(code, 400)

    def test_not_into_another_companys_project(self):
        code, _ = self.create([{'title': 'Sneaky'}], project=self.rival_project)
        self.assertEqual(code, 404)
        self.assertFalse(Task.objects.filter(title='Sneaky').exists())


class MeetingNotesTests(PMTestCase):

    RESULT = {'success': True, 'summary': 'We agreed the launch plan.',
              'action_items': [{'action': 'Book the venue', 'owner': 'Pat', 'deadline': 'TBD', 'priority': 'high'}]}

    def test_notes_on_a_project_are_kept_and_can_be_opened_again(self):
        with ai_returns(self.RESULT):
            code, body = self.call(views.meeting_notes, self.dash, {
                'project_id': self.project.id, 'meeting_text': 'Pat will book the venue.', 'topic': 'Launch'})
        self.assertEqual(code, 200, body)
        code, body = self.call(saved.saved_meeting_notes, self.dash, method='get', project_id=self.project.id)
        [notes] = body['data']
        self.assertEqual((notes['topic'], notes['result']['summary']), ('Launch', 'We agreed the launch plan.'))
        self.assertNotIn('text', notes)
        code, body = self.call(saved.saved_meeting_notes, self.dash, method='get', project_id=self.project.id,
                               data={'id': notes['id']})
        self.assertEqual(body['data']['text'], 'Pat will book the venue.')

    def test_notes_without_a_project_are_not_kept(self):
        with ai_returns(self.RESULT):
            self.call(views.meeting_notes, self.dash, {'meeting_text': 'Some notes'})
        self.assertFalse(ProjectToolResult.objects.exists())


class SchedulePlanTests(PMTestCase):

    def plan(self):
        day = (timezone.now() + timedelta(days=7)).date().isoformat()
        return {'success': True, 'schedule': [{'date': day, 'day_name': 'Monday', 'assignments': [
            {'member_name': 'Dana Tester', 'member_id': self.dana.id, 'task_title': 'Write tests', 'task_id': 7,
             'priority': 'high', 'note': 'Before the demo'},
            {'member_name': 'Dev Tester', 'member_id': self.dev.id, 'task_title': 'Fix login', 'task_id': 8}]},
            {'date': 'someday', 'assignments': [{'task_title': 'Nope', 'member_id': self.dana.id}]}],
            'conflicts': [], 'period': {'start': day, 'end': day}}

    def setUp(self):
        super().setUp()
        self.dana = self.employee('dana')        # dana@test.local: the dashboard login's own employee login
        with ai_returns(self.plan()):
            code, body = self.call(views.calendar_schedule, self.dash, {'project_id': self.project.id})
        self.assertEqual(code, 200, body)
        self.assertIn('saved_at', body['data'])

    def test_the_latest_plan_is_kept(self):
        code, body = self.call(saved.saved_schedule_plan, self.dash, method='get', project_id=self.project.id)
        self.assertEqual(body['data']['schedule'][0]['assignments'][0]['task_title'], 'Write tests')

    def test_the_ics_holds_only_my_work_and_does_not_block_my_calendar(self):
        response = self.http(self.dash).get(f'/api/project-manager/projects/{self.project.id}/schedule-plan/ics')
        self.assertEqual(response.status_code, 200)
        ics = response.content.decode()
        self.assertIn('SUMMARY:Write tests', ics)
        self.assertNotIn('Fix login', ics)
        self.assertNotIn('Nope', ics)
        self.assertIn('TRANSP:TRANSPARENT', ics)
        self.assertIn('Before the demo', ics)

    def test_the_whole_team_on_request(self):
        response = self.http(self.dash).get(
            f'/api/project-manager/projects/{self.project.id}/schedule-plan/ics?everyone=1')
        self.assertIn('Fix login', response.content.decode())

    def test_no_plan_for_another_company(self):
        code, _ = self.call(saved.saved_schedule_plan, self.rival_dash, method='get', project_id=self.project.id)
        self.assertEqual(code, 404)
