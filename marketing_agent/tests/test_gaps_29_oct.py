"""Marketing gaps fixed before its demo (29 Oct 2026), from the inside-gaps report.

CO-124: a tracked link lost everything after the first '&' of its address.
CO-125: the click address sent anyone to any website, even with a made-up token.
CO-126: mailbox passwords were stored in clear text.
CO-132: the PDF of a document took the AI's text as trusted markup.
"""
from urllib.parse import parse_qs, urlsplit

from django.db import connection
from django.test import Client, override_settings

from core.logins import user_for
from marketing_agent.models import Campaign, EmailAccount, EmailSendHistory
from marketing_agent.services import click_links
from marketing_agent.tests.base import MarketingTestCase


@override_settings(SITE_URL='https://api.example.test')
class ClickLinkTests(MarketingTestCase):

    def setUp(self):
        super().setUp()
        self.spring = self.campaign(self.ann)
        self.bilal = self.lead(self.ann, 'bilal@customer.test', campaign=self.spring)
        self.sent = EmailSendHistory.objects.create(campaign=self.spring, lead=self.bilal, status='sent',
                                                    recipient_email=self.bilal.email, subject='Spring',
                                                    tracking_token='tok-123')

    def click(self, url):
        # The email's /token is answered by the usual redirect to /token/; this is the request after it.
        parts = urlsplit(url)
        return Client().get(parts.path.rstrip('/') + '/', {k: v[0] for k, v in parse_qs(parts.query).items()})

    def test_a_link_with_two_parameters_arrives_whole(self):
        offer = 'https://acme.test/offer?a=1&b=2#top'
        response = self.click(click_links.wrap('https://api.example.test', 'tok-123', offer))
        self.assertEqual((response.status_code, response['Location']), (302, offer))
        self.sent.refresh_from_db()
        self.assertEqual(self.sent.status, 'clicked')

    def test_a_made_up_token_or_a_changed_address_goes_nowhere(self):
        signed = click_links.wrap('https://api.example.test', 'tok-123', 'https://acme.test/offer')
        swapped = signed.replace('acme.test%2Foffer', 'evil.test%2Fphish')
        for url in ('/token/?t=nobody&url=https://evil.test', swapped, '/token/?t=nobody&url=https://evil.test&s=abc'):
            response = self.click(url)
            self.assertEqual(response.status_code, 404, url)
            self.assertNotIn('Location', response)
        self.sent.refresh_from_db()
        self.assertEqual(self.sent.status, 'sent')                       # a refused click is not counted

    def test_a_link_from_an_email_sent_before_signing_still_works(self):
        response = Client().get('/token/', {'t': 'tok-123', 'url': 'https://acme.test/offer'})
        self.assertEqual((response.status_code, response['Location']), (302, 'https://acme.test/offer'))
        # The older address form takes the same rules.
        response = Client().get('/marketing/track/email/nobody/click/', {'url': 'https://evil.test'})
        self.assertEqual(response.status_code, 404)

    def test_the_sender_wraps_links_signed(self):
        from unittest import mock
        from django.core import mail
        from marketing_agent.services.email_service import EmailService
        self.mailbox(self.ann, 'ann@acme.test', is_default=True)
        template = self.template(self.spring, html_content='<html><body><a href="https://acme.test/offer?a=1&b=2">Offer</a>'
                                                           '</body></html>')
        with mock.patch('django.core.mail.backends.smtp.EmailBackend',
                        side_effect=lambda **settings: mail.get_connection('django.core.mail.backends.locmem.EmailBackend')), \
                mock.patch.object(EmailService, '_append_to_imap_sent'):
            EmailService().send_email(template=template, lead=self.bilal, campaign=self.spring)
        html = mail.outbox[-1].alternatives[0][0]
        self.assertIn('url=https%3A%2F%2Facme.test%2Foffer%3Fa%3D1%26b%3D2&s=', html)


