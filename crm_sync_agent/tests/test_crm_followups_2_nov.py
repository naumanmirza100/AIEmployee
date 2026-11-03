"""CRM Sync, 2 Nov 2026: Frontline's customers and tickets go through it (#3); Salesforce signs in with an External
Client App's key and secret (#1, Salesforce's username-password flow is being retired); Pipedrive's activity times
are UTC (#1). No test reaches a CRM: requests are replaced."""
import json
from datetime import datetime, timedelta, timezone as dt_timezone
from unittest import mock
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model

from ai_sdr_agent import tests_crm_sync as base
from crm_sync_agent.agents.crm_sync_agent import CRMSyncAgent
from crm_sync_agent.connectors.base import CRMError, refusal
from crm_sync_agent.connectors.pipedrive import PipedriveConnector, _pd_date, _pd_time
from crm_sync_agent.connectors.salesforce import SalesforceConnector, _host
from crm_sync_agent.models import CRMContactMapping, CRMIntegration, CRMSyncQueue
from crm_sync_agent.tasks import queue_support
from Frontline_agent.models import Contact, Ticket
from hr_agent.tests.base import HRTestCase


def answer(status, data=None):
    r = mock.Mock(status_code=status, text=json.dumps(data or {}))
    r.json.return_value = data or {}
    return r


class SupportBase(base.CRMBase):

    def setUp(self):
        super().setUp()
        self.staff = get_user_model().objects.create_user(username='nadia-staff', email='nadia.staff@margalla.test')
        self.customer = Contact.objects.create(company=self.company, email='kiran.shah@shahtraders.test',
                                               name='Kiran Shah', phone='+92 300 1112233')

    def ticket(self, **fields):
        return Ticket.objects.create(company=self.company, created_by=self.staff, contact=self.customer,
                                     title='Invoice shows the wrong amount', description='We were charged twice.',
                                     priority='high', category='billing', **fields)


class FrontlineGoesThroughCRMSync(SupportBase):

    def test_a_customer_goes_to_the_crm_with_name_and_phone(self):
        item, = [q for q in self.queued(CRMSyncQueue.TYPE_CONTACT) if q.source_type == CRMSyncQueue.SOURCE_FRONTLINE]
        self.assertEqual((item.payload['email'], item.payload['first_name'], item.payload['last_name'],
                          item.payload['phone']), ('kiran.shah@shahtraders.test', 'Kiran', 'Shah', '+92 300 1112233'))
        self.process.assert_called()

    def test_once_in_the_crm_later_saves_send_nothing_more(self):
        CRMSyncQueue.objects.all().delete()
        CRMContactMapping.objects.create(company=self.company, integration=self.crm, crm_contact_id='501',
                                         source_type=CRMContactMapping.SOURCE_FRONTLINE, source_id=self.customer.pk)
        self.customer.name = 'Kiran A. Shah'
        self.customer.save()
        self.assertEqual(self.queued(CRMSyncQueue.TYPE_CONTACT), [])

    def test_a_ticket_is_a_note_when_opened_and_another_when_resolved_each_once(self):
        ticket = self.ticket()
        opened, = [q for q in self.queued(CRMSyncQueue.TYPE_NOTE) if q.source_type == CRMSyncQueue.SOURCE_FRONTLINE_TICKET]
        self.assertIn(f'Support ticket #{ticket.pk} opened: Invoice shows the wrong amount', opened.payload['note_body'])
        self.assertIn('Priority: High · Category: Billing', opened.payload['note_body'])
        CRMSyncQueue.objects.filter(pk=opened.pk).update(status=CRMSyncQueue.STATUS_DONE)
        ticket.status, ticket.resolution = 'resolved', 'Refunded the second charge.'
        ticket.save()
        ticket.save()
        notes = self.queued(CRMSyncQueue.TYPE_NOTE)
        self.assertEqual([q.source_type for q in notes],
                         [CRMSyncQueue.SOURCE_FRONTLINE_TICKET, CRMSyncQueue.SOURCE_FRONTLINE_TICKET_DONE])
        self.assertIn('resolved: Invoice shows the wrong amount\n\nRefunded the second charge.', notes[1].payload['note_body'])

    def test_a_ticket_with_no_customer_sends_nothing(self):
        CRMSyncQueue.objects.all().delete()
        Ticket.objects.create(company=self.company, created_by=self.staff, title='Printer jam', description='-')
        self.assertEqual(list(CRMSyncQueue.objects.all()), [])

    def test_with_support_switched_off_nothing_goes(self):
        CRMSyncQueue.objects.all().delete()
        CRMIntegration.objects.filter(pk=self.crm.pk).update(sync_support=False)
        self.ticket()
        Contact.objects.create(company=self.company, email='new@buyer.test', name='Ali Raza')
        self.assertEqual(list(CRMSyncQueue.objects.all()), [])

    def test_without_crm_sync_bought_nothing_goes(self):
        CRMSyncQueue.objects.all().delete()
        self.subscription.delete()
        self.ticket()
        self.assertEqual(list(CRMSyncQueue.objects.all()), [])

    def test_the_note_is_filed_on_the_customer_found_or_made_and_the_link_kept(self):
        ticket = self.ticket()
        connector = mock.Mock()
        connector.find_or_create_contact.return_value = '777'
        connector.log_note.return_value = 'n1'
        agent = CRMSyncAgent(self.company)
        item = next(q for q in self.queued(CRMSyncQueue.TYPE_NOTE) if q.source_id == ticket.pk)
        self.assertEqual(agent._dispatch(connector, item), 'n1')
        email, details = connector.find_or_create_contact.call_args[0][:2]
        self.assertEqual((email, details['first_name'], details['last_name']), ('kiran.shah@shahtraders.test', 'Kiran', 'Shah'))
        connector.log_note.assert_called_with(crm_contact_id='777', body=item.payload['note_body'])
        self.assertTrue(CRMContactMapping.objects.filter(source_type=CRMContactMapping.SOURCE_FRONTLINE,
                                                         source_id=self.customer.pk, crm_contact_id='777').exists())

    def test_sync_everything_takes_frontlines_customers_and_last_months_tickets(self):
        self.ticket()
        old = self.ticket()
        Ticket.objects.filter(pk=old.pk).update(created_at=old.created_at - timedelta(days=60))
        counts = queue_support(CRMSyncAgent(self.company), self.company)
        self.assertEqual((counts['support_customers'], counts['support_tickets']), (1, 1))


