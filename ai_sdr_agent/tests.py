"""Tests for the AI SDR high-severity fixes (reply dedup, OOO resume, bounces,
unsubscribe/suppression, quoted-reply classification, deleted leads,
subscription gating, approval link)."""
import smtplib
from datetime import timedelta
from unittest import mock

from django.test import Client, TestCase
from django.utils import timezone

from ai_sdr_agent.agents import outreach_agent as oa
from ai_sdr_agent.agents.email_assistant_agent import EmailAssistantAgent
from ai_sdr_agent.models import (
    SDRCampaign, SDRCampaignEnrollment, SDRCampaignStep, SDRLead, SDRMeeting,
    SDROutreachLog,
)
from core.models import Company, CompanyModulePurchase, CompanyUser


class SDRBase(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Acme', email='acme@test.local')
        self.cu = CompanyUser.objects.create(
            company=self.company, email='cu@test.local', full_name='CU',
            role='admin', password_hash='x', is_active=True,
        )
        CompanyModulePurchase.objects.create(
            company=self.company, module_name='ai_sdr_agent',
            status='active', is_complimentary=True,
        )
        self.campaign = SDRCampaign.objects.create(
            company_user=self.cu, name='C1', status='active',
            sender_name='Sam', sender_company='Acme', postal_address='1 Main St, Town',
            smtp_host='smtp.test', smtp_username='u', smtp_password='p',
        )
        SDRCampaignStep.objects.create(
            campaign=self.campaign, step_order=1, delay_days=1, step_type='email',
            subject_template='Hello', body_template='Hi there', ai_personalize=False,
        )
        SDRCampaignStep.objects.create(
            campaign=self.campaign, step_order=2, delay_days=3, step_type='email',
            subject_template='Follow up', body_template='Ping', ai_personalize=False,
        )

    def make_lead(self, email='bob@acme.com', **kw):
        return SDRLead.objects.create(
            company_user=self.cu, email=email, first_name='Bob', full_name='Bob B', **kw)

    def enroll(self, lead, campaign=None, **kw):
        return SDRCampaignEnrollment.objects.create(
            campaign=campaign or self.campaign, lead=lead, status='active',
            next_action_at=timezone.now() - timedelta(minutes=1), **kw)

    def agent(self):
        return oa.OutreachAgent()   # no company -> no LLM; templates used as-is


class OutreachSendTests(SDRBase):
    def test_email_has_unsubscribe_footer_address_and_headers(self):
        enr = self.enroll(self.make_lead())
        with mock.patch.object(oa.OutreachAgent, '_send_via_smtp') as smtp:
            res = self.agent().process_enrollment(enr)
        self.assertEqual(res['status'], 'sent')
        kwargs = smtp.call_args.kwargs
        self.assertIn('/api/sdr/unsubscribe/', kwargs['unsubscribe_url'])
        self.assertIn('1 Main St, Town', kwargs['body'])
        self.assertIn(kwargs['unsubscribe_url'], kwargs['body'])

    def test_permanent_rejection_marks_bounced_and_stops(self):
        lead = self.make_lead()
        enr = self.enroll(lead)
        with mock.patch.object(
            oa.OutreachAgent, '_send_via_smtp', side_effect=oa.PermanentSendError('550 no user')
        ):
            self.agent().process_enrollment(enr)
        enr.refresh_from_db(); lead.refresh_from_db()
        self.assertEqual(enr.status, 'bounced')
        self.assertTrue(lead.email_bounced)

    def test_smtp_550_is_permanent_but_auth_535_is_not(self):
        server = mock.MagicMock()
        server.__enter__.return_value = server
        for code, exc_cls in ((550, oa.PermanentSendError), (535, ValueError)):
            server.sendmail.side_effect = smtplib.SMTPResponseException(code, b'x')
            with mock.patch('smtplib.SMTP', return_value=server):
                with self.assertRaises(exc_cls) as ctx:
                    self.agent()._send_via_smtp(
                        'h', 587, 'u', 'p', False, 'a@b.c', '', 'to@x.com', 's', 'b')
            self.assertEqual(isinstance(ctx.exception, oa.PermanentSendError), code == 550)

    def test_transient_failures_stop_after_max_attempts(self):
        enr = self.enroll(self.make_lead())
        with mock.patch.object(oa.OutreachAgent, '_send_via_smtp', side_effect=ValueError('timeout')):
            for _ in range(oa.MAX_SEND_ATTEMPTS):
                enr.refresh_from_db()
                self.agent().process_enrollment(enr)
        enr.refresh_from_db()
        self.assertEqual(enr.status, 'paused')
        self.assertEqual(enr.current_step, 0)
        self.assertEqual(
            SDROutreachLog.objects.filter(enrollment=enr, status='failed').count(),
            oa.MAX_SEND_ATTEMPTS)

    def test_deleted_lead_is_not_emailed(self):
        lead = self.make_lead()
        enr = self.enroll(lead)
        lead.soft_delete()
        enr = SDRCampaignEnrollment.objects.get(pk=enr.pk)
        with mock.patch.object(oa.OutreachAgent, '_send_via_smtp') as smtp:
            res = self.agent().process_enrollment(enr)
            from ai_sdr_agent.tasks import send_due_steps_impl
            with mock.patch('ai_sdr_agent.agents.outreach_agent.OutreachAgent', return_value=self.agent()):
                send_due_steps_impl()
        self.assertEqual(res['status'], 'lead_deleted')
        smtp.assert_not_called()


class SchedulerTests(SDRBase):
    def test_ooo_enrollment_resumes_after_return_date(self):
        enr = self.enroll(self.make_lead())
        SDRCampaignEnrollment.objects.filter(pk=enr.pk).update(
            status='paused', reply_sentiment='out_of_office',
            next_action_at=timezone.now() - timedelta(hours=1))
        from ai_sdr_agent.tasks import send_due_steps_impl
        with mock.patch.object(oa.OutreachAgent, '_send_via_smtp') as smtp, \
                mock.patch('ai_sdr_agent.agents.outreach_agent.OutreachAgent', return_value=self.agent()):
            send_due_steps_impl()
        enr.refresh_from_db()
        self.assertEqual(enr.current_step, 1)     # step 1 was sent after resuming
        smtp.assert_called_once()

    def test_manual_pause_is_not_resumed(self):
        enr = self.enroll(self.make_lead())
        SDRCampaignEnrollment.objects.filter(pk=enr.pk).update(status='paused', reply_sentiment='')
        from ai_sdr_agent.tasks import send_due_steps_impl
        with mock.patch.object(oa.OutreachAgent, '_send_via_smtp') as smtp, \
                mock.patch('ai_sdr_agent.agents.outreach_agent.OutreachAgent', return_value=self.agent()):
            send_due_steps_impl()
        smtp.assert_not_called()

    def test_lapsed_subscription_blocks_sending(self):
        CompanyModulePurchase.objects.filter(company=self.company).update(status='cancelled', is_complimentary=False)
        self.enroll(self.make_lead())
        from ai_sdr_agent.tasks import send_due_steps_impl
        with mock.patch.object(oa.OutreachAgent, '_send_via_smtp') as smtp, \
                mock.patch('ai_sdr_agent.agents.outreach_agent.OutreachAgent', return_value=self.agent()):
            send_due_steps_impl()
        smtp.assert_not_called()

    def test_campaign_not_completed_while_ooo_paused(self):
        enr = self.enroll(self.make_lead())
        SDRCampaignEnrollment.objects.filter(pk=enr.pk).update(
            status='paused', reply_sentiment='out_of_office')
        from ai_sdr_agent.tasks import auto_pause_expired_campaigns_impl
        auto_pause_expired_campaigns_impl()
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.status, 'active')