class MailboxPasswordTests(MarketingTestCase):

    def test_passwords_are_stored_encrypted_and_read_back_plain(self):
        box = self.mailbox(self.ann, 'ann@acme.test', smtp_password='app-pass-1', imap_password='imap-pass-2')
        with connection.cursor() as cursor:
            cursor.execute(f'SELECT smtp_password, imap_password FROM {EmailAccount._meta.db_table} WHERE id = %s', [box.id])
            smtp, imap = cursor.fetchone()
        self.assertNotIn('app-pass', smtp)
        self.assertNotIn('imap-pass', imap)
        box = EmailAccount.objects.get(id=box.id)
        self.assertEqual((box.smtp_password, box.imap_password), ('app-pass-1', 'imap-pass-2'))


class DocumentPdfTests(MarketingTestCase):

    def test_the_ais_text_is_text_not_markup(self):
        from marketing_agent.document_generator import _bold_markdown
        self.assertEqual(_bold_markdown('Write to <sales@acme.test> about **R&D**<br>'),
                         'Write to &lt;sales@acme.test&gt; about <b>R&amp;D</b>&lt;br&gt;')
        self.assertEqual(_bold_markdown('<img src="http://169.254.169.254/latest"/>'),
                         '&lt;img src="http://169.254.169.254/latest"/&gt;')

    def test_a_pdf_with_tags_and_angle_brackets_downloads(self):
        from marketing_agent.document_generator import DocumentGenerator
        from marketing_agent.models import MarketingDocument
        doc = MarketingDocument.objects.create(created_by=self.ann, title='Plan <Q4> & beyond', document_type='strategy',
                                               content='# Plan\nCall <ann@acme.test><br>\n| A | B |\n|---|---|\n'
                                                       '| <img src="file:///etc/passwd"/> | R&D |')
        response = DocumentGenerator.generate_pdf(doc)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b'%PDF'))


