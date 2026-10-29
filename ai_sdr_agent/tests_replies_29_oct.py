"""The SDR's reply rules, fixed before its demo (29 Oct 2026), from the inside-gaps report.

CO-144: a lead with a meeting could not opt out by reply, and meeting emails ignored the do-not-email list.
CO-145: word lists decided most replies and misread common ones; 'not interested' opted people out for good.
CO-241: an out-of-office message put a lead who had already answered back into the sequence.
CO-243: a lead in two campaigns who replied once was answered twice.
"""
from datetime import timedelta
from unittest import mock

from django.test import TestCase, override_settings
from django.utils import timezone

from ai_sdr_agent.agents.email_assistant_agent import EmailAssistantAgent
from ai_sdr_agent.models import SDRCampaign, SDRCampaignEnrollment, SDRMeeting, SDROutreachLog
from ai_sdr_agent.reply_actions import handle_inbox_reply
from ai_sdr_agent.tests import SDRBase
from core.do_not_email import UNSUBSCRIBED, block, is_blocked

UNSUBSCRIBE = {'action': 'unsubscribe', 'category': 'unsubscribe', 'label': 'Unsubscribe'}
POSITIVE = {'action': 'book_meeting', 'category': 'positive_interest', 'label': 'Interested'}
AWAY = {'action': 'pause', 'category': 'out_of_office', 'label': 'Out of Office'}


class ReadingTests(TestCase):

    def cat(self, text):
        return EmailAssistantAgent().classify_reply(text)['category']        # no company: the word lists only

    def test_common_replies_the_word_lists_misread(self):
        self.assertNotEqual(self.cat('Absolutely not.'), 'positive_interest')
        self.assertEqual(self.cat('Not right now, maybe next quarter.'), 'neutral')
        self.assertNotEqual(self.cat('Sounds good, but not this year.'), 'positive_interest')
        self.assertEqual(self.cat('No thanks, we already have a tool.'), 'not_interested')
        self.assertEqual(self.cat('Please stop emailing me.'), 'unsubscribe')

    def test_our_footer_quoted_without_a_wrote_line_is_not_their_words(self):
        reply = 'Thanks, will read it.\n--\nUnsubscribe: https://api.example.test/api/sdr/unsubscribe/abc/'
        self.assertEqual(self.cat(reply), 'neutral')

    def test_the_ai_reads_first_and_the_lists_only_when_it_cannot(self):
        agent = EmailAssistantAgent()
        agent.groq_client = mock.MagicMock()
        answer = mock.MagicMock()
        answer.choices = [mock.MagicMock(message=mock.MagicMock(
            content='{"category": "neutral", "reason": "asks to talk next quarter"}'))]
        agent.groq_client.chat.completions.create.return_value = answer
        self.assertEqual(agent.classify_reply('Not interested right now, ask me next quarter')['category'], 'neutral')
        agent.groq_client.chat.completions.create.side_effect = RuntimeError('down')
        self.assertEqual(agent.classify_reply('Please unsubscribe me')['category'], 'unsubscribe')

    def test_a_return_date_without_a_year_that_has_passed_is_next_years(self):
        when = EmailAssistantAgent._extract_return_date('I am away, back on January 3')
        self.assertGreater(when, timezone.now())
        self.assertEqual((when.month, when.day), (1, 4))


