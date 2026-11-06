"""Email templates and industry sends (6 Nov 2026): the user writes an HTML template, previews it with a real lead, and
sends it to the leads of one industry through a campaign's mailbox. The scheduler sends it a few at a time, within
the mailbox's daily limit shared with the campaigns, one email per lead per day, never to the do-not-email list."""
import email
from datetime import timedelta
from unittest import mock

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from ai_sdr_agent import tasks
from ai_sdr_agent.agents import outreach_agent as oa
from ai_sdr_agent.email_templates import html_to_text, render, unknown_variables
from ai_sdr_agent.models import (
    SDREmailSend, SDREmailSendRecipient, SDREmailTemplate, SDRLead, SDROutreachLog,
)
from ai_sdr_agent.tests import SDRBase
from api.views import ai_sdr_agent as views
from core.models import Company, CompanyUser

HTML = ('<html><body><p>Hi {first_name},</p><p>About {company_name}: '
        '<a href="https://acme.example/x">see this</a></p>'
        '<p><a href="{unsubscribe_url}">Unsubscribe</a></p></body></html>')


class Base(SDRBase):
    def setUp(self):
        super().setUp()
        self.rf = APIRequestFactory()
        self.campaign.sender_name, self.campaign.sender_company = 'Sam Carter', 'Acme Ltd'
        self.campaign.save()

    def call(self, view, method='get', data=None, user=None, **kw):
        req = getattr(self.rf, method)('/x', data or {}, format='json')
        force_authenticate(req, user=user or self.cu)
        return view(req, **kw)

    def lead(self, email, industry='Dentistry', **kw):
        return SDRLead.objects.create(company_user=self.cu, email=email, first_name=email.split('@')[0].title(),
                                      full_name=email, company_name='Smile <Co>', company_industry=industry, **kw)

    def template(self, html=HTML, subject='For {first_name}'):
        return SDREmailTemplate.objects.create(company_user=self.cu, name='Spring', subject=subject, html=html)

    def outsider(self):
        return CompanyUser.objects.create(company=Company.objects.create(name='R', email='r@t.local'),
                                          email='o@r.local', full_name='O', role='admin', password_hash='x',
                                          is_active=True)


class RenderTests(Base):
    def test_variables_are_filled_and_lead_values_escaped(self):
        subject, html, text = render(HTML, 'For {first_name}', self.lead('kiran@x.example'), self.campaign, 'https://u/1')
        self.assertEqual(subject, 'For Kiran')
        self.assertIn('About Smile &lt;Co&gt;', html)                    # a lead's value never becomes HTML
        self.assertIn('href="https://u/1"', html)
        self.assertIn('see this (https://acme.example/x)', text)        # the plain text keeps the link
        self.assertNotIn('<p>', text)

    def test_a_template_without_an_unsubscribe_link_gets_the_footer(self):
        self.campaign.postal_address = '1 Main St, Leeds'
        _, html, text = render('<p>Hi {first_name}</p>', '', self.lead('a@x.example'), self.campaign, 'https://u/2')
        self.assertIn('href="https://u/2"', html)
        self.assertIn('1 Main St, Leeds', html)
        self.assertIn('Unsubscribe (https://u/2)', text)
        _, with_link, _ = render(HTML, '', self.lead('b@x.example'), self.campaign, 'https://u/3')
        self.assertEqual(with_link.count('https://u/3'), 1)              # its own link: no second footer

    def test_unknown_variables_are_found(self):
        self.assertEqual(unknown_variables('Hi {first_name} {pain_point}', '{offer} {pain_point}'),
                         ['{offer}', '{pain_point}'])

    def test_html_to_text_drops_styles_and_keeps_lines(self):
        self.assertEqual(html_to_text('<style>p{color:red}</style><p>One</p><p>Two<br/>Three</p>'), 'One\nTwo\nThree')


