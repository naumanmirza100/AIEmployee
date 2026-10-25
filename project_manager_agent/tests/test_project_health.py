"""Project health is progress against the time gone, not the share of tasks done.

Seen while rehearsing the PM demo (25 Oct 2026): a project made that day, nothing late, 35 days to its deadline,
scored 0 / 100, "Critical", because the score started from the completion rate.
"""
from datetime import timedelta

from django.utils import timezone

from project_manager_agent.ai_agents.analytics_dashboard_agent import AnalyticsDashboardAgent

from .base import PMTestCase


class ProjectHealthTests(PMTestCase):

    def health(self, start_days_ago, deadline_in):
        today = timezone.localdate()
        self.project.start_date = today - timedelta(days=start_days_ago)
        self.project.deadline = self.project.end_date = today + timedelta(days=deadline_in)
        self.project.save()
        return AnalyticsDashboardAgent().calculate_health_score(self.project.id, company_user=self.dash)

    def test_a_project_just_started_with_nothing_late_is_healthy(self):
        self.task(title='Cart')
        self.task(title='Menu')
        result = self.health(0, 35)
        self.assertEqual((result['health_score'], result['grade']), (100, 'A'))
        self.assertEqual(result['metrics']['time_elapsed_percent'], 0)

    def test_halfway_through_the_time_with_nothing_done_is_at_risk(self):
        self.task(title='Cart')
        self.task(title='Menu')
        result = self.health(10, 10)
        self.assertEqual(result['health_score'], 50)
        self.assertEqual(result['breakdown']['behind_schedule_penalty'], 50)

    def test_work_ahead_of_the_time_is_not_penalised_and_overdue_work_is(self):
        self.task(title='Cart', status='done')
        self.task(title='Menu', due_date=timezone.now() - timedelta(days=1))
        result = self.health(10, 30)     # a quarter of the time gone, half the work done, one task late
        self.assertEqual(result['health_score'], 75)
        self.assertEqual(result['breakdown']['overdue_penalty'], 25)


class TeamScoreTests(PMTestCase):
    """Team Performance gave everyone a red 0 on a project made that day (PM demo rehearsal, 25 Oct 2026)."""

    def scores(self):
        result = AnalyticsDashboardAgent().analyze_productivity(self.project.id, company_user=self.dash)
        return {m['name']: m['score'] for m in result['members']}

    def test_nothing_due_yet_has_no_score_and_work_done_or_late_does(self):
        later = timezone.now() + timedelta(days=9)
        self.task(title='Cart', assignee=self.dev, due_date=later)
        self.task(title='Menu', assignee=self.pm, status='done', due_date=later)
        self.task(title='Late', assignee=self.pm, due_date=timezone.now() - timedelta(days=1))
        self.assertEqual(self.scores(), {'Dev Tester': None, 'Pat Tester': 40})
