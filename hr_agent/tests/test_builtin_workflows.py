"""The three ready-made HR workflows run to the end.

As shipped, none did. Their steps were written in a shape the engine did not
read: emails carried their own subject and text where the engine wanted a saved
template ("Template not found"), meetings named a day where it wanted a moment
("scheduled_at required"). Onboarding stopped at the welcome email, the 30-day
check-in at its first step, and offboarding, once approved, was marked
Completed without running anything. Nobody was told a run had failed.
"""
from datetime import date, datetime, timedelta, timezone as dt_timezone
from types import SimpleNamespace
from unittest import mock

from django.core import mail
from django.utils import timezone

from api.views import hr_agent as views
from hr_agent import alerts
from hr_agent.models import Employee, HRMeeting, HRNotificationTemplate, HRWorkflow, HRWorkflowExecution
from hr_agent.workflow_engine import _day_from_offset, execute_workflow
from hr_agent.workflow_templates import BUILTIN_WORKFLOWS
from project_manager_agent.models import PMNotification

from .base import HRTestCase


class BuiltInWorkflowTests(HRTestCase):

    def install(self, key):
        code, body = self.call(views.create_workflow_from_template, self.admin, {'template_key': key})
        self.assertEqual(code, 201, body)
        return HRWorkflow.objects.get(pk=body['data']['id'])

    def hire(self, with_login=True, **fields):
        """A new starter reporting to Mo, with or without an employee login."""
        fields.setdefault('start_date', timezone.localdate() + timedelta(days=14))
        if with_login:
            employee = self.employee_with_login('nina', 'Nina New', self.company, self.admin)
            Employee.objects.filter(pk=employee.pk).update(manager=self.member_emp, **fields)
            employee.refresh_from_db()
            return employee
        return Employee.objects.create(company=self.company, full_name='Nina New', work_email='nina@test.local',
                                       manager=self.member_emp, employment_status='active', **fields)

    def run_for(self, workflow, employee):
        code, body = self.call(views.execute_hr_workflow, self.admin, {'context': {'employee_id': employee.id}},
                               workflow_id=workflow.id)
        self.assertIn(code, (200, 202), body)
        return HRWorkflowExecution.objects.get(pk=body['data']['execution_id'])

    def alerts_to(self, who):
        return list(PMNotification.objects.filter(company_user=who).values_list('title', flat=True))

    # ---- onboarding --------------------------------------------------------

    def test_onboarding_sends_the_welcome_email_and_books_both_meetings(self):
        nina = self.hire()
        workflow = self.install('new_hire_onboarding')
        run = self.run_for(workflow, nina)
        self.assertEqual((run.status, run.error_message), ('completed', None), run.result_data)
        self.assertEqual(run.result_data['steps_completed'], len(BUILTIN_WORKFLOWS['new_hire_onboarding']['steps']))

        welcome, = mail.outbox
        self.assertEqual(welcome.to, ['nina@test.local'])
        self.assertEqual(welcome.subject, 'Welcome to the team, Nina New!')
        self.assertIn(f'{nina.start_date:%d %B %Y}', welcome.body)
        self.assertNotIn('{{', welcome.subject + welcome.body)

        orientation, check_in = HRMeeting.objects.filter(company=self.company).order_by('scheduled_at')
        self.assertEqual((orientation.title, orientation.organizer), ('Onboarding orientation', self.member_emp))
        self.assertEqual(list(orientation.participants.all()), [nina])
        self.assertGreaterEqual(orientation.scheduled_at.date(), nina.start_date)      # on or just after day one
        self.assertLess(orientation.scheduled_at.date(), nina.start_date + timedelta(days=4))
        self.assertGreaterEqual(check_in.scheduled_at.date(), nina.start_date + timedelta(days=30))
        for meeting in (orientation, check_in):
            self.assertLess(meeting.scheduled_at.weekday(), 5)                         # never a weekend

    def test_a_new_hire_with_no_login_still_gets_the_email_and_hr_is_told_about_the_meetings(self):
        workflow = self.install('new_hire_onboarding')
        nina = self.hire(with_login=False)
        run = HRWorkflowExecution.objects.get(workflow=workflow, employee_id=nina.id)   # started by being added
        self.assertEqual(run.status, 'completed', run.result_data)
        self.assertEqual(run.result_data['steps_skipped'], 2)
        self.assertEqual([m.to for m in mail.outbox], [['nina@test.local']])
        self.assertFalse(HRMeeting.objects.filter(company=self.company).exists())
        title = 'Workflow finished with a step skipped: New hire onboarding'
        self.assertEqual(self.alerts_to(self.admin).count(title), 1)
        note = PMNotification.objects.get(company_user=self.admin, title=title)
        self.assertIn('no login yet', note.message)
        self.assertEqual(self.alerts_to(self.rival_admin), [])

    def test_a_meeting_moves_to_a_free_time_when_the_day_is_taken(self):
        nina = self.hire()
        workflow = self.install('thirty_day_check_in')
        first = self.run_for(workflow, nina)
        second = self.run_for(workflow, nina)                       # the same day and hour again
        self.assertEqual((first.status, second.status), ('completed', 'completed'), second.result_data)
        times = list(HRMeeting.objects.filter(company=self.company).values_list('scheduled_at', flat=True))
        self.assertEqual(len(set(times)), 2)

    def test_a_day_offset_means_ten_oclock_on_a_working_day_that_has_not_passed(self):
        friday_afternoon = datetime(2026, 10, 9, 15, 0, tzinfo=dt_timezone.utc)
        started = SimpleNamespace(start_date=date(2026, 9, 1))        # long ago
        starts = SimpleNamespace(start_date=date(2026, 10, 24))       # a Saturday
        with mock.patch('django.utils.timezone.now', return_value=friday_afternoon):
            cases = {
                'tomorrow is Saturday, so Monday': ({'offset_days_from_now': 1}, None, (2026, 10, 12, 10)),
                'today is never used': ({'offset_days_from_now': 0}, None, (2026, 10, 12, 10)),
                'a start date that has passed': ({'offset_days_from_start': 0}, started, (2026, 10, 12, 10)),
                'a start date on a Saturday': ({'offset_days_from_start': 0}, starts, (2026, 10, 26, 10)),
                'counted from the start date': ({'offset_days_from_start': 30}, started, (2026, 10, 12, 10)),
                'the hour the step asks for': ({'offset_days_from_now': 4, 'at_hour': 14}, None, (2026, 10, 13, 14)),
                'no start date: counted from today': ({'offset_days_from_start': 5}, None, (2026, 10, 14, 10)),
            }
            for name, (step, employee, expected) in cases.items():
                with self.subTest(name):
                    at = _day_from_offset(step, employee, 'Asia/Karachi')
                    self.assertEqual((at.year, at.month, at.day, at.hour), expected)
                    self.assertEqual(at.utcoffset(), timedelta(hours=5))      # the hour is local

    # ---- 30-day check-in ---------------------------------------------------

    def test_the_30_day_check_in_books_the_meeting_and_emails_the_agenda(self):
        nina = self.hire(start_date=timezone.localdate() - timedelta(days=30))
        workflow = self.install('thirty_day_check_in')
        run = self.run_for(workflow, nina)
        self.assertEqual(run.status, 'completed', run.result_data)
        meeting = HRMeeting.objects.get(company=self.company)
        self.assertEqual((meeting.title, meeting.organizer), ('30-day check-in', self.member_emp))
        self.assertGreater(meeting.scheduled_at, timezone.now())
        self.assertEqual(mail.outbox[-1].subject, 'Your 30-day check-in is scheduled')

    # ---- offboarding -------------------------------------------------------

    def test_offboarding_runs_its_steps_once_approved_and_finishes_after_the_second_approval(self):
        workflow = self.install('offboarding')
        nina = self.hire()
        nina.employment_status = 'notice'
        nina.save(update_fields=['employment_status', 'updated_at'])
        run = HRWorkflowExecution.objects.get(workflow=workflow, employee_id=nina.id)
        self.assertEqual(run.status, 'awaiting_approval')
        self.assertEqual(len(mail.outbox), 0)                        # nothing before approval

        code, body = self.call(views.approve_hr_workflow_execution, self.admin, {}, execution_id=run.id)
        self.assertEqual(code, 200, body)
        run.refresh_from_db()
        # It used to be 'completed' here, with no step run.
        self.assertEqual(run.status, 'awaiting_approval', run.result_data)
        exit_interview = HRMeeting.objects.get(company=self.company)
        self.assertEqual((exit_interview.title, exit_interview.visibility), ('Exit interview', 'private'))
        self.assertEqual(exit_interview.organizer, self.admin_emp)   # 'with_hr': an HR admin runs it
        self.assertEqual(mail.outbox[-1].subject, 'Off-boarding: equipment return')
        nina.refresh_from_db()
        self.assertEqual(nina.employment_status, 'notice')

        code, body = self.call(views.approve_hr_workflow_execution, self.admin, {}, execution_id=run.id)
        self.assertEqual(code, 200, body)
        run.refresh_from_db()
        nina.refresh_from_db()
        self.assertEqual((run.status, nina.employment_status), ('completed', 'offboarded'), run.result_data)
        nina.user.refresh_from_db()
        self.assertFalse(nina.user.is_active)                        # and their login goes with it

    # ---- the engine, for workflows people write themselves ------------------

    def test_a_saved_template_still_works_and_a_missing_one_still_fails(self):
        HRNotificationTemplate.objects.create(company=self.company, name='Welcome', subject='Hi {{ employee.first_name }}',
                                              body='Welcome, {{employee.full_name}}.', channel='email')
        workflow = HRWorkflow.objects.create(company=self.company, name='Mine', steps=[
            {'type': 'send_email', 'template_name': 'Welcome'}])
        self.assertEqual(self.run_for(workflow, self.member_emp).status, 'completed')
        self.assertEqual((mail.outbox[-1].subject, mail.outbox[-1].body), ('Hi Mo', 'Welcome, Mo Member.'))

        workflow.steps = [{'type': 'send_email', 'template_name': 'No such template', 'body': 'ignored'}]
        workflow.save()
        run = self.run_for(workflow, self.member_emp)
        self.assertEqual((run.status, run.error_message), ('failed', 'Template not found'))

    def test_an_email_step_with_nothing_to_say_fails(self):
        workflow = HRWorkflow.objects.create(company=self.company, name='Empty', steps=[{'type': 'send_email'}])
        run = self.run_for(workflow, self.member_emp)
        self.assertEqual(run.status, 'failed')
        self.assertIn('no template and no text', run.error_message)

    def test_a_meeting_step_at_a_fixed_time_is_not_moved(self):
        nina = self.hire()
        taken = (timezone.now() + timedelta(days=5)).replace(hour=10, minute=0, second=0, microsecond=0)
        while taken.weekday() >= 5:
            taken += timedelta(days=1)
        step = {'type': 'schedule_meeting', 'title': 'Fixed', 'scheduled_at': taken.isoformat()}
        workflow = HRWorkflow.objects.create(company=self.company, name='Fixed', steps=[step])
        self.assertEqual(self.run_for(workflow, nina).status, 'completed')
        run = self.run_for(workflow, nina)
        self.assertEqual(run.status, 'failed')                        # a clash, as before
        self.assertEqual(HRMeeting.objects.filter(company=self.company).count(), 1)

    def test_a_step_stops_the_run_unless_it_says_to_carry_on(self):
        broken = {'type': 'update_employee', 'fields': {}}
        steps = [broken, {'type': 'update_employee', 'fields': {'job_title': 'Reached'}}]
        ok, result, error = execute_workflow(
            HRWorkflow(company=self.company, name='Stops', steps=steps), {'employee_id': self.member_emp.id}, None)
        self.assertEqual((ok, error, len(result['results'])), (False, 'No `fields` to update', 1))

        steps[0] = {**broken, 'continue_on_error': True}
        ok, result, error = execute_workflow(
            HRWorkflow(company=self.company, name='Carries on', steps=steps), {'employee_id': self.member_emp.id}, None)
        self.assertEqual((ok, error, result['steps_skipped'], result['steps_completed']), (True, None, 1, 1))
        self.assertTrue(result['results'][0]['skipped'])
        self.member_emp.refresh_from_db()
        self.assertEqual(self.member_emp.job_title, 'Reached')

    # ---- telling people ------------------------------------------------------

    def test_hr_admins_hear_once_when_a_run_fails(self):
        workflow = HRWorkflow.objects.create(company=self.company, name='Broken', steps=[{'type': 'send_email'}])
        run = self.run_for(workflow, self.member_emp)
        run.save()                                                   # saved again later: no second alert
        self.assertEqual(self.alerts_to(self.admin).count('Workflow failed: Broken'), 1)
        self.assertEqual(self.alerts_to(self.member), [])            # not an HR admin
        note = PMNotification.objects.get(company_user=self.admin, title='Workflow failed: Broken')
        self.assertIn('Mo Member', note.message)
        self.assertIn('no template and no text', note.message)

    def test_a_clean_run_alerts_nobody(self):
        workflow = HRWorkflow.objects.create(company=self.company, name='Fine', steps=[
            {'type': 'update_employee', 'fields': {'job_title': 'Designer'}}])
        self.assertEqual(self.run_for(workflow, self.member_emp).status, 'completed')
        self.assertEqual(self.alerts_to(self.admin), [])

    def test_the_hand_off_alert_says_how_onboarding_really_went(self):
        HRWorkflow.objects.create(company=self.company, name='Welcome pack', is_active=True,
                                  trigger_conditions={'on': 'employee_hired'}, steps=[{'type': 'send_email'}])
        self.install('new_hire_onboarding')
        nina = self.hire(with_login=False)
        PMNotification.objects.all().delete()
        alerts.new_starter_from_recruitment(nina, added_by='Rae', onboarding=['Welcome pack', 'New hire onboarding'])
        message = PMNotification.objects.get(company_user=self.admin).message
        self.assertIn('Welcome pack (failed: This email step has no template and no text)', message)
        self.assertIn('New hire onboarding (done, 2 steps skipped)', message)
        self.assertNotIn('Onboarding started', message)
