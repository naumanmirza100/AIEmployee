"""CRM Sync before its demo (30 Oct 2026): CO-158, 159, 160 (with tests_crm_connection), 161, 162, 206, 253, 275,
and the Inbox Manager's part of the client's list: Reply Draft's mail from customers and leads, and the replies
sent, on the CRM contact. No test reaches a CRM: the connectors' calls are replaced.
"""
from datetime import timedelta
from unittest import mock

import requests
from django.utils import timezone

from ai_sdr_agent.models import SDRMeeting, SDROutreachLog
from api.views import crm_sync_agent as views
from core.logins import user_for
from crm_sync_agent.agents.crm_sync_agent import CRMSyncAgent
from crm_sync_agent.connectors.base import CRMError, PermissionMissing
from crm_sync_agent.connectors.hubspot import HubSpotConnector
from crm_sync_agent.connectors.pipedrive import PipedriveConnector
from crm_sync_agent.connectors.salesforce import SalesforceConnector
from crm_sync_agent.models import CRMActivityMapping, CRMIntegration, CRMSyncLog, CRMSyncQueue
from hr_agent.tests.base import HRTestCase
from marketing_agent.models import EmailAccount
from reply_draft_agent.models import InboxEmail, ReplyDraft

from . import tests_crm_sync as base


def response(status=200, data=None):
    r = mock.Mock(status_code=status, text='')
    r.json.return_value = data or {}
    return r


class QueueTests(base.CRMBase):
    call = HRTestCase.call
    factory = HRTestCase.factory

    def setUp(self):
        super().setUp()
        CRMSyncQueue.objects.all().delete()          # the lead made in setUp queued its contact

    def entry(self, **fields):
        values = dict(company=self.company, integration=self.crm, object_type=CRMSyncQueue.TYPE_NOTE,
                      source_type=CRMSyncQueue.SOURCE_SDR_NOTE, source_id=1, payload={'email': 'bob@acme.com'})
        values.update(fields)
        return CRMSyncQueue.objects.create(**values)

    def test_an_entry_is_claimed_once_however_many_runs_reach_it(self):
        # CO-206: every save started its own thread over the same waiting entries.
        item = self.entry()
        self.assertTrue(CRMSyncAgent._claim(item))
        self.assertFalse(CRMSyncAgent._claim(CRMSyncQueue.objects.get(pk=item.pk)))
        item.refresh_from_db()
        self.assertEqual((item.status, item.attempts), (CRMSyncQueue.STATUS_PROCESSING, 1))

    def test_a_refused_key_holds_entries_until_the_key_works_and_retry_brings_back_the_dead(self):
        # CO-159: a refused key used up every attempt, and Retry said '0 items re-queued'.
        item = self.entry()
        with mock.patch.object(CRMSyncAgent, '_dispatch', side_effect=CRMError('refused', retriable=False,
                                                                                  status_code=401)):
            CRMSyncAgent(self.company).process_pending()
        item.refresh_from_db()
        self.crm.refresh_from_db()
        self.assertEqual((item.status, item.attempts), (CRMSyncQueue.STATUS_WAITING, 0))
        self.assertIsNotNone(self.crm.key_refused_at)
        self.assertEqual(CRMSyncAgent.release_waiting(self.crm), 1)
        item.refresh_from_db()
        self.assertEqual(item.status, CRMSyncQueue.STATUS_PENDING)
        dead = self.entry(source_id=2, status=CRMSyncQueue.STATUS_FAILED, attempts=3)
        code, body = self.call(views.retry_failed, self.cu)
        dead.refresh_from_db()
        self.assertEqual((code, body['requeued'], dead.status, dead.attempts), (200, 1, CRMSyncQueue.STATUS_PENDING, 0))

    def test_queued_again_a_dead_entry_is_tried_afresh(self):
        dead = self.entry(object_type=CRMSyncQueue.TYPE_CONTACT, source_type=CRMSyncQueue.SOURCE_SDR_LEAD,
                          source_id=self.lead.pk, status=CRMSyncQueue.STATUS_FAILED, attempts=3)
        CRMSyncAgent(self.company).enqueue_sdr_lead(self.lead)
        dead.refresh_from_db()
        self.assertEqual((dead.status, dead.attempts), (CRMSyncQueue.STATUS_PENDING, 0))

    def test_a_full_account_spends_no_attempt(self):
        item = self.entry()
        with mock.patch.object(CRMSyncAgent, '_dispatch', side_effect=CRMError('limit', retriable=False,
                                                                                  status_code=402)):
            CRMSyncAgent(self.company).process_pending()
        item.refresh_from_db()
        self.assertEqual((item.status, item.attempts), (CRMSyncQueue.STATUS_FAILED, 0))
        self.assertGreater(item.scheduled_at, timezone.now() + timedelta(minutes=50))

    def test_a_refused_permission_is_skipped_and_said_not_counted_as_sent(self):
        # CO-162: a 403 on an email became 'no id' and was recorded as a success.
        item = self.entry(object_type=CRMSyncQueue.TYPE_EMAIL, source_type=CRMSyncQueue.SOURCE_SDR_EMAIL)
        hubspot = HubSpotConnector('synthetic')
        with mock.patch('crm_sync_agent.connectors.hubspot.requests.request', return_value=response(403)):
            with self.assertRaises(PermissionMissing) as caught:
                hubspot.log_email_activity('1', 'Hi', 'Hello', None)
        self.assertIn('sales-email-read', str(caught.exception))
        with mock.patch.object(CRMSyncAgent, '_dispatch', side_effect=caught.exception):
            CRMSyncAgent(self.company).process_pending()
        item.refresh_from_db()
        self.crm.refresh_from_db()
        self.assertEqual(item.status, CRMSyncQueue.STATUS_SKIPPED)
        self.assertIn('sales-email-read', self.crm.missing_permission)
        self.assertEqual(CRMSyncLog.objects.get().status, CRMSyncLog.STATUS_SKIPPED)


