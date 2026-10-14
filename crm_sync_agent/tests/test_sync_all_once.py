""""Sync All Leads" does not send the CRM an email it already has.

The button queues every lead, every sent email and every timed meeting. Its own
note said an email already in the CRM is not sent twice, but only meetings had
that check: for an email the queue looked only for an entry still waiting, so a
finished one was not counted and the email was logged in the CRM again on every
press.

And an entry left at 'processing' when the process stopped stayed there for
good; it counts as sent, so that email or meeting could never be queued again.
"""
from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from ai_sdr_agent.models import SDRCampaign, SDRCampaignEnrollment, SDRLead, SDROutreachLog
from core.models import Company, CompanyModulePurchase, CompanyUser
from crm_sync_agent import tasks
from crm_sync_agent.agents.crm_sync_agent import CRMSyncAgent
from crm_sync_agent.models import CRMIntegration, CRMSyncQueue

EMAIL = CRMSyncQueue.TYPE_EMAIL


class SyncAllOnceTests(TestCase):

    def setUp(self):
        patcher = mock.patch('crm_sync_agent.signals._process_async')     # the queue is only filled here
        patcher.start()
        self.addCleanup(patcher.stop)
        self.company = Company.objects.create(name='Acme', email='acme@test.local')
        for module in ('crm_sync_agent', 'ai_sdr_agent'):
            CompanyModulePurchase.objects.create(company=self.company, module_name=module, status='active',
                                                 is_complimentary=True)
        self.cu = CompanyUser.objects.create(company=self.company, email='cu@test.local', full_name='CU',
                                             role='admin', password_hash='x', is_active=True)
        self.hubspot = self.connect('hubspot', {'access_token': 'synthetic-token'})
        lead = SDRLead.objects.create(company_user=self.cu, email='bilal@customer.test', first_name='Bilal')
        campaign = SDRCampaign.objects.create(company_user=self.cu, name='C1', status='active')
        enrolment = SDRCampaignEnrollment.objects.create(campaign=campaign, lead=lead, status='active')
        self.sent_emails = [
            SDROutreachLog.objects.create(enrollment=enrolment, step_order=n, action_type='email', status='sent',
                                          subject_sent=f'Email {n}', body_sent='Hi', sent_at=timezone.now())
            for n in (1, 2)]
        CRMSyncQueue.objects.all().delete()                # only what "Sync All Leads" queues from here on

    def connect(self, provider, credentials):
        return CRMIntegration.objects.create(company=self.company, provider=provider, credentials=credentials,
                                             is_active=True)

    def press_sync_all(self):
        return tasks.sync_sdr_leads_to_crm(company_id=self.company.id)

    def emails(self, **filters):
        return CRMSyncQueue.objects.filter(object_type=EMAIL, **filters)

    def test_an_email_that_has_gone_to_the_crm_is_not_queued_again(self):
        self.press_sync_all()
        self.assertEqual(self.emails().count(), 2)
        self.emails().update(status=CRMSyncQueue.STATUS_DONE)

        for _ in range(3):
            self.press_sync_all()

        self.assertEqual(self.emails().count(), 2)
        self.assertEqual(self.emails(status=CRMSyncQueue.STATUS_PENDING).count(), 0)

    def test_nor_one_that_is_being_sent_at_this_moment(self):
        self.press_sync_all()
        self.emails().update(status=CRMSyncQueue.STATUS_PROCESSING, last_attempted_at=timezone.now())
        self.press_sync_all()
        self.assertEqual(self.emails().count(), 2)

    def test_one_still_waiting_or_failed_is_kept_as_one_entry(self):
        self.press_sync_all()
        later = timezone.now() + timedelta(hours=6)
        self.emails().update(status=CRMSyncQueue.STATUS_FAILED, scheduled_at=later, payload={'subject': 'stale'})
        self.press_sync_all()
        self.assertEqual(self.emails().count(), 2)
        # ... and brought up to date: it is due now, with the email as it stands.
        for entry in self.emails():
            self.assertLessEqual(entry.scheduled_at, timezone.now())
            self.assertIn(entry.payload['subject'], ('Email 1', 'Email 2'))

    def test_an_email_sent_since_the_last_press_is_queued(self):
        self.press_sync_all()
        self.emails().update(status=CRMSyncQueue.STATUS_DONE)
        newest = SDROutreachLog.objects.create(
            enrollment=self.sent_emails[0].enrollment, step_order=3, action_type='email', status='sent',
            subject_sent='Email 3', body_sent='Hi', sent_at=timezone.now())
        self.emails().filter(source_id=newest.pk).delete()            # as if it had been sent with the CRM off
        self.press_sync_all()
        self.assertEqual(list(self.emails(status=CRMSyncQueue.STATUS_PENDING).values_list('source_id', flat=True)),
                         [newest.pk])

    def test_a_second_crm_connected_later_gets_the_history_once(self):
        self.press_sync_all()
        self.emails().update(status=CRMSyncQueue.STATUS_DONE)
        second = self.connect('pipedrive', {'api_token': 'synthetic-token'})

        self.press_sync_all()

        self.assertEqual(self.emails(integration=second).count(), 2)
        self.assertEqual(self.emails(integration=self.hubspot).count(), 2)      # and the first gets nothing new
        self.emails().update(status=CRMSyncQueue.STATUS_DONE)
        self.press_sync_all()
        self.assertEqual(self.emails().count(), 4)

    def test_the_live_path_is_checked_the_same_way(self):
        agent = CRMSyncAgent(self.company)
        agent.enqueue_email_sent(self.sent_emails[0])
        self.emails().update(status=CRMSyncQueue.STATUS_DONE)
        agent.enqueue_email_sent(self.sent_emails[0])
        self.assertEqual(self.emails().count(), 1)