class ReplyProcessingTests(SDRBase):
    def _run_inbox(self, replies, classification):
        from ai_sdr_agent.tasks import check_inbox_replies_impl
        fake_agent = mock.MagicMock()
        fake_agent.check_inbox_for_replies.return_value = replies
        fake_email = mock.MagicMock()
        fake_email.classify_reply.return_value = classification
        fake_email.generate_more_info_email.return_value = {'subject': 's', 'body': 'b'}
        with mock.patch('ai_sdr_agent.agents.outreach_agent.OutreachAgent', return_value=fake_agent), \
                mock.patch('ai_sdr_agent.agents.email_assistant_agent.EmailAssistantAgent', return_value=fake_email):
            check_inbox_replies_impl()
        return fake_agent, fake_email

    def reply(self, enr, mid='<m1@x>', text='tell me more'):
        return {'enrollment': enr, 'reply_text': text, 'sender_email': enr.lead.email,
                'subject': 'Re: Hello', 'message_id': mid,
                'received_at': timezone.now() - timedelta(minutes=1)}

    def test_same_reply_polled_twice_sends_one_info_email(self):
        enr = self.enroll(self.make_lead())
        cls = {'action': 'send_info', 'category': 'wants_more_info', 'label': 'x'}
        agent, _ = self._run_inbox([self.reply(enr)], cls)
        enr = SDRCampaignEnrollment.objects.get(pk=enr.pk)
        agent2, _ = self._run_inbox([self.reply(enr)], cls)
        self.assertEqual(agent.send_email.call_count, 1)
        self.assertEqual(agent2.send_email.call_count, 0)
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.replies_received, 1)

    def test_new_reply_after_first_is_processed(self):
        enr = self.enroll(self.make_lead())
        cls = {'action': 'send_info', 'category': 'wants_more_info', 'label': 'x'}
        self._run_inbox([self.reply(enr, '<m1@x>')], cls)
        enr = SDRCampaignEnrollment.objects.get(pk=enr.pk)
        r2 = self.reply(enr, '<m2@x>'); r2['received_at'] = timezone.now() + timedelta(minutes=5)
        agent, _ = self._run_inbox([r2], cls)
        self.assertEqual(agent.send_email.call_count, 1)

    def test_neutral_reply_stops_followups(self):
        enr = self.enroll(self.make_lead())
        self._run_inbox([self.reply(enr, text='ok')],
                        {'action': 'wait', 'category': 'neutral', 'label': 'x'})
        enr.refresh_from_db()
        self.assertEqual(enr.status, 'replied')

    def test_not_interested_unsubscribes_across_campaigns(self):
        lead = self.make_lead()
        enr = self.enroll(lead)
        other = SDRCampaign.objects.create(company_user=self.cu, name='C2', status='active')
        enr2 = SDRCampaignEnrollment.objects.create(campaign=other, lead=self.make_lead('bob@acme.com'))
        self._run_inbox([self.reply(enr, text='no thanks')],
                        {'action': 'stop', 'category': 'not_interested', 'label': 'x'})
        enr.refresh_from_db(); enr2.refresh_from_db()
        self.assertEqual(enr.status, 'unsubscribed')
        self.assertEqual(enr2.status, 'unsubscribed')
        self.assertTrue(oa.is_email_suppressed(self.cu, 'BOB@acme.com'))

    def test_bounce_notice_marks_lead_bounced(self):
        lead = self.make_lead()
        enr = self.enroll(lead)
        r = {'enrollment': enr, 'reply_text': 'x', 'sender_email': 'mailer-daemon@g.com',
             'subject': 'Delivery Status Notification (Failure)', 'is_bounce': True,
             'bounced_email': lead.email, 'message_id': '<b1>',
             'received_at': timezone.now()}
        self._run_inbox([r], {'action': 'wait', 'category': 'neutral', 'label': 'x'})
        enr.refresh_from_db(); lead.refresh_from_db()
        self.assertEqual(enr.status, 'bounced')
        self.assertTrue(lead.email_bounced)

    def test_claim_reply_is_atomic_and_stable(self):
        enr = self.enroll(self.make_lead())
        r = self.reply(enr)
        self.assertTrue(oa.claim_reply(enr, r))
        stale = SDRCampaignEnrollment.objects.get(pk=enr.pk)
        self.assertFalse(oa.claim_reply(stale, r))


