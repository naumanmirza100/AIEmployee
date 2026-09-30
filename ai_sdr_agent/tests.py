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
            with mock.patch('smtplib.SMTP', return_value=server), \
                    mock.patch.object(oa, 'validate_mail_server', return_value=None):
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


# ─────────────────────────── Medium-severity fixes ────────────────────────────
from django.test import override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from ai_sdr_agent import scheduler as sdr_scheduler
from ai_sdr_agent.agents import meeting_scheduling_agent as msa
from ai_sdr_agent.models import SDRIcpProfile, SDRAgentSettings
from api.views import ai_sdr_agent as views


class SendGuardTests(SDRBase):
    def test_unfilled_placeholder_is_never_sent(self):
        step = self.campaign.steps.get(step_order=1)
        step.body_template = "We help companies like yours [key value proposition]."
        step.save()
        enr = self.enroll(self.make_lead())
        with mock.patch.object(oa.OutreachAgent, '_send_via_smtp') as smtp:
            res = self.agent().process_enrollment(enr)
        self.assertEqual(res['status'], 'failed')
        self.assertIn('placeholder', res['error'])
        smtp.assert_not_called()

    @override_settings(SDR_MAX_EMAILS_PER_CAMPAIGN_PER_CYCLE=3)
    def test_send_throttle_limits_a_cycle(self):
        for i in range(8):
            self.enroll(self.make_lead(f'lead{i}@x{i}.com'))
        from ai_sdr_agent.tasks import send_due_steps_impl
        with mock.patch.object(oa.OutreachAgent, '_send_via_smtp') as smtp, \
                mock.patch('ai_sdr_agent.agents.outreach_agent.OutreachAgent', return_value=self.agent()):
            send_due_steps_impl()
        self.assertEqual(smtp.call_count, 3)

    @override_settings(SDR_MAX_EMAILS_PER_CAMPAIGN_PER_DAY=2)
    def test_daily_cap_counts_todays_sent_emails(self):
        for i in range(4):
            self.enroll(self.make_lead(f'd{i}@y{i}.com'))
        from ai_sdr_agent.tasks import send_due_steps_impl
        with mock.patch.object(oa.OutreachAgent, '_send_via_smtp') as smtp, \
                mock.patch('ai_sdr_agent.agents.outreach_agent.OutreachAgent', return_value=self.agent()):
            send_due_steps_impl()
            send_due_steps_impl()
        self.assertEqual(smtp.call_count, 2)


class MailServerValidationTests(TestCase):
    def test_blank_host_is_allowed(self):
        self.assertIsNone(oa.validate_mail_server('', 587))

    def test_private_and_loopback_hosts_are_rejected(self):
        for host in ('localhost', '127.0.0.1', '169.254.169.254', '10.0.0.5'):
            self.assertIsNotNone(oa.validate_mail_server(host, 587), host)

    def test_odd_ports_are_rejected(self):
        self.assertIsNotNone(oa.validate_mail_server('smtp.gmail.com', 6379, 'smtp'))
        self.assertIsNotNone(oa.validate_mail_server('imap.gmail.com', 25, 'imap'))

    def test_public_host_passes_and_override_allows_private(self):
        public = [(2, 1, 6, '', ('142.250.1.1', 0))]
        with mock.patch('socket.getaddrinfo', return_value=public):
            self.assertIsNone(oa.validate_mail_server('smtp.gmail.com', 587))
        with override_settings(SDR_ALLOW_PRIVATE_MAIL_HOSTS=True):
            self.assertIsNone(oa.validate_mail_server('localhost', 587))

    def test_send_to_internal_host_is_blocked_before_connecting(self):
        with mock.patch('smtplib.SMTP') as smtp:
            with self.assertRaises(ValueError):
                oa.OutreachAgent()._send_via_smtp(
                    '127.0.0.1', 587, 'u', 'p', False, 'a@b.c', '', 't@x.com', 's', 'b')
        smtp.assert_not_called()