class ReplyRuleTests(SDRBase):

    def reply(self, enrollment, text='x', mid='<m1@x>'):
        return {'enrollment': enrollment, 'reply_text': text, 'sender_email': enrollment.lead.email,
                'subject': 'Re: Hello', 'message_id': mid, 'received_at': timezone.now() + timedelta(minutes=1)}

    def handle(self, reply, classification):
        reader = mock.MagicMock()
        reader.classify_reply.return_value = classification
        with mock.patch('ai_sdr_agent.agents.meeting_scheduling_agent.MeetingSchedulingAgent') as scheduler:
            scheduler.return_value.generate_prep_notes.return_value = 'Notes'
            scheduler.return_value.send_scheduling_email_once.return_value = True
            return handle_inbox_reply(self.campaign, reply, email_agent=reader, outreach_agent=mock.MagicMock())

    def test_a_lead_with_a_meeting_can_still_opt_out_by_reply(self):
        lead = self.make_lead()
        enrollment = self.enroll(lead)
        SDRCampaignEnrollment.objects.filter(pk=enrollment.pk).update(status='replied')
        enrollment.refresh_from_db()
        meeting = SDRMeeting.objects.create(company_user=self.cu, lead=lead, enrollment=enrollment,
                                            status='scheduled', scheduled_at=timezone.now() + timedelta(days=2))
        result = self.handle(self.reply(enrollment, 'please unsubscribe me'), UNSUBSCRIBE)
        self.assertEqual(result['action'], 'unsubscribed')
        meeting.refresh_from_db()
        self.assertEqual(meeting.status, 'cancelled')
        self.assertTrue(is_blocked(self.company.id, lead.email))

    def test_anything_else_from_a_lead_with_a_meeting_is_left_alone(self):
        lead = self.make_lead()
        enrollment = self.enroll(lead)
        SDRCampaignEnrollment.objects.filter(pk=enrollment.pk).update(status='replied')
        enrollment.refresh_from_db()
        SDRMeeting.objects.create(company_user=self.cu, lead=lead, enrollment=enrollment, status='scheduled')
        self.assertIsNone(self.handle(self.reply(enrollment, 'See you Tuesday'), POSITIVE))
        self.assertEqual(SDRMeeting.objects.count(), 1)

    def test_an_away_message_leaves_a_lead_who_answered_as_they_were(self):
        enrollment = self.enroll(self.make_lead())
        SDRCampaignEnrollment.objects.filter(pk=enrollment.pk).update(status='replied', reply_content='Yes, call me')
        enrollment.refresh_from_db()
        self.handle(self.reply(enrollment, 'Out of office until Monday'), AWAY)
        enrollment.refresh_from_db()
        self.assertEqual((enrollment.status, enrollment.reply_content), ('replied', 'Yes, call me'))

    def test_an_away_message_keeps_a_later_next_step(self):
        enrollment = self.enroll(self.make_lead())
        later = timezone.now() + timedelta(days=20)
        SDRCampaignEnrollment.objects.filter(pk=enrollment.pk).update(next_action_at=later)
        enrollment.refresh_from_db()
        self.handle(self.reply(enrollment), {**AWAY, 'resume_date': timezone.now() + timedelta(days=3)})
        enrollment.refresh_from_db()
        self.assertEqual((enrollment.status, enrollment.next_action_at), ('paused', later))

    def test_one_reply_from_a_lead_in_two_campaigns_is_answered_once(self):
        first = self.enroll(self.make_lead('kiran@clinic.example'))
        other = SDRCampaign.objects.create(company_user=self.cu, name='C2', status='active')
        second = self.enroll(self.make_lead('kiran@clinic.example'), campaign=other)
        self.assertEqual(self.handle(self.reply(first, 'Yes, book a call'), POSITIVE)['action'], 'meeting_created')
        self.assertIsNone(self.handle(self.reply(second, 'Yes, book a call'), POSITIVE))
        second.refresh_from_db()
        self.assertEqual(second.status, 'replied')                     # its own emails stop
        self.assertEqual(SDRMeeting.objects.count(), 1)


class MeetingEmailTests(SDRBase):

    def send(self, to_email):
        from ai_sdr_agent.agents.meeting_scheduling_agent import MeetingSchedulingAgent
        server = mock.MagicMock()
        with mock.patch('smtplib.SMTP') as smtp, \
                mock.patch('ai_sdr_agent.agents.outreach_agent.validate_mail_server', return_value=None):
            smtp.return_value.__enter__.return_value = server
            MeetingSchedulingAgent()._send_email(
                self.campaign, to_email, 'Pick a time', "Hi\n\n---\nReply 'unsubscribe' to opt out.",
                '<p>Hi</p><p>simply reply with <strong>unsubscribe</strong>.</p>')
        return server

    def test_a_meeting_email_is_not_sent_to_an_address_on_the_do_not_email_list(self):
        from ai_sdr_agent.agents.outreach_agent import OnDoNotEmailList
        block(self.company.id, 'gone@clinic.example', UNSUBSCRIBED, source='test')
        with self.assertRaises(OnDoNotEmailList):
            self.send('gone@clinic.example')

    def test_a_meeting_email_carries_the_unsubscribe_link(self):
        self.enroll(self.make_lead('kiran@clinic.example'))
        server = self.send('kiran@clinic.example')
        message = server.sendmail.call_args[0][2]
        self.assertIn('/api/sdr/unsubscribe/', message)
        self.assertIn('List-Unsubscribe:', message)


