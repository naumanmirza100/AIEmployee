"""Marketing gaps fixed before its demo (29 Oct 2026), from the inside-gaps report.

CO-124: a tracked link lost everything after the first '&' of its address.
CO-125: the click address sent anyone to any website, even with a made-up token.
CO-126: mailbox passwords were stored in clear text.
CO-132: the PDF of a document took the AI's text as trusted markup.
"""
from urllib.parse import parse_qs, urlsplit

from django.db import connection
from django.test import Client, override_settings

from marketing_agent.models import EmailAccount, EmailSendHistory
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