class EmailHtmlEscapeTests(TestCase):
    def test_lead_and_sender_fields_are_escaped(self):
        out = msa._build_scheduling_html(
            '<script>alert(1)</script>', 'Sam <b>', 'CEO', 'A&B', '30 min',
            'https://x.test/b?a=1&b=2', '<img src=x onerror=1>')
        self.assertNotIn('<script>', out)
        self.assertNotIn('<img src=x', out)
        self.assertIn('&lt;script&gt;', out)
        self.assertIn('A&amp;B', out)


class JobLockTests(TestCase):
    def test_only_one_process_can_hold_a_job(self):
        self.assertTrue(sdr_scheduler.acquire_job('t1', 600))
        self.assertFalse(sdr_scheduler.acquire_job('t1', 600))     # held by someone else
        sdr_scheduler.release_job('t1')
        self.assertTrue(sdr_scheduler.acquire_job('t1', 600))

    def test_min_interval_blocks_a_rerun_after_restart(self):
        self.assertTrue(sdr_scheduler.acquire_job('daily', 600, min_interval_seconds=82800))
        sdr_scheduler.release_job('daily')
        self.assertFalse(sdr_scheduler.acquire_job('daily', 600, min_interval_seconds=82800))

    def test_singleton_decorator_skips_when_held(self):
        calls = []

        @sdr_scheduler.singleton_job('deco', ttl_seconds=600)
        def job():
            calls.append(1)

        sdr_scheduler.acquire_job('deco', 600)   # another process holds it
        job()
        self.assertEqual(calls, [])
        sdr_scheduler.release_job('deco')
        job()
        self.assertEqual(calls, [1])


class LifecycleTests(SDRBase):
    def test_late_enrolled_lead_is_not_cut_off_by_campaign_end_date(self):
        SDRCampaign.objects.filter(pk=self.campaign.pk).update(
            end_date=timezone.now().date() - timedelta(days=1))
        old = self.enroll(self.make_lead('old@a.com'))
        late = self.enroll(self.make_lead('late@a.com'))
        SDRCampaignEnrollment.objects.filter(pk=old.pk).update(
            enrolled_at=timezone.now() - timedelta(days=30))
        from ai_sdr_agent.tasks import auto_pause_expired_campaigns_impl
        auto_pause_expired_campaigns_impl()
        old.refresh_from_db(); late.refresh_from_db(); self.campaign.refresh_from_db()
        self.assertEqual(old.status, 'completed')
        self.assertEqual(late.status, 'active')
        self.assertEqual(self.campaign.status, 'active')

    def test_qualify_queue_retries_stuck_and_keeps_lead_status(self):
        from ai_sdr_agent.tasks import qualify_queue_impl
        SDRIcpProfile.objects.create(company_user=self.cu, is_active=True)
        stuck = self.make_lead('stuck@a.com', status='replied')
        SDRLead.objects.filter(pk=stuck.pk).update(
            qualification_status='processing',
            updated_at=timezone.now() - timedelta(hours=1))
        agent = mock.MagicMock()
        agent.qualify_lead.return_value = {'score': 80, 'temperature': 'hot'}
        with mock.patch('api.views.ai_sdr_agent._get_qualification_agent', return_value=agent):
            qualify_queue_impl()
        stuck.refresh_from_db()
        self.assertEqual(stuck.qualification_status, 'done')
        self.assertEqual(stuck.status, 'replied')          # not regressed to "qualified"

    def test_qualify_queue_without_icp_fails_once_with_reason(self):
        from ai_sdr_agent.tasks import qualify_queue_impl
        lead = self.make_lead('noicp@a.com', qualification_status='pending')
        with mock.patch('api.views.ai_sdr_agent._get_qualification_agent', return_value=mock.MagicMock()):
            qualify_queue_impl()
        lead.refresh_from_db()
        self.assertEqual(lead.qualification_status, 'failed')
        self.assertIn('ICP', lead.qualification_error)


