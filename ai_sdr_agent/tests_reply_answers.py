"""The sales AI's answer to a lead waits for a person when the campaign says so.

When a lead wrote back "tell me more", the AI wrote an email and sent it within
minutes, in the salesperson's name, with nobody having read it, and it was asked
to list product benefits it had never been told about. A campaign now has a
switch: with it on, the answer is kept as a draft until its owner sends it,
changed or not, or discards it. A lead who says stop is still stopped at once.
"""
from datetime import timedelta
from unittest import mock

from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from ai_sdr_agent import reply_answers
from ai_sdr_agent.agents.email_assistant_agent import EmailAssistantAgent
from ai_sdr_agent.models import SDRCampaign, SDRCampaignEnrollment, SDRReplyDraft
from ai_sdr_agent.tests import SDRBase
from api.views import ai_sdr_agent as views
from core.do_not_email import block, is_blocked
from core.models import Company, CompanyUser
from project_manager_agent.models import PMNotification

WANTS_MORE = {'action': 'send_info', 'category': 'wants_more_info', 'label': 'Wants more info'}
SAYS_STOP = {'action': 'unsubscribe', 'category': 'unsubscribe', 'label': 'Unsubscribe'}


class ReplyAnswersTestCase(SDRBase):

    def setUp(self):
        super().setUp()
        self.lead = self.make_lead()
        self.enrolment = self.enroll(self.lead)

    def switch(self, on):
        SDRCampaign.objects.filter(pk=self.campaign.pk).update(review_ai_replies=on)
        self.campaign.refresh_from_db()

    def inbox(self, classification, text='Sounds interesting, tell me more'):
        """One run of the scheduled reply check with one reply from the lead."""
        from ai_sdr_agent.tasks import check_inbox_replies_impl
        enrolment = SDRCampaignEnrollment.objects.get(pk=self.enrolment.pk)
        reply = {'enrollment': enrolment, 'reply_text': text, 'sender_email': self.lead.email,
                 'subject': 'Re: Hello', 'message_id': f'<{timezone.now().timestamp()}@x>',
                 'received_at': timezone.now() + timedelta(minutes=1)}
        sender = mock.MagicMock()
        sender.check_inbox_for_replies.return_value = [reply]
        writer = mock.MagicMock()
        writer.classify_reply.return_value = classification
        writer.generate_more_info_email.return_value = {'subject': 'More about Acme', 'body': 'Here is more.'}
        with mock.patch('ai_sdr_agent.agents.outreach_agent.OutreachAgent', return_value=sender), \
                mock.patch('ai_sdr_agent.agents.email_assistant_agent.EmailAssistantAgent', return_value=writer):
            check_inbox_replies_impl()
        return sender

    def their_thread(self):
        """The answer goes out as a reply to the lead's email."""
        return {'in_reply_to': SDRCampaignEnrollment.objects.get(pk=self.enrolment.pk).last_reply_message_id}

    def call(self, view, method='post', data=None, actor=None, **kwargs):
        request = getattr(APIRequestFactory(), method)('/x', data or {}, format='json')
        force_authenticate(request, user=actor or self.cu)
        return view(request, **kwargs)


class HeldForAPersonTests(ReplyAnswersTestCase):

    def test_a_new_campaign_checks_answers_first(self):
        fresh = SDRCampaign.objects.create(company_user=self.cu, name='Fresh')
        self.assertTrue(fresh.review_ai_replies)

    def test_with_the_switch_on_nothing_is_sent_and_the_answer_waits(self):
        sender = self.inbox(WANTS_MORE)
        sender.send_email.assert_not_called()
        [draft] = SDRReplyDraft.objects.all()
        self.assertEqual((draft.status, draft.subject, draft.body, draft.enrollment_id),
                         ('pending', 'More about Acme', 'Here is more.', self.enrolment.id))
        self.assertIn('tell me more', draft.lead_reply)

    def test_the_owner_is_told_there_is_something_to_check(self):
        self.inbox(WANTS_MORE)
        [alert] = PMNotification.objects.filter(company_user=self.cu)
        self.assertIn('waiting for you', alert.title)

    def test_with_the_switch_off_it_is_sent_at_once_as_before(self):
        self.switch(False)
        sender = self.inbox(WANTS_MORE)
        sender.send_email.assert_called_once_with(self.campaign, self.lead.email, 'More about Acme', 'Here is more.',
                                                  **self.their_thread())
        self.assertFalse(SDRReplyDraft.objects.exists())

    def test_a_lead_who_says_stop_is_stopped_at_once_whatever_the_switch(self):
        self.inbox(SAYS_STOP, text='Please stop emailing me')
        self.assertTrue(is_blocked(self.company.id, self.lead.email))
        self.assertEqual(SDRCampaignEnrollment.objects.get(pk=self.enrolment.pk).status, 'unsubscribed')
        self.assertFalse(SDRReplyDraft.objects.exists())

    def test_the_check_replies_button_holds_the_answer_too(self):
        writer = mock.MagicMock()
        writer.generate_more_info_email.return_value = {'subject': 'S', 'body': 'B'}
        sender = mock.MagicMock()
        # The button hands its own agents to the shared reply rules (ai_sdr_agent/reply_actions.py).
        result = views._apply_reply_action(self.cu, self.campaign, self.enrolment, self.lead, WANTS_MORE,
                                           'tell me more', email_agent=writer, outreach_agent=sender)
        sender.send_email.assert_not_called()
        self.assertEqual((result['action'], result['answer_held'], result['info_email_sent']),
                         ('answer_waiting', True, False))
        self.assertEqual(SDRReplyDraft.objects.count(), 1)

    def test_the_campaign_says_how_many_are_waiting_and_carries_the_switch(self):
        self.inbox(WANTS_MORE)
        data = self.call(views.sdr_campaign_detail, 'get', campaign_id=self.campaign.id).data['data']
        self.assertEqual((data['review_ai_replies'], data['answers_waiting']), (True, 1))
        with mock.patch.object(views, '_validate_mail_settings', return_value=None):
            saved = self.call(views.sdr_campaign_detail, 'put', {'review_ai_replies': False},
                              campaign_id=self.campaign.id).data['data']
        self.assertFalse(saved['review_ai_replies'])
        self.assertFalse(SDRCampaign.objects.get(pk=self.campaign.pk).review_ai_replies)


