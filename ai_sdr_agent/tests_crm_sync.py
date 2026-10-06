"""What AI SDR tells the CRM, and when.

Replies from leads never reached the CRM: the listener looked for a field the
enrollment does not have and gave up every time. A meeting was sent the moment
the AI created it, before any time was chosen, so the CRM filed it under that
moment and was never told the real time.
"""
from datetime import timedelta
from unittest import mock

from django.utils import timezone

from ai_sdr_agent.models import SDRCampaignEnrollment, SDRMeeting
from ai_sdr_agent.tests import SDRBase
from core.models import CompanyModulePurchase
from crm_sync_agent import signals as crm_signals
from crm_sync_agent.models import CRMIntegration, CRMSyncQueue


class CRMBase(SDRBase):

    def setUp(self):
        super().setUp()
        self.crm = CRMIntegration.objects.create(company=self.company, provider='hubspot',
                                                 credentials={'access_token': 'synthetic-token'}, is_active=True)
        self.subscription = CompanyModulePurchase.objects.create(
            company=self.company, module_name='crm_sync_agent', status='active', is_complimentary=True)
        # The queue is worked in a background thread; here it is only filled.
        patcher = mock.patch.object(crm_signals, '_process_async')
        self.process = patcher.start()
        self.addCleanup(patcher.stop)
        self.lead = self.make_lead()

    def queued(self, kind):
        return list(CRMSyncQueue.objects.filter(object_type=kind).order_by('id'))


class ReplyNoteTests(CRMBase):

    def reply(self, enrollment, text='Sounds interesting, tell me more', sentiment='positive', at=None):
        enrollment.replied_at = at or timezone.now()
        enrollment.reply_content = text
        enrollment.reply_sentiment = sentiment
        enrollment.save(update_fields=['replied_at', 'reply_content', 'reply_sentiment'])

    def test_a_reply_is_written_to_the_crm_with_what_was_said(self):
        enrollment = self.enroll(self.lead)
        self.reply(enrollment)
        note, = self.queued(CRMSyncQueue.TYPE_NOTE)
        self.assertEqual(note.payload['email'], 'bob@acme.com')
        self.assertIn('Sounds interesting, tell me more', note.payload['note_body'])
        self.assertIn('positive', note.payload['note_body'])
        self.process.assert_called()

    def test_later_saves_of_the_same_enrollment_do_not_send_it_again(self):
        enrollment = self.enroll(self.lead)
        self.reply(enrollment)
        enrollment.status = 'replied'
        enrollment.save()
        self.assertEqual(len(self.queued(CRMSyncQueue.TYPE_NOTE)), 1)
        # ... nor once the note has gone to the CRM and left the queue.
        CRMSyncQueue.objects.update(status=CRMSyncQueue.STATUS_DONE)
        enrollment.current_step = 2
        enrollment.save()
        self.assertEqual(len(self.queued(CRMSyncQueue.TYPE_NOTE)), 1)

    def test_a_second_reply_is_a_second_note(self):
        enrollment = self.enroll(self.lead)
        self.reply(enrollment, at=timezone.now() - timedelta(days=2))
        CRMSyncQueue.objects.update(status=CRMSyncQueue.STATUS_DONE)
        self.reply(enrollment, text='Actually, call me Thursday')
        first, second = self.queued(CRMSyncQueue.TYPE_NOTE)
        self.assertIn('call me Thursday', second.payload['note_body'])
        self.assertNotIn('call me Thursday', first.payload['note_body'])

    def test_an_enrollment_with_no_reply_sends_nothing(self):
        enrollment = self.enroll(self.lead)
        enrollment.current_step = 1
        enrollment.save()
        self.assertEqual(self.queued(CRMSyncQueue.TYPE_NOTE), [])

    def test_a_reply_time_with_nothing_said_sends_nothing(self):
        # e.g. the unsubscribe link, which stamps the time and has no words.
        enrollment = self.enroll(self.lead)
        enrollment.replied_at = timezone.now()
        enrollment.save(update_fields=['replied_at'])
        self.assertEqual(self.queued(CRMSyncQueue.TYPE_NOTE), [])

    def test_notes_switched_off_for_the_crm_stay_off(self):
        CRMIntegration.objects.filter(pk=self.crm.pk).update(sync_notes=False)
        self.reply(self.enroll(self.lead))
        self.assertEqual(self.queued(CRMSyncQueue.TYPE_NOTE), [])