class SendingTests(MarketingTestCase):
    """CO-120, 121, 122, 127, 129, 130, 190, 191, 192, 233, 234."""

    def setUp(self):
        super().setUp()
        self.box = self.mailbox(self.ann, 'ann@acme.test', is_default=True)
        self.spring = self.campaign(self.ann, email_account=self.box)
        self.main = self.sequence(self.spring, steps=2)
        self.bilal = self.lead(self.ann, 'bilal@customer.test', campaign=self.spring, first_name='Bilal')

    def test_a_reply_is_matched_only_within_the_mailboxs_company(self):           # CO-120
        from email.message import EmailMessage
        from marketing_agent.management.commands.sync_inbox import Command
        theirs = self.campaign(self.rita, name='Rival offer')
        sent = EmailSendHistory.objects.create(campaign=theirs, lead=self.lead(self.rita, 'bilal@customer.test'),
                                               subject='Offer', recipient_email='bilal@customer.test',
                                               message_id='abc@rival', status='sent')
        msg = EmailMessage()
        msg['From'], msg['Subject'], msg['In-Reply-To'] = 'bilal@customer.test', 'Re: Offer', '<abc@rival>'
        self.assertEqual(Command().detect_reply(msg, self.box), (False, None))
        rival_box = self.mailbox(self.rita, 'rita@rival.test')
        self.assertEqual(Command().detect_reply(msg, rival_box), (True, sent))

    def test_a_future_start_is_scheduled_and_the_sender_keeps_to_the_dates(self):  # CO-121
        from datetime import timedelta
        from marketing_agent.agents.outreach_campaign_agent import OutreachCampaignAgent
        from marketing_agent.services.launch_checks import today_for
        agent = OutreachCampaignAgent.__new__(OutreachCampaignAgent)
        agent.log_action = lambda *a, **k: None
        self.spring.status = 'draft'
        self.spring.save()
        later = today_for(self.ann) + timedelta(days=5)
        result = agent.launch_campaign(self.spring.id, self.ann.id, campaign_data={'start_date': later.isoformat()})
        self.spring.refresh_from_db()
        self.assertTrue(result['success'], result)
        self.assertEqual(self.spring.status, 'scheduled')
        self.assertIn('scheduled to start', result['message'])
        # Active but ended yesterday: nothing goes out.
        type(self.spring).objects.filter(pk=self.spring.pk).update(
            status='active', start_date=today_for(self.ann) - timedelta(days=9),
            end_date=today_for(self.ann) - timedelta(days=1))
        self.assertEqual(self.run_sender(), [])

    def test_schedule_and_the_starter_make_launchs_checks(self):                    # CO-130
        from datetime import timedelta
        from marketing_agent.agents.outreach_campaign_agent import OutreachCampaignAgent
        from marketing_agent.services.launch_checks import today_for
        from marketing_agent.tasks import auto_start_campaigns_task
        agent = OutreachCampaignAgent.__new__(OutreachCampaignAgent)
        agent.log_action = lambda *a, **k: None
        bare = self.campaign(self.ann, name='Bare', status='draft')
        past = (today_for(self.ann) - timedelta(days=2)).isoformat()
        self.assertIn('past', agent.schedule_campaign(self.spring.id, self.ann.id, {'start_date': past})['error'])
        result = agent.schedule_campaign(bare.id, self.ann.id, {'start_date': today_for(self.ann).isoformat()})
        self.assertEqual(result.get('error_code'), 'no_steps')
        # Scheduled with no sending mailbox: the starter leaves it scheduled.
        nobox = self.campaign(self.ann, name='No box', status='draft')
        self.sequence(nobox, steps=1)
        type(nobox).objects.filter(pk=nobox.pk).update(status='scheduled', start_date=today_for(self.ann))
        auto_start_campaigns_task()
        nobox.refresh_from_db()
        self.assertEqual(nobox.status, 'scheduled')

    def test_an_address_must_be_an_address_and_failures_back_off_then_stop(self):  # CO-122
        from api.views import marketing_agent as views
        from marketing_agent.models import CampaignContact
        code, body = self.call(views.add_campaign_lead, self.ann_login, {'email': 'n/a'}, campaign_id=self.spring.id)
        self.assertEqual((code, body.get('error')), (400, 'invalid_email'))
        contact = CampaignContact.objects.create(campaign=self.spring, lead=self.bilal, sequence=self.main)
        for _ in range(CampaignContact.MAX_SEND_FAILURES):
            contact.note_send_failure()
        contact.refresh_from_db()
        self.assertEqual((contact.gave_up, contact.completed), (True, True))
        self.assertEqual(self.run_sender(), [])

    def test_adding_a_lead_where_a_follow_up_series_exists_says_it_was_added(self):  # CO-127
        from api.views import marketing_agent as views
        from marketing_agent.models import CampaignContact
        self.sequence(self.spring, steps=1, name='If interested', is_sub_sequence=True, parent_sequence=self.main)
        code, body = self.call(views.add_campaign_lead, self.ann_login,
                               {'email': 'sara@customer.test', 'first_name': 'Sara'}, campaign_id=self.spring.id)
        self.assertEqual(code, 201, body)
        self.assertEqual(CampaignContact.objects.filter(lead__email='sara@customer.test').count(), 1)

    def test_a_mailbox_is_not_read_for_a_company_that_stopped_paying(self):       # CO-129
        from core.models import CompanyModulePurchase
        from marketing_agent.services.subscription import mailboxes_to_read
        rival_box = self.mailbox(self.rita, 'rita@rival.test')
        CompanyModulePurchase.objects.filter(company=self.rival).update(status='cancelled')
        self.assertEqual(mailboxes_to_read([self.box, rival_box]), [self.box])

    def test_a_switched_off_mailbox_sends_nothing(self):                          # CO-190
        self.box.is_active = False
        self.box.save()
        self.assertEqual(self.run_sender(), [])
        self.assertFalse(EmailSendHistory.objects.exists())

    def test_a_paused_campaign_or_a_contact_another_run_holds_is_not_sent(self):  # CO-191
        from marketing_agent.management.commands.send_sequence_emails import Command
        from marketing_agent.models import CampaignContact
        contact = CampaignContact.objects.create(campaign=self.spring, lead=self.bilal, sequence=self.main)
        self.assertTrue(Command()._claim(contact))
        self.assertFalse(Command()._claim(contact))                  # held by the first run
        CampaignContact.objects.filter(pk=contact.pk).update(retry_after=None)
        type(self.spring).objects.filter(pk=self.spring.pk).update(status='paused')
        self.assertFalse(Command()._claim(contact))                  # paused meanwhile

    def test_a_bounce_is_recorded_and_an_out_of_office_is_not_a_reply(self):     # CO-192
        from email.message import EmailMessage
        from core.do_not_email import is_blocked
        from marketing_agent.management.commands.sync_inbox import Command
        self.run_sender()
        bounce = EmailMessage()
        bounce['From'] = 'Mail Delivery Subsystem <mailer-daemon@googlemail.com>'
        bounce['Subject'] = 'Delivery Status Notification (Failure)'
        bounce.set_content('Your message to bilal@customer.test could not be delivered: user unknown.')
        command = Command()
        self.assertEqual(command._automatic(bounce, 'mailer-daemon@googlemail.com'), 'bounce')
        self.assertEqual(command._record_bounce(bounce, self.box), 'bilal@customer.test')
        self.assertEqual(EmailSendHistory.objects.filter(status='bounced').count(), 1)
        self.assertTrue(is_blocked(self.acme, 'bilal@customer.test'))
        away = EmailMessage()
        away['From'], away['Subject'], away['Auto-Submitted'] = 'bilal@customer.test', 'Out of office', 'auto-replied'
        self.assertEqual(command._automatic(away, 'bilal@customer.test'), 'auto')

    def test_a_step_cannot_lose_its_template_and_a_gap_is_stepped_over(self):     # CO-233
        from api.views import marketing_agent as views
        step_one = self.main.steps.get(step_order=1)
        type(self.spring).objects.filter(pk=self.spring.pk).update(status='paused')
        code, body = self.call(views.delete_template, self.ann_login, campaign_id=self.spring.id,
                               template_id=step_one.template_id)
        self.assertEqual((code, body.get('error')), (400, 'template_in_sequence'))
        type(self.spring).objects.filter(pk=self.spring.pk).update(status='active')
        step_one.delete()                                   # a gap: only step 2 is left
        self.assertEqual(self.run_sender(), [('bilal@customer.test', 'Main 2')])

    def test_no_view_in_browser_line(self):                                          # CO-234
        from unittest import mock
        from django.core import mail
        from marketing_agent.services.email_service import EmailService
        template = self.template(self.spring, html_content='<html><body><p>Hi</p></body></html>')
        with mock.patch('django.core.mail.backends.smtp.EmailBackend',
                        side_effect=lambda **settings: mail.get_connection('django.core.mail.backends.locmem.EmailBackend')), \
                mock.patch.object(EmailService, '_append_to_imap_sent'):
            EmailService().send_email(template=template, lead=self.bilal, campaign=self.spring)
        self.assertNotIn('View in browser', mail.outbox[-1].alternatives[0][0])


