"""CRM Sync's live run on Margalla with a real HubSpot (31 Oct 2026).

A wrong HubSpot key was saved and the page said "HubSpot connected!"; Test Connection then said only "Ping failed";
there was no way to put in a new key but Remove, which drops what waits in the queue. Connecting and a new key are
now tried with the CRM first, and the reason it refused is said. No test reaches a CRM: requests are replaced.
"""
import json
from unittest import mock

import requests

from api.views import crm_sync_agent as views
from crm_sync_agent.connectors.base import CRMError, refusal
from crm_sync_agent.connectors.hubspot import HubSpotConnector
from crm_sync_agent.connectors.pipedrive import PipedriveConnector
from crm_sync_agent.models import CRMIntegration, CRMSyncQueue
from hr_agent.tests.base import HRTestCase

from . import tests_crm_sync as base

GOOD = 'pat-synthetic-good-0123456789abcdef'
WRONG = 'pat-synthetic-wrong-0123456789abcdef'


def answer(status, data=None):
    r = mock.Mock(status_code=status, text=json.dumps(data or {}))
    r.json.return_value = data or {}
    return r


def hubspot_takes(*good_keys):
    """requests.request as HubSpot answers it: 200 for a key it knows, 401 for any other."""
    def request(method, url, headers=None, **kwargs):
        key = (headers or {}).get('Authorization', '').replace('Bearer ', '')
        return answer(200, {'results': []}) if key in good_keys else answer(401, {'message': 'Authentication credentials not found.'})
    return mock.patch('crm_sync_agent.connectors.hubspot.requests.request', side_effect=request)


class KeyCheckTests(base.CRMBase):
    call = HRTestCase.call
    factory = HRTestCase.factory

    def setUp(self):
        super().setUp()
        CRMIntegration.objects.all().delete()

    def connect(self, key):
        with hubspot_takes(GOOD):
            return self.call(views.integrations_list, self.cu, {'provider': 'hubspot', 'credentials': {'access_token': key}})

    def test_a_wrong_key_is_refused_with_the_reason_and_not_saved(self):
        code, body = self.connect(WRONG)
        self.assertEqual(code, 400)
        self.assertIn('HubSpot refused the key', body['message'])      # the screens show 'message'
        self.assertFalse(CRMIntegration.objects.exists())
        self.assertNotIn(WRONG, json.dumps(body))

    def test_a_good_key_is_saved_and_shown_as_connected_at_once(self):
        code, body = self.connect(GOOD)
        self.assertEqual(code, 201, body)
        self.assertTrue(body['last_ping_ok'])

    def test_a_new_key_is_tried_before_it_replaces_the_old_one(self):
        self.connect(GOOD)
        integration = CRMIntegration.objects.get()
        with hubspot_takes(GOOD):
            code, body = self.call(views.integration_detail, self.cu, {'credentials': {'access_token': WRONG}},
                                   method='patch', integration_id=integration.id)
        integration.refresh_from_db()
        self.assertEqual((code, integration.get_credentials()['access_token']), (400, GOOD))
        self.assertIn('refused the key', body['message'])

    def test_a_good_new_key_releases_what_waited(self):
        self.connect(GOOD)
        integration = CRMIntegration.objects.get()
        CRMSyncQueue.objects.all().delete()
        CRMSyncQueue.objects.create(company=self.company, integration=integration, object_type=CRMSyncQueue.TYPE_NOTE,
                                    operation=CRMSyncQueue.OP_CREATE, source_type='sdr_reply', source_id=1,
                                    payload={'email': 'bob@acme.com', 'body': 'Hi'}, status=CRMSyncQueue.STATUS_WAITING)
        with hubspot_takes(GOOD, 'pat-synthetic-newer-0123456789abcdef'):
            code, _ = self.call(views.integration_detail, self.cu,
                                {'credentials': {'access_token': 'pat-synthetic-newer-0123456789abcdef'}},
                                method='patch', integration_id=integration.id)
        self.assertEqual(code, 200)
        self.assertEqual(CRMSyncQueue.objects.get().status, CRMSyncQueue.STATUS_PENDING)

    def test_test_connection_says_why(self):
        integration = CRMIntegration(company=self.company, provider='hubspot')
        integration.set_credentials({'access_token': WRONG})
        integration.save()
        with hubspot_takes(GOOD):
            code, body = self.call(views.integration_ping, self.cu, integration_id=integration.id)
        # An answer, not a server fault: a 502 made the page say only "Ping failed".
        self.assertEqual((code, body['status']), (200, 'failed'))
        self.assertIn('HubSpot refused the key', body['message'])
        integration.refresh_from_db()
        self.assertFalse(integration.last_ping_ok)


class IncomingMailTests(base.CRMBase):

    def sent(self, direction):
        with mock.patch('crm_sync_agent.connectors.hubspot.requests.request',
                        return_value=answer(200, {'engagement': {'id': 7}})) as request:
            HubSpotConnector(GOOD).log_email_activity('42', 'Booking app ki qeemat', 'Kitni hai?', None, direction)
        return request.call_args.kwargs['json']

    def test_a_customers_email_goes_as_incoming_mail(self):
        # Status 'RECEIVED' does not exist in HubSpot: "400 Unable to process JSON" for all 13 of Margalla's.
        payload = self.sent('INBOUND')
        self.assertEqual(payload['engagement']['type'], 'INCOMING_EMAIL')
        self.assertNotIn('status', payload['metadata'])

    def test_our_email_goes_as_sent(self):
        payload = self.sent('OUTBOUND')
        self.assertEqual((payload['engagement']['type'], payload['metadata']['status']), ('EMAIL', 'SENT'))


class RefusalWordsTests(base.CRMBase):

    def test_each_kind_of_refusal_is_said_plainly(self):
        self.assertIn('refused the key', refusal('HubSpot', CRMError('x', status_code=401)))
        self.assertIn('permission to read and write contacts', refusal('HubSpot', CRMError('x', status_code=403)))
        self.assertIn('could not be reached', refusal('Pipedrive', CRMError('x')))
        self.assertIn('refused the sign-in details',
                      refusal('Salesforce', CRMError('Salesforce auth failed (400): invalid_grant', status_code=400)))

    def test_a_pipedrive_network_error_is_said_without_the_request(self):
        boom = requests.ConnectionError('https://api.pipedrive.com/v1/users/me (synthetic-pipedrive-key)')
        with mock.patch('crm_sync_agent.connectors.pipedrive.requests.request', side_effect=boom):
            reason = PipedriveConnector('synthetic-pipedrive-key').check()
        self.assertIn('Pipedrive could not be reached', reason)
        self.assertNotIn('synthetic-pipedrive-key', reason)

    def test_ping_still_answers_yes_or_no(self):
        with hubspot_takes(GOOD):
            self.assertTrue(HubSpotConnector(GOOD).ping())
            self.assertFalse(HubSpotConnector(WRONG).ping())