class SendingOrDiscardingTests(ReplyAnswersTestCase):

    def setUp(self):
        super().setUp()
        self.inbox(WANTS_MORE)
        self.draft = SDRReplyDraft.objects.get()
        self.sender = mock.MagicMock()

    def decide(self, decision, data=None, actor=None, draft=None):
        with mock.patch.object(views, 'OutreachAgent', return_value=self.sender):
            return self.call(views.sdr_reply_draft_decide, 'post', data, actor=actor,
                             draft_id=(draft or self.draft).id, decision=decision)

    def waiting(self):
        return self.call(views.sdr_reply_drafts, 'get', campaign_id=self.campaign.id).data['data']

    def test_the_waiting_answer_is_listed_with_what_the_lead_wrote(self):
        [row] = self.waiting()
        self.assertEqual((row['id'], row['lead_email'], row['subject'], row['body']),
                         (self.draft.id, 'bob@acme.com', 'More about Acme', 'Here is more.'))
        self.assertIn('tell me more', row['lead_reply'])

    def test_sent_as_written(self):
        response = self.decide('send')
        self.assertEqual(response.status_code, 200, response.data)
        self.sender.send_email.assert_called_once_with(self.campaign, 'bob@acme.com', 'More about Acme',
                                                       'Here is more.', **self.their_thread())
        self.draft.refresh_from_db()
        self.assertEqual((self.draft.status, self.draft.decided_by_id), ('sent', self.cu.id))
        self.assertEqual(self.waiting(), [])

    def test_sending_a_written_answer_needs_the_mailbox_and_no_ai_key(self):
        """The text is already written. A company whose AI key has run out can still send it."""
        from ai_sdr_agent.agents.outreach_agent import OutreachAgent
        from core.api_key_service import KeyServiceError

        SDRCampaign.objects.filter(pk=self.campaign.pk).update(
            smtp_host='smtp.acme.test', smtp_username='sal@acme.test', smtp_password='not-a-real-one')
        with mock.patch('ai_sdr_agent.agents.sdr_key_resolver.resolve_sdr_groq_client',
                        side_effect=KeyServiceError('no key')) as asked_for_a_key, \
                mock.patch.object(OutreachAgent, '_send_via_smtp') as smtp:
            response = self.call(views.sdr_reply_draft_decide, 'post', draft_id=self.draft.id, decision='send')
        self.assertEqual(response.status_code, 200, response.data)
        asked_for_a_key.assert_not_called()
        self.assertEqual(smtp.call_args.kwargs['to_email'], 'bob@acme.com')
        self.assertEqual(SDRReplyDraft.objects.get().status, 'sent')

    def test_sent_as_the_person_changed_it(self):
        self.decide('send', {'subject': 'About your question', 'body': 'A better answer.'})
        self.sender.send_email.assert_called_once_with(self.campaign, 'bob@acme.com', 'About your question',
                                                       'A better answer.', **self.their_thread())
        self.draft.refresh_from_db()
        self.assertEqual((self.draft.subject, self.draft.body), ('About your question', 'A better answer.'))

    def test_discarded_sends_nothing(self):
        self.assertEqual(self.decide('discard').status_code, 200)
        self.sender.send_email.assert_not_called()
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.status, 'discarded')
        self.assertEqual(self.waiting(), [])

    def test_it_can_only_be_decided_once(self):
        self.decide('send')
        for decision in ('send', 'discard'):
            response = self.decide(decision)
            self.assertEqual(response.status_code, 400)
            self.assertIn('already', response.data['message'])
        self.assertEqual(self.sender.send_email.call_count, 1)

    def test_an_empty_answer_is_not_sent(self):
        response = self.decide('send', {'body': '   '})
        self.assertEqual(response.status_code, 400)
        self.sender.send_email.assert_not_called()
        self.assertEqual(SDRReplyDraft.objects.get().status, 'pending')

    def test_not_to_someone_who_has_since_unsubscribed(self):
        block(self.company.id, 'bob@acme.com')
        response = self.decide('send')
        self.assertEqual(response.status_code, 400)
        self.assertIn('do-not-email', response.data['message'])
        self.sender.send_email.assert_not_called()

    def test_if_the_mailbox_will_not_send_the_answer_is_still_waiting(self):
        self.sender.send_email.side_effect = ValueError('SMTP error: timed out')
        response = self.decide('send')
        self.assertEqual(response.status_code, 400)
        self.assertIn('would not send', response.data['message'])
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.status, 'pending')
        self.assertIn('timed out', self.draft.error)
        self.sender.send_email.side_effect = None
        self.assertEqual(self.decide('send').status_code, 200)

    def test_someone_elses_campaign_cannot_be_read_or_decided(self):
        rival = Company.objects.create(name='Rival', email='rival@test.local')
        rita = CompanyUser.objects.create(company=rival, email='rita@rival.test', full_name='Rita', role='admin',
                                          password_hash='x', is_active=True)
        self.assertEqual(self.call(views.sdr_reply_drafts, 'get', actor=rita, campaign_id=self.campaign.id).status_code,
                         404)
        for decision in ('send', 'discard'):
            self.assertEqual(self.decide(decision, actor=rita).status_code, 404)
        self.sender.send_email.assert_not_called()
        self.assertEqual(SDRReplyDraft.objects.get().status, 'pending')