class ApiTests(SDRBase):
    def setUp(self):
        super().setUp()
        self.rf = APIRequestFactory()

    def call(self, view, method, path='/x', data=None, **kw):
        req = getattr(self.rf, method)(path, data or {}, format='json')
        force_authenticate(req, user=self.cu)
        return view(req, **kw)

    def test_manual_meeting_is_created_listed_and_validated(self):
        lead = self.make_lead()
        bad = self.call(views.sdr_meetings_list, 'post', data={'lead_id': lead.id, 'status': 'bogus'})
        self.assertEqual(bad.status_code, 400)
        bad = self.call(views.sdr_meetings_list, 'post', data={'lead_id': lead.id, 'scheduled_at': 'not-a-date'})
        self.assertEqual(bad.status_code, 400)
        ok = self.call(views.sdr_meetings_list, 'post', data={
            'lead_id': lead.id, 'scheduled_at': '2030-01-01T10:00:00Z', 'duration_minutes': 45})
        self.assertEqual(ok.status_code, 201)
        listed = self.call(views.sdr_meetings_list, 'get')
        self.assertEqual(listed.data['total'], 1)          # no longer filtered out as an orphan

    def test_meeting_update_rejects_bad_values_instead_of_500(self):
        lead = self.make_lead()
        m = SDRMeeting.objects.create(company_user=self.cu, lead=lead, is_manual=True)
        resp = self.call(views.sdr_meeting_detail, 'put', data={'scheduled_at': 'garbage'}, meeting_id=m.id)
        self.assertEqual(resp.status_code, 400)
        resp = self.call(views.sdr_meeting_detail, 'put', data={'duration_minutes': 'abc'}, meeting_id=m.id)
        self.assertEqual(resp.status_code, 400)

    def test_enroll_does_not_override_pause_or_start_date(self):
        lead = self.make_lead()
        SDRCampaign.objects.filter(pk=self.campaign.pk).update(status='paused')
        self.call(views.sdr_enroll_leads, 'post', data={'lead_ids': [lead.id]}, campaign_id=self.campaign.id)
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.status, 'paused')

        other = SDRCampaign.objects.create(
            company_user=self.cu, name='Fut', status='draft', smtp_host='h', smtp_username='u',
            smtp_password='p', start_date=timezone.now().date() + timedelta(days=5))
        SDRCampaignStep.objects.create(campaign=other, step_order=1, body_template='b', subject_template='s')
        self.call(views.sdr_enroll_leads, 'post',
                  data={'lead_ids': [self.make_lead('z@z.com').id]}, campaign_id=other.id)
        other.refresh_from_db()
        self.assertEqual(other.status, 'scheduled')

    def test_enroll_does_not_activate_a_campaign_without_steps(self):
        empty = SDRCampaign.objects.create(
            company_user=self.cu, name='Empty', status='draft',
            smtp_host='h', smtp_username='u', smtp_password='p')
        self.call(views.sdr_enroll_leads, 'post',
                  data={'lead_ids': [self.make_lead('e@e.com').id]}, campaign_id=empty.id)
        empty.refresh_from_db()
        self.assertEqual(empty.status, 'draft')

    def test_process_requires_active_campaign_and_survives_a_failure(self):
        SDRCampaign.objects.filter(pk=self.campaign.pk).update(status='paused')
        resp = self.call(views.sdr_process_outreach, 'post', campaign_id=self.campaign.id)
        self.assertEqual(resp.status_code, 400)

        SDRCampaign.objects.filter(pk=self.campaign.pk).update(status='active')
        self.enroll(self.make_lead('a@a.com'))
        self.enroll(self.make_lead('b@b.com'))
        fake = mock.MagicMock()
        fake.process_enrollment.side_effect = [RuntimeError('boom'), {'status': 'sent'}]
        with mock.patch.object(views, '_get_outreach_agent', return_value=fake):
            resp = self.call(views.sdr_process_outreach, 'post', campaign_id=self.campaign.id)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual((resp.data['failed'], resp.data['sent']), (1, 1))

    def test_campaign_update_validates_status_and_mail_host(self):
        resp = self.call(views.sdr_campaign_detail, 'put', data={'status': 'nonsense'}, campaign_id=self.campaign.id)
        self.assertEqual(resp.status_code, 400)
        resp = self.call(views.sdr_campaign_detail, 'put', data={'smtp_host': '127.0.0.1'}, campaign_id=self.campaign.id)
        self.assertEqual(resp.status_code, 400)
        SDRCampaign.objects.filter(pk=self.campaign.pk).update(status='paused', smtp_password='')
        resp = self.call(views.sdr_campaign_detail, 'put', data={'status': 'active'}, campaign_id=self.campaign.id)
        self.assertEqual(resp.status_code, 400)      # no SMTP password -> can't activate

    def test_settings_keys_are_masked(self):
        SDRAgentSettings.objects.create(company_user=self.cu, apollo_api_key='abcd1234efgh5678')
        resp = self.call(views.sdr_agent_settings, 'get')
        self.assertNotIn('1234efgh', resp.data['apollo_api_key'])
        self.assertTrue(resp.data['apollo_api_key_set'])

    @override_settings(DEBUG=False)
    def test_google_oauth_helper_is_disabled_outside_debug(self):
        req = self.rf.get('/api/sdr/google-auth/callback/', {'code': 'x'})
        self.assertEqual(views.sdr_google_auth_callback(req).status_code, 404)
        self.assertEqual(views.sdr_google_auth_start(self.rf.get('/x')).status_code, 404)