class ReplyDraftDisconnectTests(MarketingTestCase):

    def test_marketing_still_reads_a_mailbox_reply_draft_lets_go(self):            # CO-155
        from unittest import mock
        from api.views import reply_draft_agent as views
        from core.models import CompanyModulePurchase
        CompanyModulePurchase.objects.create(company=self.acme, module_name='reply_draft_agent', status='active',
                                             is_complimentary=True)
        box = self.mailbox(self.ann, 'ann@acme.test', is_reply_agent_account=True, enable_imap_sync=True)
        with mock.patch.object(views, 'delete_reply_draft_account_data'):
            code, body = self.call(views.delete_reply_account, self.ann_login, method='delete')
        box.refresh_from_db()
        self.assertEqual((box.is_reply_agent_account, box.enable_imap_sync), (False, True), body)


class ReplyReadingTests(MarketingTestCase):
    """CO-128: keyword rules overrode the AI and read the company's own subject line."""

    def read(self, ai_says, content, subject='Re: Spring offer - unsubscribe anytime'):
        from unittest import mock
        from marketing_agent.utils.reply_analyzer import ReplyAnalyzer
        analyzer = ReplyAnalyzer.__new__(ReplyAnalyzer)
        analyzer.system_prompt = ''
        answer = '{"interest_level": "%s", "analysis": "test", "confidence": 90}' % ai_says
        with mock.patch.object(ReplyAnalyzer, '_call_groq_qa', create=True, return_value=answer):
            return analyzer.analyze_reply(subject, content, 'Spring offer', company_id=self.acme.id)['interest_level']

    def test_the_ai_reads_the_reply_and_the_subject_does_not_unsubscribe_anyone(self):
        self.assertEqual(self.read('positive', 'Sure, send me the details for next week.'), 'positive')
        self.assertEqual(self.read('negative', 'Not interested, thanks.'), 'negative')       # a no, not a stop
        self.assertEqual(self.read('requested_info', 'We will ensure the budget first - what does it cost?'),
                         'requested_info')

    def test_an_explicit_request_to_stop_is_always_one(self):
        self.assertEqual(self.read('negative', "Please don't email me again, unsubscribe me."), 'unsubscribe')