class FrontlinesOlderHubSpotLink(SupportBase):
    call = HRTestCase.call
    factory = HRTestCase.factory

    def setUp(self):
        super().setUp()
        from Frontline_agent.crm.hubspot import encrypt_access_token
        self.company.hubspot_config = {'enabled': True, 'access_token': encrypt_access_token('pat-synthetic-old')}
        self.company.save(update_fields=['hubspot_config'])

    def test_it_stands_aside_when_crm_sync_carries_support(self):
        with mock.patch('Frontline_agent.tasks.sync_contact_to_hubspot.delay') as old_link:
            with self.captureOnCommitCallbacks(execute=True):
                Contact.objects.create(company=self.company, email='a@buyer.test', name='Sana Malik')
        old_link.assert_not_called()

    def test_without_crm_sync_it_keeps_working(self):
        self.subscription.delete()
        with mock.patch('Frontline_agent.tasks.sync_contact_to_hubspot.delay') as old_link:
            with self.captureOnCommitCallbacks(execute=True):
                Contact.objects.create(company=self.company, email='b@buyer.test', name='Bilal Ahmed')
        old_link.assert_called_once()

    def test_it_fills_only_what_hubspot_has_empty(self):
        from Frontline_agent.crm.hubspot import HubSpotClient
        client = HubSpotClient(access_token='pat-synthetic-old')
        found = {'id': '42', 'properties': {'email': 'c@buyer.test', 'firstname': 'Hira', 'lastname': '', 'phone': ''}}
        with mock.patch.object(client, 'find_contact_by_email', return_value=found), \
                mock.patch.object(client, '_patch') as patch:
            client.upsert_contact('c@buyer.test', name='Someone Else', phone='+92 321 0000000')
        patch.assert_called_once_with('/crm/v3/objects/contacts/42',
                                      json={'properties': {'lastname': 'Else', 'phone': '+92 321 0000000'}})

    def test_it_is_not_switched_on_again_but_can_be_switched_off(self):
        from api.views import frontline_agent as views
        call = self.call
        self.cu.role = 'admin'
        self.cu.save(update_fields=['role'])
        self.company.hubspot_config = {'enabled': False}
        self.company.save(update_fields=['hubspot_config'])
        code, body = call(views.hubspot_update_config, self.cu, {'enabled': True, 'access_token': 'pat-x'}, method='patch')
        self.assertEqual(code, 400)
        self.assertIn('CRM Sync', body['message'])
        code, _ = call(views.hubspot_update_config, self.cu, {'enabled': False}, method='patch')
        self.assertEqual(code, 200)


