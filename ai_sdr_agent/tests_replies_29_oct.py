"""The SDR's reply rules, fixed before its demo (29 Oct 2026), from the inside-gaps report.

CO-144: a lead with a meeting could not opt out by reply, and meeting emails ignored the do-not-email list.
CO-145: word lists decided most replies and misread common ones; 'not interested' opted people out for good.
CO-241: an out-of-office message put a lead who had already answered back into the sequence.
CO-243: a lead in two campaigns who replied once was answered twice.
"""
from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from ai_sdr_agent.agents.email_assistant_agent import EmailAssistantAgent
from ai_sdr_agent.models import SDRCampaign, SDRCampaignEnrollment, SDRMeeting
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