class QAReadingTests(MarketingTestCase):
    """The Q&A assistant's routing is the AI's reading; keyword rules only when it fails (29 Oct 2026). CO-239."""

    def agent(self):
        from marketing_agent.agents.marketing_qa_agent import MarketingQAAgent
        agent = MarketingQAAgent.__new__(MarketingQAAgent)
        agent.log_action = lambda *a, **k: None
        agent.system_prompt = ''
        return agent

    def ask(self, ai_says, question, context=None):
        from unittest import mock
        from marketing_agent.agents.marketing_qa_agent import MarketingQAAgent
        agent = self.agent()
        with mock.patch.object(MarketingQAAgent, '_call_llm_for_reasoning', create=True, return_value=ai_says), \
                mock.patch.object(MarketingQAAgent, '_handle_llm_reasoning', return_value={'answer': 'from the data'}) as data:
            result = agent.process(question, context or {}, user_id=self.ann.id)
        return result, data

    def test_a_command_is_refused_and_an_off_topic_request_declined(self):
        result, data = self.ask('{"kind": "command", "about": "campaigns"}', 'pause spring offer now')
        self.assertTrue(result.get('action_refused'))
        data.assert_not_called()
        result, data = self.ask('{"kind": "off_topic"}', 'write a poem about my campaigns')
        self.assertIn("outside what I can help with", result['answer'])
        data.assert_not_called()

    def test_a_data_question_reaches_the_data_with_the_ais_reading(self):
        result, data = self.ask('{"kind": "data", "about": "leads", "continues": true}',
                                'to which campaign do they belong?')
        self.assertEqual(result, {'answer': 'from the data'})
        reading = data.call_args[0][3]
        self.assertEqual((reading['about'], reading['continues'], reading['asks_why']), ('leads', True, False))

    def test_when_the_reading_fails_the_keyword_rules_decide(self):
        result, data = self.ask('not json at all', 'delete campaign spring offer')
        self.assertTrue(result.get('action_refused'))

    def test_the_tidy_up_corrects_only_a_count_of_campaigns(self):
        agent = self.agent()
        campaigns = [{'name': n} for n in ('alpha', 'beta', 'gamma', 'delta')]
        rows = '\n'.join(f'- {n}: sent: 3' for n in ('alpha', 'beta', 'gamma', 'delta'))
        self.assertEqual(agent._fix_count_mismatch('2 campaigns match:\n' + rows, campaigns).split('\n')[0],
                         '4 campaigns match:')
        answer = '120 emails went out:\n' + rows
        self.assertEqual(agent._fix_count_mismatch(answer, campaigns), answer)


