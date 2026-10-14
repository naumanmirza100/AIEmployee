"""A mailbox that will not send is the mailbox's problem, not the lead's.

Any refusal from the mail server numbered 550, 551, 553 or 554 was read as 'this
recipient will never work'. The lead was flagged as bounced, all their open
enrolments stopped, and the address went on the company-wide do-not-email list
that Marketing obeys too. But the same numbers are used for a daily sending
limit and for a From address the account may not use, which are the same for
every lead: one bad day at the mailbox wiped out the whole list that was due.
"""
import smtplib
from unittest import mock

from rest_framework.test import APIRequestFactory, force_authenticate

from ai_sdr_agent.agents import outreach_agent as oa
from ai_sdr_agent.models import SDRCampaign, SDRCampaignEnrollment, SDRLead, SDROutreachLog
from ai_sdr_agent.tests import SDRBase
from api.views import ai_sdr_agent as views
from core.do_not_email import is_blocked
from project_manager_agent.models import PMNotification

QUOTA = (550, b'5.4.5 Daily user sending quota exceeded. j3sm123 - gsmtp')
NO_SUCH_USER = (550, b'5.1.1 The email account that you tried to reach does not exist.')


class WhatTheRefusalIsAboutTests(SDRBase):
    """How one send reads the mail server's answer."""

    def outcome(self, raised):
        server = mock.MagicMock()
        server.__enter__.return_value = server
        server.sendmail.side_effect = raised
        with mock.patch('smtplib.SMTP', return_value=server), \
                mock.patch.object(oa, 'validate_mail_server', return_value=None):
            try:
                self.agent()._send_via_smtp('h', 587, 'u', 'p', False, 'a@b.c', '', 'to@x.com', 's', 'b')
            except oa.PermanentSendError:
                return 'dead address'
            except oa.MailboxRefusedError:
                return 'mailbox refused'
            except ValueError:
                return 'try again'
        return 'sent'

    def at_recipient(self, code, said):
        return self.outcome(smtplib.SMTPRecipientsRefused({'to@x.com': (code, said)}))

    def test_a_refusal_naming_the_recipient_means_a_dead_address(self):
        self.assertEqual(self.at_recipient(*NO_SUCH_USER), 'dead address')
        self.assertEqual(self.at_recipient(550, b'User unknown'), 'dead address')
        self.assertEqual(self.at_recipient(553, b'no such mailbox here'), 'dead address')     # says nothing else

    def test_a_sending_limit_or_a_from_address_problem_is_not_a_dead_address(self):
        for answer in (QUOTA, (550, b'5.7.1 Sender address rejected: not owned by user u@acme.test'),
                       (554, b'5.7.1 Relay access denied'), (553, b'You have exceeded your hourly sending limit')):
            self.assertEqual(self.at_recipient(*answer), 'mailbox refused', answer)

    def test_a_temporary_refusal_is_tried_again(self):
        self.assertEqual(self.at_recipient(451, b'4.7.1 Greylisted, try again later'), 'try again')
        self.assertEqual(self.outcome(smtplib.SMTPDataError(452, b'4.2.2 Mailbox full')), 'try again')

    def test_the_server_refusing_the_sender_or_the_login_is_the_mailbox(self):
        self.assertEqual(self.outcome(smtplib.SMTPSenderRefused(550, b'Sender not allowed', 'a@b.c')),
                         'mailbox refused')
        self.assertEqual(self.outcome(smtplib.SMTPAuthenticationError(535, b'Username and Password not accepted')),
                         'mailbox refused')

    def test_a_refusal_when_the_message_is_handed_over_is_only_believed_when_it_says_which(self):
        self.assertEqual(self.outcome(smtplib.SMTPDataError(*QUOTA)), 'mailbox refused')
        self.assertEqual(self.outcome(smtplib.SMTPDataError(*NO_SUCH_USER)), 'dead address')
        self.assertEqual(self.outcome(smtplib.SMTPDataError(554, b'Transaction failed')), 'try again')
        self.assertEqual(self.outcome(smtplib.SMTPResponseException(550, b'x')), 'try again')