class SalesforceSignsInWithAnApp(base.CRMBase):

    CREDS = {'instance_url': 'https://acme-dev.lightning.force.com/lightning/page/home',
             'client_id': '3MVG-synthetic', 'client_secret': 'synthetic-secret'}

    def test_the_host_is_the_my_domain_whatever_was_pasted(self):
        self.assertEqual(_host(self.CREDS['instance_url']), 'acme-dev.my.salesforce.com')
        self.assertEqual(_host('acme-dev.my.salesforce.com/'), 'acme-dev.my.salesforce.com')
        self.assertEqual(_host('test'), 'test.salesforce.com')

    def test_it_uses_the_client_credentials_flow_at_the_my_domain(self):
        token = answer(200, {'access_token': 'at', 'instance_url': 'https://acme-dev.my.salesforce.com'})
        with mock.patch('crm_sync_agent.connectors.salesforce.requests.post', return_value=token) as post, \
                mock.patch('crm_sync_agent.connectors.salesforce.requests.request', return_value=answer(200, {})):
            self.assertIsNone(SalesforceConnector(self.CREDS).check())
        url, = post.call_args[0]
        self.assertEqual(url, 'https://acme-dev.my.salesforce.com/services/oauth2/token')
        self.assertEqual(post.call_args[1]['data']['grant_type'], 'client_credentials')

    def test_it_says_which_part_of_the_salesforce_set_up_is_missing(self):
        for reply, words in (({'error': 'invalid_client_id', 'error_description': 'client identifier invalid'}, 'key and secret'),
                             ({'error': 'invalid_grant', 'error_description': 'no client credentials user enabled'}, 'Run As'),
                             ({'error': 'unsupported_grant_type'}, 'Enable Client Credentials Flow')):
            with mock.patch('crm_sync_agent.connectors.salesforce.requests.post', return_value=answer(400, reply)):
                said = SalesforceConnector(self.CREDS).check()
            self.assertIn(words, said)
            self.assertNotIn('synthetic-secret', said)

    def test_a_plan_without_api_access_is_named(self):
        token = answer(200, {'access_token': 'at', 'instance_url': 'https://acme-dev.my.salesforce.com'})
        refused = answer(403, [{'errorCode': 'API_DISABLED_FOR_ORG', 'message': 'API is not enabled for this Organization'}])
        refused.text = '[{"errorCode":"API_DISABLED_FOR_ORG"}]'
        with mock.patch('crm_sync_agent.connectors.salesforce.requests.post', return_value=token), \
                mock.patch('crm_sync_agent.connectors.salesforce.requests.request', return_value=refused):
            self.assertIn('no API access', SalesforceConnector(self.CREDS).check())

    def test_a_connection_saved_the_old_way_still_signs_in_the_old_way_until_given_a_my_domain(self):
        old = {'client_id': 'c', 'client_secret': 's', 'username': 'u@x.test', 'password': 'p', 'security_token': 't'}
        token = answer(200, {'access_token': 'at', 'instance_url': 'https://x.my.salesforce.com'})
        with mock.patch('crm_sync_agent.connectors.salesforce.requests.post', return_value=token) as post, \
                mock.patch('crm_sync_agent.connectors.salesforce.requests.request', return_value=answer(200, {})):
            SalesforceConnector(old).check()
            self.assertEqual(post.call_args[1]['data']['grant_type'], 'password')
            SalesforceConnector({**old, **self.CREDS}).check()
            self.assertEqual(post.call_args[1]['data']['grant_type'], 'client_credentials')

    def test_the_my_domain_is_shown_and_the_secret_is_not(self):
        crm = CRMIntegration(company=self.company, provider='salesforce')
        crm.set_credentials({'instance_url': 'acme-dev.my.salesforce.com', 'client_id': '3MVG-synthetic-key-0123456789',
                             'client_secret': 'synthetic-secret-0123456789'})
        shown = crm.credentials_preview()
        self.assertEqual(shown['instance_url'], 'acme-dev.my.salesforce.com')
        self.assertEqual(shown['client_secret'], '********')
        self.assertNotIn('synthetic-key', shown['client_id'])

    def test_an_email_goes_without_the_type_field_some_plans_hide(self):
        token = answer(200, {'access_token': 'at', 'instance_url': 'https://acme-dev.my.salesforce.com'})
        refused = answer(400, [{'errorCode': 'INVALID_FIELD'}])
        refused.text = "No such column 'TaskSubtype' on sobject of type Task"
        with mock.patch('crm_sync_agent.connectors.salesforce.requests.post', return_value=token),                 mock.patch('crm_sync_agent.connectors.salesforce.requests.request',
                           side_effect=[refused, answer(201, {'id': '00T1'})]) as req:
            self.assertEqual(SalesforceConnector(self.CREDS).log_email_activity('003X', 'Prices', 'Hello', None), '00T1')
        first, second = (call[1]['json'] for call in req.call_args_list)
        self.assertNotIn('Type', first)
        self.assertEqual(first['TaskSubtype'], 'Email')
        self.assertNotIn('TaskSubtype', second)

    def test_a_reason_overrides_the_status_code_words(self):
        self.assertEqual(refusal('Salesforce', CRMError('x', status_code=401, reason='Because.')), 'Because.')


