"""One do-not-email list per company, for every agent that does outreach.

Someone who unsubscribed used to stop one salesperson's AI SDR campaigns only.
A colleague's campaign and any Marketing campaign in the same company kept
emailing them, Marketing kept no list at all, and nothing stopped the address
being added to the next campaign. Now both agents write to and ask one list
(core/do_not_email.py), and an admin can take a wrong entry off it.
"""
import io
from contextlib import contextmanager
from datetime import timedelta
from importlib import import_module
from unittest import mock

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.mail import EmailMultiAlternatives
from django.test import TestCase
from django.utils import timezone

from ai_sdr_agent.agents import outreach_agent as oa
from ai_sdr_agent.models import SDRCampaign, SDRCampaignEnrollment, SDRCampaignStep, SDRLead
from ai_sdr_agent.tests import SDRBase
from api.views import do_not_email as views
from api.views import marketing_agent as marketing_views
from core import do_not_email
from core.models import Company, CompanyModulePurchase, CompanyUser, DoNotEmail
from hr_agent.tests.base import HRTestCase
from marketing_agent.models import (
    Campaign, CampaignContact, CampaignLead, EmailAccount, EmailSendHistory, EmailSequence,
    EmailSequenceStep, EmailTemplate, Lead, Reply, ReplySubSequenceRun,
)

VIC = 'vic@prospect.example'


class TheListTests(TestCase):
    """core/do_not_email.py on its own."""

    def setUp(self):
        self.acme = Company.objects.create(name='Acme', email='acme@test.local')
        self.rival = Company.objects.create(name='Rival', email='rival@test.local')

    def test_an_address_is_blocked_for_its_company_only_however_it_is_typed(self):
        self.assertTrue(do_not_email.block(self.acme, '  Vic@Prospect.Example '))
        self.assertTrue(do_not_email.is_blocked(self.acme, 'VIC@prospect.example'))
        self.assertTrue(do_not_email.is_blocked(self.acme.id, VIC))
        self.assertFalse(do_not_email.is_blocked(self.rival, VIC))
        self.assertFalse(do_not_email.is_blocked(self.acme, 'someone.else@prospect.example'))
        self.assertEqual(DoNotEmail.objects.get().email, VIC)

    def test_listing_twice_keeps_one_row_and_the_first_reason(self):
        do_not_email.block(self.acme, VIC, do_not_email.UNSUBSCRIBED, source='marketing')
        self.assertFalse(do_not_email.block(self.acme, VIC.upper(), do_not_email.BOUNCED, source='ai_sdr'))
        self.assertEqual(DoNotEmail.objects.count(), 1)
        self.assertEqual(do_not_email.reason_for(self.acme, VIC), 'unsubscribed')

    def test_nothing_to_check_is_not_blocked(self):
        for company, email in ((None, VIC), (self.acme, ''), (self.acme, None)):
            self.assertFalse(do_not_email.block(company, email))
            self.assertFalse(do_not_email.is_blocked(company, email))
        self.assertEqual(DoNotEmail.objects.count(), 0)

    def test_several_addresses_are_checked_at_once(self):
        do_not_email.block(self.acme, VIC)
        do_not_email.block(self.rival, 'only.rival@prospect.example')
        found = do_not_email.blocked_among(self.acme, ['VIC@prospect.example', 'only.rival@prospect.example', '', None])
        self.assertEqual(found, {VIC})

    def test_taking_an_address_off(self):
        do_not_email.block(self.acme, VIC)
        do_not_email.block(self.rival, VIC)
        self.assertTrue(do_not_email.unblock(self.acme, 'Vic@prospect.example'))
        self.assertFalse(do_not_email.is_blocked(self.acme, VIC))
        self.assertTrue(do_not_email.is_blocked(self.rival, VIC))           # the other company's entry stays
        self.assertFalse(do_not_email.unblock(self.acme, VIC))               # already off


