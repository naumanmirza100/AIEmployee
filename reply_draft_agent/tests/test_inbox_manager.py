"""The Inbox Manager's missing parts (the AI Employee list, 30 Oct 2026) and the open Reply Draft gaps.

Triage as mail arrives, summaries of a conversation and of an attachment, questions about the inbox, alerts and the
daily summary; and CO-154, 156, 204, 205, 246, 247, 248, 249, 250, 251. No test reaches the AI or a mail server.
"""
import json
from datetime import timedelta
from unittest import mock

from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from api.views import reply_draft_agent as views
from core.api_key_service import KeyServiceError
from core.logins import user_for
from core.models import Company, CompanyModulePurchase, CompanyUser
from marketing_agent.models import EmailAccount
from project_manager_agent.models import PMNotification
from reply_draft_agent import alerts, insights, triage
from reply_draft_agent.agents.reply_draft_agent import ReplyDraftAgent
from reply_draft_agent.models import InboxAttachment, InboxEmail, ReplyDraft
from reply_draft_agent.tasks import delete_reply_draft_account_data, triage_inbox_task
from reply_draft_agent.text import SHORTENED, for_ai


def ai(*answers):
    """The AI, answering these in turn. autospec: a call with an argument the real one does not take fails (the
    first version passed json_mode, which the agent's AI call does not have, and every email fell back)."""
    return mock.patch.object(ReplyDraftAgent, '_call_llm', autospec=True, side_effect=list(answers))


class InboxTestCase(TestCase):
    """Margalla's inbox, connected by Nadia; Bilal is a colleague."""

    def setUp(self):
        self.company = Company.objects.create(name='Margalla', email='hello@margalla.test')
        CompanyModulePurchase.objects.create(company=self.company, module_name='reply_draft_agent', status='active',
                                             is_complimentary=True)
        self.nadia = self.login('nadia@margalla.test', 'Nadia Rehman', 'owner')
        self.bilal = self.login('bilal@margalla.test', 'Bilal Ahmed', 'admin')
        self.mailbox = EmailAccount.objects.create(
            owner=user_for(self.nadia), name='Margalla', email='hello@margalla.test', smtp_host='smtp.margalla.test',
            smtp_username='hello@margalla.test', smtp_password='synthetic', imap_host='imap.margalla.test',
            imap_username='hello@margalla.test', imap_password='synthetic', enable_imap_sync=True,
            is_reply_agent_account=True, is_marketing_account=False)

    def login(self, email, name, role, company=None):
        return CompanyUser.objects.create(company=company or self.company, email=email, full_name=name, role=role,
                                          password_hash='x', is_active=True)

    def mail(self, subject='A question', body='Hello, what does it cost?', sender='kiran@clinic.test', **more):
        fields = dict(owner=user_for(self.nadia), email_account=self.mailbox, message_id=f'<{subject}@x>',
                      from_email=sender, from_name='Kiran Shah', subject=subject, body=body,
                      received_at=timezone.now(), to_email='hello@margalla.test')
        fields.update(more)
        return InboxEmail.objects.create(**fields)

    def call(self, view, login, data=None, method='post', **kwargs):
        factory = APIRequestFactory()
        request = (factory.post('/x', data or {}, format='json') if method == 'post' else factory.get('/x', data or {}))
        force_authenticate(request, user=login)
        return view(request, **kwargs)


