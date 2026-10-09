"""Google Calendar follows a meeting that moves.

An interview or a sales call put an event on the company's Google calendar
when it was booked. The event's id was not kept and nothing ever updated or
deleted one, so a meeting that moved or was called off stayed in Google at its
old time.
"""
from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from ai_sdr_agent.models import SDRLead, SDRMeeting
from core import google_calendar, google_events
from core.google_calendar import event_state
from core.models import Company, CompanyUser
from recruitment_agent.models import Interview


class GoogleEventsTestCase(TestCase):

    def setUp(self):
        self.company = Company.objects.create(name='Acme', email='acme@test.local')
        self.cu = CompanyUser.objects.create(company=self.company, email='rae@test.local', full_name='Rae Recruiter',
                                             role='admin', password_hash='x', is_active=True)
        self.when = (timezone.now() + timedelta(days=3)).replace(hour=10, minute=0, second=0, microsecond=0)
        update = mock.patch.object(google_calendar, 'update_google_event', return_value=True)
        delete = mock.patch.object(google_calendar, 'delete_google_event', return_value=True)
        self.update, self.delete = update.start(), delete.start()
        self.addCleanup(update.stop)
        self.addCleanup(delete.stop)

    def interview(self, event='ev-1', **fields):
        fields.setdefault('status', 'SCHEDULED')
        return Interview.objects.create(
            candidate_name='Cara Candidate', candidate_email='cara@test.local', job_role='Backend',
            available_slots_json='[]', company_user=self.cu, timezone_name='UTC',
            scheduled_datetime=self.when, duration_minutes=30, google_event_id=event,
            google_event_state=event_state(self.when, 30) if event else '', **fields)

    def call(self, event='ev-9', **fields):
        lead = SDRLead.objects.create(company_user=self.cu, email='bob@lead.example', first_name='Bob')
        fields.setdefault('status', 'scheduled')
        return SDRMeeting.objects.create(
            company_user=self.cu, lead=lead, scheduled_at=self.when, duration_minutes=30,
            google_event_id=event, google_event_state=event_state(self.when, 30) if event else '', **fields)

    def save(self, row, **changes):
        """Save a change the way a request does: Google hears once it has committed."""
        for name, value in changes.items():
            setattr(row, name, value)
        with self.captureOnCommitCallbacks(execute=True):
            row.save()
        return type(row).objects.get(pk=row.pk)


