"""The CRM connection: who may change it, what leaves the server, and the full sync.

The saved CRM credentials (the HubSpot key, or the Salesforce user name,
password and secret) were stored in clear text and sent whole to the browser
of any dashboard login in the company, and any such login could replace or
delete the connection. And "Sync All Leads" answered "Sync queued" while the
job behind it failed on its first step every time.
"""
import json
from datetime import timedelta
from importlib import import_module
from unittest import mock

from django.apps import apps
from django.utils import timezone

from ai_sdr_agent.models import SDRCampaign, SDRCampaignEnrollment, SDRLead, SDRMeeting, SDROutreachLog
from api.views import crm_sync_agent as views
from core.models import CompanyModulePurchase, CompanyUser
from crm_sync_agent.agents import crm_sync_agent as agent_module
from crm_sync_agent.models import CRMIntegration, CRMSyncQueue
from crm_sync_agent.tasks import sync_sdr_leads_to_crm
from hr_agent.tests.base import HRTestCase

from . import tests_crm_sync as base      # the module, so its own tests are not collected here too

SECRET = 'pat-synthetic-0123456789abcdef'


class ConnectionBase(base.CRMBase):
    call = HRTestCase.call
    factory = HRTestCase.factory

    def setUp(self):
        super().setUp()
        CRMIntegration.objects.all().delete()
        self.member = CompanyUser.objects.create(company=self.company, email='mo@test.local', full_name='Mo Member',
                                                 role='company_user', password_hash='x', is_active=True)

    def connect(self, actor=None, **credentials):
        credentials = credentials or {'access_token': SECRET}
        return self.call(views.integrations_list, actor or self.cu, {'provider': 'hubspot', 'credentials': credentials})

    def stored(self):
        return json.dumps(list(CRMIntegration.objects.values_list('credentials', flat=True)))


class CredentialTests(ConnectionBase):

    def test_they_are_kept_encrypted_and_still_work(self):
        code, _ = self.connect()
        self.assertEqual(code, 201)
        self.assertNotIn(SECRET, self.stored())
        integration = CRMIntegration.objects.get()
        self.assertEqual(integration.get_credentials(), {'access_token': SECRET})
        with mock.patch.object(agent_module, 'HubSpotConnector') as hubspot:
            agent_module.CRMSyncAgent(self.company)._get_connector(integration)
        hubspot.assert_called_once_with(access_token=SECRET)

    def test_only_a_masked_preview_ever_leaves_the_server(self):
        _, created = self.connect()
        integration = CRMIntegration.objects.get()
        _, listed = self.call(views.integrations_list, self.member, method='get')
        _, one = self.call(views.integration_detail, self.member, method='get', integration_id=integration.id)
        for body in (created, listed, one):
            self.assertNotIn(SECRET, json.dumps(body))
        self.assertEqual(one['credentials_preview'], {'access_token': 'pat-********cdef'})

    def test_where_to_sign_in_is_shown_but_the_password_is_not(self):
        CRMIntegration.objects.all().delete()
        salesforce = CRMIntegration(company=self.company, provider='salesforce')
        salesforce.set_credentials({'username': 'ops@acme.example', 'password': 'synthetic-password-1',
                                    'domain': 'login'})
        salesforce.save()
        self.assertEqual(salesforce.credentials_preview(),
                         {'username': 'ops@acme.example', 'password': 'synt********rd-1', 'domain': 'login'})

    def test_a_connection_saved_before_encryption_still_works_and_is_then_encrypted(self):
        old = CRMIntegration.objects.create(company=self.company, provider='pipedrive',
                                            credentials={'api_token': SECRET})
        self.assertEqual(old.get_credentials(), {'api_token': SECRET})
        self.assertIn(SECRET, self.stored())
        encrypt = import_module('crm_sync_agent.migrations.0004_encrypt_credentials').encrypt_saved_credentials
        encrypt(apps, None)
        encrypt(apps, None)                                   # safe to run twice
        self.assertNotIn(SECRET, self.stored())
        self.assertEqual(CRMIntegration.objects.get().get_credentials(), {'api_token': SECRET})