class PipedriveTimesAreUTC(base.CRMBase):

    def test_a_call_at_three_in_karachi_is_ten_utc(self):
        at = datetime(2030, 11, 4, 15, 0, tzinfo=ZoneInfo('Asia/Karachi'))
        self.assertEqual((_pd_date(at), _pd_time(at)), ('2030-11-04', '10:00'))
        late = datetime(2030, 11, 4, 2, 30, tzinfo=ZoneInfo('Asia/Karachi'))
        self.assertEqual((_pd_date(late), _pd_time(late)), ('2030-11-03', '21:30'))

    def test_a_meeting_is_sent_with_utc_time(self):
        at = datetime(2030, 11, 4, 15, 0, tzinfo=ZoneInfo('Asia/Karachi'))
        with mock.patch('crm_sync_agent.connectors.pipedrive.requests.request',
                        return_value=answer(201, {'success': True, 'data': {'id': 9}})) as req:
            PipedriveConnector('synthetic').log_meeting('5', 'Call', at, at + timedelta(minutes=30))
        sent = req.call_args[1]['json']
        self.assertEqual((sent['due_date'], sent['due_time'], sent['duration'], sent['done']),
                         ('2030-11-04', '10:00', '00:30', 0))


class MarketingRepliesWhenSwitchedOn(base.CRMBase):
    """#2: the people who reply to a campaign, with their reply. Off until switched on."""

    def setUp(self):
        super().setUp()
        from marketing_agent.models import Campaign, CampaignContact, EmailSendHistory, Lead
        self.owner = get_user_model().objects.create_user(username='adeel', email='adeel@margalla.test')
        self.cu.login_user = self.owner
        self.cu.save(update_fields=['login_user'])
        self.campaign = Campaign.objects.create(name='Spring prices', owner=self.owner)
        self.mlead = Lead.objects.create(owner=self.owner, email='Usman.Tariq@tariqfoods.test', first_name='Usman',
                                         last_name='Tariq', company='Tariq Foods', job_title='Owner')
        self.contact = CampaignContact.objects.create(campaign=self.campaign, lead=self.mlead)
        self.sent = EmailSendHistory.objects.create(campaign=self.campaign, lead=self.mlead, subject='Our spring prices',
                                                    recipient_email=self.mlead.email, status='sent')
        CRMSyncQueue.objects.all().delete()

    def reply(self, interest='positive', text='Yes, send me the price list.'):
        from marketing_agent.models import Reply
        return Reply.objects.create(contact=self.contact, campaign=self.campaign, lead=self.mlead, reply_subject='Re: Our spring prices',
                                    reply_content=text, interest_level=interest, triggering_email=self.sent)

    def switch_on(self):
        CRMIntegration.objects.filter(pk=self.crm.pk).update(sync_marketing=True)

    def test_off_until_switched_on(self):
        self.assertFalse(CRMIntegration.objects.get(pk=self.crm.pk).sync_marketing)
        self.reply()
        self.assertEqual(list(CRMSyncQueue.objects.all()), [])

    def test_a_reply_brings_the_person_and_the_reply_with_its_campaign(self):
        self.switch_on()
        reply = self.reply()
        contact, = self.queued(CRMSyncQueue.TYPE_CONTACT)
        email, = self.queued(CRMSyncQueue.TYPE_EMAIL)
        self.assertEqual((contact.source_type, contact.payload['email'], contact.payload['company'], contact.payload['job_title']),
                         (CRMSyncQueue.SOURCE_MARKETING_LEAD, 'usman.tariq@tariqfoods.test', 'Tariq Foods', 'Owner'))
        self.assertEqual((email.source_type, email.source_id, email.payload['direction']),
                         (CRMSyncQueue.SOURCE_MARKETING_REPLY, reply.pk, 'INBOUND'))
        self.assertIn('Yes, send me the price list.', email.payload['body'])
        self.assertIn('Marketing campaign "Spring prices", email "Our spring prices"', email.payload['body'])
        self.assertIn('Positive/Interested', email.payload['body'])

    def test_unsubscribe_requests_never_go(self):
        self.switch_on()
        self.reply(interest='unsubscribe', text='Remove me please')
        self.assertEqual(list(CRMSyncQueue.objects.all()), [])

    def test_the_reply_is_filed_on_the_person_found_or_made(self):
        self.switch_on()
        self.reply()
        connector = mock.Mock()
        connector.find_or_create_contact.return_value = '88'
        connector.log_email_activity.return_value = 'e1'
        item, = self.queued(CRMSyncQueue.TYPE_EMAIL)
        self.assertEqual(CRMSyncAgent(self.company)._dispatch(connector, item), 'e1')
        details = connector.find_or_create_contact.call_args[0][1]
        self.assertEqual((details['first_name'], details['last_name'], details['company']), ('Usman', 'Tariq', 'Tariq Foods'))
        self.assertTrue(CRMContactMapping.objects.filter(source_type=CRMContactMapping.SOURCE_MARKETING_LEAD,
                                                         source_id=self.mlead.pk, crm_contact_id='88').exists())

    def test_sync_everything_takes_last_months_replies_only_when_on(self):
        from crm_sync_agent.tasks import queue_marketing
        self.reply()
        self.assertEqual(queue_marketing(CRMSyncAgent(self.company), self.company)['marketing_replies'], 0)
        self.switch_on()
        self.assertEqual(queue_marketing(CRMSyncAgent(self.company), self.company)['marketing_replies'], 1)