class TriageTests(InboxTestCase):
    def test_the_ais_reading_is_kept_and_a_bad_answer_falls_back(self):
        self.assertEqual(triage.read_triage(
            '{"category": "billing", "priority": "urgent", "summary": "The invoice is due tomorrow.", '
            '"needs_reply": true}'),
            {'category': 'billing', 'priority': 'urgent', 'ai_summary': 'The invoice is due tomorrow.',
             'needs_reply': True})
        with self.assertRaises(ValueError):
            triage.read_triage('{"category": "spam", "priority": "urgent", "summary": "x"}')
        news = self.mail(subject='Weekly news', sender='no-reply@shop.test', body='Our offers. Unsubscribe here.')
        with ai('not json'):
            self.assertEqual(triage.triage_email(news, ReplyDraftAgent()),
                             {'category': 'newsletter', 'priority': 'low', 'ai_summary': 'Weekly news',
                              'needs_reply': False})

    def test_the_job_reads_new_mail_once_and_tells_about_urgent_mail_once(self):
        urgent = self.mail(subject='Booking page down', body='Our patients cannot book since this morning!')
        old = self.mail(subject='Old', received_at=timezone.now() - timedelta(days=30))
        answer = ('{"category": "support", "priority": "urgent", "summary": "Their booking page is down.", '
                  '"needs_reply": true}')
        with ai(answer) as llm:
            self.assertEqual(triage_inbox_task(), {'read': 1})
            self.assertEqual(triage_inbox_task(), {'read': 0})          # read once
        self.assertEqual(llm.call_count, 1)
        urgent.refresh_from_db()
        old.refresh_from_db()
        self.assertEqual((urgent.category, urgent.priority, urgent.needs_reply), ('support', 'urgent', True))
        self.assertIsNone(old.triaged_at)                                 # a backlog costs no AI tokens
        [alert] = PMNotification.objects.filter(company_user=self.nadia)
        self.assertEqual(alert.title, 'Urgent email from Kiran Shah')
        self.assertIn('Their booking page is down.', alert.message)
        self.assertEqual(alert.data['link'], f'/reply-draft/emails?email={urgent.id}')
        alerts.urgent_email(urgent)                                       # never twice
        self.assertEqual(PMNotification.objects.filter(company_user=self.nadia).count(), 1)

    def test_without_the_ai_the_mail_waits_for_the_next_run(self):
        email = self.mail()
        with mock.patch.object(ReplyDraftAgent, '_call_llm', autospec=True, side_effect=KeyServiceError('no tokens left')):
            self.assertEqual(triage_inbox_task(), {'read': 0})
        email.refresh_from_db()
        self.assertIsNone(email.triaged_at)

    def test_an_ai_that_cannot_be_reached_leaves_the_mail_for_the_next_run(self):
        # A connection error gave the plain fallback, and the email kept it for good (the Reply Draft film, 30 Oct).
        for n in range(4):
            self.mail(subject=f'Question {n}')
        with mock.patch.object(ReplyDraftAgent, '_call_llm', autospec=True,
                               side_effect=ConnectionError('Connection error.')) as llm:
            self.assertEqual(triage_inbox_task(), {'read': 0})
        self.assertEqual(llm.call_count, 2)                                   # twice, then the run stops
        self.assertFalse(InboxEmail.objects.exclude(triaged_at=None).exists())

    def test_a_company_without_the_agent_is_not_read(self):
        CompanyModulePurchase.objects.filter(company=self.company).delete()
        self.mail()
        with ai() as llm:
            triage_inbox_task()
        llm.assert_not_called()


class DigestTests(InboxTestCase):
    def test_the_days_mail_in_a_few_lines(self):
        self.mail(subject='Price?', category='customer', priority='high', needs_reply=True,
                  ai_summary='Kiran asks the price for two branches.')
        self.mail(subject='Down', category='support', priority='urgent', needs_reply=True,
                  ai_summary='Their booking page is down.')
        self.mail(subject='News', category='newsletter', priority='low', needs_reply=False)
        text = alerts.digest_text(self.mailbox, timezone.now() - timedelta(days=1))
        self.assertIn('3 new emails since yesterday.', text)
        self.assertIn('Urgent:\n- Kiran Shah: Their booking page is down.', text)
        self.assertIn('Waiting for an answer (2):', text)
        self.assertIsNone(alerts.digest_text(self.mailbox, timezone.now() + timedelta(minutes=1)))

    def test_it_goes_by_email_by_default_and_not_to_the_bell(self):
        self.mail(category='customer', priority='high', needs_reply=True, ai_summary='A question.')
        with mock.patch('core.notification_settings.send_email') as send:
            self.assertTrue(alerts.send_digest(self.mailbox))
        self.assertEqual(send.call_args.args[:2], (self.nadia, 'inbox_digest'))
        self.assertFalse(PMNotification.objects.filter(company_user=self.nadia).exists())