class TwoSalespeopleTests(SDRBase):
    """AI SDR: the opt-out is the company's, not one login's."""

    def setUp(self):
        super().setUp()
        self.colleague = CompanyUser.objects.create(company=self.company, email='cole@test.local', full_name='Cole',
                                                    role='company_user', password_hash='x', is_active=True)
        self.theirs = self.campaign_for(self.colleague)
        rival = Company.objects.create(name='Rival', email='rival@test.local')
        self.rival_cu = CompanyUser.objects.create(company=rival, email='rhea@test.local', full_name='Rhea',
                                                   role='admin', password_hash='x', is_active=True)
        CompanyModulePurchase.objects.create(company=rival, module_name='ai_sdr_agent', status='active',
                                             is_complimentary=True)
        self.rivals = self.campaign_for(self.rival_cu)

    def campaign_for(self, company_user):
        campaign = SDRCampaign.objects.create(
            company_user=company_user, name=f'{company_user.full_name} outreach', status='active',
            sender_name='Sam', sender_company='Co', postal_address='1 Main St, Town',
            smtp_host='smtp.test', smtp_username='u', smtp_password='p')
        SDRCampaignStep.objects.create(campaign=campaign, step_order=1, delay_days=1, step_type='email',
                                       subject_template='Hello', body_template='Hi there', ai_personalize=False)
        return campaign

    def enrolled(self, campaign, email=VIC):
        lead = SDRLead.objects.create(company_user=campaign.company_user, email=email, first_name='Vic',
                                      full_name='Vic V')
        return SDRCampaignEnrollment.objects.create(campaign=campaign, lead=lead, status='active',
                                                    next_action_at=timezone.now() - timedelta(minutes=1))

    def send(self, enrollment):
        with mock.patch.object(oa.OutreachAgent, '_send_via_smtp') as smtp:
            result = self.agent().process_enrollment(enrollment)
        return result['status'], smtp.called

    def test_unsubscribing_from_one_salesperson_stops_the_colleague_too(self):
        mine, theirs, rivals = self.enrolled(self.campaign), self.enrolled(self.theirs, VIC.upper()), self.enrolled(self.rivals)
        oa.apply_unsubscribe(mine)
        for e in (mine, theirs, rivals):
            e.refresh_from_db()
            e.lead.refresh_from_db()
        self.assertEqual((mine.status, theirs.status), ('unsubscribed', 'unsubscribed'))
        self.assertEqual(theirs.lead.status, 'disqualified')
        self.assertTrue(oa.is_email_suppressed(self.colleague, VIC))
        # another company's outreach to the same person is its own business
        self.assertEqual(rivals.status, 'active')
        self.assertFalse(oa.is_email_suppressed(self.rival_cu, VIC))
        self.assertEqual(self.send(rivals), ('sent', True))

    def test_the_unsubscribe_link_puts_the_address_on_the_list(self):
        mine = self.enrolled(self.campaign)
        self.client.post('/api/sdr/unsubscribe/' + oa.make_unsubscribe_token(mine.id) + '/')
        entry = DoNotEmail.objects.get(company=self.company)
        self.assertEqual((entry.email, entry.reason, entry.source), (VIC, 'unsubscribed', 'ai_sdr'))

    def test_a_colleagues_campaign_does_not_send_to_an_address_that_bounced(self):
        mine, theirs = self.enrolled(self.campaign), self.enrolled(self.theirs)
        oa.mark_bounced(mine, '550 no such user')
        self.assertEqual(do_not_email.reason_for(self.company, VIC), 'bounced')
        self.assertEqual(self.send(theirs), ('suppressed', False))
        theirs.refresh_from_db()
        self.assertEqual(theirs.status, 'bounced')           # said as what it is, not 'unsubscribed'

    def test_a_listed_address_is_not_sent_to_even_with_no_sdr_history(self):
        do_not_email.block(self.company, VIC, source='marketing')        # asked Marketing to stop
        theirs = self.enrolled(self.theirs)
        self.assertEqual(self.send(theirs), ('suppressed', False))
        theirs.refresh_from_db()
        self.assertEqual(theirs.status, 'unsubscribed')

    def test_taken_off_the_list_the_address_can_be_emailed_again(self):
        mine = self.enrolled(self.campaign)
        oa.mark_bounced(mine, '550 mailbox full')
        do_not_email.unblock(self.company, VIC)
        mine.lead.refresh_from_db()
        self.assertFalse(mine.lead.email_bounced)                         # AI SDR's own mark goes too
        again = SDRCampaignEnrollment.objects.create(campaign=self.theirs, lead=mine.lead, status='active',
                                                     next_action_at=timezone.now() - timedelta(minutes=1))
        self.assertEqual(self.send(again), ('sent', True))

    def test_what_sdr_already_knew_is_copied_onto_the_list(self):
        backfill = import_module('ai_sdr_agent.migrations.0026_backfill_do_not_email').backfill
        gone = self.enrolled(self.campaign, 'Gone@Prospect.example')
        SDRCampaignEnrollment.objects.filter(pk=gone.pk).update(status='unsubscribed')
        dead = self.enrolled(self.theirs, 'dead@prospect.example')
        SDRLead.objects.filter(pk=dead.lead_id).update(email_bounced=True)
        both = self.enrolled(self.rivals, 'both@prospect.example')
        SDRCampaignEnrollment.objects.filter(pk=both.pk).update(status='unsubscribed')
        SDRLead.objects.filter(pk=both.lead_id).update(email_bounced=True)
        self.enrolled(self.campaign, 'fine@prospect.example')

        backfill(apps, None)
        backfill(apps, None)                                               # safe to run twice
        listed = {(e.company_id, e.email): e.reason for e in DoNotEmail.objects.all()}
        self.assertEqual(listed, {
            (self.company.id, 'gone@prospect.example'): 'unsubscribed',
            (self.company.id, 'dead@prospect.example'): 'bounced',
            (self.rival_cu.company_id, 'both@prospect.example'): 'unsubscribed',
        })