class TemplateEndpointTests(Base):
    def test_create_list_update_delete(self):
        r = self.call(views.sdr_email_templates, 'post', {'name': ' Spring  offer ', 'subject': 'Hi', 'html': HTML})
        self.assertEqual((r.status_code, r.data['data']['name']), (201, 'Spring offer'))
        tid = r.data['data']['id']
        listed = self.call(views.sdr_email_templates).data
        self.assertEqual([t['id'] for t in listed['data']], [tid])
        self.assertNotIn('html', listed['data'][0])
        self.assertIn('{unsubscribe_url}', listed['variables'])
        r = self.call(views.sdr_email_template_detail, 'put', {'name': 'Autumn', 'html': '<p>x</p>'}, template_id=tid)
        self.assertEqual(SDREmailTemplate.objects.get(pk=tid).name, 'Autumn')
        self.call(views.sdr_email_template_detail, 'delete', template_id=tid)
        self.assertFalse(SDREmailTemplate.objects.exists())

    def test_a_name_is_needed(self):
        self.assertEqual(self.call(views.sdr_email_templates, 'post', {'name': ' ', 'html': 'x'}).status_code, 400)

    def test_another_accounts_template_is_not_found(self):
        t = self.template()
        for method in ('get', 'put', 'delete'):
            r = self.call(views.sdr_email_template_detail, method, {'name': 'X'}, user=self.outsider(), template_id=t.id)
            self.assertEqual(r.status_code, 404, method)

    def test_preview_uses_a_lead_of_the_industry_and_reports_unknown_variables(self):
        self.lead('law@x.example', industry='Law')
        self.lead('kiran@x.example')
        r = self.call(views.sdr_email_template_preview, 'post',
                      {'subject': 'For {first_name}', 'html': HTML + '{offer}', 'industry': 'dentistry'})
        self.assertEqual((r.data['subject'], r.data['lead']['email']), ('For Kiran', 'kiran@x.example'))
        self.assertIn('Hi Kiran', r.data['html'])
        self.assertEqual(r.data['unknown_variables'], ['{offer}'])

    def test_preview_with_no_leads_uses_a_sample(self):
        r = self.call(views.sdr_email_template_preview, 'post', {'html': '<p>Hi {first_name}</p>'})
        self.assertTrue(r.data['lead']['sample'])
        self.assertIn('Hi Alex', r.data['html'])


class StartingASendTests(Base):
    def start(self, **data):
        body = {'template_id': self.template().id, 'campaign_id': self.campaign.id, 'industry': 'Dentistry'}
        body.update(data)
        return self.call(views.sdr_email_sends, 'post', body)

    def test_only_the_industrys_leads_with_an_email_and_the_blocked_are_skipped(self):
        from core.do_not_email import block
        a, b = self.lead('a@x.example'), self.lead('b@x.example', email_bounced=True)
        c = self.lead('c@x.example')
        block(self.company.id, 'c@x.example')
        self.lead('law@x.example', industry='Law')
        SDRLead.objects.create(company_user=self.cu, email='', full_name='No mail', company_industry='Dentistry')
        dry = self.start(dry_run=True)
        self.assertEqual((dry.data['will_send'], dry.data['skipped']), (1, 2))
        self.assertFalse(SDREmailSend.objects.exists())                  # a dry run sends nothing
        r = self.start()
        self.assertEqual(r.status_code, 201, r.data)
        got = dict(SDREmailSendRecipient.objects.values_list('email', 'status'))
        self.assertEqual(got, {'a@x.example': 'queued', 'b@x.example': 'skipped', 'c@x.example': 'skipped'})

    def test_unknown_variables_and_a_campaign_without_a_mailbox_are_refused(self):
        self.lead('a@x.example')
        r = self.start(template_id=self.template(html='<p>{offer}</p>').id)
        self.assertEqual((r.status_code, r.data['code']), (400, 'unknown_variables'))
        self.campaign.smtp_password = ''
        self.campaign.save()
        self.assertEqual(self.start().status_code, 400)

    def test_another_accounts_campaign_is_refused(self):
        from ai_sdr_agent.models import SDRCampaign
        theirs = SDRCampaign.objects.create(company_user=self.outsider(), name='T', smtp_host='h', smtp_username='u',
                                            smtp_password='p')
        self.lead('a@x.example')
        self.assertEqual(self.start(campaign_id=theirs.id).status_code, 400)
        self.assertFalse(SDREmailSend.objects.exists())