class FiguresTests(MarketingTestCase):
    """CO-135 graphs, CO-137 reports, CO-194 mailbox counts, CO-195 people not messages."""

    def setUp(self):
        super().setUp()
        from marketing_agent.models import CampaignContact, Reply
        self.box = self.mailbox(self.ann, 'ann@acme.test', is_default=True)
        self.spring = self.campaign(self.ann, email_account=self.box, target_conversions=4)
        template = self.template(self.spring)
        for n, interest in enumerate(('positive', 'positive', 'neutral')):
            lead = self.lead(self.ann, f'lead{n}@customer.test', campaign=self.spring)
            EmailSendHistory.objects.create(campaign=self.spring, lead=lead, email_template=template, subject='Hi',
                                            recipient_email=lead.email, status='opened', email_account=self.box)
            contact = CampaignContact.objects.create(campaign=self.spring, lead=lead)
            Reply.objects.create(contact=contact, campaign=self.spring, lead=lead, interest_level=interest,
                                 reply_content='hi')
        # The first lead wrote twice: one person, two messages.
        first = self.spring.leads.order_by('id').first()
        Reply.objects.create(contact=CampaignContact.objects.get(lead=first), campaign=self.spring, lead=first,
                             interest_level='positive', reply_content='again')

    def test_one_set_of_figures_counting_people(self):
        from marketing_agent.services.campaign_numbers import numbers
        n = numbers(self.spring)
        self.assertEqual((n['sent'], n['replied_leads'], n['reply_messages'], n['conversions']), (3, 3, 4, 2))
        self.assertEqual(n['conversion_progress'], 50.0)

    def test_a_graph_shows_the_metric_the_ai_named_under_its_own_title(self):
        from unittest import mock
        from marketing_agent.agents.graph_generator_agent import GraphGeneratorAgent as Graphs
        agent = Graphs.__new__(Graphs)
        agent.user = self.ann
        answer = '{"chart_type": "bar", "metric": "conversions", "title": "Whatever", "data": {}}'
        with mock.patch.object(Graphs, '_call_llm', create=True, return_value=answer):
            chart = agent.generate_graph('which campaigns convert best?')['chart']
        self.assertEqual(chart['title'], 'Conversions by Campaign')
        self.assertEqual(chart['data'], {'Spring offer': 2})

    def test_a_report_counts_conversions_like_the_campaign_page(self):
        from marketing_agent.agents.document_authoring_agent import DocumentAuthoringAgent
        agent = DocumentAuthoringAgent.__new__(DocumentAuthoringAgent)
        data = agent._get_campaign_data_for_document(self.spring, 'report')
        self.assertEqual(data['conversions'], 2)
        text = agent._format_campaign_data(data)
        self.assertIn('Actual Conversions: 2', text)
        self.assertNotIn('Zero conversions', text)

    def test_mailbox_counts_and_the_dashboard_total(self):
        from api.views import marketing_agent as views
        code, body = self.call(views.list_email_accounts, self.ann_login, method='get')
        self.assertEqual(code, 200, body)
        self.assertEqual(body['total_sent'], 3)
        self.assertEqual(body['data'][0]['sent_count'], 3)