class ApifyKeyTests(SDRBase):
    """CO-142: the Apify key went in the web address, so any failed request wrote it into the log, the research record
    and the red message on the customer's screen."""

    def test_the_key_goes_in_a_header_not_the_address(self):
        from ai_sdr_agent.agents.lead_research_agent import LeadResearchAgent
        runs = mock.MagicMock(status_code=200)
        runs.json.return_value = {'data': {'items': []}}
        with mock.patch('requests.get', return_value=runs) as get, self.assertRaises(ValueError):
            LeadResearchAgent(apify_token='secret-tok', apify_actor='a/b').fetch_apify_runs()
        self.assertNotIn('secret-tok', str(get.call_args.kwargs.get('params')) + get.call_args.args[0])
        self.assertEqual(get.call_args.kwargs['headers'], {'Authorization': 'Bearer secret-tok'})

    def test_fetching_runs_needs_the_persons_own_key(self):
        from rest_framework.test import APIRequestFactory, force_authenticate
        from api.views import ai_sdr_agent as views
        request = APIRequestFactory().post('/x', {}, format='json')
        force_authenticate(request, user=self.cu)
        with override_settings(APIFY_API_TOKEN='platform-tok'), mock.patch('requests.get') as get:
            response = views.fetch_apify_leads(request)
        self.assertEqual((response.status_code, response.data['code']), (400, 'no_lead_source'))
        get.assert_not_called()


class ClearingTests(SDRBase):
    """CO-147: Clear Leads always ended in an error after removing the leads, with the old figures left.
    CO-148: deleting a campaign or clearing its leads left its booked calls alive but hidden."""

    def call(self, view, method='post', data=None, **kwargs):
        from rest_framework.test import APIRequestFactory, force_authenticate
        request = getattr(APIRequestFactory(), method)('/x', data or {}, format='json')
        force_authenticate(request, user=self.cu)
        return view(request, **kwargs)

    def booked(self, status='scheduled'):
        lead = self.make_lead(f'{status}@clinic.example')
        enrollment = self.enroll(lead)
        SDROutreachLog.objects.create(enrollment=enrollment, action_type='email', status='sent', sent_at=timezone.now())
        return SDRMeeting.objects.create(company_user=self.cu, lead=lead, enrollment=enrollment, status=status,
                                         scheduled_at=timezone.now() + timedelta(days=1))

    def test_clear_leads_answers_success_with_true_figures_and_cancels_open_calls(self):
        from api.views import ai_sdr_agent as views
        open_call, done_call = self.booked('scheduled'), self.booked('completed')
        response = self.call(views.sdr_clear_campaign_leads, campaign_id=self.campaign.id)
        self.assertEqual(response.status_code, 200)
        self.campaign.refresh_from_db()
        self.assertEqual((self.campaign.total_leads, self.campaign.emails_sent, self.campaign.meetings_booked),
                         (0, 0, 0))
        open_call.refresh_from_db(); done_call.refresh_from_db()
        self.assertEqual((open_call.status, done_call.status), ('cancelled', 'completed'))

    def test_a_deleted_campaigns_calls_are_cancelled_and_still_listed(self):
        from api.views import ai_sdr_agent as views
        call = self.booked('scheduled')
        self.call(views.sdr_campaign_detail, 'delete', campaign_id=self.campaign.id)
        call.refresh_from_db()
        self.assertEqual(call.status, 'cancelled')
        [row] = self.call(views.sdr_meetings_list, 'get').data['results']
        self.assertTrue(row['campaign_removed'])


class EnrolTests(SDRBase):
    """CO-146: only the 25 highest-scoring leads could ever be put into a campaign.
    CO-149: adding leads to a draft started it, the first email going out within five minutes."""

    def call(self, view, method='post', data=None, **kwargs):
        from rest_framework.test import APIRequestFactory, force_authenticate
        request = getattr(APIRequestFactory(), method)('/x', data or {}, format='json')
        force_authenticate(request, user=self.cu)
        return view(request, **kwargs)

    def test_adding_leads_to_a_draft_leaves_it_a_draft_until_start(self):
        from api.views import ai_sdr_agent as views
        SDRCampaign.objects.filter(pk=self.campaign.pk).update(status='draft')
        response = self.call(views.sdr_enroll_leads, data={'lead_ids': [self.make_lead().id]},
                             campaign_id=self.campaign.id)
        self.assertEqual(response.data['campaign_status'], 'draft')
        with mock.patch.object(views, '_validate_mail_settings', return_value=None):
            self.call(views.sdr_campaign_detail, 'put', {'status': 'active'}, campaign_id=self.campaign.id)
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.status, 'active')
        self.assertIsNotNone(self.campaign.activated_at)

    def test_the_dialog_can_reach_every_lead_not_yet_in_the_campaign(self):
        from rest_framework.test import APIRequestFactory, force_authenticate
        from api.views import ai_sdr_agent as views
        inside = self.make_lead('in@clinic.example')
        self.enroll(inside)
        for i in range(30):
            self.make_lead(f'lead{i}@clinic.example')
        request = APIRequestFactory().get('/x', {'not_in_campaign': self.campaign.id, 'page': 2, 'page_size': 25})
        force_authenticate(request, user=self.cu)
        data = views.leads_list(request).data
        self.assertEqual((data['pagination']['total_count'], len(data['data'])), (30, 5))
        self.assertNotIn('in@clinic.example', [l['email'] for l in data['data']])