class WhoMayChangeItTests(ConnectionBase):

    def setUp(self):
        super().setUp()
        self.connect()
        self.integration = CRMIntegration.objects.get()

    def test_a_member_cannot_connect_change_or_disconnect_a_crm(self):
        CRMIntegration.objects.all().delete()
        code, body = self.connect(self.member)
        self.assertEqual((code, CRMIntegration.objects.count()), (403, 0))
        self.assertIn('owner or admin', body['message'])
        self.connect()
        integration = CRMIntegration.objects.get()
        for method, data in (('patch', {'is_active': False}), ('patch', {'credentials': {'access_token': 'x' * 30}}),
                             ('delete', None)):
            code, _ = self.call(views.integration_detail, self.member, data, method=method,
                                integration_id=integration.id)
            self.assertEqual(code, 403, (method, data))
        integration.refresh_from_db()
        self.assertEqual((integration.is_active, integration.get_credentials()), (True, {'access_token': SECRET}))

    def test_an_admin_can(self):
        code, _ = self.call(views.integration_detail, self.cu, {'sync_notes': False}, method='patch',
                            integration_id=self.integration.id)
        self.integration.refresh_from_db()
        self.assertEqual((code, self.integration.sync_notes), (200, False))
        code, _ = self.call(views.integration_detail, self.cu, method='delete', integration_id=self.integration.id)
        self.assertEqual((code, CRMIntegration.objects.count()), (204, 0))

    def test_a_field_sent_back_masked_or_blank_keeps_the_saved_value(self):
        for sent in ('pat-********cdef', '', '   ', '********'):
            code, _ = self.call(views.integration_detail, self.cu, {'credentials': {'access_token': sent}},
                                method='patch', integration_id=self.integration.id)
            self.integration.refresh_from_db()
            self.assertEqual((code, self.integration.get_credentials()), (200, {'access_token': SECRET}), sent)

    def test_a_field_that_was_retyped_replaces_it(self):
        new = 'pat-synthetic-new-9876543210'
        self.call(views.integration_detail, self.cu, {'credentials': {'access_token': new}}, method='patch',
                  integration_id=self.integration.id)
        self.integration.refresh_from_db()
        self.assertEqual(self.integration.get_credentials(), {'access_token': new})
        self.assertNotIn(new, self.stored())

    def test_another_companys_connection_is_not_found(self):
        from core.models import Company
        rival = Company.objects.create(name='Rival', email='rival@test.local')
        rhea = CompanyUser.objects.create(company=rival, email='rhea@test.local', full_name='Rhea', role='admin',
                                          password_hash='x', is_active=True)
        for method in ('get', 'patch', 'delete'):
            code, _ = self.call(views.integration_detail, rhea, method=method, integration_id=self.integration.id)
            self.assertEqual(code, 404, method)
        self.assertEqual(CRMIntegration.objects.count(), 1)


class SyncEverythingTests(ConnectionBase):

    def setUp(self):
        super().setUp()
        self.connect()
        colleague = CompanyUser.objects.create(company=self.company, email='cole@test.local', full_name='Cole',
                                               role='company_user', password_hash='x', is_active=True)
        # Leads that were there before the CRM was connected, under two salespeople.
        theirs = SDRLead.objects.create(company_user=colleague, email='pia@prospect.example', first_name='Pia')
        enrollment = self.enroll(self.lead)
        SDROutreachLog.objects.create(enrollment=enrollment, step_order=1, action_type='email', status='sent',
                                      subject_sent='Hello', body_sent='Hi', sent_at=timezone.now())
        SDROutreachLog.objects.create(enrollment=enrollment, step_order=2, action_type='email', status='failed')
        SDRMeeting.objects.create(company_user=self.cu, lead=self.lead, status='scheduled',
                                  scheduled_at=timezone.now() + timedelta(days=2))
        SDRMeeting.objects.create(company_user=colleague, lead=theirs, status='pending')      # no time yet
        CRMSyncQueue.objects.all().delete()                   # only what the full sync queues from here on

    def queued(self):
        return sorted(CRMSyncQueue.objects.values_list('object_type', flat=True))

    def test_sync_all_queues_every_lead_sent_email_and_timed_meeting(self):
        # It used to fail on its first line: leads have no `company` field.
        self.assertEqual(sync_sdr_leads_to_crm(company_id=self.company.id), 4)
        self.assertEqual(self.queued(), ['contact', 'contact', 'email_activity', 'meeting'])

    def test_running_it_again_does_not_pile_up_duplicates(self):
        sync_sdr_leads_to_crm(company_id=self.company.id)
        sync_sdr_leads_to_crm(company_id=self.company.id)
        self.assertEqual(len(self.queued()), 4)

    def test_it_does_nothing_for_a_company_whose_crm_sync_has_lapsed(self):
        CompanyModulePurchase.objects.filter(pk=self.subscription.pk).update(status='cancelled')
        self.assertEqual(sync_sdr_leads_to_crm(company_id=self.company.id), 0)
        self.assertEqual(self.queued(), [])

    def test_the_button_works_when_the_queue_is_unreachable(self):
        integration = CRMIntegration.objects.get()
        with mock.patch.object(sync_sdr_leads_to_crm, 'delay', side_effect=ConnectionError('no broker')), \
                mock.patch.object(agent_module.CRMSyncAgent, 'process_pending', return_value={'processed': 4}):
            code, body = self.call(views.integration_sync_leads, self.member, integration_id=integration.id)
        self.assertEqual((code, body['status']), (200, 'done'), body)
        self.assertEqual(body['message'], 'Synced 2 leads, 1 emails, 1 meetings.')