class InterviewEventTests(GoogleEventsTestCase):

    def test_moving_the_interview_moves_its_event(self):
        later = self.when + timedelta(hours=3)
        saved = self.save(self.interview(), scheduled_datetime=later)
        self.update.assert_called_once_with(self.company, 'ev-1', start_dt=later, duration_minutes=30)
        self.assertEqual(saved.google_event_state, event_state(later, 30))

    def test_a_longer_interview_is_a_changed_one(self):
        self.save(self.interview(), duration_minutes=60)
        self.update.assert_called_once_with(self.company, 'ev-1', start_dt=self.when, duration_minutes=60)

    def test_cancelling_it_removes_the_event_and_forgets_it(self):
        saved = self.save(self.interview(), status='CANCELLED')
        self.delete.assert_called_once_with(self.company, 'ev-1')
        self.assertEqual((saved.google_event_id, saved.google_event_state), ('', ''))
        self.update.assert_not_called()

    def test_a_finished_interview_keeps_its_event(self):
        saved = self.save(self.interview(), status='COMPLETED')
        self.delete.assert_not_called()
        self.assertEqual(saved.google_event_id, 'ev-1')

    def test_a_save_that_moves_nothing_asks_nothing_of_google(self):
        interview = self.interview()
        self.save(interview, notes='Bring the take-home task')
        with self.captureOnCommitCallbacks(execute=True):
            interview.save(update_fields=['notes'])
        self.update.assert_not_called()
        self.delete.assert_not_called()

    def test_following_by_hand_a_meeting_with_no_event_does_nothing(self):
        self.assertEqual(google_events.follow_meeting(self.interview(event='', status='CANCELLED')), '')
        self.delete.assert_not_called()

    def test_an_interview_with_no_event_is_left_alone(self):
        self.save(self.interview(event=''), scheduled_datetime=self.when + timedelta(days=1))
        self.save(self.interview(event=''), status='CANCELLED')
        self.update.assert_not_called()
        self.delete.assert_not_called()

    def test_google_hears_only_once_the_change_has_committed(self):
        interview = self.interview()
        interview.scheduled_datetime = self.when + timedelta(hours=1)
        with self.captureOnCommitCallbacks() as waiting:
            interview.save()
            self.update.assert_not_called()                          # still inside the booking's transaction
        self.assertEqual(len(waiting), 1)

    def test_deleting_the_interview_deletes_the_event_once_that_has_committed(self):
        interview = self.interview()
        with self.captureOnCommitCallbacks(execute=True):
            interview.delete()
            self.delete.assert_not_called()
        self.delete.assert_called_once_with(self.company, 'ev-1')

    def test_deleting_one_with_no_event_asks_nothing(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.interview(event='').delete()
        self.delete.assert_not_called()

    # ---- when Google does not answer --------------------------------------------------

    def test_a_failed_move_is_tried_again_at_the_next_save(self):
        self.update.return_value = False
        later = self.when + timedelta(hours=3)
        saved = self.save(self.interview(), scheduled_datetime=later)
        self.assertEqual(saved.google_event_state, event_state(self.when, 30))     # still what Google has
        self.update.return_value = True
        saved = self.save(saved, notes='again')
        self.assertEqual(self.update.call_count, 2)
        self.assertEqual(saved.google_event_state, event_state(later, 30))

    def test_a_failed_removal_keeps_the_id_so_it_can_be_tried_again(self):
        self.delete.return_value = False
        saved = self.save(self.interview(), status='CANCELLED')
        self.assertEqual(saved.google_event_id, 'ev-1')

    def test_a_crash_while_following_never_reaches_the_person_saving(self):
        self.update.side_effect = RuntimeError('boom')
        saved = self.save(self.interview(), scheduled_datetime=self.when + timedelta(hours=1))
        self.assertEqual(saved.scheduled_datetime, self.when + timedelta(hours=1))
        self.assertEqual(google_events.follow_meeting(saved), 'failed')


class SalesCallEventTests(GoogleEventsTestCase):

    def test_moving_the_call_moves_its_event(self):
        later = self.when + timedelta(days=1)
        saved = self.save(self.call(), scheduled_at=later)
        self.update.assert_called_once_with(self.company, 'ev-9', start_dt=later, duration_minutes=30)
        self.assertEqual(saved.google_event_state, event_state(later, 30))

    def test_cancelling_it_removes_the_event(self):
        saved = self.save(self.call(), status='cancelled')
        self.delete.assert_called_once_with(self.company, 'ev-9')
        self.assertEqual(saved.google_event_id, '')

    def test_a_call_that_happened_or_was_missed_keeps_its_event(self):
        for status in ('completed', 'no_show'):
            SDRLead.objects.all().delete()
            self.save(self.call(), status=status)
        self.delete.assert_not_called()

    def test_deleting_the_call_deletes_the_event(self):
        call = self.call()
        with self.captureOnCommitCallbacks(execute=True):
            call.delete()
        self.delete.assert_called_once_with(self.company, 'ev-9')

    def test_a_call_changed_without_a_save_can_be_followed_by_hand(self):
        call = self.call()
        later = self.when + timedelta(hours=2)
        SDRMeeting.objects.filter(pk=call.pk).update(scheduled_at=later)             # no signal
        call.refresh_from_db()
        self.assertEqual(google_events.follow_meeting(call), 'moved')
        self.update.assert_called_once_with(self.company, 'ev-9', start_dt=later, duration_minutes=30)


class FakeEvents:
    """Stands in for Google's `events()` resource and records what it is asked."""

    def __init__(self, fail=None):
        self.asked, self.fail = [], fail

    def __call__(self):
        return self

    def _ask(self, verb, **kwargs):
        self.asked.append((verb, kwargs))
        return self

    def insert(self, **kwargs):
        return self._ask('insert', **kwargs)

    def patch(self, **kwargs):
        return self._ask('patch', **kwargs)

    def delete(self, **kwargs):
        return self._ask('delete', **kwargs)

    def execute(self):
        if self.fail is not None:
            raise self.fail
        return {'id': 'ev-new', 'hangoutLink': 'https://meet.google.com/abc-defg-hij'}


class Gone(Exception):
    class resp:
        status = 404


class GoogleCallTests(TestCase):
    """What is asked of Google itself."""

    def setUp(self):
        self.company = Company.objects.create(name='Acme', email='acme@test.local')
        self.when = (timezone.now() + timedelta(days=3)).replace(microsecond=0)

    def google(self, fail=None):
        events = FakeEvents(fail)
        service = mock.Mock()
        service.events = events
        patcher = mock.patch.object(google_calendar, '_calendar', return_value=(service, 'primary'))
        patcher.start()
        self.addCleanup(patcher.stop)
        return events

    def test_a_new_event_gives_back_its_id_as_well_as_the_link(self):
        events = self.google()
        made = google_calendar.create_google_event(self.company, start_dt=self.when, duration_minutes=45,
                                                   summary='Interview', attendee_email='cara@test.local')
        self.assertEqual(made, {'event_id': 'ev-new', 'meet_url': 'https://meet.google.com/abc-defg-hij'})
        [(verb, sent)] = events.asked
        self.assertEqual((verb, sent['calendarId'], sent['conferenceDataVersion']), ('insert', 'primary', 1))
        self.assertEqual(sent['body']['end']['dateTime'], (self.when + timedelta(minutes=45)).isoformat())
        # The older call, for a caller that does not keep the event, still answers with the link.
        self.assertEqual(google_calendar.create_google_meet_link(self.company, start_dt=self.when),
                         'https://meet.google.com/abc-defg-hij')

    def test_a_move_changes_that_event_to_the_new_time_and_length(self):
        events = self.google()
        self.assertTrue(google_calendar.update_google_event(self.company, 'ev-1', start_dt=self.when,
                                                            duration_minutes=60))
        [(verb, sent)] = events.asked
        self.assertEqual((verb, sent['eventId'], sent['calendarId'], sent['sendUpdates']),
                         ('patch', 'ev-1', 'primary', 'none'))
        self.assertEqual((sent['body']['start']['dateTime'], sent['body']['end']['dateTime']),
                         (self.when.isoformat(), (self.when + timedelta(hours=1)).isoformat()))

    def test_a_removal_deletes_that_event(self):
        events = self.google()
        self.assertTrue(google_calendar.delete_google_event(self.company, 'ev-1'))
        self.assertEqual(events.asked, [('delete', {'calendarId': 'primary', 'eventId': 'ev-1', 'sendUpdates': 'none'})])

    def test_an_event_google_no_longer_has_counts_as_removed(self):
        self.google(fail=Gone())
        self.assertTrue(google_calendar.delete_google_event(self.company, 'ev-1'))

    def test_any_other_failure_is_a_failure_and_is_not_raised(self):
        self.google(fail=RuntimeError('quota'))
        self.assertFalse(google_calendar.delete_google_event(self.company, 'ev-1'))
        self.assertFalse(google_calendar.update_google_event(self.company, 'ev-1', start_dt=self.when))
        self.assertIsNone(google_calendar.create_google_event(self.company, start_dt=self.when))

    def test_a_company_that_has_not_connected_google_is_asked_nothing(self):
        # The real lookup: no connection is stored for this company.
        self.assertFalse(google_calendar.update_google_event(self.company, 'ev-1', start_dt=self.when))
        self.assertFalse(google_calendar.delete_google_event(self.company, 'ev-1'))
        self.assertIsNone(google_calendar.create_google_event(self.company, start_dt=self.when))

    def test_nothing_is_asked_about_an_event_with_no_id(self):
        events = self.google()
        self.assertFalse(google_calendar.update_google_event(self.company, '', start_dt=self.when))
        self.assertFalse(google_calendar.delete_google_event(self.company, ''))
        self.assertEqual(events.asked, [])