class BookedCallTests(SDRBase):
    """CO-150: only the booking page gave a call its video link and calendar event.
    CO-151: a salesperson with no employee login had no clash check at all.
    CO-152: the screen said the email went when it had failed or was never tried; a passed time could be accepted."""

    def setUp(self):
        super().setUp()
        self.lead = self.make_lead('kiran@clinic.example')
        self.enrollment = self.enroll(self.lead)

    def meeting(self, enrollment='own', **kw):
        return SDRMeeting.objects.create(company_user=self.cu, lead=self.lead,
                                         enrollment=self.enrollment if enrollment == 'own' else enrollment, **kw)

    def confirm(self, meeting, when, **extra):
        from rest_framework.test import APIRequestFactory, force_authenticate
        from api.views import ai_sdr_agent as views
        request = APIRequestFactory().post('/x', {'scheduled_at': when.isoformat(), **extra}, format='json')
        force_authenticate(request, user=self.cu)
        with mock.patch.object(views, '_create_google_meet_link', return_value=None), \
                mock.patch('ai_sdr_agent.agents.meeting_scheduling_agent.MeetingSchedulingAgent') as agent:
            response = views.sdr_confirm_meeting(request, meeting_id=meeting.id)
        return response, agent

    def test_a_call_the_salesperson_confirms_gets_its_own_room(self):
        meeting = self.meeting(status='pending', calendar_link='https://calendly.com/acme/demo')
        response, _ = self.confirm(meeting, timezone.now() + timedelta(days=2))
        meeting.refresh_from_db()
        self.assertTrue(meeting.calendar_link.startswith('https://meet.jit.si/SDR-'))
        self.assertTrue(response.data['email_sent'])

    def test_the_lead_accepting_a_time_gets_the_room_too(self):
        from django.test import Client
        meeting = self.meeting(status='awaiting_approval', scheduled_at=timezone.now() + timedelta(days=2))
        with mock.patch('api.views.ai_sdr_agent._create_google_meet_link', return_value=None), \
                mock.patch('ai_sdr_agent.agents.meeting_scheduling_agent.MeetingSchedulingAgent'):
            Client().post(f'/api/sdr/meeting-approval/{meeting.approval_token}/yes/')
        meeting.refresh_from_db()
        self.assertEqual(meeting.status, 'scheduled')
        self.assertTrue(meeting.calendar_link.startswith('https://meet.jit.si/'))

    def test_a_time_that_has_passed_cannot_be_accepted(self):
        from django.test import Client
        meeting = self.meeting(status='awaiting_approval', scheduled_at=timezone.now() - timedelta(hours=1))
        page = Client().post(f'/api/sdr/meeting-approval/{meeting.approval_token}/yes/')
        meeting.refresh_from_db()
        self.assertEqual(meeting.status, 'awaiting_approval')
        self.assertIn('already passed', page.content.decode())

    def test_asking_the_lead_needs_a_mailbox_and_a_failed_email_is_said(self):
        manual = SDRMeeting.objects.create(company_user=self.cu, lead=self.lead, is_manual=True, status='pending')
        response, _ = self.confirm(manual, timezone.now() + timedelta(days=2), send_approval='true')
        self.assertEqual((response.status_code, response.data['code']), (400, 'no_mailbox'))
        meeting = self.meeting(status='pending')
        from rest_framework.test import APIRequestFactory, force_authenticate
        from api.views import ai_sdr_agent as views
        request = APIRequestFactory().post('/x', {'scheduled_at': (timezone.now() + timedelta(days=3)).isoformat()},
                                           format='json')
        force_authenticate(request, user=self.cu)
        with mock.patch.object(views, '_create_google_meet_link', return_value=None), \
                mock.patch('ai_sdr_agent.agents.meeting_scheduling_agent.MeetingSchedulingAgent') as agent:
            agent.return_value.send_confirmation_email.side_effect = ValueError('SMTP error: 535')
            response = views.sdr_confirm_meeting(request, meeting_id=meeting.id)
        self.assertFalse(response.data['email_sent'])
        self.assertIn('535', response.data['email_error'])

    def test_two_calls_of_a_salesperson_without_a_calendar_cannot_overlap(self):
        when = timezone.now() + timedelta(days=2)
        self.meeting(status='awaiting_approval', scheduled_at=when)          # offered to someone, awaiting them
        other = self.meeting(enrollment=self.enroll(self.make_lead('sara@clinic.example')), status='pending')
        response, _ = self.confirm(other, when + timedelta(minutes=10))
        self.assertEqual(response.status_code, 409)


