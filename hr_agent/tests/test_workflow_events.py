"""Every HR workflow event is one the code actually fires.

Two of the three built-in templates listened for events nothing sent —
`employee_offboarding_started` and `employee_30_days` — so a company that
installed them believed offboarding and 30-day check-ins were automated, and
they never ran. The API also accepted any event name, so the same mistake could
be made by hand.
"""

from datetime import timedelta

from django.utils import timezone

from api.views import hr_agent as views
from hr_agent import tasks
from hr_agent.models import Employee, HRWorkflow, HRWorkflowExecution
from hr_agent.signals import WORKFLOW_EVENTS
from hr_agent.workflow_templates import BUILTIN_WORKFLOWS, get_template

from .base import HRTestCase


class HRWorkflowEventTests(HRTestCase):

    def install(self, key):
        spec = get_template(key)
        return HRWorkflow.objects.create(
            company=self.company, name=spec['name'],
            trigger_conditions=spec['trigger_conditions'], steps=spec['steps'],
            requires_approval=spec['requires_approval'], is_active=True)

    def runs(self, workflow, employee):
        return HRWorkflowExecution.objects.filter(workflow=workflow, employee_id=employee.id).count()

    def started(self, days_ago, status='active'):
        return Employee.objects.create(
            company=self.company, full_name=f'Started {days_ago} days ago',
            work_email=f'start{days_ago}{status}@test.local', employment_status=status,
            start_date=timezone.now().date() - timedelta(days=days_ago))

    # ---- the templates ------------------------------------------------------

    def test_every_built_in_template_listens_for_an_event_that_fires(self):
        for key, spec in BUILTIN_WORKFLOWS.items():
            with self.subTest(template=key):
                self.assertIn(spec['trigger_conditions']['on'], WORKFLOW_EVENTS)

    def test_serving_notice_starts_the_offboarding_template(self):
        workflow = self.install('offboarding')
        self.member_emp.employment_status = 'notice'
        self.member_emp.save()
        run = HRWorkflowExecution.objects.get(workflow=workflow, employee_id=self.member_emp.id)
        # The template asks HR to approve before it does anything.
        self.assertEqual(run.status, 'awaiting_approval')

    def test_other_status_changes_do_not_start_offboarding(self):
        workflow = self.install('offboarding')
        self.member_emp.employment_status = 'probation'
        self.member_emp.save()
        self.assertEqual(self.runs(workflow, self.member_emp), 0)

    # ---- 30 days after the start date -------------------------------------------

    def test_the_30_day_check_in_runs_30_days_after_the_start_date(self):
        workflow = self.install('thirty_day_check_in')
        due, early = self.started(30), self.started(29)
        tasks.walk_hr_time_based_events()
        self.assertEqual(self.runs(workflow, due), 1)
        self.assertEqual(self.runs(workflow, early), 0)

    def test_it_runs_once_however_often_the_daily_job_runs(self):
        workflow = self.install('thirty_day_check_in')
        due = self.started(30)
        tasks.walk_hr_time_based_events()
        tasks.walk_hr_time_based_events()
        self.assertEqual(self.runs(workflow, due), 1)

    def test_a_missed_day_is_caught_up_within_a_week(self):
        workflow = self.install('thirty_day_check_in')
        late, too_late = self.started(30 + 7), self.started(30 + 8)
        tasks.walk_hr_time_based_events()
        self.assertEqual(self.runs(workflow, late), 1)
        self.assertEqual(self.runs(workflow, too_late), 0)

    def test_someone_who_already_left_gets_no_check_in(self):
        workflow = self.install('thirty_day_check_in')
        gone = self.started(30, status='offboarded')
        tasks.walk_hr_time_based_events()
        self.assertEqual(self.runs(workflow, gone), 0)

    # ---- the API ------------------------------------------------------------

    def test_a_workflow_for_an_event_that_never_fires_is_refused(self):
        code, body = self.call(views.create_hr_workflow, self.admin, {
            'name': 'Typo', 'trigger_conditions': {'on': 'employee_offboarded'}})
        self.assertEqual(code, 400)
        self.assertIn('employee_offboarded', body['message'])
        self.assertFalse(HRWorkflow.objects.filter(name='Typo').exists())

    def test_known_events_and_manual_workflows_are_accepted(self):
        for tc in ({'on': 'employee_30_days'}, {}):
            with self.subTest(trigger=tc):
                code, _ = self.call(views.create_hr_workflow, self.admin, {
                    'name': f'OK {tc}', 'trigger_conditions': tc})
                self.assertEqual(code, 201)

    def test_editing_a_workflow_to_an_unknown_event_is_refused(self):
        workflow = self.install('offboarding')
        code, _ = self.call(views.update_hr_workflow, self.admin,
                            {'trigger_conditions': {'on': 'nope'}},
                            method='patch', workflow_id=workflow.id)
        self.assertEqual(code, 400)
        workflow.refresh_from_db()
        self.assertEqual(workflow.trigger_conditions['on'], 'employee_offboarding_started')