class MarketingBase(TestCase):
    factory = HRTestCase.factory
    call = HRTestCase.call          # call a view as a dashboard login

    def setUp(self):
        self.company = Company.objects.create(name='Acme', email='acme@test.local')
        CompanyModulePurchase.objects.create(company=self.company, module_name='marketing_agent', status='active',
                                             is_complimentary=True)
        self.mia = CompanyUser.objects.create(company=self.company, email='mia@acme.example', full_name='Mia M',
                                              role='admin', password_hash='x', is_active=True)
        # A campaign belongs to the user with the login's email.
        self.owner = get_user_model().objects.create_user(username='mia', password='x', email='mia@acme.example')
        self.campaign = Campaign.objects.create(name='Spring', owner=self.owner, status='active')
        EmailAccount.objects.create(owner=self.owner, name='Main', email='mia@acme.example', smtp_host='smtp.test',
                                    smtp_port=587, smtp_username='u', smtp_password='p', is_active=True,
                                    is_default=True)
        self.template = EmailTemplate.objects.create(campaign=self.campaign, name='Hello', subject='Hello',
                                                     html_content='<p>Hi</p>')
        self.sequence = self.sequence_of('Main', steps=2)

    def sequence_of(self, name, steps=1, **fields):
        sequence = EmailSequence.objects.create(name=name, campaign=self.campaign, is_active=True, **fields)
        for order in range(1, steps + 1):
            EmailSequenceStep.objects.create(sequence=sequence, template=self.template, step_order=order,
                                             delay_days=0 if order == 1 else 2)
        return sequence

    def follow_up(self, interest):
        return self.sequence_of(f'After a {interest} reply', steps=2, parent_sequence=self.sequence,
                                is_sub_sequence=True, interest_level=interest)

    def lead(self, email=VIC):
        lead = Lead.objects.create(email=email, owner=self.owner, first_name='Vic', last_name='V')
        CampaignLead.objects.create(campaign=self.campaign, lead=lead)
        return lead

    @contextmanager
    def sending(self):
        """Yields the list of addresses actually mailed."""
        sent = []
        from marketing_agent.services.email_service import EmailService
        with mock.patch.object(EmailMultiAlternatives, 'send', autospec=True,
                               side_effect=lambda message, *a, **k: sent.extend(message.to) or 1), \
                mock.patch.object(EmailService, '_append_to_imap_sent'):
            yield sent

    def run_sender(self):
        from marketing_agent.management.commands.send_sequence_emails import Command
        with self.sending() as sent:
            Command(stdout=io.StringIO(), stderr=io.StringIO())._run(dry_run=False)
        return sent

    def reply(self, lead, text='Please unsubscribe me', read_as='unsubscribe'):
        from marketing_agent.services.reply_processor import process_reply_directly
        CampaignContact.objects.get_or_create(campaign=self.campaign, lead=lead, sequence=self.sequence,
                                              defaults={'current_step': 1, 'last_sent_at': timezone.now()})
        with mock.patch('marketing_agent.services.reply_processor.ReplyAnalyzer') as analyzer:
            analyzer.return_value.analyze_reply.return_value = {'interest_level': read_as, 'analysis': 'test'}
            return process_reply_directly(self.campaign, lead, 'Re: Hello', text)