class DeliveryTests(Base):
    def make_send(self, emails):
        send = SDREmailSend.objects.create(company_user=self.cu, campaign=self.campaign, industry='Dentistry',
                                           subject='For {first_name}', html=HTML)
        for e in emails:
            SDREmailSendRecipient.objects.create(send=send, lead=self.lead(e), email=e)
        return send

    def deliver(self):
        with mock.patch.object(oa.OutreachAgent, '_send_via_smtp') as smtp:
            tasks.send_email_sends_impl()
        return smtp

    def test_each_lead_gets_its_html_and_text_with_an_unsubscribe_link(self):
        send = self.make_send(['a@x.example', 'b@x.example'])
        smtp = self.deliver()
        self.assertEqual(smtp.call_count, 2)
        kw = smtp.call_args.kwargs
        self.assertIn('/api/sdr/unsubscribe/', kw['unsubscribe_url'])
        self.assertIn(kw['unsubscribe_url'], kw['html'])
        self.assertNotIn('<p>', kw['body'])
        send.refresh_from_db()
        self.assertEqual(send.status, 'done')
        self.assertEqual(set(send.recipients.values_list('status', flat=True)), {'sent'})
        self.assertEqual(self.deliver().call_count, 0)                   # nobody gets it twice

    def test_the_unsubscribe_link_works_without_an_enrollment(self):
        self.make_send(['a@x.example'])
        url = self.deliver().call_args.kwargs['unsubscribe_url']
        claims = oa.read_unsubscribe_token(url.rstrip('/').rsplit('/', 1)[1])
        self.assertEqual(oa.unsubscribe_target(claims)[:2], (self.company.id, 'a@x.example'))

    @override_settings(SDR_MAX_EMAILS_PER_CAMPAIGN_PER_DAY=3, SDR_MAX_EMAILS_PER_CAMPAIGN_PER_CYCLE=25)
    def test_the_mailbox_daily_limit_is_shared_with_the_campaign(self):
        enr = self.enroll(self.make_lead('campaign@x.example'))
        SDROutreachLog.objects.create(enrollment=enr, action_type='email', status='sent', sent_at=timezone.now())
        self.make_send(['a@x.example', 'b@x.example', 'c@x.example'])
        self.assertEqual(self.deliver().call_count, 2)                   # 3 a day, 1 used by the campaign

    def test_a_lead_emailed_today_waits_for_tomorrow(self):
        enr = self.enroll(self.make_lead('a@x.example'))
        SDROutreachLog.objects.create(enrollment=enr, action_type='email', status='sent', sent_at=timezone.now())
        send = self.make_send(['a@x.example'])
        self.assertEqual(self.deliver().call_count, 0)
        self.assertEqual(send.recipients.get().status, 'queued')

    def test_a_bounce_marks_the_lead_and_blocks_the_address(self):
        from core.do_not_email import is_blocked
        send = self.make_send(['gone@x.example'])
        with mock.patch.object(oa.OutreachAgent, '_send_via_smtp', side_effect=oa.PermanentSendError('550 no user')):
            tasks.send_email_sends_impl()
        r = send.recipients.get()
        self.assertEqual(r.status, 'failed')
        self.assertTrue(r.lead.email_bounced)
        self.assertTrue(is_blocked(self.company.id, 'gone@x.example'))

    def test_stop_leaves_the_rest_unsent(self):
        send = self.make_send(['a@x.example', 'b@x.example'])
        r = self.call(views.sdr_email_send_stop, 'post', send_id=send.id)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.deliver().call_count, 0)
        send.refresh_from_db()
        self.assertEqual(send.status, 'stopped')