class CampaignPausedNotLeadsBouncedTests(SDRBase):

    def setUp(self):
        super().setUp()
        self.leads = [self.make_lead(f'lead{n}@customer.test') for n in range(4)]
        self.enrolments = [self.enroll(lead) for lead in self.leads]

    def run_job(self, raised):
        from ai_sdr_agent.tasks import send_due_steps_impl
        agent = self.agent()                    # the real one, with no AI behind it
        with mock.patch.object(oa.OutreachAgent, '_send_via_smtp', side_effect=raised) as smtp, \
                mock.patch('ai_sdr_agent.agents.outreach_agent.OutreachAgent', return_value=agent):
            send_due_steps_impl()
        return smtp.call_count

    def test_one_refusal_from_the_mailbox_pauses_the_campaign_and_marks_nobody(self):
        tried = self.run_job(oa.MailboxRefusedError('550 5.4.5 Daily user sending quota exceeded'))

        self.assertEqual(tried, 1)                                   # it did not go on through the list
        campaign = SDRCampaign.objects.get(pk=self.campaign.pk)
        self.assertEqual(campaign.status, 'paused')
        self.assertIn('Daily user sending quota exceeded', campaign.paused_reason)
        for lead in self.leads:
            lead.refresh_from_db()
            self.assertFalse(lead.email_bounced, lead.email)
            self.assertFalse(is_blocked(self.company.id, lead.email), lead.email)
        self.assertEqual(set(SDRCampaignEnrollment.objects.filter(campaign=campaign).values_list('status', flat=True)),
                         {'active'})

    def test_the_lead_it_was_trying_keeps_its_place(self):
        self.run_job(oa.MailboxRefusedError('550 quota'))
        tried = SDROutreachLog.objects.get(status='failed').enrollment
        self.assertEqual((tried.status, tried.current_step), ('active', 0))

    def test_the_owner_is_told_once_what_the_mailbox_said(self):
        self.run_job(oa.MailboxRefusedError('550 5.4.5 Daily user sending quota exceeded'))
        [alert] = PMNotification.objects.filter(company_user=self.cu)
        self.assertIn('was paused', alert.title)
        self.assertIn('Daily user sending quota exceeded', alert.message)
        self.run_job(oa.MailboxRefusedError('550 quota'))                 # paused: nothing is tried, nobody told again
        self.assertEqual(PMNotification.objects.filter(company_user=self.cu).count(), 1)

    def test_a_dead_address_is_still_marked_and_the_campaign_carries_on(self):
        tried = self.run_job(oa.PermanentSendError('550 5.1.1 no such user'))
        self.assertEqual(tried, len(self.leads))
        self.assertEqual(SDRCampaign.objects.get(pk=self.campaign.pk).status, 'active')
        self.assertTrue(all(SDRLead.objects.get(pk=lead.pk).email_bounced for lead in self.leads))

    def test_the_screen_is_given_the_reason_while_it_is_paused_and_resuming_clears_it(self):
        self.run_job(oa.MailboxRefusedError('553 From address not allowed'))

        def call(method, data=None):
            request = getattr(APIRequestFactory(), method)('/x', data or {}, format='json')
            force_authenticate(request, user=self.cu)
            with mock.patch.object(views, '_validate_mail_settings', return_value=None):
                return views.sdr_campaign_detail(request, campaign_id=self.campaign.id).data['data']

        self.assertIn('From address not allowed', call('get')['paused_reason'])
        self.assertIn('From address not allowed', call('put', {'name': 'Renamed'})['paused_reason'])   # still paused
        resumed = call('put', {'status': 'active'})
        self.assertEqual((resumed['status'], resumed['paused_reason']), ('active', ''))
        self.assertEqual(call('put', {'status': 'paused'})['paused_reason'], '')       # paused by a person: no reason
