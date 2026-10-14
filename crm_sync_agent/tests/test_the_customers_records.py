"""A record the customer already has in their CRM is theirs.

Any save of a lead pushed our names, phone, company, job title and lead status
over whatever the CRM held. And an email, meeting or note for a contact we had
no saved link to went through the same 'create or update' call with the email's
own payload, which has no names in it: Salesforce and Pipedrive were sent the
part of the address before the @ as the person's name.

These talk to no CRM. Each connector's HTTP call is replaced by a stand-in that
answers from a script and writes down what it was sent.
"""
from unittest import mock

from django.test import SimpleTestCase, TestCase

from ai_sdr_agent.models import SDRLead
from core.models import Company, CompanyModulePurchase, CompanyUser
from crm_sync_agent.agents.crm_sync_agent import CRMSyncAgent
from crm_sync_agent.connectors import hubspot, pipedrive, salesforce
from crm_sync_agent.connectors.base import CRMError
from crm_sync_agent.models import CRMContactMapping, CRMIntegration, CRMSyncQueue

OURS = {'email': 'bilal@customer.test', 'first_name': 'Bilal', 'last_name': 'Ahmed', 'name': 'Bilal Ahmed',
        'phone': '0300 1112233', 'company': 'Ahmed Traders', 'job_title': 'Owner', 'linkedin_url': '',
        'lead_score': 82, 'lead_status': 'hot', 'source': 'ai_sdr_agent'}


class Answer:
    def __init__(self, body, status=200):
        self._body, self.status_code, self.text = body, status, str(body)

    def json(self):
        return self._body


class FakeCRM:
    """Answers the first scripted (method, part of the address) that matches; {} otherwise."""

    def __init__(self, *script):
        self.script, self.calls = list(script), []

    def __call__(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs.get('json'), kwargs.get('params')))
        for scripted_method, fragment, body in self.script:
            if scripted_method == method and fragment in url:
                return Answer(body)
        return Answer({})

    def writes(self):
        """Every call that changes something, as (method, last part of the address, what was sent)."""
        return [(method, '/'.join(url.rstrip('/').rsplit('/', 2)[-2:]), body)
                for method, url, body, _ in self.calls
                if method in ('POST', 'PATCH', 'PUT') and not url.endswith('/search')]


