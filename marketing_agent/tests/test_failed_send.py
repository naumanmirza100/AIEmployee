"""A send that failed is tried again by the sender, once, and by nothing else.

A separate job ran every 15 minutes, took the emails marked failed or pending in
the last day and sent each one again. A resend that worked was written as a new
row and the old row stayed 'failed', so the next run picked it up again: one
failure could go out up to 96 times in a day, whether or not the campaign was
still running or the lead had replied. The job is gone. The sequence sender
already repeats a failed step on its next run, because it does not move the
contact forward when a send fails.
"""
from importlib import import_module

from django.conf import settings

from marketing_agent import tasks
from marketing_agent.models import CampaignContact, EmailSendHistory
from marketing_agent.tests.base import MarketingTestCase


class FailedSendTests(MarketingTestCase):

    def setUp(self):
        super().setUp()
        self.spring = self.campaign(self.ann)
        self.main = self.sequence(self.spring, steps=2)
        self.lead_a = self.lead(self.ann, 'bilal@customer.test', campaign=self.spring)

    def contact(self):
        return CampaignContact.objects.get(campaign=self.spring, lead=self.lead_a, sequence=self.main)

    def test_the_resend_job_is_gone(self):
        self.assertFalse(hasattr(tasks, 'retry_failed_emails_task'))
        named = [entry['task'] for entry in settings.CELERY_BEAT_SCHEDULE.values()]
        self.assertNotIn('marketing_agent.tasks.retry_failed_emails_task', named)
        self.assertNotIn('retry-failed-emails', settings.CELERY_BEAT_SCHEDULE)

    def test_every_marketing_job_on_the_schedule_exists(self):
        for name, entry in settings.CELERY_BEAT_SCHEDULE.items():
            module, _, function = entry['task'].rpartition('.')
            if module.startswith('marketing_agent'):
                self.assertTrue(hasattr(import_module(module), function), f'{name}: {entry["task"]}')

    def test_a_failed_step_is_sent_again_after_a_wait_and_then_no_more(self):
        self.assertEqual(self.run_sender(False), [('bilal@customer.test', 'Main 1')])
        contact = self.contact()
        self.assertEqual((contact.current_step, contact.send_failures), (0, 1))  # it did not move on
        # Not on the very next run (every five minutes, for ever, CO-122): after its retry time.
        self.assertEqual(self.run_sender(), [])
        from django.utils import timezone
        type(contact).objects.filter(pk=contact.pk).update(retry_after=timezone.now())

        self.assertEqual(self.run_sender(True), [('bilal@customer.test', 'Main 1')])
        self.assertEqual(self.contact().current_step, 1)

        # Step two waits for its own delay (none here); step one is never sent a third time.
        later = self.run_sender() + self.run_sender() + self.run_sender()
        self.assertEqual(later, [('bilal@customer.test', 'Main 2')])

    def test_a_row_left_marked_failed_makes_nothing_go_out_again(self):
        self.run_sender(True, True)
        self.run_sender()
        template = self.main.steps.get(step_order=1).template
        EmailSendHistory.objects.create(campaign=self.spring, lead=self.lead_a, email_template=template,
                                        subject=template.subject, recipient_email=self.lead_a.email,
                                        status='failed')
        EmailSendHistory.objects.create(campaign=self.spring, lead=self.lead_a, email_template=template,
                                        subject=template.subject, recipient_email=self.lead_a.email,
                                        status='pending')
        for _ in range(3):
            self.assertEqual(self.run_sender(), [])