class DealsWhenSwitchedOn(base.CRMBase):
    """#5: off until a pipeline and stage are picked; one deal per person, when a call is booked."""
    call = HRTestCase.call
    factory = HRTestCase.factory

    PIPES = {'results': [{'id': 'default', 'label': 'Sales Pipeline', 'stages': [
        {'id': 'qualified', 'label': 'Qualified to buy', 'displayOrder': 1},
        {'id': 'appt', 'label': 'Appointment scheduled', 'displayOrder': 0}]}]}

    def setUp(self):
        super().setUp()
        self.cu.role = 'admin'
        self.cu.save(update_fields=['role'])
        CRMSyncQueue.objects.all().delete()

    def book(self):
        from ai_sdr_agent.models import SDRMeeting
        from django.utils import timezone
        return SDRMeeting.objects.create(lead=self.lead, company_user=self.cu, title='Intro call',
                                         scheduled_at=timezone.now() + timedelta(days=2), status='scheduled')

    def choose(self, pipeline='default', stage='appt'):
        from api.views import crm_sync_agent as views
        with mock.patch('crm_sync_agent.connectors.hubspot.requests.request', return_value=answer(200, self.PIPES)):
            return self.call(views.integration_detail, self.cu,
                             {'deal_settings': {'pipeline_id': pipeline, 'stage_id': stage}, 'sync_deals': True},
                             method='patch', integration_id=self.crm.id)

    def test_off_until_switched_on(self):
        self.assertFalse(CRMIntegration.objects.get(pk=self.crm.pk).sync_deals)
        self.book()
        self.assertEqual(self.queued(CRMSyncQueue.TYPE_DEAL), [])

    def test_the_pipelines_are_read_from_the_crm_in_its_order(self):
        from api.views import crm_sync_agent as views
        with mock.patch('crm_sync_agent.connectors.hubspot.requests.request', return_value=answer(200, self.PIPES)):
            code, body = self.call(views.integration_pipelines, self.cu, method='get', integration_id=self.crm.id)
        self.assertEqual(code, 200, body)
        self.assertEqual([s['label'] for s in body['pipelines'][0]['stages']], ['Appointment scheduled', 'Qualified to buy'])

    def test_on_needs_a_stage_the_crm_has_and_keeps_its_names(self):
        from api.views import crm_sync_agent as views
        code, body = self.call(views.integration_detail, self.cu, {'sync_deals': True}, method='patch',
                               integration_id=self.crm.id)
        self.assertEqual(code, 400)
        self.assertIn('Choose the pipeline and stage', body['message'])
        code, body = self.choose(stage='no-such-stage')
        self.assertEqual(code, 400)
        code, body = self.choose()
        self.assertEqual(code, 200, body)
        self.assertEqual((body['sync_deals'], body['deal_settings']['pipeline_label'], body['deal_settings']['stage_label']),
                         (True, 'Sales Pipeline', 'Appointment scheduled'))

    def test_a_booked_call_makes_one_deal_for_the_person(self):
        self.choose()
        self.book()
        self.book()                       # a second call for the same lead: still one deal
        deal, = self.queued(CRMSyncQueue.TYPE_DEAL)
        self.assertEqual((deal.source_type, deal.source_id), (CRMSyncQueue.SOURCE_SDR_LEAD, self.lead.pk))

    def test_the_deal_is_made_in_the_chosen_stage_and_linked(self):
        self.choose()
        self.book()
        deal, = self.queued(CRMSyncQueue.TYPE_DEAL)
        connector = mock.Mock()
        connector.find_or_create_contact.return_value = '301'
        connector.create_deal.return_value = 'd9'
        self.assertEqual(CRMSyncAgent(self.company)._dispatch(connector, deal), 'd9')
        contact, name, pipeline, stage = connector.create_deal.call_args[0]
        self.assertEqual((contact, pipeline, stage), ('301', 'default', 'appt'))
        self.assertTrue(name)
        self.assertEqual(CRMContactMapping.objects.get(source_type=CRMContactMapping.SOURCE_SDR_LEAD,
                                                       source_id=self.lead.pk).crm_deal_id, 'd9')
        self.book()
        self.assertEqual(len(self.queued(CRMSyncQueue.TYPE_DEAL)), 1)       # the person has a deal now

    def test_hubspot_deal_is_linked_to_its_contact(self):
        from crm_sync_agent.connectors.hubspot import HubSpotConnector
        with mock.patch('crm_sync_agent.connectors.hubspot.requests.request',
                        return_value=answer(201, {'id': '555'})) as req:
            self.assertEqual(HubSpotConnector('synthetic').create_deal('301', 'Bob (Acme)', 'default', 'appt'), '555')
        body = req.call_args[1]['json']
        self.assertEqual(body['properties'], {'dealname': 'Bob (Acme)', 'pipeline': 'default', 'dealstage': 'appt'})
        self.assertEqual(body['associations'][0]['to']['id'], '301')

    def test_a_key_without_deal_rights_is_said_on_the_card(self):
        from crm_sync_agent.connectors.base import PermissionMissing
        from crm_sync_agent.connectors.hubspot import HubSpotConnector
        with mock.patch('crm_sync_agent.connectors.hubspot.requests.request', return_value=answer(403, {})):
            with self.assertRaises(PermissionMissing) as caught:
                HubSpotConnector('synthetic').create_deal('301', 'Bob', 'default', 'appt')
        self.assertIn('crm.objects.deals.write', str(caught.exception))