class MailboxProblemTests(SDRBase):
    """CO-197: an inbox that could not be read was only logged; the screen said it was checked every five minutes.
    CO-198: a wrong password or an unreachable server parked every lead one by one, then the campaign showed
    'Completed'; nothing said why and nothing restarted them."""

    def call(self, view, method='post', data=None, **kwargs):
        from rest_framework.test import APIRequestFactory, force_authenticate
        request = getattr(APIRequestFactory(), method)('/x', data or {}, format='json')
        force_authenticate(request, user=self.cu)
        return view(request, **kwargs)

    def test_an_unreadable_inbox_is_kept_on_the_campaign_and_cleared_when_it_reads(self):
        from ai_sdr_agent.reply_actions import read_inbox
        agent = mock.MagicMock()
        agent.check_inbox_for_replies.side_effect = ValueError('IMAP login failed: [AUTHENTICATIONFAILED]')
        self.assertIsNone(read_inbox(self.campaign, [], agent))
        self.campaign.refresh_from_db()
        self.assertIn('AUTHENTICATIONFAILED', self.campaign.inbox_error)
        agent.check_inbox_for_replies.side_effect, agent.check_inbox_for_replies.return_value = None, []
        self.assertEqual(read_inbox(self.campaign, [], agent), [])
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.inbox_error, '')

    def test_mailbox_settings_are_tried_before_they_are_saved(self):
        import smtplib
        from api.views import ai_sdr_agent as views
        refused = smtplib.SMTPAuthenticationError(535, b'5.7.8 Username and Password not accepted')
        with mock.patch('ai_sdr_agent.agents.outreach_agent.validate_mail_server', return_value=None), \
                mock.patch('smtplib.SMTP') as smtp, mock.patch('imaplib.IMAP4_SSL') as imap:
            smtp.return_value.login.side_effect = refused
            message = views._validate_mail_settings({'smtp_host': 'smtp.gmail.com', 'smtp_username': 'a@gmail.com',
                                                     'smtp_password': 'wrong'})
        self.assertIn('refused the login (535', message)
        self.assertIn("app password", message)
        imap.assert_not_called()

    def test_an_unreachable_server_pauses_the_campaign_not_each_lead(self):
        enrollment = self.enroll(self.make_lead())
        agent = self.agent()
        with mock.patch('ai_sdr_agent.agents.outreach_agent.validate_mail_server', return_value=None), \
                mock.patch('smtplib.SMTP', side_effect=OSError('Connection timed out')):
            agent.process_enrollment(enrollment)
        self.campaign.refresh_from_db(); enrollment.refresh_from_db()
        self.assertEqual(self.campaign.status, 'paused')
        self.assertIn('could not connect', self.campaign.paused_reason)
        self.assertEqual(enrollment.status, 'active')                  # keeps its place

    def test_leads_parked_after_failed_sends_are_open_shown_and_retried(self):
        from ai_sdr_agent.tasks import auto_pause_expired_campaigns_impl
        from api.views import ai_sdr_agent as views
        enrollment = self.enroll(self.make_lead())
        SDROutreachLog.objects.create(enrollment=enrollment, action_type='email', status='failed', step_order=1,
                                      error_message='SMTP error: 550 quota')
        SDRCampaignEnrollment.objects.filter(pk=enrollment.pk).update(status='paused', reply_sentiment='send_failed')
        auto_pause_expired_campaigns_impl()
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.status, 'active')               # not 'Completed'
        enrollment.refresh_from_db()
        self.assertIn('550 quota', views._serialize_enrollment(enrollment)['send_error'])
        self.assertEqual(self.call(views.sdr_retry_failed, campaign_id=self.campaign.id).data['retried'], 1)
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.status, 'active')
