"""The recruiter's automatic-email switches and timings are honoured.

"Send follow-ups automatically" and "send reminders automatically" were saved
from Recruitment settings and read by nothing; and the timings saved there were
never used either, because they're stored against the dashboard login while
the senders only looked at the older employee-login recruiter.
"""
from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from core.models import Company, CompanyModulePurchase, CompanyUser
from recruitment_agent import tasks
from recruitment_agent.models import Interview, RecruiterEmailSettings


class EmailSwitchTests(TestCase):

    def setUp(self):
        company = Company.objects.create(name='Acme', email='acme@test.local')
        self.purchase = CompanyModulePurchase.objects.create(
            company=company, module_name='recruitment_agent', status='active', is_complimentary=True)
        self.recruiter = CompanyUser.objects.create(company=company, email='rae@test.local', full_name='Rae',
                                                    role='admin', password_hash='x', is_active=True)
        self.settings, _ = RecruiterEmailSettings.objects.update_or_create(
            company_user=self.recruiter, defaults={'followup_delay_hours': 1, 'reminder_hours_before': 5})
        now = timezone.now()
        with mock.patch('recruitment_agent.signals.threading.Thread'):     # no background checks here
            self.waiting = Interview.objects.create(
                candidate_name='Cara', candidate_email='cara@test.local', job_role='Designer',
                status='PENDING', available_slots_json='[]', company_user=self.recruiter,
                invitation_sent_at=now - timedelta(hours=3))
            self.booked = Interview.objects.create(
                candidate_name='Dev', candidate_email='dev@test.local', job_role='Backend',
                status='SCHEDULED', available_slots_json='[]', company_user=self.recruiter,
                scheduled_datetime=now + timedelta(hours=5), timezone_name='UTC')

    def run_job(self):
        agent = mock.Mock()
        agent.send_followup_reminder.return_value = {'success': True}
        agent.send_pre_interview_reminder.return_value = {'success': True}
        with mock.patch.object(tasks, 'get_interview_agent', return_value=agent), \
                mock.patch('recruitment_agent.signals.threading.Thread'):
            tasks.check_and_send_followup_emails()
        return agent

    def test_the_dashboard_settings_are_the_ones_used(self):
        self.assertEqual(self.waiting.get_followup_delay_hours(), 1)      # not the default 48
        self.assertEqual(self.booked.get_reminder_hours_before(), 5)

    def test_both_go_out_when_switched_on(self):
        agent = self.run_job()
        agent.send_followup_reminder.assert_called_once_with(self.waiting.id)
        agent.send_pre_interview_reminder.assert_called_once()

    def test_nothing_goes_out_once_the_subscription_is_not_active(self):
        # The screens lock when Recruitment lapses; candidates must not keep hearing from it.
        self.purchase.status = 'cancelled'
        self.purchase.save()
        agent = self.run_job()
        agent.send_followup_reminder.assert_not_called()
        agent.send_pre_interview_reminder.assert_not_called()

    def test_nothing_goes_out_when_switched_off(self):
        self.settings.auto_send_followups = False
        self.settings.auto_send_reminders = False
        self.settings.save()
        agent = self.run_job()
        agent.send_followup_reminder.assert_not_called()
        agent.send_pre_interview_reminder.assert_not_called()