class BookingTests(SDRBase):
    def setUp(self):
        super().setUp()
        self.client = Client()
        self.lead = self.make_lead()
        self.enr = self.enroll(self.lead)

    def meeting(self, **kw):
        return SDRMeeting.objects.create(
            company_user=self.cu, lead=self.lead, enrollment=self.enr, status='pending', **kw)

    def book(self, m, when):
        return self.client.post(
            f'/api/sdr/book/{m.booking_token}/confirm/',
            {'scheduled_at': when.isoformat()}, content_type='application/json')

    def test_booking_sets_lead_status_and_creates_meet_only_once(self):
        m = self.meeting()
        when = timezone.now() + timedelta(days=3)
        with mock.patch.object(views, '_create_google_meet_link',
                               return_value='https://meet.google.com/abc') as meet, \
                mock.patch('ai_sdr_agent.agents.meeting_scheduling_agent.MeetingSchedulingAgent'):
            self.assertEqual(self.book(m, when).status_code, 200)
            self.assertEqual(self.book(m, when).status_code, 400)       # double submit
        self.assertEqual(meet.call_count, 1)                            # no orphan Meet event
        m.refresh_from_db(); self.lead.refresh_from_db()
        self.assertEqual(m.calendar_link, 'https://meet.google.com/abc')
        self.assertEqual(self.lead.status, 'meeting_scheduled')

    def test_booking_too_far_ahead_is_rejected(self):
        m = self.meeting()
        resp = self.book(m, timezone.now() + timedelta(days=400))
        self.assertEqual(resp.status_code, 400)
        m.refresh_from_db()
        self.assertEqual(m.status, 'pending')

    def test_booking_overlapping_another_meeting_is_refused(self):
        when = timezone.now() + timedelta(days=3)
        other_lead = self.make_lead('o@o.com')
        SDRMeeting.objects.create(company_user=self.cu, lead=other_lead, status='scheduled',
                                  scheduled_at=when + timedelta(minutes=10), duration_minutes=30)
        m = self.meeting()
        with mock.patch.object(views, '_create_google_meet_link') as meet:
            resp = self.book(m, when)
        self.assertEqual(resp.status_code, 409)
        meet.assert_not_called()
        m.refresh_from_db()
        self.assertEqual(m.status, 'pending')