class HtmlPartTests(Base):
    def smtp_message(self, **kw):
        server = mock.MagicMock()
        server.__enter__.return_value = server
        with mock.patch('smtplib.SMTP', return_value=server), \
                mock.patch.object(oa, 'validate_mail_server', return_value=None):
            oa.OutreachAgent()._send_via_smtp('h', 587, 'u', 'p', False, 'a@b.c', 'Sam', 'to@x.com', 'Hi', 'plain', **kw)
        return email.message_from_string(server.sendmail.call_args.args[2])

    def test_with_html_the_email_is_text_then_html(self):
        msg = self.smtp_message(html='<p>html</p>')
        self.assertEqual([p.get_content_type() for p in msg.get_payload()], ['text/plain', 'text/html'])

    def test_campaign_emails_stay_plain_only(self):
        self.assertEqual([p.get_content_type() for p in self.smtp_message().get_payload()], ['text/plain'])


class ReadyMadeTemplateTests(Base):
    """Ready-made templates (ai_sdr_agent/email_presets.py): ready but for what the sender offers, which they fill in."""

    def test_they_are_offered_with_the_template_list(self):
        presets = self.call(views.sdr_email_templates).data['presets']
        self.assertEqual({p['key'] for p in presets}, {'dental_medical', 'education', 'real_estate'})
        for p in presets:
            self.assertTrue(p['html'].strip() and p['subject'] and p['accent'], p['key'])

    def test_only_their_your_parts_are_left_to_fill_in(self):
        from ai_sdr_agent.email_presets import PRESETS
        for p in PRESETS:
            left = unknown_variables(p['subject'], p['html'])
            self.assertTrue(left, p['key'])
            self.assertTrue(all(x.startswith('[Your ') for x in left), (p['key'], left))   # no unknown {variable}
            self.assertIn('{unsubscribe_url}', p['html'])

    def test_one_left_unfilled_is_not_sent_and_filled_in_it_is(self):
        from ai_sdr_agent.email_presets import PRESETS
        import re
        self.lead('a@x.example')
        preset = PRESETS[0]
        t = self.template(html=preset['html'], subject=preset['subject'])
        body = {'template_id': t.id, 'campaign_id': self.campaign.id, 'industry': 'Dentistry'}
        r = self.call(views.sdr_email_sends, 'post', body)
        self.assertEqual((r.status_code, r.data['code']), (400, 'unknown_variables'))
        self.assertIn('[Your booking link]', r.data['unknown_variables'])
        t.html = re.sub(r'\[Your [^\]]+\]', 'Our clinic software', preset['html'])
        t.save()
        self.assertEqual(self.call(views.sdr_email_sends, 'post', body).status_code, 201)

    def test_a_your_part_is_found_but_an_outlook_comment_is_not(self):
        self.assertEqual(unknown_variables('<!--[if mso]>x<![endif]--> [Your offer] [note]'), ['[Your offer]'])