class SummaryTests(InboxTestCase):
    def test_a_conversation_is_summarised_once_until_it_grows(self):
        first = self.mail(subject='Price?', thread_key='root:1', body='What does it cost for two branches?')
        self.mail(subject='Re: Price?', thread_key='root:1', direction='out', from_email='hello@margalla.test',
                  body='It depends on the size. Can we talk?\n\n> What does it cost for two branches?')
        answer = '{"points": ["Kiran asked the price.", "We asked for a call."], "next_step": "", "open_questions": []}'
        with ai(answer) as llm:
            summary = insights.summarize_conversation(first, ReplyDraftAgent())
            first.refresh_from_db()
            again = insights.summarize_conversation(first, ReplyDraftAgent())
        self.assertEqual(llm.call_count, 1)
        self.assertEqual(again, summary)
        self.assertEqual(summary['messages'], 2)
        prompt = llm.call_args.kwargs['prompt']
        self.assertIn('WE WROTE', prompt)
        self.assertEqual(prompt.count('What does it cost for two branches?'), 1)     # the quote is left out
        self.mail(subject='Re: Re: Price?', thread_key='root:1', body='Tuesday works.')
        with ai(answer) as llm:
            insights.summarize_conversation(first, ReplyDraftAgent())
        self.assertEqual(llm.call_count, 1)                                   # a new message: made again

    def test_a_text_attachment_is_summarised_and_a_picture_is_not(self):
        email = self.mail()
        doc = InboxAttachment(inbox_email=email, filename='invoice.txt', content_type='text/plain', size_bytes=40)
        doc.file.save('invoice.txt', ContentFile(b'Invoice 44. Amount due: Rs 25,000 by 5 November.'), save=True)
        answer = '{"what": "An invoice", "points": ["Invoice 44."], "figures": ["Rs 25,000", "5 November"]}'
        with ai(answer) as llm:
            summary = insights.summarize_attachment(doc, ReplyDraftAgent())
        self.assertEqual(summary['figures'], ['Rs 25,000', '5 November'])
        self.assertIn('Amount due: Rs 25,000', llm.call_args.kwargs['prompt'])
        self.assertTrue(insights.can_summarize('lease.PDF'))
        self.assertFalse(insights.can_summarize('photo.jpg', 'image/jpeg'))
        response = self.call(views.summarize_attachment, self.bilal, email_id=email.id, attachment_id=doc.id)
        self.assertEqual(response.data['data']['what'], 'An invoice')        # stored, and open to a colleague


class AskTests(InboxTestCase):
    def test_a_question_in_roman_urdu_is_answered_from_the_emails_it_names(self):
        price = self.mail(subject='Price for two branches', body='What is the monthly price for two branches?')
        self.mail(subject='Lunch', sender='friend@home.test', body='Lunch on Friday?')
        plan = '{"terms": ["price"], "people": ["Kiran"], "days": null, "categories": []}'
        answer = json.dumps({'answer': f'Kiran ne do branches ki monthly price poochi hai [#{price.id}].',
                             'sources': [price.id, 999]})
        with ai(plan, answer) as llm:
            response = self.call(views.ask_inbox, self.bilal, {'question': 'Kiran ne qeemat ke baare mein kya poocha?'})
        data = response.data['data']
        self.assertIn('do branches', data['answer'])
        self.assertEqual([s['id'] for s in data['sources']], [price.id])     # an id it was not given is dropped
        emails = llm.call_args_list[1].kwargs['prompt']
        self.assertLess(emails.index(f'[#{price.id}]'), emails.index('Lunch'))   # the match first
        self.assertIn('same language and script as the question', llm.call_args_list[1].kwargs['system_prompt'])

    def test_short_questions_and_an_empty_inbox(self):
        self.assertEqual(self.call(views.ask_inbox, self.nadia, {'question': 'hi'}).status_code, 400)
        with ai('{"terms": [], "people": [], "days": null, "categories": []}'):
            data = self.call(views.ask_inbox, self.nadia, {'question': 'What came today?'}).data['data']
        self.assertEqual(data['answer'], 'There is no mail in this inbox yet.')


