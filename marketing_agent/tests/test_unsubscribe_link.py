"""Every Marketing campaign email carries a way to unsubscribe.

The sender added a tracking pixel, rewrote links and added a 'View in browser'
line, but no unsubscribe link and no List-Unsubscribe header. A lead could only
opt out by replying, and only if the mailbox's inbox sync was working and the
reply was read as an unsubscribe.
"""
import re
from unittest import mock

from django.core import mail
from django.test import Client, override_settings

from core.do_not_email import is_blocked
from marketing_agent.services import unsubscribe as links
from marketing_agent.services.email_service import EmailService
from marketing_agent.tests.base import MarketingTestCase

LOCAL = 'django.core.mail.backends.locmem.EmailBackend'


@override_settings(SITE_URL='https://api.example.test')
class UnsubscribeLinkTests(MarketingTestCase):

    def setUp(self):
        super().setUp()
        self.mailbox(self.ann, 'ann@acme.test', is_default=True)
        self.spring = self.campaign(self.ann)
        self.bilal = self.lead(self.ann, 'bilal@customer.test', campaign=self.spring, first_name='Bilal')

    def send(self, html='<html><body><p>Hi {{first_name}}</p><a href="https://acme.test/offer?a=1">Offer</a></body></html>',
             text='Hi {{first_name}}', **more):
        template = self.template(self.spring, html_content=html, text_content=text)
        # The real service, with the mailbox's SMTP connection swapped for the test outbox.
        with mock.patch('django.core.mail.backends.smtp.EmailBackend',
                        side_effect=lambda **settings: mail.get_connection(LOCAL)), \
                mock.patch.object(EmailService, '_append_to_imap_sent'):
            result = EmailService().send_email(template=template, lead=self.bilal, campaign=self.spring, **more)
        return result, (mail.outbox[-1] if mail.outbox else None)

    def link_in(self, text):
        found = re.search(r'https://api\.example\.test/api/marketing/unsubscribe/[\w:-]+/', text)
        return found.group(0) if found else None

    def path(self, url):
        return url.replace('https://api.example.test', '')

    def blocked(self, address='bilal@customer.test', company=None):
        return is_blocked((company or self.acme).id, address)

    # ---- the email -----------------------------------------------------------

    def test_the_email_has_the_link_in_both_parts_and_the_one_click_header(self):
        result, message = self.send()
        self.assertTrue(result['success'], result)
        html = message.alternatives[0][0]
        link = self.link_in(html)
        self.assertIsNotNone(link)
        self.assertEqual(self.link_in(message.body), link)
        self.assertIn('Unsubscribe', html)
        self.assertEqual(message.extra_headers['List-Unsubscribe'], f'<{link}>')
        self.assertEqual(message.extra_headers['List-Unsubscribe-Post'], 'List-Unsubscribe=One-Click')
        self.assertEqual(links.read_token(link.rstrip('/').rsplit('/', 1)[1]), (self.acme.id, 'bilal@customer.test'))

    def test_the_link_is_not_sent_through_click_tracking(self):
        _, message = self.send()
        html = message.alternatives[0][0]
        self.assertIn('/token?t=', html)                                   # the offer link is tracked
        self.assertRegex(html, r'href="https://api\.example\.test/api/marketing/unsubscribe/')
        self.assertNotRegex(html, r'url=[^"]*marketing/unsubscribe')

    def test_the_footer_goes_inside_the_body(self):
        _, message = self.send()
        html = message.alternatives[0][0]
        self.assertLess(html.index('/api/marketing/unsubscribe/'), html.lower().index('</body>'))

    def test_a_template_with_no_body_tag_or_text_part_still_gets_it(self):
        _, message = self.send(html='<p>Hi</p>', text='')
        self.assertIsNotNone(self.link_in(message.alternatives[0][0]))
        self.assertIsNotNone(self.link_in(message.body))

    def test_a_template_can_place_the_link_itself_and_gets_no_second_one(self):
        _, message = self.send(html='<body><a href="{{unsubscribe_url}}">Stop these</a></body>',
                               text='Stop: {{unsubscribe_url}}')
        html = message.alternatives[0][0]
        self.assertEqual(html.count('/api/marketing/unsubscribe/'), 1)
        self.assertIn('Stop these', html)
        self.assertEqual(message.body.count('/api/marketing/unsubscribe/'), 1)
        self.assertIn('List-Unsubscribe', message.extra_headers)

    def test_a_test_send_has_none(self):
        _, message = self.send(test_email='ann@acme.test')
        self.assertEqual(message.to, ['ann@acme.test'])
        self.assertIsNone(self.link_in(message.alternatives[0][0]))
        self.assertNotIn('List-Unsubscribe', message.extra_headers)

    def test_no_link_is_made_when_the_company_cannot_be_told(self):
        with mock.patch.object(links, 'company_id_for_campaign', return_value=None):
            self.assertEqual(links.url_for(self.spring, 'bilal@customer.test'), '')
        self.assertEqual(links.url_for(self.spring, '  '), '')

    # ---- the page ------------------------------------------------------------

    def test_opening_the_link_changes_nothing_and_pressing_the_button_unsubscribes(self):
        _, message = self.send()
        path = self.path(self.link_in(message.body))

        page = Client().get(path)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'bilal@customer.test')
        self.assertContains(page, '<form method="post"')
        self.assertFalse(self.blocked())

        done = Client().post(path)
        self.assertEqual(done.status_code, 200)
        self.assertContains(done, 'unsubscribed')
        self.assertTrue(self.blocked())
        self.assertFalse(self.blocked(company=self.rival))                 # only the company that wrote

    def test_after_that_the_campaign_does_not_email_them(self):
        _, message = self.send()
        Client().post(self.path(self.link_in(message.body)))
        mail.outbox.clear()
        result, _ = self.send()
        self.assertEqual((result['success'], result.get('blocked')), (False, True))
        self.assertEqual(mail.outbox, [])

    def test_it_works_twice_and_after_the_campaign_and_the_lead_are_gone(self):
        _, message = self.send()
        path = self.path(self.link_in(message.body))
        self.spring.delete()
        self.bilal.delete()
        self.assertEqual(Client().post(path).status_code, 200)
        self.assertEqual(Client().post(path).status_code, 200)
        self.assertTrue(self.blocked())

    def test_a_link_nobody_signed_is_refused_and_says_so(self):
        _, message = self.send()
        good = self.path(self.link_in(message.body))
        for bad in ('/api/marketing/unsubscribe/garbage/', good[:-6] + 'xxxxx/'):
            for response in (Client().get(bad), Client().post(bad)):
                self.assertEqual(response.status_code, 404, bad)
                self.assertIn(b'could not unsubscribe you', response.content)
        self.assertFalse(self.blocked())

    def test_a_sales_link_is_not_accepted_here(self):
        from django.core import signing
        other = signing.dumps({'c': self.acme.id, 'm': 'bilal@customer.test'}, salt='sdr-unsubscribe')
        self.assertEqual(Client().post(f'/api/marketing/unsubscribe/{other}/').status_code, 404)
        self.assertFalse(self.blocked())

    def test_what_is_typed_into_the_page_is_shown_as_text(self):
        token = links.make_token(self.acme.id, '<script>x</script>@customer.test')
        page = Client().get(f'/api/marketing/unsubscribe/{token}/')
        self.assertNotIn(b'<script>x</script>', page.content)
