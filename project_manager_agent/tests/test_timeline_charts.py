"""The Timeline / Gantt charts read correctly, a task never ends after its due date, and the Q&A graphs use the
words people see.

Seen on the live site while rehearsing the PM demo (25 Oct 2026): the burndown climbed because it counted tasks
by their start week, the people chart showed logins, and the AI ended a task a day after its due date while its
reasoning said it ended on it. The Q&A "tasks by status" chart labelled its bar "todo".
"""
import json
from datetime import datetime, time, timedelta
from unittest import mock

from django.utils import timezone

from api.views import pm_agent
from project_manager_agent.ai_agents.timeline_gantt_agent import TimelineGanttAgent

from .base import PMTestCase


def due(day):
    return timezone.make_aware(datetime.combine(day, time(12)))


class GanttChartTests(PMTestCase):

    def setUp(self):
        super().setUp()
        today = timezone.localdate()
        self.monday = today - timedelta(days=today.weekday())
        self.done = self.task(title='Schema', assignee=self.dev, due_date=due(self.monday + timedelta(days=4)))
        self.done.mark_complete()
        self.done.save()
        self.api = self.task(title='API', assignee=self.pm, due_date=due(self.monday + timedelta(days=11)))
        self.loose = self.task(title='Launch', due_date=due(self.monday + timedelta(days=18)))

    def gantt(self):
        day = lambda n: (self.monday + timedelta(days=n)).isoformat()
        plan = [
            {'task_id': self.done.id, 'start_date': day(0), 'end_date': day(4), 'reasoning': ''},
            # One day past its due date, as the AI did on the live site.
            {'task_id': self.api.id, 'start_date': day(7), 'end_date': day(12), 'reasoning': ''},
            {'task_id': self.loose.id, 'start_date': day(14), 'end_date': day(18), 'reasoning': ''},
        ]
        with mock.patch.object(TimelineGanttAgent, '_call_llm', return_value=json.dumps(plan)):
            result = TimelineGanttAgent().generate_gantt_chart(self.project.id)
        return result['gantt_chart']

    def test_a_task_ends_on_its_due_date_at_the_latest(self):
        tasks = {task['id']: task for task in self.gantt()['tasks']}
        self.assertEqual(tasks[self.api.id]['end_date'], (self.monday + timedelta(days=11)).isoformat())

    def test_the_burndown_counts_down_week_by_week(self):
        weeks = self.gantt()['charts']['burndown']['data']
        self.assertEqual([week['planned'] for week in weeks], [2, 1, 0])
        self.assertEqual(weeks[0]['week'], f"{self.monday.day} {self.monday.strftime('%b')}")
        self.assertEqual((weeks[0]['completed'], weeks[0]['remaining'], weeks[0]['total']), (1, 2, 3))
        self.assertNotIn('remaining', weeks[1])     # the weeks ahead have only the plan

    def test_people_are_shown_by_name(self):
        rows = self.gantt()['charts']['resource_utilization']['data']
        self.assertEqual(sorted(row['name'] for row in rows), ['Dev Tester', 'Pat Tester', 'Unassigned'])


class GraphLabelTests(PMTestCase):

    def test_statuses_and_priorities_are_in_words(self):
        self.task(title='Cart', status='todo', priority='high')
        self.task(title='Menu', status='in_progress', priority='high')
        data = pm_agent._pm_build_analytics_data(self.dash, project_id=self.project.id)
        self.assertEqual(data['tasks_by_status_obj'], {'To Do': 1, 'In Progress': 1})
        self.assertEqual(data['tasks_by_priority_obj'], {'High': 2})