class MeetingTests(CRMBase):

    def meeting(self, **fields):
        return SDRMeeting.objects.create(company_user=self.cu, lead=self.lead, **fields)

    def test_a_meeting_with_no_time_yet_is_not_sent(self):
        self.meeting(status='pending')
        self.assertEqual(self.queued(CRMSyncQueue.TYPE_MEETING), [])

    def test_nor_is_a_time_still_waiting_for_the_leads_yes(self):
        self.meeting(status='awaiting_approval', scheduled_at=timezone.now() + timedelta(days=2))
        self.assertEqual(self.queued(CRMSyncQueue.TYPE_MEETING), [])

    def test_it_is_sent_when_the_time_is_set_with_its_real_start_and_end(self):
        meeting = self.meeting(status='pending', duration_minutes=45)
        when = (timezone.now() + timedelta(days=3)).replace(microsecond=0)
        meeting.scheduled_at, meeting.status = when, 'scheduled'
        meeting.save()
        row, = self.queued(CRMSyncQueue.TYPE_MEETING)
        self.assertEqual(row.payload['start_time'], when.isoformat())
        self.assertEqual(row.payload['end_time'], (when + timedelta(minutes=45)).isoformat())

    def test_a_meeting_made_by_hand_with_a_time_is_sent_straight_away(self):
        when = timezone.now() + timedelta(days=1)
        self.meeting(status='scheduled', scheduled_at=when, is_manual=True)
        self.assertEqual(len(self.queued(CRMSyncQueue.TYPE_MEETING)), 1)

    def test_it_is_sent_once(self):
        meeting = self.meeting(status='scheduled', scheduled_at=timezone.now() + timedelta(days=1))
        meeting.notes = 'Bring the pricing sheet'
        meeting.save()
        self.assertEqual(len(self.queued(CRMSyncQueue.TYPE_MEETING)), 1)

    def test_a_new_time_updates_one_still_waiting_but_never_adds_a_second_in_the_crm(self):
        meeting = self.meeting(status='scheduled', scheduled_at=timezone.now() + timedelta(days=1))
        moved = (timezone.now() + timedelta(days=4)).replace(microsecond=0)
        meeting.scheduled_at = moved
        meeting.save()
        row, = self.queued(CRMSyncQueue.TYPE_MEETING)
        self.assertEqual(row.payload['start_time'], moved.isoformat())      # still in the queue: brought up to date

        CRMSyncQueue.objects.update(status=CRMSyncQueue.STATUS_DONE)        # it has gone to the CRM
        meeting.scheduled_at = moved + timedelta(days=1)
        meeting.save()
        self.assertEqual(len(self.queued(CRMSyncQueue.TYPE_MEETING)), 1)

    def test_the_leads_confirm_page_sends_it_too(self):
        # That page changes the meeting with one UPDATE, which no listener sees.
        meeting = self.meeting(status='awaiting_approval', scheduled_at=timezone.now() + timedelta(days=2))
        response = self.client.post(f'/api/sdr/meeting-approval/{meeting.approval_token}/yes/')
        self.assertEqual(response.status_code, 200)
        meeting.refresh_from_db()
        self.assertEqual(meeting.status, 'scheduled')
        self.assertEqual(len(self.queued(CRMSyncQueue.TYPE_MEETING)), 1)


class QueueWorkerTests(CRMBase):

    def setUp(self):
        super().setUp()
        mock.patch.stopall()            # the real _process_async, with the thread held back

    def start(self):
        with mock.patch('crm_sync_agent.signals.threading.Thread') as thread:
            crm_signals._process_async(self.company)
        return thread.called

    def test_the_queue_is_worked_while_the_company_has_crm_sync(self):
        self.assertTrue(self.start())

    def test_and_waits_once_it_has_lapsed(self):
        CompanyModulePurchase.objects.filter(pk=self.subscription.pk).update(status='cancelled')
        self.assertFalse(self.start())