class ColleagueTests(InboxTestCase):
    """CO-204: a colleague saw the company's inbox and drafts but could do nothing with them."""

    def test_a_colleague_drafts_approves_and_sends_from_the_companys_mailbox(self):
        email = self.mail(reply_to='kiran.shah@gmail.test', from_email='forms@website.test')
        draft_json = json.dumps({'interest_level': 'requested_info', 'analysis': 'Asks the price.',
                                 'subject': 'Re: A question', 'body': 'Hello Kiran,', 'reasoning': ''})
        with ai(draft_json):
            made = self.call(views.generate_draft, self.bilal, {'inbox_email_id': email.id})
        self.assertEqual(made.status_code, 200, made.data)
        draft = ReplyDraft.objects.get(pk=made.data['data']['draft_id'])
        self.assertEqual(draft.email_account, self.mailbox)
        self.assertEqual(self.call(views.approve_draft, self.bilal, draft_id=draft.id).status_code, 200)
        with mock.patch('reply_draft_agent.agents.reply_draft_agent.email_service.send_raw_email',
                        return_value={'success': True, 'message_id': 'sent-1@margalla.test'}) as send:
            sent = self.call(views.send_draft, self.bilal, draft_id=draft.id)
        self.assertEqual(sent.status_code, 200, sent.data)
        draft.refresh_from_db()
        self.assertEqual((draft.status, draft.approved_by, draft.sent_by), ('sent', user_for(self.bilal),
                                                                              user_for(self.bilal)))
        self.assertEqual(send.call_args.kwargs['to_email'], 'kiran.shah@gmail.test')   # Reply-To (CO-205)
        self.assertEqual(views._serialize_draft(draft)['approved_by'], 'Bilal Ahmed')
        # CO-246: the reply is in the Sent tab at once.
        self.assertTrue(InboxEmail.objects.filter(email_account=self.mailbox, direction='out',
                                                  message_id='sent-1@margalla.test').exists())

    def test_another_companys_login_still_cannot(self):
        other = Company.objects.create(name='Other', email='o@o.test')
        CompanyModulePurchase.objects.create(company=other, module_name='reply_draft_agent', status='active',
                                             is_complimentary=True)
        stranger = self.login('x@o.test', 'X', 'owner', company=other)
        draft = ReplyDraft.objects.create(owner=user_for(self.nadia), inbox_email=self.mail(),
                                          email_account=self.mailbox, draft_subject='Re', draft_body='Hi')
        self.assertEqual(self.call(views.approve_draft, stranger, draft_id=draft.id).status_code, 400)
        self.assertEqual(self.call(views.reject_draft, stranger, draft_id=draft.id).status_code, 404)


class SendTwiceTests(InboxTestCase):
    """CO-156: the same draft could be sent twice."""

    def draft(self, status='approved', **more):
        return ReplyDraft.objects.create(owner=user_for(self.nadia), inbox_email=self.mail(), status=status,
                                         email_account=self.mailbox, draft_subject='Re', draft_body='Hi', **more)

    def test_a_draft_being_sent_is_not_sent_again_until_the_claim_is_old(self):
        draft = self.draft(status='sending')
        agent = ReplyDraftAgent(user=user_for(self.nadia))
        with mock.patch('reply_draft_agent.agents.reply_draft_agent.email_service.send_raw_email',
                        return_value={'success': True, 'message_id': 'a@b'}) as send:
            self.assertEqual(agent.send_approved(draft.id)['error'], 'This draft is already being sent.')
            send.assert_not_called()
            ReplyDraft.objects.filter(pk=draft.pk).update(updated_at=timezone.now() - timedelta(minutes=11))
            self.assertTrue(agent.send_approved(draft.id)['success'])
        self.assertEqual(send.call_count, 1)

    def test_a_send_that_raises_ends_failed_not_sending(self):
        draft = self.draft()
        with mock.patch('reply_draft_agent.agents.reply_draft_agent.email_service.send_raw_email',
                        side_effect=OSError('connection reset')):
            result = ReplyDraftAgent(user=user_for(self.nadia)).send_approved(draft.id)
        draft.refresh_from_db()
        self.assertEqual((result['success'], draft.status), (False, 'failed'))

    def test_the_agent_keeps_no_second_sent_copy_of_its_own(self):
        self.assertFalse(hasattr(ReplyDraftAgent, '_append_to_imap_sent'))        # CO-247