class ConnectorTests(base.CRMBase):

    def test_the_pipedrive_key_goes_in_a_header_and_never_into_an_error(self):
        # CO-158: the key was in the address, and the address in the saved error text.
        pipedrive = PipedriveConnector('synthetic-pipedrive-key')
        with mock.patch('crm_sync_agent.connectors.pipedrive.requests.request',
                        return_value=response(200, {'success': True})) as request:
            pipedrive.ping()
        self.assertEqual(request.call_args.kwargs['headers'], {'x-api-token': 'synthetic-pipedrive-key'})
        self.assertNotIn('api_token', str(request.call_args.kwargs.get('params') or {}))
        boom = requests.ConnectionError('https://api.pipedrive.com/v1/users/me?api_token=synthetic-pipedrive-key')
        with mock.patch('crm_sync_agent.connectors.pipedrive.requests.request', side_effect=boom):
            with self.assertRaises(CRMError) as caught:
                pipedrive.ping() or pipedrive.find_contact_by_email('a@b.test')
        self.assertNotIn('synthetic-pipedrive-key', str(caught.exception))

    def test_salesforce_meetings_give_start_and_end_only(self):
        # CO-161: a fixed 'DurationInMinutes': 60 with a half-hour start and end.
        salesforce = SalesforceConnector({'client_id': 'x', 'client_secret': 'y', 'username': 'u', 'password': 'p',
                                          'security_token': 't'})
        salesforce._access_token, salesforce._instance_url = 'token', 'https://example.my.salesforce.test'
        start = timezone.now() + timedelta(days=1)
        with mock.patch.object(salesforce, '_post', return_value=response(201, {'id': 'E1'})) as post:
            salesforce.log_meeting('C1', 'Demo', start, start + timedelta(minutes=30))
        self.assertNotIn('DurationInMinutes', post.call_args.kwargs['json'])

    def test_a_future_meeting_is_not_marked_done_in_pipedrive(self):
        fields = PipedriveConnector._meeting_fields('Demo', timezone.now() + timedelta(days=2),
                                                    timezone.now() + timedelta(days=2, minutes=30), '')
        self.assertEqual((fields['done'], fields['duration']), (0, '00:30'))


class LinkedInTests(base.CRMBase):

    def test_a_linkedin_reminder_is_not_logged_as_an_email(self):
        # CO-253: a LinkedIn step's 'sent' row reached the CRM as an email, subject '(no subject)'.
        enrollment = self.enroll(self.lead)
        SDROutreachLog.objects.create(enrollment=enrollment, step_order=1, action_type='linkedin', status='sent',
                                      body_sent='Send a LinkedIn connection to Bob', sent_at=timezone.now())
        self.assertEqual(self.queued(CRMSyncQueue.TYPE_EMAIL), [])
        SDROutreachLog.objects.create(enrollment=enrollment, step_order=2, action_type='email', status='sent',
                                      subject_sent='Hello', body_sent='Hi', sent_at=timezone.now())
        self.assertEqual(len(self.queued(CRMSyncQueue.TYPE_EMAIL)), 1)