class StuckEntryTests(TestCase):

    def setUp(self):
        self.company = Company.objects.create(name='Acme', email='acme@test.local')
        self.crm = CRMIntegration.objects.create(company=self.company, provider='hubspot',
                                                 credentials={'access_token': 'synthetic-token'}, is_active=True)

    def entry(self, status, minutes_ago, attempts=1):
        return CRMSyncQueue.objects.create(
            company=self.company, integration=self.crm, object_type=EMAIL, operation=CRMSyncQueue.OP_CREATE,
            source_type=CRMSyncQueue.SOURCE_SDR_EMAIL, source_id=CRMSyncQueue.objects.count() + 1, payload={},
            status=status, attempts=attempts, last_attempted_at=timezone.now() - timedelta(minutes=minutes_ago))

    def status(self, entry):
        return CRMSyncQueue.objects.get(pk=entry.pk).status

    def test_an_entry_left_being_sent_for_too_long_goes_back_in_the_queue(self):
        abandoned = self.entry(CRMSyncQueue.STATUS_PROCESSING, minutes_ago=15)       # a quarter of an hour is abandoned
        tasks.retry_failed_crm_syncs()
        self.assertEqual(self.status(abandoned), CRMSyncQueue.STATUS_PENDING)
        self.assertLessEqual(CRMSyncQueue.objects.get(pk=abandoned.pk).scheduled_at, timezone.now())

    def test_one_that_only_just_started_is_left_to_finish(self):
        in_flight = self.entry(CRMSyncQueue.STATUS_PROCESSING, minutes_ago=1)
        tasks.retry_failed_crm_syncs()
        self.assertEqual(self.status(in_flight), CRMSyncQueue.STATUS_PROCESSING)

    def test_finished_entries_are_not_touched(self):
        done = self.entry(CRMSyncQueue.STATUS_DONE, minutes_ago=60)
        tasks.retry_failed_crm_syncs()
        self.assertEqual(self.status(done), CRMSyncQueue.STATUS_DONE)