class SmtpPasswordEncryptionTests(SDRBase):
    def raw_password(self, pk):
        from django.db import connection
        with connection.cursor() as cur:
            cur.execute("SELECT smtp_password FROM sdr_campaign WHERE id = %s", [pk])
            return cur.fetchone()[0]

    def test_password_is_ciphertext_in_db_and_plaintext_in_python(self):
        c = SDRCampaign.objects.create(company_user=self.cu, name='Enc', smtp_password='s3cret-Pass!')
        raw = self.raw_password(c.pk)
        self.assertNotIn('s3cret', raw)
        self.assertTrue(raw.startswith('gAAAA'))
        self.assertEqual(SDRCampaign.objects.get(pk=c.pk).smtp_password, 's3cret-Pass!')

    def test_saving_again_does_not_double_encrypt(self):
        c = SDRCampaign.objects.get(pk=self.campaign.pk)
        c.name = 'renamed'
        c.save()
        c.save()
        self.assertEqual(SDRCampaign.objects.get(pk=c.pk).smtp_password, 'p')

    def test_update_encrypts_and_empty_stays_empty(self):
        SDRCampaign.objects.filter(pk=self.campaign.pk).update(smtp_password='newpw')
        self.assertNotEqual(self.raw_password(self.campaign.pk), 'newpw')
        self.assertEqual(SDRCampaign.objects.get(pk=self.campaign.pk).smtp_password, 'newpw')
        SDRCampaign.objects.filter(pk=self.campaign.pk).update(smtp_password='')
        self.assertEqual(self.raw_password(self.campaign.pk), '')

    def test_legacy_plaintext_row_still_works_and_migration_encrypts_it(self):
        from django.db import connection
        with connection.cursor() as cur:
            cur.execute("UPDATE sdr_campaign SET smtp_password = %s WHERE id = %s", ['legacy-plain', self.campaign.pk])
        self.assertEqual(SDRCampaign.objects.get(pk=self.campaign.pk).smtp_password, 'legacy-plain')

        import importlib
        from django.apps import apps
        mig = importlib.import_module('ai_sdr_agent.migrations.0025_encrypt_campaign_smtp_password')
        mig.encrypt_existing_passwords(apps, None)
        raw = self.raw_password(self.campaign.pk)
        self.assertTrue(raw.startswith('gAAAA'))
        self.assertEqual(SDRCampaign.objects.get(pk=self.campaign.pk).smtp_password, 'legacy-plain')

    def test_password_readable_after_key_rotation_with_fallback(self):
        from cryptography.fernet import Fernet
        old_key = Fernet.generate_key().decode()
        new_key = Fernet.generate_key().decode()
        with override_settings(FIELD_ENCRYPTION_KEY=old_key):
            c = SDRCampaign.objects.create(company_user=self.cu, name='Rot', smtp_password='rot-pw')
        with override_settings(FIELD_ENCRYPTION_KEY=new_key, FIELD_ENCRYPTION_KEY_FALLBACKS=old_key):
            self.assertEqual(SDRCampaign.objects.get(pk=c.pk).smtp_password, 'rot-pw')
            from django.core.management import call_command
            from io import StringIO
            call_command('reencrypt_secrets', stdout=StringIO())
            self.assertEqual(SDRCampaign.objects.get(pk=c.pk).smtp_password, 'rot-pw')
        with override_settings(FIELD_ENCRYPTION_KEY=new_key, FIELD_ENCRYPTION_KEY_FALLBACKS='',
                               SECRET_KEY='something-else-entirely'):
            # re-encrypted with the new key, so the old key is no longer needed
            self.assertEqual(SDRCampaign.objects.get(pk=c.pk).smtp_password, 'rot-pw')

    def test_sending_uses_the_decrypted_password(self):
        enr = self.enroll(self.make_lead())
        fresh = SDRCampaign.objects.get(pk=self.campaign.pk)
        enr.campaign = fresh
        with mock.patch.object(oa.OutreachAgent, '_send_via_smtp') as smtp:
            self.agent().process_enrollment(enr)
        self.assertEqual(smtp.call_args.kwargs['password'], 'p')

    def test_api_never_returns_the_password(self):
        rf = APIRequestFactory()
        req = rf.get('/x')
        force_authenticate(req, user=self.cu)
        resp = views.sdr_campaign_detail(req, campaign_id=self.campaign.id)
        self.assertNotIn('smtp_password', str(resp.data))