class MarketingSendTests(MarketingBase):

    def send(self, lead, **kwargs):
        from marketing_agent.services.email_service import EmailService
        with self.sending() as sent:
            result = EmailService().send_email(self.template, lead, self.campaign, **kwargs)
        return result, sent

    def test_a_listed_address_is_not_emailed(self):
        vic, ann = self.lead(), self.lead('ann@prospect.example')
        do_not_email.block(self.company, VIC.upper(), source='ai_sdr')     # opted out of AI SDR
        result, sent = self.send(vic)
        self.assertEqual((result['success'], result.get('blocked'), sent), (False, True, []))
        self.assertFalse(EmailSendHistory.objects.filter(lead=vic).exists())    # nothing left to retry
        result, sent = self.send(ann)
        self.assertEqual((result['success'], sent), (True, ['ann@prospect.example']))

    def test_a_test_send_still_reaches_the_person_testing(self):
        do_not_email.block(self.company, VIC)
        do_not_email.block(self.company, 'mia@acme.example')
        result, sent = self.send(self.lead(), test_email='mia@acme.example')
        self.assertEqual((result['success'], sent), (True, ['mia@acme.example']))

    def test_another_companys_list_does_not_apply(self):
        other = Company.objects.create(name='Other', email='other@test.local')
        do_not_email.block(other, VIC)
        result, sent = self.send(self.lead())
        self.assertEqual((result['success'], sent), (True, [VIC]))

    def test_a_campaign_with_no_known_company_sends_as_before(self):
        CompanyUser.objects.filter(pk=self.mia.pk).update(email='moved@acme.example')
        do_not_email.block(self.company, VIC)
        result, sent = self.send(self.lead())
        self.assertEqual((result['success'], sent), (True, [VIC]))

    def test_the_sequence_sender_passes_over_a_listed_lead(self):
        self.lead()
        self.lead('ann@prospect.example')
        do_not_email.block(self.company, VIC)
        self.assertEqual(self.run_sender(), ['ann@prospect.example'])
        self.assertEqual(self.run_sender(), [])                             # and does not keep trying