class MailboxTests(InboxTestCase):
    def test_reply_to_is_kept_only_when_it_is_another_address(self):
        import email as email_lib
        from marketing_agent.management.commands.sync_inbox import Command
        raw = ('From: Website <forms@site.test>\r\nReply-To: Kiran Shah <Kiran.Shah@Gmail.test>\r\n'
               'Subject: Contact form\r\nMessage-ID: <f1@site.test>\r\n\r\nPlease call me.')
        row = Command()._build_inbox_email(email_lib.message_from_string(raw), self.mailbox, 'forms@site.test')
        self.assertEqual(row.reply_to, 'kiran.shah@gmail.test')
        same = raw.replace('Kiran Shah <Kiran.Shah@Gmail.test>', 'forms@site.test')
        self.assertEqual(Command()._build_inbox_email(email_lib.message_from_string(same), self.mailbox,
                                                      'forms@site.test').reply_to, '')

    def test_an_html_only_email_keeps_its_words_not_its_style_sheet(self):
        import email as email_lib
        from marketing_agent.management.commands.sync_inbox import Command
        raw = ('Content-Type: text/html\r\n\r\n<html><head><style>.a{color:red}</style></head>'
               '<body><p>Hello&nbsp;there</p><script>var x=1;</script><p>Second line</p></body></html>')
        plain, _html = Command().get_email_body(email_lib.message_from_string(raw))
        self.assertEqual(plain, 'Hello\xa0there\nSecond line')               # CO-249

    def test_the_ai_is_given_the_senders_words_cut_to_a_size(self):
        text = for_ai('My question.\n\nOn Mon, 1 Jan 2026 at 10:00, Nadia <n@x.test> wrote:\n> old text')
        self.assertEqual(text, 'My question.')
        self.assertTrue(for_ai('word ' * 5000).endswith(SHORTENED))

    def test_an_email_with_a_draft_is_not_pruned(self):
        from marketing_agent.management.commands.sync_inbox import Command
        old = timezone.now() - timedelta(days=120)
        drafted = self.mail(subject='Drafted', received_at=old)
        self.mail(subject='Plain', received_at=old)
        ReplyDraft.objects.create(owner=user_for(self.nadia), inbox_email=drafted, email_account=self.mailbox,
                                  draft_subject='Re', draft_body='Hi')
        EmailAccount.objects.filter(pk=self.mailbox.pk).update(imap_sync_days=90)
        self.mailbox.refresh_from_db()
        Command()._prune_to_caps(self.mailbox)
        self.assertEqual(list(InboxEmail.objects.values_list('subject', flat=True)), ['Drafted'])     # CO-154

    def test_an_edit_tests_the_login_on_the_stored_server(self):
        with mock.patch('api.views.marketing_agent.verify_imap_credentials', return_value=(False, 'no')) as verify:
            self.call(views.create_reply_account, self.bilal, {
                'email': 'hello@margalla.test', 'imap_host': 'evil.example', 'imap_port': 143, 'imap_use_ssl': False})
        self.assertEqual(verify.call_args.args[:3], ('imap.margalla.test', 993, True))      # CO-248, and a colleague

    def test_a_failed_search_leaves_the_attachments_to_try_again(self):
        email = self.mail()
        imap = mock.MagicMock()
        imap.select.return_value = ('NO', [b''])
        with mock.patch('imaplib.IMAP4_SSL', return_value=imap):
            response = self.call(views.fetch_inbox_attachments, self.nadia, email_id=email.id)
        email.refresh_from_db()
        self.assertEqual((response.status_code, email.attachments_fetched), (503, False))      # CO-250
        imap.select.return_value = ('OK', [b'1'])
        imap.search.return_value = ('OK', [b''])
        with mock.patch('imaplib.IMAP4_SSL', return_value=imap):
            response = self.call(views.fetch_inbox_attachments, self.nadia, email_id=email.id)
        email.refresh_from_db()
        self.assertEqual((response.data.get('missing'), email.attachments_fetched), (True, True))

    def test_a_mailbox_connected_again_is_not_deleted(self):
        self.mail()
        delete_reply_draft_account_data([user_for(self.nadia).id], self.mailbox.id, drop_account_row=True)
        self.assertTrue(EmailAccount.objects.filter(pk=self.mailbox.pk).exists())          # CO-251
        self.assertEqual(InboxEmail.objects.count(), 1)


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class DashboardTests(InboxTestCase):
    def test_the_dashboard_says_what_needs_someone(self):
        urgent = self.mail(subject='Down', category='support', priority='urgent', needs_reply=True,
                           triaged_at=timezone.now())
        answered = self.mail(subject='Price', category='customer', priority='high', needs_reply=True,
                             triaged_at=timezone.now())
        self.mail(subject='Fresh')
        ReplyDraft.objects.create(owner=user_for(self.nadia), inbox_email=answered, email_account=self.mailbox,
                                  draft_subject='Re', draft_body='Hi', status='sent')
        needs = self.call(views.dashboard, self.bilal, method='get').data['data']['needs_you']
        self.assertEqual((needs['urgent'], needs['waiting_for_answer'], needs['not_read_yet']), (1, 1, 1))
        self.assertEqual(needs['by_category'], {'support': 1, 'customer': 1})
        self.assertEqual([m['id'] for m in needs['top']], [urgent.id])