class WhatTheAIIsToldTests(ReplyAnswersTestCase):
    """The answer is written from what the campaign says about the product, and nothing else."""

    def prompt_for(self, description):
        SDRCampaign.objects.filter(pk=self.campaign.pk).update(description=description)
        self.campaign.refresh_from_db()
        writer = EmailAssistantAgent.__new__(EmailAssistantAgent)
        writer.model, writer._key_ctx = 'test-model', None
        writer.groq_client = mock.MagicMock()
        writer.groq_client.chat.completions.create.return_value = mock.Mock(
            usage=mock.Mock(total_tokens=0),
            choices=[mock.Mock(message=mock.Mock(content='{"subject": "s", "body": "b"}'))])
        with mock.patch('ai_sdr_agent.agents.sdr_key_resolver.record_sdr_usage'):
            writer.generate_more_info_email(self.lead, self.campaign, 'tell me more')
        return writer.groq_client.chat.completions.create.call_args.kwargs['messages'][0]['content']

    def test_the_campaigns_own_description_is_what_it_may_use(self):
        prompt = self.prompt_for('Payroll software for clinics. Runs payroll in ten minutes.')
        self.assertIn('Payroll software for clinics. Runs payroll in ten minutes.', prompt)
        self.assertIn('ONLY facts you may use', prompt)
        self.assertIn('Never states a fact', prompt)

    def test_with_no_description_it_is_told_not_to_describe_the_product(self):
        prompt = self.prompt_for('')
        self.assertIn('nothing has been written down', prompt)
        self.assertIn('Does NOT describe the product', prompt)
        self.assertNotIn('key benefits', prompt)


class AnswerInTheirConversationTests(ReplyAnswersTestCase):
    """The answer is a reply: "Re:" the email the lead answered, with the headers that keep it in their thread.

    It went out under the AI's own subject ("Quick overview of our mobile banking solutions") with no reply
    headers, so it started a new conversation in the lead's inbox, away from their question.
    """

    def test_the_answer_is_titled_as_a_reply_to_the_email_they_answered(self):
        from ai_sdr_agent.models import SDROutreachLog
        SDROutreachLog.objects.create(enrollment=self.enrolment, action_type='email', status='sent',
                                      subject_sent="Accelerate Acme's mobile banking")
        self.inbox(WANTS_MORE)
        self.assertEqual(SDRReplyDraft.objects.get().subject, "Re: Accelerate Acme's mobile banking")

    def test_the_email_carries_the_reply_headers(self):
        from ai_sdr_agent.agents.outreach_agent import OutreachAgent
        with mock.patch('ai_sdr_agent.agents.outreach_agent.validate_mail_server', return_value=None), \
                mock.patch('ai_sdr_agent.agents.outreach_agent.smtplib.SMTP') as smtp:
            OutreachAgent._send_via_smtp(
                OutreachAgent.__new__(OutreachAgent), host='smtp.acme.test', port=2525, username='sal@acme.test',
                password='x', use_tls=False, from_addr='sal@acme.test', display_name='Sal', to_email='bob@acme.com',
                subject='Re: Hello', body='Here is more.', in_reply_to='<bob-1@acme.com>')
        sent = smtp.return_value.__enter__.return_value.sendmail.call_args.args[2]
        self.assertIn('In-Reply-To: <bob-1@acme.com>', sent)
        self.assertIn('References: <bob-1@acme.com>', sent)