class MarketingReplyTests(MarketingBase):

    def test_a_reply_asking_to_stop_goes_on_the_companys_list(self):
        vic = self.lead()
        self.assertTrue(self.reply(vic)['success'])
        entry = DoNotEmail.objects.get(company=self.company)
        self.assertEqual((entry.email, entry.reason, entry.source), (VIC, 'unsubscribed', 'marketing'))
        self.assertIn('Spring', entry.note)

    def test_other_replies_do_not(self):
        self.reply(self.lead(), 'Not for us, thanks', read_as='negative')
        self.assertFalse(DoNotEmail.objects.exists())

    def test_it_stops_their_other_campaigns_and_ai_sdr(self):
        vic = self.lead()
        self.reply(vic)
        other = Campaign.objects.create(name='Summer', owner=self.owner, status='active')
        from marketing_agent.services.email_service import EmailService
        with self.sending() as sent:
            result = EmailService().send_email(self.template, vic, other)
        self.assertEqual((result.get('blocked'), sent), (True, []))
        self.assertTrue(oa.is_email_suppressed(self.mia, VIC))

    def test_the_any_reply_follow_up_does_not_start_for_them(self):
        self.follow_up('any')
        vic, ann = self.lead(), self.lead('ann@prospect.example')
        self.reply(vic)
        self.assertFalse(ReplySubSequenceRun.objects.filter(lead=vic).exists())
        self.reply(ann, 'Tell me more', read_as='neutral')                  # everyone else still gets it
        self.assertTrue(ReplySubSequenceRun.objects.filter(lead=ann).exists())

    def test_the_companys_own_unsubscribe_confirmation_goes_out_once(self):
        confirmation = self.follow_up('unsubscribe')                        # two steps set up
        vic = self.lead()
        self.reply(vic)
        run = ReplySubSequenceRun.objects.get(lead=vic)
        self.assertEqual(run.sub_sequence, confirmation)
        self.assertEqual(self.run_sender(), [VIC])
        run.refresh_from_db()
        self.assertTrue(run.completed)                                      # the second step never goes
        ReplySubSequenceRun.objects.filter(pk=run.pk).update(last_sent_at=timezone.now() - timedelta(days=30))
        self.assertEqual(self.run_sender(), [])

    def test_a_follow_up_already_under_way_is_dropped_once_they_are_listed(self):
        interested = self.follow_up('positive')
        vic = self.lead()
        self.reply(vic, 'Sounds good', read_as='positive')
        run = ReplySubSequenceRun.objects.get(lead=vic)
        self.assertEqual(run.sub_sequence, interested)
        do_not_email.block(self.company, VIC, source='ai_sdr')
        self.assertEqual(self.run_sender(), [])
        run.refresh_from_db()
        self.assertTrue(run.cancelled)


class MarketingAddLeadTests(MarketingBase):
    """Adding a lead by hand or from a file."""

    def add(self, email):
        return self.call(marketing_views.add_campaign_lead, self.mia, {'email': email, 'first_name': 'Vic'},
                         campaign_id=self.campaign.id)

    def test_a_listed_address_cannot_be_added_to_a_campaign(self):
        do_not_email.block(self.company, VIC)
        code, body = self.add('Vic@Prospect.example')
        self.assertEqual((code, body.get('error')), (400, 'do_not_email'))
        self.assertIn('asked not to be emailed', body['message'])
        self.assertFalse(Lead.objects.filter(email=VIC).exists())
        code, _ = self.add('ann@prospect.example')
        self.assertEqual(code, 201)

    def test_the_message_says_when_it_bounced(self):
        do_not_email.block(self.company, VIC, do_not_email.BOUNCED)
        self.assertIn('bounced', self.add(VIC)[1]['message'])

    def test_a_file_upload_leaves_listed_addresses_out_and_says_so(self):
        do_not_email.block(self.company, VIC)
        csv = b'email,first_name,last_name\nVIC@prospect.example,Vic,V\nann@prospect.example,Ann,A\n'
        result, error = marketing_views._upload_leads_from_file(self.campaign, self.owner,
                                                                 SimpleUploadedFile('leads.csv', csv))
        self.assertIsNone(error)
        self.assertEqual((result['created_count'], result['rejected_reasons']['do_not_email']), (1, 1))
        self.assertEqual(result['rejected_rows'][0]['value'], VIC)
        self.assertIn('do-not-email', result['rejected_rows'][0]['reason'])
        self.assertEqual(list(self.campaign.leads.values_list('email', flat=True)), ['ann@prospect.example'])


