"""Things that are easy to unwire by accident: the audit trail, the rate
limits on the AI endpoints, and pagination on the list endpoints.
"""
from api.views import company_projects_tasks as company
from api.views import pm_agent as dashboard
from api.views import pm_subtasks
from api.views import user_project_manager as employee
from core.models import UserActivityLog
from project_manager_agent.models import PMAuditLog

from .base import PMTestCase


def throttles(view):
    """The throttle classes DRF will apply to an @api_view function."""
    return [cls.__name__ for cls in getattr(view, 'cls', view).throttle_classes]


class AuditTrailTests(PMTestCase):
    """D7 — one entry per write, in whichever log that login uses."""

    def test_a_dashboard_create_is_recorded(self):
        before = PMAuditLog.objects.count()
        code, body = self.call(dashboard.create_project_manual, self.dash, {'name': 'Audited'})
        self.assertEqual(code, 201, body)
        self.assertEqual(PMAuditLog.objects.count(), before + 1)
        entry = PMAuditLog.objects.latest('id')
        self.assertEqual(entry.company_user_id, self.dash.id)
        self.assertEqual(entry.action, 'project_created')

    def test_a_company_family_update_is_recorded(self):
        """This family used to write nothing at all."""
        before = PMAuditLog.objects.count()
        code, body = self.call(company.update_company_project, self.dash, {'name': 'Renamed'},
                               method='put', project_id=self.project.id)
        self.assertEqual(code, 200, body)
        self.assertEqual(PMAuditLog.objects.count(), before + 1)

    def test_an_employee_write_is_recorded_against_the_person(self):
        before = UserActivityLog.objects.count()
        code, body = self.call(employee.create_project_manager_project, self.pm,
                               {'name': 'Employee project'})
        self.assertEqual(code, 201, body)
        self.assertEqual(UserActivityLog.objects.count(), before + 1)
        entry = UserActivityLog.objects.latest('id')
        self.assertEqual(entry.user_id, self.pm.id)

    def test_a_refused_write_records_nothing(self):
        before = PMAuditLog.objects.count()
        self.call(dashboard.create_project_manual, self.dash, {'name': 'X', 'status': 'nope'})
        self.assertEqual(PMAuditLog.objects.count(), before)


class ThrottleWiringTests(PMTestCase):
    """GAP-3 — every LLM-backed endpoint is billable, so none may be unlimited."""

    AI_TOOLS = ['generate_subtasks', 'timeline_gantt', 'pm_generate_graph',
                'project_pilot_from_file', 'daily_standup', 'project_status_report',
                'meeting_notes', 'workflow_suggest', 'calendar_schedule', 'time_estimation']
    CHAT_TOOLS = ['project_pilot', 'task_prioritization', 'knowledge_qa', 'meeting_schedule']

    def test_ai_tool_endpoints_have_their_own_budget(self):
        for name in self.AI_TOOLS:
            with self.subTest(endpoint=name):
                self.assertIn('PMLLMToolThrottle', throttles(getattr(dashboard, name)))

    def test_chat_endpoints_share_the_conversation_budget(self):
        for name in self.CHAT_TOOLS:
            with self.subTest(endpoint=name):
                self.assertIn('PMLLMThrottle', throttles(getattr(dashboard, name)))

    def test_subtask_writes_are_throttled(self):
        for name in ['create_subtask', 'update_subtask', 'delete_subtask', 'reorder_subtasks']:
            with self.subTest(endpoint=name):
                self.assertIn('PMCRUDThrottle', throttles(getattr(pm_subtasks, name)))


class PaginationTests(PMTestCase):
    """PERF-2 — list endpoints report their window instead of returning everything."""

    def test_the_company_user_list_reports_its_window(self):
        code, body = self.call(employee.get_company_users_for_pm, self.pm, method='get')
        self.assertEqual(code, 200, body)
        self.assertEqual(
            set(body['pagination']), {'limit', 'offset', 'total', 'returned', 'has_more'})
        self.assertEqual(body['pagination']['total'], len(body['data']))

    def test_a_limit_is_honoured(self):
        code, body = self.call(employee.get_company_users_for_pm, self.pm, {'limit': 1},
                               method='get')
        self.assertEqual(code, 200, body)
        self.assertEqual(len(body['data']), 1)
        self.assertTrue(body['pagination']['has_more'])