class OneCompanyTests(Base):
    """Sending to the leads at one company, instead of a whole industry."""

    def start(self, **data):
        body = {'template_id': self.template().id, 'campaign_id': self.campaign.id}
        body.update(data)
        return self.call(views.sdr_email_sends, 'post', body)

    def test_only_that_companys_leads_get_it(self):
        a = SDRLead.objects.create(company_user=self.cu, email='a@smile.example', full_name='A', company_name='Smile Line')
        SDRLead.objects.create(company_user=self.cu, email='b@smile.example', full_name='B', company_name='smile line')
        SDRLead.objects.create(company_user=self.cu, email='c@other.example', full_name='C', company_name='Other Co')
        r = self.start(company='Smile Line')
        self.assertEqual((r.status_code, r.data['will_send']), (201, 2), r.data)
        send = SDREmailSend.objects.get()
        self.assertEqual((send.company, send.industry), ('Smile Line', ''))
        self.assertEqual(set(send.recipients.values_list('email', flat=True)), {'a@smile.example', 'b@smile.example'})

    def test_an_industry_or_a_company_not_both_or_neither(self):
        self.lead('a@x.example')
        self.assertEqual(self.start().status_code, 400)
        self.assertEqual(self.start(industry='Dentistry', company='Smile <Co>').status_code, 400)

    def test_companies_are_searched_with_their_emailable_lead_counts_and_only_mine(self):
        for e in ('a@s.example', 'b@s.example'):
            SDRLead.objects.create(company_user=self.cu, email=e, full_name=e, company_name='Smile Line')
        SDRLead.objects.create(company_user=self.cu, email='', full_name='No mail', company_name='Smile Line')
        SDRLead.objects.create(company_user=self.cu, email='x@o.example', full_name='X', company_name='Other Co')
        SDRLead.objects.create(company_user=self.outsider(), email='t@s.example', full_name='T', company_name='Smile Theirs')
        req = self.rf.get('/x', {'q': 'smile'})
        force_authenticate(req, user=self.cu)
        self.assertEqual(views.sdr_lead_companies(req).data['data'], [{'name': 'Smile Line', 'lead_count': 2}])

    def test_preview_uses_a_lead_at_the_company(self):
        SDRLead.objects.create(company_user=self.cu, email='k@s.example', first_name='Kiran', full_name='Kiran',
                               company_name='Smile Line')
        self.lead('other@x.example')
        r = self.call(views.sdr_email_template_preview, 'post', {'html': '<p>Hi {first_name}</p>', 'company': 'Smile Line'})
        self.assertEqual(r.data['lead']['email'], 'k@s.example')


class EmptyValueTests(Base):
    def test_a_blank_sender_company_leaves_no_dangling_comma(self):
        # "{sender_title}, {sender_company}" with no company read "Developer," (6 Nov 2026).
        self.campaign.sender_title, self.campaign.sender_company = 'Developer', ''
        _, html, _ = render('<p>{sender_title}, {sender_company}</p>{unsubscribe_url}', '', self.lead('a@x.example'),
                            self.campaign, 'u')
        self.assertIn('<p>Developer</p>', html)

    def test_filled_values_keep_their_comma(self):
        self.campaign.sender_title, self.campaign.sender_company = 'CEO', 'Acme'
        _, html, _ = render('<p>{sender_title}, {sender_company}</p>{unsubscribe_url}', '', self.lead('a@x.example'),
                            self.campaign, 'u')
        self.assertIn('<p>CEO, Acme</p>', html)

    def test_the_preview_says_whose_sender_details_it_shows(self):
        r = self.call(views.sdr_email_template_preview, 'post', {'html': '<p>{sender_name}</p>'})
        self.assertEqual(r.data['sender_campaign']['id'], self.campaign.id)


class TemplateNameTests(Base):
    """Two templates called the same could not be told apart when choosing one (6 Nov 2026): "(2)" is added."""

    def test_a_taken_name_gets_a_number(self):
        first = self.call(views.sdr_email_templates, 'post', {'name': 'Dental', 'html': 'x'}).data['data']
        second = self.call(views.sdr_email_templates, 'post', {'name': 'dental', 'html': 'x'}).data['data']
        third = self.call(views.sdr_email_templates, 'post', {'name': 'Dental', 'html': 'x'}).data['data']
        self.assertEqual((first['name'], second['name'], third['name']), ('Dental', 'dental (2)', 'Dental (3)'))

    def test_saving_a_template_under_its_own_name_keeps_it(self):
        t = self.template()
        r = self.call(views.sdr_email_template_detail, 'put', {'name': t.name, 'html': 'y'}, template_id=t.id)
        self.assertEqual(r.data['data']['name'], t.name)
