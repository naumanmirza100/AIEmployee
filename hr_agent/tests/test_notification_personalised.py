"""An HR reminder with "Personalise each message with AI" is rewritten for its person, and dates read as people
write them.

The template screen offered the tick, and the template kept it, but the sender never looked at it: every message
went out exactly as written. And the daily check's dates went out as 2026-11-03.
"""
from unittest import mock

from django.core import mail
from django.utils import timezone

from hr_agent.models import HRNotificationTemplate, HRScheduledNotification
from hr_agent.tasks import _render_template_body, process_hr_scheduled_notifications

from .base import HRTestCase

AGENT = 'core.HR_agent.hr_agent.HRAgent.personalize_message'


class PersonalisedTests(HRTestCase):

    def send(self, personalise):
        bilal = self.employee_with_login('bilal', 'Bilal Ahmed', self.company, self.admin)
        template = HRNotificationTemplate.objects.create(
            company=self.company, name='Probation ending', channel='email', subject='Your probation ends on {{event_date}}',
            body='Dear {{employee_name}}, your probation ends on {{event_date}}.', trigger_config={'on': 'probation_ending'},
            use_llm_personalization=personalise)
        notif = HRScheduledNotification.objects.create(
            company=self.company, template=template, recipient_employee=bilal, recipient_email=bilal.work_email,
            scheduled_at=timezone.now(), status='pending',
            context={'employee_name': 'Bilal Ahmed', 'event_date': '2026-11-03'})
        process_hr_scheduled_notifications()
        notif.refresh_from_db()
        self.assertEqual(notif.status, 'sent', notif.error_message)
        return mail.outbox[-1]

    def test_the_ai_writes_the_message_when_the_template_asks(self):
        with mock.patch(AGENT, return_value='Dear Bilal, a note just for you: your probation ends on 3 November 2026.') as ai:
            sent = self.send(personalise=True)
        self.assertIn('just for you', sent.body)
        self.assertEqual(ai.call_args.kwargs['name'], 'Bilal Ahmed')
        self.assertIn('3 November 2026', ai.call_args.args[0])

    def test_the_message_as_written_when_the_ai_fails(self):
        with mock.patch(AGENT, side_effect=RuntimeError('no key')):
            sent = self.send(personalise=True)
        self.assertEqual(sent.body, 'Dear Bilal Ahmed, your probation ends on 3 November 2026.')

    def test_no_ai_when_the_template_does_not_ask(self):
        with mock.patch(AGENT) as ai:
            sent = self.send(personalise=False)
        ai.assert_not_called()
        self.assertEqual(sent.subject, 'Your probation ends on 3 November 2026')


class ReadableDateTests(HRTestCase):

    def test_a_date_reads_as_people_write_it(self):
        self.assertEqual(_render_template_body('Ends {{d}}', {'d': '2026-02-08'}), 'Ends 8 February 2026')

    def test_other_values_are_left_alone(self):
        self.assertEqual(_render_template_body('{{a}} {{b}}', {'a': '2026-13-45', 'b': 'Q3 review'}),
                         '2026-13-45 Q3 review')