class ClassificationTests(TestCase):
    def setUp(self):
        self.agent = EmailAssistantAgent()

    def cat(self, text):
        return self.agent.classify_reply(text)['category']

    def test_quoted_unsubscribe_footer_is_ignored(self):
        text = ("Sure, thanks.\n\nOn Mon, Jan 1, 2024 at 10:00 AM Sam\n<s@x.com> wrote:\n"
                "> Reply 'unsubscribe' to opt out")
        self.assertEqual(self.cat(text), 'neutral')

    def test_real_unsubscribe_still_detected(self):
        self.assertEqual(self.cat('Please unsubscribe me'), 'not_interested')

    def test_im_interested_is_not_im_in(self):
        self.assertNotEqual(self.cat("I'm interested in learning more"), 'positive_interest')
        self.assertEqual(self.cat("I'm in, let's talk"), 'positive_interest')


class PublicLinkTests(SDRBase):
    def setUp(self):
        super().setUp()
        self.client = Client()
        self.lead = self.make_lead()
        self.enr = self.enroll(self.lead)

    def test_unsubscribe_get_is_safe_post_unsubscribes(self):
        url = oa.build_unsubscribe_url(self.enr).split('.test')[-1]
        path = '/api/sdr/unsubscribe/' + oa.make_unsubscribe_token(self.enr.id) + '/'
        self.assertEqual(self.client.get(path).status_code, 200)
        self.enr.refresh_from_db()
        self.assertEqual(self.enr.status, 'active')          # GET changed nothing
        self.assertEqual(self.client.post(path).status_code, 200)
        self.enr.refresh_from_db(); self.lead.refresh_from_db()
        self.assertEqual(self.enr.status, 'unsubscribed')
        self.assertEqual(self.lead.status, 'disqualified')
        self.assertIn(b'expired', self.client.get('/api/sdr/unsubscribe/garbage/').content.lower())

    def test_suppressed_lead_is_not_sent_by_another_campaign(self):
        self.client.post('/api/sdr/unsubscribe/' + oa.make_unsubscribe_token(self.enr.id) + '/')
        other = SDRCampaign.objects.create(
            company_user=self.cu, name='C2', status='active', smtp_host='h',
            smtp_username='u', smtp_password='p')
        SDRCampaignStep.objects.create(campaign=other, step_order=1, subject_template='s',
                                       body_template='b', ai_personalize=False)
        dup = SDRLead.objects.create(company_user=self.cu, email='BOB@acme.com', first_name='B')
        enr2 = self.enroll(dup, campaign=other)
        with mock.patch.object(oa.OutreachAgent, '_send_via_smtp') as smtp:
            res = self.agent().process_enrollment(enr2)
        self.assertEqual(res['status'], 'suppressed')
        smtp.assert_not_called()

    def _meeting(self, status='awaiting_approval', scheduled=True):
        return SDRMeeting.objects.create(
            company_user=self.cu, lead=self.lead, enrollment=self.enr, status=status,
            scheduled_at=timezone.now() + timedelta(days=2) if scheduled else None)

    def test_approval_get_does_not_confirm_post_confirms_once(self):
        m = self._meeting()
        path = f'/api/sdr/meeting-approval/{m.approval_token}/yes/'
        with mock.patch(
            'ai_sdr_agent.agents.meeting_scheduling_agent.MeetingSchedulingAgent'
        ) as sched_cls:
            self.client.get(path)
            m.refresh_from_db(); self.assertEqual(m.status, 'awaiting_approval')
            self.client.post(path); self.client.post(path)      # double click
            m.refresh_from_db(); self.assertEqual(m.status, 'scheduled')
            self.assertEqual(
                sched_cls.return_value.send_confirmation_email.call_count, 1)

    def test_approval_refuses_meeting_without_time_or_not_proposed(self):
        for kwargs in ({'scheduled': False}, {'status': 'pending'}):
            SDRMeeting.objects.all().delete()
            m = self._meeting(**kwargs)
            self.client.post(f'/api/sdr/meeting-approval/{m.approval_token}/yes/')
            m.refresh_from_db()
            self.assertNotEqual(m.status, 'scheduled')

    def test_suggest_get_does_not_change_status(self):
        m = self._meeting()
        self.client.get(f'/api/sdr/meeting-approval/{m.approval_token}/suggest/')
        m.refresh_from_db()
        self.assertEqual(m.status, 'awaiting_approval')