class SharingTests(MarketingTestCase):
    """Decision of 29 Oct: an owner or admin opens and manages any campaign of the company; it still sends from its
    maker's mailbox and only its maker deletes it. Anyone else reaches only their own."""

    def setUp(self):
        super().setUp()
        self.bob_login = self.login(self.acme, 'bob@acme.test', 'Bob Baig', role='marketing_agent')
        self.bob = user_for(self.bob_login)
        self.bob_box = self.mailbox(self.bob, 'bob@acme.test')
        self.ann_box = self.mailbox(self.ann, 'ann@acme.test')
        self.bobs = self.campaign(self.bob, name="Bob's launch", status='draft', email_account=self.bob_box)
        self.anns = self.campaign(self.ann, name="Ann's own", status='draft')

    def test_an_admin_opens_a_colleagues_campaign_and_sees_whose_it_is(self):
        from api.views import marketing_agent as views
        code, body = self.call(views.get_campaign, self.ann_login, method='get', campaign_id=self.bobs.id)
        self.assertEqual(code, 200, body)
        self.assertFalse(body['data']['campaign']['is_own'])
        self.assertEqual(body['data']['campaign']['made_by'], 'Bob Baig')

    def test_a_member_still_reaches_only_their_own(self):
        from api.views import marketing_agent as views
        code, _ = self.call(views.get_campaign, self.bob_login, method='get', campaign_id=self.anns.id)
        self.assertEqual(code, 404)
        code, _ = self.call(views.get_campaign, self.rita_login, method='get', campaign_id=self.bobs.id)
        self.assertEqual(code, 404)

    def test_a_lead_added_by_the_admin_is_the_makers(self):
        from api.views import marketing_agent as views
        code, body = self.call(views.add_campaign_lead, self.ann_login, {'email': 'sara@customer.test'},
                               campaign_id=self.bobs.id)
        self.assertEqual(code, 201, body)
        self.assertEqual(self.bobs.leads.get().owner_id, self.bob.pk)

    def test_the_campaign_keeps_its_makers_mailboxes(self):
        from api.views import marketing_agent as views
        code, body = self.call(views.list_email_accounts, self.ann_login, {'campaign_id': self.bobs.id}, method='get')
        self.assertEqual(code, 200, body)
        self.assertEqual([a['email'] for a in body['data']], ['bob@acme.test'])
        code, _ = self.call(views.update_campaign, self.ann_login, {'email_account_id': self.ann_box.id},
                            method='put', campaign_id=self.bobs.id)
        self.bobs.refresh_from_db()
        self.assertEqual(self.bobs.email_account_id, self.bob_box.id)

    def test_only_the_maker_deletes_it(self):
        from api.views import marketing_agent as views
        code, body = self.call(views.campaign_delete, self.ann_login, campaign_id=self.bobs.id)
        self.assertEqual((code, body.get('error')), (403, 'not_the_maker'))
        self.assertTrue(Campaign.objects.filter(id=self.bobs.id).exists())

    def test_the_admin_launches_it_for_its_maker(self):
        from unittest import mock
        from api.views import marketing_agent as views
        agent = mock.Mock()
        agent.process.return_value = {'success': True}
        with mock.patch.object(views.AgentRegistry, 'get_agent', return_value=agent):
            code, _ = self.call(views.outreach_campaign, self.ann_login,
                                {'action': 'launch', 'campaign_id': self.bobs.id, 'campaign_data': {}})
            self.assertEqual(code, 200)
            self.assertEqual(agent.process.call_args.kwargs['user_id'], self.bob.pk)
            self.call(views.outreach_campaign, self.bob_login,
                      {'action': 'launch', 'campaign_id': self.anns.id, 'campaign_data': {}})
            self.assertEqual(agent.process.call_args.kwargs['user_id'], self.bob.pk)