class ChangesFromTheCRM(SupportBase):
    """#4: corrections made in the CRM come back to the linked records. Off until switched on."""

    def setUp(self):
        super().setUp()
        CRMContactMapping.objects.create(company=self.company, integration=self.crm, crm_contact_id='901',
                                         source_type=CRMContactMapping.SOURCE_SDR_LEAD, source_id=self.lead.pk)
        CRMContactMapping.objects.create(company=self.company, integration=self.crm, crm_contact_id='902',
                                         source_type=CRMContactMapping.SOURCE_FRONTLINE, source_id=self.customer.pk)
        CRMIntegration.objects.filter(pk=self.crm.pk).update(sync_back=True)
        self.crm.refresh_from_db()

    def pull(self, rows):
        with mock.patch('crm_sync_agent.connectors.hubspot.HubSpotConnector.changed_contacts', return_value=rows) as asked:
            counts = CRMSyncAgent(self.company).pull_changes(self.crm)
        return counts, asked

    def test_a_correction_in_the_crm_reaches_the_lead_and_the_customer(self):
        counts, _ = self.pull([
            {'id': '901', 'email': 'bob@acme.com', 'first_name': 'Robert', 'last_name': 'Khan', 'phone': '+92 333 1234567',
             'job_title': 'CTO', 'company': 'Acme Ltd'},
            {'id': '902', 'email': 'kiran.shah@shahtraders.test', 'first_name': 'Kiran', 'last_name': 'Shah-Ali',
             'phone': '', 'job_title': '', 'company': ''},
            {'id': '999', 'email': 'stranger@x.test', 'first_name': 'Not', 'last_name': 'Ours', 'phone': '',
             'job_title': '', 'company': ''},
        ])
        self.assertEqual(counts, {'read': 3, 'updated': 2})
        self.lead.refresh_from_db()
        self.assertEqual((self.lead.first_name, self.lead.last_name, self.lead.full_name, self.lead.phone,
                          self.lead.job_title, self.lead.company_name),
                         ('Robert', 'Khan', 'Robert Khan', '+92 333 1234567', 'CTO', 'Acme Ltd'))
        self.customer.refresh_from_db()
        # A field the CRM has empty never empties ours.
        self.assertEqual((self.customer.name, self.customer.phone), ('Kiran Shah-Ali', '+92 300 1112233'))

    def test_copying_back_sends_nothing_to_the_crm(self):
        CRMSyncQueue.objects.all().delete()
        self.pull([{'id': '901', 'email': 'bob@acme.com', 'first_name': 'Robert', 'last_name': '', 'phone': '',
                    'job_title': '', 'company': ''}])
        self.assertEqual(list(CRMSyncQueue.objects.all()), [])

    def test_it_reads_from_a_little_before_the_last_run_and_moves_on(self):
        from django.utils import timezone
        last = timezone.now() - timedelta(minutes=15)
        CRMIntegration.objects.filter(pk=self.crm.pk).update(last_pulled_at=last)
        self.crm.refresh_from_db()
        _, asked = self.pull([])
        self.assertEqual(asked.call_args[0][0], last - CRMSyncAgent.PULL_OVERLAP)
        self.crm.refresh_from_db()
        self.assertGreater(self.crm.last_pulled_at, last)

    def test_the_job_runs_only_for_crms_with_it_on(self):
        from crm_sync_agent.tasks import pull_crm_changes
        with mock.patch('crm_sync_agent.connectors.hubspot.HubSpotConnector.changed_contacts', return_value=[]) as asked:
            self.assertEqual(pull_crm_changes()['integrations'], 1)
            CRMIntegration.objects.filter(pk=self.crm.pk).update(sync_back=False)
            self.assertEqual(pull_crm_changes()['integrations'], 0)
        self.assertEqual(asked.call_count, 1)

    def test_a_refused_key_is_logged_and_the_time_does_not_move(self):
        from crm_sync_agent.models import CRMSyncLog
        from crm_sync_agent.tasks import pull_crm_changes
        with mock.patch('crm_sync_agent.connectors.hubspot.HubSpotConnector.changed_contacts',
                        side_effect=CRMError('HubSpot auth failed (401)', retriable=False, status_code=401)):
            self.assertEqual(pull_crm_changes()['failed'], 1)
        self.crm.refresh_from_db()
        self.assertIsNone(self.crm.last_pulled_at)
        self.assertTrue(CRMSyncLog.objects.filter(operation=CRMSyncLog.OP_PULL, status=CRMSyncLog.STATUS_FAILED).exists())

    def test_only_our_contacts_are_asked_about(self):
        # It read every contact changed in the CRM, the company's own too, and kept ours (3 Nov 2026).
        _, asked = self.pull([])
        self.assertEqual(sorted(asked.call_args[0][1]), ['901', '902'])

    def test_with_no_linked_contacts_the_crm_is_not_asked(self):
        CRMContactMapping.objects.all().delete()
        counts, asked = self.pull([])
        asked.assert_not_called()
        self.assertEqual(counts, {'read': 0, 'updated': 0})

    def test_a_row_for_someone_not_ours_is_never_applied(self):
        counts, _ = self.pull([{'id': '999', 'email': 'stranger@x.test', 'first_name': 'Not', 'last_name': 'Ours',
                                'phone': '+1 555', 'job_title': '', 'company': ''}])
        self.assertEqual(counts['updated'], 0)

    def test_hubspot_is_asked_about_our_ids_changed_since(self):
        from crm_sync_agent.connectors.hubspot import HubSpotConnector
        page = answer(200, {'results': [{'id': '7', 'properties': {
            'email': 'a@b.test', 'firstname': 'Ali', 'lastname': 'Raza', 'phone': None, 'jobtitle': 'Owner',
            'company': 'Raza Co'}}]})
        with mock.patch('crm_sync_agent.connectors.hubspot.requests.request', return_value=page) as req:
            rows = HubSpotConnector('synthetic').changed_contacts(
                datetime(2026, 11, 2, 10, 0, tzinfo=dt_timezone.utc), ['7', '8', 'not-an-id'])
        filters = req.call_args[1]['json']['filterGroups'][0]['filters']
        self.assertEqual((filters[0]['propertyName'], filters[0]['operator'], filters[0]['values']),
                         ('hs_object_id', 'IN', ['7', '8']))
        self.assertEqual(filters[1]['propertyName'], 'lastmodifieddate')
        self.assertEqual(rows, [{'id': '7', 'email': 'a@b.test', 'first_name': 'Ali', 'last_name': 'Raza', 'phone': '',
                                 'job_title': 'Owner', 'company': 'Raza Co'}])

    def test_hubspot_asks_100_ids_at_a_time(self):
        from crm_sync_agent.connectors.hubspot import HubSpotConnector
        with mock.patch('crm_sync_agent.connectors.hubspot.requests.request',
                        return_value=answer(200, {'results': []})) as req:
            HubSpotConnector('synthetic').changed_contacts(datetime(2026, 11, 2, tzinfo=dt_timezone.utc),
                                                           [str(i) for i in range(1, 251)])
        self.assertEqual(req.call_count, 3)

    def test_salesforce_asks_by_id_and_keeps_out_anything_not_an_id(self):
        from crm_sync_agent.connectors.salesforce import SalesforceConnector
        c = SalesforceConnector({'instance_url': 'https://acme.my.salesforce.com', 'client_id': 'x', 'client_secret': 'y'})
        c._access_token, c._instance_url = 'synthetic', 'https://acme.my.salesforce.com'
        with mock.patch.object(SalesforceConnector, '_ensure_token'), \
             mock.patch('crm_sync_agent.connectors.salesforce.requests.request',
                        return_value=answer(200, {'records': []})) as req:
            c.changed_contacts(datetime(2026, 11, 2, tzinfo=dt_timezone.utc),
                               ['003d500000J4gLuAAJ', "x') OR Name LIKE ('%"])
        q = req.call_args[1]['params']['q']
        self.assertIn("WHERE Id IN ('003d500000J4gLuAAJ') AND LastModifiedDate >", q)
        self.assertNotIn('LIKE', q)

    def test_pipedrive_asks_which_of_ours_changed_then_reads_those_whole(self):
        listed = answer(200, {'data': [{'id': 5}]})
        person = answer(200, {'data': {
            'id': 5, 'first_name': 'Sana', 'last_name': 'Malik', 'org_name': 'Malik and Sons', 'job_title': '',
            'email': [{'value': 'old@x.test', 'primary': False}, {'value': 'sana@malik.test', 'primary': True}],
            'phone': [{'value': '+92 300 7654321', 'primary': True}]}})
        with mock.patch('crm_sync_agent.connectors.pipedrive.requests.request', side_effect=[listed, person]) as req:
            rows = PipedriveConnector('synthetic').changed_contacts(
                datetime(2026, 11, 2, 15, 0, tzinfo=ZoneInfo('Asia/Karachi')), ['5', '6'])
        first = req.call_args_list[0]
        self.assertEqual(first[0][1], 'https://api.pipedrive.com/api/v2/persons')
        self.assertEqual((first[1]['params']['ids'], first[1]['params']['updated_since']), ('5,6', '2026-11-02T10:00:00Z'))
        self.assertEqual(req.call_args_list[1][0][1], 'https://api.pipedrive.com/v1/persons/5')
        self.assertEqual((rows[0]['email'], rows[0]['phone'], rows[0]['company']),
                         ('sana@malik.test', '+92 300 7654321', 'Malik and Sons'))