class MeetingChangeTests(base.CRMBase):
    """CO-275: a meeting moved or cancelled after it reached the CRM stayed there as it was."""

    def test_a_moved_meeting_updates_the_crms_and_a_cancelled_one_is_cancelled_there(self):
        start = timezone.now() + timedelta(days=3)
        meeting = SDRMeeting.objects.create(company_user=self.cu, lead=self.lead, status='scheduled',
                                            scheduled_at=start, title='Demo call')
        agent = CRMSyncAgent(self.company)
        with mock.patch.object(HubSpotConnector, 'find_or_create_contact', return_value='C1'), \
                mock.patch.object(HubSpotConnector, 'upsert_contact', return_value='C1'), \
                mock.patch.object(HubSpotConnector, 'log_meeting', return_value='M9') as created:
            agent.process_pending()
        created.assert_called_once()
        self.assertEqual(CRMActivityMapping.objects.get().crm_object_id, 'M9')
        meeting.scheduled_at = start + timedelta(days=1)
        meeting.save()
        meeting.save()                                          # no change: nothing more
        update, = CRMSyncQueue.objects.filter(operation=CRMSyncQueue.OP_UPDATE, status=CRMSyncQueue.STATUS_PENDING)
        with mock.patch.object(HubSpotConnector, 'update_meeting') as moved:
            CRMSyncAgent(self.company).process_pending()
        self.assertEqual(moved.call_args.args[0], 'M9')
        self.assertFalse(moved.call_args.kwargs['cancelled'])
        meeting.status = 'cancelled'
        meeting.save()
        with mock.patch.object(HubSpotConnector, 'update_meeting') as cancelled:
            CRMSyncAgent(self.company).process_pending()
        self.assertTrue(cancelled.call_args.kwargs['cancelled'])
        del update

    def test_a_meeting_cancelled_before_it_reached_the_crm_is_never_sent(self):
        SDRMeeting.objects.create(company_user=self.cu, lead=self.lead, status='cancelled',
                                  scheduled_at=timezone.now() + timedelta(days=1))
        self.assertEqual(self.queued(CRMSyncQueue.TYPE_MEETING), [])


class InboxTests(base.CRMBase):
    """The client's list puts CRM & System Sync in the Inbox Manager too: Reply Draft's mail from customers and
    leads, and the replies sent, go on the CRM contact."""

    def setUp(self):
        super().setUp()
        self.mailbox = EmailAccount.objects.create(
            owner=user_for(self.cu), name='Inbox', email='hello@acme.test', smtp_host='smtp.acme.test',
            smtp_username='hello@acme.test', smtp_password='synthetic', imap_host='imap.acme.test',
            imap_username='hello@acme.test', imap_password='synthetic', enable_imap_sync=True,
            is_reply_agent_account=True, is_marketing_account=False)

    def mail(self, category='customer', **more):
        fields = dict(owner=user_for(self.cu), email_account=self.mailbox, message_id=f'<{category}@x>',
                      from_email='kiran@clinic.test', from_name='Kiran Shah', subject='Price?',
                      body='How much for two branches?', received_at=timezone.now(), to_email='hello@acme.test',
                      direction='in', category=category, priority='high', triaged_at=timezone.now())
        fields.update(more)
        return InboxEmail.objects.create(**fields)

    def test_a_customers_email_goes_to_the_crm_and_a_newsletter_does_not(self):
        from crm_sync_agent.signals import queue_inbox_email
        queue_inbox_email(self.mail())
        queue_inbox_email(self.mail(category='newsletter', from_email='news@shop.test'))
        email, = self.queued(CRMSyncQueue.TYPE_EMAIL)
        self.assertEqual((email.source_type, email.payload['email'], email.payload['direction'],
                          email.payload['contact_name']),
                         (CRMSyncQueue.SOURCE_INBOX_EMAIL, 'kiran@clinic.test', 'INBOUND', 'Kiran Shah'))
        with mock.patch.object(HubSpotConnector, 'find_or_create_contact', return_value='C7') as contact, \
                mock.patch.object(HubSpotConnector, 'log_email_activity', return_value='E1') as logged:
            CRMSyncAgent(self.company).process_pending()
        self.assertEqual(contact.call_args.args[1]['first_name'], 'Kiran')
        self.assertTrue(contact.call_args.kwargs['create'])
        self.assertEqual(logged.call_args.kwargs['direction'], 'INBOUND')

    def test_a_reply_sent_goes_on_the_recipients_contact_once(self):
        from crm_sync_agent.signals import queue_inbox_reply
        draft = ReplyDraft.objects.create(owner=user_for(self.cu), inbox_email=self.mail(),
                                          email_account=self.mailbox, draft_subject='Re: Price?',
                                          draft_body='Rs 12,000 a month.', status='sent', sent_at=timezone.now())
        queue_inbox_reply(draft, 'kiran@clinic.test', 'Re: Price?', 'Rs 12,000 a month.')
        CRMSyncQueue.objects.update(status=CRMSyncQueue.STATUS_DONE)
        queue_inbox_reply(draft, 'kiran@clinic.test', 'Re: Price?', 'Rs 12,000 a month.')
        reply, = self.queued(CRMSyncQueue.TYPE_EMAIL)
        self.assertEqual((reply.source_type, reply.payload['direction']), (CRMSyncQueue.SOURCE_INBOX_REPLY, 'OUTBOUND'))

    def test_without_crm_sync_nothing_is_queued(self):
        from crm_sync_agent.signals import queue_inbox_email
        self.subscription.delete()
        queue_inbox_email(self.mail())
        self.assertEqual(self.queued(CRMSyncQueue.TYPE_EMAIL), [])

    def test_sync_all_brings_the_inbox_too(self):
        from crm_sync_agent.tasks import queue_everything
        self.mail()
        counts = queue_everything(CRMSyncAgent(self.company), self.company)
        self.assertEqual(counts['inbox_emails'], 1)
        self.assertTrue(CRMIntegration.objects.get().is_active)