class WebResearchTests(MarketingTestCase):
    """Decision of 29 Oct: research searches the web (OpenAI's web_search) and shows the pages it read; without a
    search it says so. Deleting a research chat deletes the research it saved (CO-274)."""

    @staticmethod
    def _response(text, cited=(), consulted=()):
        from types import SimpleNamespace as NS
        notes = [NS(type='url_citation', url=url, title=title) for url, title in cited]
        return NS(output=[NS(type='web_search_call', action=NS(sources=[NS(type='url', url=u) for u in consulted])),
                          NS(type='message', content=[NS(type='output_text', annotations=notes)])],
                  output_text=text, usage=NS(input_tokens=900, output_tokens=300))

    def test_the_answer_loses_its_inline_marks_and_lists_the_pages(self):
        from marketing_agent.services.web_search import answer_and_sources
        text, sources = answer_and_sources(self._response(
            'Plans cost PKR 3,000 to 60,000 a month. ([edish.net](https://edish.net/plans?utm_source=openai)) '
            'See [the guide](https://www.example.com/guide).',
            cited=[('https://edish.net/plans?utm_source=openai', 'Maintenance plans | Edish')],
            consulted=['https://www.example.com/guide', 'https://edish.net/plans', 'javascript:alert(1)']))
        self.assertEqual(text, 'Plans cost PKR 3,000 to 60,000 a month. See the guide.')
        self.assertEqual(sources, [
            {'title': 'Maintenance plans | Edish', 'url': 'https://edish.net/plans', 'site': 'edish.net'},
            {'title': 'example.com', 'url': 'https://www.example.com/guide', 'site': 'example.com'}])

    def _agent(self):
        from marketing_agent.agents.market_research_agent import MarketResearchAgent
        agent = MarketResearchAgent()
        agent.company_id, agent.agent_key_name = self.acme.id, 'marketing_agent'
        return agent

    def test_research_keeps_the_pages_it_read(self):
        from unittest import mock
        agent = self._agent()
        page = {'title': 'Solar in Pakistan', 'url': 'https://pv.example/solar', 'site': 'pv.example'}
        with mock.patch.object(agent, '_wants_brief_answer', return_value=True), \
                mock.patch.object(agent, '_call_with_web_search', return_value=('Demand is rising.', [page])), \
                mock.patch.object(agent, '_call_llm_for_reasoning') as plain:
            found = agent._conduct_research('market_trend', 'Is demand for solar rising in Pakistan?', {})
        plain.assert_not_called()
        self.assertEqual((found['source_urls'], found['checked_on_web']), ([page], True))

    def test_without_a_search_the_answer_says_so(self):
        from unittest import mock
        agent = self._agent()
        with mock.patch.object(agent, '_wants_brief_answer', return_value=True), \
                mock.patch.object(agent, '_call_with_web_search', return_value=None), \
                mock.patch.object(agent, '_call_llm_for_reasoning', return_value='Demand is rising.'):
            found = agent._conduct_research('market_trend', 'Is demand for solar rising in Pakistan?', {})
        self.assertEqual((found['source_urls'], found['checked_on_web']), ([], False))

    def test_a_company_on_free_groq_tokens_searches_with_the_platforms_openai_key(self):
        from unittest import mock
        from core.api_key_service import CallContext
        from core.models import PlatformAPIKey
        from marketing_agent.agents import marketing_base_agent as base
        key = PlatformAPIKey(provider='openai', status='active')
        key.set_plaintext_key('sk-test-not-real')
        key.save()
        groq = CallContext(company_id=self.acme.id, agent_name='marketing_agent', mode='platform', provider='groq',
                           api_key='gsk-test', key_id=1, quota_id=None)
        agent = self._agent()
        client = mock.Mock()
        client.responses.create.return_value = self._response('Rising. ([a.example](https://a.example/x))',
                                                             cited=[('https://a.example/x', 'A')])
        recorded = []
        with mock.patch.object(agent, '_resolve_company_client', return_value=(mock.Mock(), groq)), \
                mock.patch.object(base, 'OpenAI', return_value=client) as made, \
                mock.patch('core.api_key_service.record_usage', side_effect=lambda ctx, n: recorded.append((ctx, n))):
            text, sources = agent._call_with_web_search('Is demand rising?', 'system')
        self.assertEqual(made.call_args.kwargs['api_key'], 'sk-test-not-real')
        self.assertEqual(client.responses.create.call_args.kwargs['tools'], [{'type': 'web_search'}])
        self.assertEqual((text, [s['url'] for s in sources]), ('Rising.', ['https://a.example/x']))
        self.assertEqual((recorded[0][0].provider, recorded[0][0].mode, recorded[0][1]), ('openai', 'platform', 1200))

    def test_an_own_groq_key_does_not_borrow_the_platforms(self):
        from core.api_key_service import CallContext, platform_context_for
        own = CallContext(company_id=self.acme.id, agent_name='marketing_agent', mode='byok', provider='groq',
                          api_key='gsk-own', key_id=1)
        self.assertIsNone(platform_context_for(own, 'openai'))

    def test_deleting_a_research_chat_deletes_its_research(self):
        from api.views import marketing_agent as views
        from marketing_agent.models import MarketResearch, MarketResearchChat, MarketResearchChatMessage
        kept = MarketResearch.objects.create(research_type='market_trend', topic='Kept', created_by=self.ann)
        gone = MarketResearch.objects.create(research_type='market_trend', topic='Gone', created_by=self.ann)
        chat = MarketResearchChat.objects.create(company_user=self.ann_login, title='Solar')
        MarketResearchChatMessage.objects.create(chat=chat, role='user', content='Solar?')
        MarketResearchChatMessage.objects.create(chat=chat, role='assistant', content='Rising.',
                                                 response_data={'research_id': gone.id})
        code, _ = self.call(views.delete_research_chat, self.ann_login, method='delete', chat_id=chat.id)
        self.assertEqual(code, 200)
        self.assertEqual(list(MarketResearch.objects.values_list('topic', flat=True)), ['Kept'])