class TheSettingsPageTests(HRTestCase):
    """company/do-not-email: see it, add by hand, and an admin can take one off."""

    def page(self, actor=None):
        code, body = self.call(views.company_do_not_email, actor or self.member, method='get')
        self.assertEqual(code, 200, body)
        return body['data']

    def test_each_company_sees_its_own_list(self):
        do_not_email.block(self.company, VIC, source='marketing', note='Asked to stop')
        do_not_email.block(self.rival, 'theirs@prospect.example')
        page = self.page()
        self.assertEqual([e['email'] for e in page['entries']], [VIC])
        self.assertEqual((page['entries'][0]['source_label'], page['entries'][0]['reason_label'], page['total']),
                         ('Marketing', 'Unsubscribed', 1))
        self.assertFalse(page['can_remove'])
        self.assertTrue(self.page(self.admin)['can_remove'])

    def test_anyone_in_the_company_can_add_an_address_by_hand(self):
        code, body = self.call(views.company_do_not_email, self.member, {'email': ' Vic@Prospect.example ',
                                                                         'note': 'Phoned to ask'})
        self.assertEqual((code, body['added']), (201, True))
        entry = DoNotEmail.objects.get(company=self.company)
        self.assertEqual((entry.email, entry.reason, entry.source, entry.note, entry.added_by),
                         (VIC, 'manual', 'manual', 'Phoned to ask', self.member))
        self.assertEqual(body['data']['entries'][0]['added_by'], 'Mo Member')
        code, body = self.call(views.company_do_not_email, self.member, {'email': VIC})
        self.assertEqual((code, body['added'], DoNotEmail.objects.count()), (200, False, 1))

    def test_something_that_is_not_an_address_is_refused(self):
        for bad in ('', 'vic', 'vic@', 'a@b.example, c@d.example'):
            code, _ = self.call(views.company_do_not_email, self.member, {'email': bad})
            self.assertEqual(code, 400, bad)
        self.assertFalse(DoNotEmail.objects.exists())

    def test_only_an_admin_can_take_an_address_off(self):
        do_not_email.block(self.company, VIC)
        entry = DoNotEmail.objects.get()
        code, _ = self.call(views.company_do_not_email_entry, self.member, method='delete', entry_id=entry.id)
        self.assertEqual((code, do_not_email.is_blocked(self.company, VIC)), (403, True))
        code, body = self.call(views.company_do_not_email_entry, self.admin, method='delete', entry_id=entry.id)
        self.assertEqual((code, body['data']['entries'], do_not_email.is_blocked(self.company, VIC)), (200, [], False))

    def test_an_admin_cannot_touch_another_companys_list(self):
        do_not_email.block(self.company, VIC)
        entry = DoNotEmail.objects.get()
        code, _ = self.call(views.company_do_not_email_entry, self.rival_admin, method='delete', entry_id=entry.id)
        self.assertEqual((code, do_not_email.is_blocked(self.company, VIC)), (404, True))

    def test_the_list_can_be_searched(self):
        for email in (VIC, 'ann@prospect.example', 'ann@elsewhere.example'):
            do_not_email.block(self.company, email)
        request = self.factory.get('/', {'q': 'PROSPECT'})
        from rest_framework.test import force_authenticate
        force_authenticate(request, user=self.member)
        response = views.company_do_not_email(request)
        self.assertEqual(sorted(e['email'] for e in response.data['data']['entries']), ['ann@prospect.example', VIC])
        self.assertEqual(response.data['data']['total'], 3)

    def test_the_address_works_over_http_and_needs_a_login(self):
        self.assertIn(self.client.get('/api/company/do-not-email').status_code, (401, 403))
        code, body = self.send(self.http(self.admin), 'post', '/api/company/do-not-email', {'email': VIC})
        self.assertEqual(code, 201, body)
        entry = DoNotEmail.objects.get()
        code, _ = self.send(self.http(self.admin), 'delete', f'/api/company/do-not-email/{entry.id}')
        self.assertEqual((code, DoNotEmail.objects.count()), (200, 0))