class HubSpotTests(SimpleTestCase):

    def crm(self, *script):
        fake = FakeCRM(*script)
        patcher = mock.patch.object(hubspot.requests, 'request', fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        return fake, hubspot.HubSpotConnector(access_token='synthetic-token')

    def existing(self, **properties):
        return ('POST', '/contacts/search', {'results': [{'id': '501', 'properties': properties}]})

    def test_a_contact_with_every_field_filled_is_not_written_to_at_all(self):
        fake, connector = self.crm(self.existing(
            email='bilal@customer.test', firstname='Bill', lastname='A.', phone='021 555', company='Ahmed & Sons',
            jobtitle='Managing Director', hs_lead_status='CONNECTED'))
        self.assertEqual(connector.upsert_contact('bilal@customer.test', OURS), '501')
        self.assertEqual(fake.writes(), [])

    def test_only_the_empty_fields_are_filled(self):
        fake, connector = self.crm(self.existing(
            email='bilal@customer.test', firstname='Bill', lastname='A.', phone='', company=None, jobtitle='  '))
        connector.upsert_contact('bilal@customer.test', OURS)
        [(method, where, sent)] = fake.writes()
        self.assertEqual((method, where), ('PATCH', 'contacts/501'))
        self.assertEqual(sent, {'properties': {'phone': '0300 1112233', 'company': 'Ahmed Traders', 'jobtitle': 'Owner'}})

    def test_the_lead_status_of_an_existing_contact_is_never_set_even_when_empty(self):
        fake, connector = self.crm(self.existing(
            email='bilal@customer.test', firstname='Bill', lastname='A.', phone='1', company='c', jobtitle='t',
            hs_lead_status=''))
        connector.upsert_contact('bilal@customer.test', OURS)
        self.assertEqual(fake.writes(), [])

    def test_the_lookup_asks_for_the_fields_it_must_not_overwrite(self):
        fake, connector = self.crm()
        connector.find_contact_by_email('bilal@customer.test')
        asked = fake.calls[0][2]['properties']
        for field in ('firstname', 'lastname', 'phone', 'company', 'jobtitle', 'hs_lead_status'):
            self.assertIn(field, asked)

    def test_a_contact_that_is_not_there_is_created_with_everything_we_know(self):
        fake, connector = self.crm(('POST', '/objects/contacts', {'id': '777'}))
        self.assertEqual(connector.upsert_contact('bilal@customer.test', OURS), '777')
        [(method, where, sent)] = fake.writes()
        self.assertEqual((method, where), ('POST', 'objects/contacts'))
        self.assertEqual(sent['properties'], {
            'email': 'bilal@customer.test', 'firstname': 'Bilal', 'lastname': 'Ahmed', 'phone': '0300 1112233',
            'company': 'Ahmed Traders', 'jobtitle': 'Owner', 'hs_lead_status': 'IN_PROGRESS'})

    def test_filing_an_email_never_changes_a_contact_that_exists(self):
        fake, connector = self.crm(self.existing(email='bilal@customer.test', firstname='', lastname=''))
        self.assertEqual(connector.find_or_create_contact('bilal@customer.test', OURS), '501')
        self.assertEqual(fake.writes(), [])

    def test_filing_an_email_for_someone_not_there_creates_them_unless_told_not_to(self):
        fake, connector = self.crm(('POST', '/objects/contacts', {'id': '778'}))
        self.assertIsNone(connector.find_or_create_contact('bilal@customer.test', OURS, create=False))
        self.assertEqual(fake.writes(), [])
        self.assertEqual(connector.find_or_create_contact('bilal@customer.test', OURS), '778')
        self.assertEqual(fake.writes()[0][2]['properties']['firstname'], 'Bilal')


class SalesforceTests(SimpleTestCase):

    def crm(self, *script):
        fake = FakeCRM(*script)
        patcher = mock.patch.object(salesforce.requests, 'request', fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        connector = salesforce.SalesforceConnector(credentials={
            'client_id': 'i', 'client_secret': 's', 'username': 'u', 'password': 'p', 'security_token': 't'})
        connector._access_token, connector._instance_url = 'synthetic', 'https://example.my.salesforce.test'
        return fake, connector

    def existing(self, **fields):
        return ('GET', '/query', {'records': [dict({'Id': '003X'}, **fields)]})

    def test_a_contact_with_every_field_filled_is_not_written_to_at_all(self):
        fake, connector = self.crm(self.existing(FirstName='Bill', LastName='A.', Phone='021', Title='MD'))
        self.assertEqual(connector.upsert_contact('bilal@customer.test', OURS), '003X')
        self.assertEqual(fake.writes(), [])

    def test_only_the_empty_fields_are_filled_and_never_the_description_or_the_account(self):
        fake, connector = self.crm(self.existing(FirstName='Bill', LastName='A.', Phone=None, Title=''))
        connector.upsert_contact('bilal@customer.test', OURS)
        [(method, where, sent)] = fake.writes()
        self.assertEqual((method, where), ('PATCH', 'Contact/003X'))
        self.assertEqual(sent, {'Phone': '0300 1112233', 'Title': 'Owner'})

    def test_the_lookup_asks_for_the_title_too(self):
        fake, connector = self.crm()
        connector.find_contact_by_email('bilal@customer.test')
        self.assertIn('Title', fake.calls[0][3]['q'])

    def test_a_new_contact_carries_no_company_or_account_field(self):
        fake, connector = self.crm(('POST', '/sobjects/Contact', {'id': '003NEW'}))
        self.assertEqual(connector.upsert_contact('bilal@customer.test', OURS), '003NEW')
        sent = fake.writes()[0][2]
        self.assertEqual(sent, {'Email': 'bilal@customer.test', 'FirstName': 'Bilal', 'LastName': 'Ahmed',
                                'Phone': '0300 1112233', 'Title': 'Owner', 'Description': 'Lead score: 82'})

    def test_filing_an_email_never_renames_a_contact_that_exists(self):
        fake, connector = self.crm(self.existing(FirstName='Bill', LastName='A.'))
        self.assertEqual(connector.find_or_create_contact('bilal@customer.test', {'email': 'bilal@customer.test'}),
                         '003X')
        self.assertEqual(fake.writes(), [])


class PipedriveTests(SimpleTestCase):

    def crm(self, *script):
        fake = FakeCRM(*script)
        patcher = mock.patch.object(pipedrive.requests, 'request', fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        return fake, pipedrive.PipedriveConnector(api_token='synthetic-token')

    FOUND = ('GET', '/persons/search', {'data': {'items': [{'item': {'id': 42, 'name': 'Bill Ahmed'}}]}})

    def person(self, **fields):
        return ('GET', '/persons/42', {'data': dict({'id': 42, 'name': 'Bill Ahmed'}, **fields)})

    def test_a_person_with_a_phone_and_a_title_is_not_written_to_at_all(self):
        fake, connector = self.crm(self.FOUND, self.person(
            phone=[{'value': '021 555', 'primary': True}, {'value': '0333 999', 'primary': False}],
            email=[{'value': 'bilal@customer.test', 'primary': True}, {'value': 'bill@home.test', 'primary': False}],
            job_title='Managing Director'))
        self.assertEqual(connector.upsert_contact('bilal@customer.test', OURS), '42')
        self.assertEqual(fake.writes(), [])

    def test_a_missing_phone_or_title_is_added_and_the_name_and_emails_are_left_alone(self):
        fake, connector = self.crm(self.FOUND, self.person(phone=[{'value': '', 'primary': True}], job_title=None))
        connector.upsert_contact('bilal@customer.test', OURS)
        [(method, where, sent)] = fake.writes()
        self.assertEqual((method, where), ('PUT', 'persons/42'))
        self.assertEqual(sent, {'phone': [{'value': '0300 1112233', 'primary': True}], 'job_title': 'Owner'})

    def test_with_nothing_of_ours_to_add_the_person_is_not_even_read(self):
        fake, connector = self.crm(self.FOUND)
        connector.upsert_contact('bilal@customer.test', {'email': 'bilal@customer.test', 'first_name': 'Bilal'})
        self.assertEqual([call[1].rsplit('/', 1)[-1].split('?')[0] for call in fake.calls], ['search'])

    def test_someone_not_there_is_created(self):
        fake, connector = self.crm(('POST', '/persons', {'data': {'id': 99}}))
        self.assertEqual(connector.upsert_contact('bilal@customer.test', OURS), '99')
        sent = fake.writes()[0][2]
        self.assertEqual((sent['name'], sent['email'][0]['value']), ('Bilal Ahmed', 'bilal@customer.test'))

    def test_filing_an_email_never_renames_a_person_who_exists(self):
        fake, connector = self.crm(self.FOUND)
        self.assertEqual(connector.find_or_create_contact('bilal@customer.test', {'email': 'bilal@customer.test'}), '42')
        self.assertEqual(fake.writes(), [])


class FilingAnActivityTests(TestCase):
    """The sync agent's side: an email, meeting or note for a lead with no saved link."""

    def setUp(self):
        self.company = Company.objects.create(name='Acme', email='acme@test.local')
        CompanyModulePurchase.objects.create(company=self.company, module_name='crm_sync_agent', status='active',
                                             is_complimentary=True)
        self.cu = CompanyUser.objects.create(company=self.company, email='cu@test.local', full_name='CU',
                                             role='admin', password_hash='x', is_active=True)
        with mock.patch('crm_sync_agent.signals._process_async'):
            self.lead = SDRLead.objects.create(company_user=self.cu, email='bilal@customer.test', first_name='Bilal',
                                               last_name='Ahmed', full_name='Bilal Ahmed', job_title='Owner')
        self.crm = CRMIntegration.objects.create(company=self.company, provider='hubspot',
                                                 credentials={'access_token': 'synthetic-token'}, is_active=True)
        CRMSyncQueue.objects.all().delete()
        self.connector = mock.Mock()
        self.connector.find_or_create_contact.return_value = 'crm-501'
        self.email_payload = {'email': 'bilal@customer.test', 'subject': 'Hello', 'body': 'Hi',
                              'lead_first_name': 'Bilal', 'lead_last_name': 'Ahmed'}

    def resolve(self):
        return CRMSyncAgent(self.company)._resolve_crm_contact_id(
            self.crm, CRMContactMapping.SOURCE_SDR_LEAD, 'bilal@customer.test', self.connector, self.email_payload)

    def test_it_looks_the_contact_up_and_never_goes_through_create_or_update(self):
        self.assertEqual(self.resolve(), 'crm-501')
        self.connector.upsert_contact.assert_not_called()
        (email, details), options = self.connector.find_or_create_contact.call_args
        self.assertEqual(email, 'bilal@customer.test')
        self.assertEqual((details['first_name'], details['last_name'], details['name'], details['job_title']),
                         ('Bilal', 'Ahmed', 'Bilal Ahmed', 'Owner'))            # the lead's own, not the email's
        self.assertEqual(options, {'create': True})

    def test_the_link_is_saved_so_the_crm_is_not_asked_again(self):
        self.resolve()
        self.assertEqual(CRMContactMapping.objects.get(source_id=self.lead.pk).crm_contact_id, 'crm-501')
        self.connector.reset_mock()
        self.assertEqual(self.resolve(), 'crm-501')
        self.connector.find_or_create_contact.assert_not_called()

    def test_with_contacts_switched_off_nobody_is_created(self):
        CRMIntegration.objects.filter(pk=self.crm.pk).update(sync_contacts=False)
        self.crm.refresh_from_db()
        self.resolve()
        self.assertEqual(self.connector.find_or_create_contact.call_args.kwargs, {'create': False})

    def test_an_activity_for_nobody_we_know_creates_nobody(self):
        SDRLead.all_objects.all().delete()
        self.resolve()
        self.assertEqual(self.connector.find_or_create_contact.call_args.kwargs, {'create': False})

    def test_when_no_contact_can_be_found_the_email_waits_and_is_tried_again(self):
        self.connector.find_or_create_contact.return_value = None
        item = CRMSyncQueue.objects.create(
            company=self.company, integration=self.crm, object_type=CRMSyncQueue.TYPE_EMAIL,
            operation=CRMSyncQueue.OP_CREATE, source_type=CRMSyncQueue.SOURCE_SDR_EMAIL, source_id=1,
            payload=self.email_payload)
        with self.assertRaises(CRMError) as raised:
            CRMSyncAgent(self.company)._sync_email(self.connector, item, self.email_payload)
        self.assertTrue(raised.exception.retriable)
        self.connector.log_email_activity.assert_not_called()
