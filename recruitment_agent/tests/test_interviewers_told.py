"""Interviewers are told about their interviews, and an interview cannot be
quietly put back on top of something else.

Colleagues added to an interview heard nothing at any point. And setting a
cancelled interview back to Scheduled saved its old hour onto everyone's
calendar unchecked, over anything booked in the meantime.
"""
from unittest import mock

from api.views.recruitment_agent import reschedule_interview, update_interview
from core.models import CalendarBlock, Notification
from recruitment_agent import interviewer_alerts
from recruitment_agent.agents.interview_scheduling import interview_scheduling_agent as scheduling
from recruitment_agent.models import Interview

from . import test_interview_scheduling as base      # the module, so its own tests are not collected here too


@mock.patch.object(scheduling, '_create_google_meet_link', return_value=None)
@mock.patch.object(scheduling.InterviewSchedulingAgent, 'send_confirmation_email', return_value=True)
@mock.patch.object(scheduling.InterviewSchedulingAgent, 'send_reschedule_email', return_value=True)
class InterviewersAreToldTests(base.InterviewSchedulingTests):
    # The parent's tests are not run a second time from here.
    locals().update({name: None for name in dir(base.InterviewSchedulingTests) if name.startswith('test_')})

    def setUp(self):
        super().setUp()
        self.tia = base.employee_login(self.company, 'tia@test.local', 'Tia')

    def patch(self, **data):
        return self.call(update_interview, 'patch', data, interview_id=self.interview.id)

    def told(self, user):
        return [(n.type, n.title) for n in Notification.objects.filter(user=user).order_by('id')]

    def forget(self):
        Notification.objects.all().delete()

    # ---- joining and leaving ------------------------------------------------

    def test_someone_added_before_a_time_is_picked_is_told_so(self, *_):
        self.patch(interviewer_ids=[self.sam.id])
        note = Notification.objects.get(user=self.sam)
        self.assertEqual((note.type, note.title), ('interview_added', "You're interviewing Cara Candidate"))
        self.assertIn('Backend engineer', note.message)
        self.assertIn('has not picked a time yet', note.message)
        self.assertEqual(note.action_url, '/me/meetings')

    def test_someone_added_to_a_booked_interview_is_told_when_it_is(self, *_):
        self.book()
        self.patch(interviewer_ids=[self.sam.id])
        self.assertIn('10:00', Notification.objects.get(user=self.sam).message)

    def test_they_are_emailed_as_well_as_alerted(self, *_):
        # In the bell only, an interviewer who was not signed in that day heard nothing.
        from django.core import mail
        self.book()
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            self.patch(interviewer_ids=[self.sam.id])
        [sent] = mail.outbox
        self.assertEqual((sent.to, sent.subject), ([self.sam.email], "You're interviewing Cara Candidate"))
        self.assertIn('10:00', sent.body)
        self.assertIn('/me/meetings', sent.body)

    def test_only_the_people_who_changed_are_told(self, *_):
        self.patch(interviewer_ids=[self.sam.id])
        self.forget()
        self.patch(interviewer_ids=[self.sam.id, self.tia.id])           # Tia joins; Sam was already on it
        self.assertEqual(self.told(self.sam), [])
        self.assertEqual([t for t, _ in self.told(self.tia)], ['interview_added'])
        self.forget()
        self.patch(interviewer_ids=[self.tia.id])                         # Sam is taken off
        self.assertEqual(self.told(self.sam), [('interview_removed', "You're no longer interviewing Cara Candidate")])
        self.assertEqual(self.told(self.tia), [])

    def test_a_busy_interviewer_who_is_refused_is_not_told_they_joined(self, *_):
        self.book()
        self.busy(self.sam, 10)
        code, _body = self.patch(interviewer_ids=[self.sam.id])
        self.assertEqual((code, self.told(self.sam)), (409, []))

    # ---- booked, moved, called off -------------------------------------------

    def test_they_hear_when_the_candidate_picks_a_time(self, *_):
        self.interview.interviewers.add(self.sam)
        self.book()
        note = Notification.objects.get(user=self.sam)
        self.assertEqual((note.type, note.title), ('interview_booked', 'Interview booked: Cara Candidate'))
        self.assertIn('10:00', note.message)

    def test_they_hear_when_it_moves(self, *_):
        self.interview.interviewers.add(self.sam)
        self.book()
        self.forget()
        code, body = self.call(reschedule_interview, interview_id=self.interview.id,
                               data={'new_slot_datetime': self.at(11).isoformat()})
        self.assertEqual(code, 200, body)
        note = Notification.objects.get(user=self.sam)
        self.assertEqual(note.title, 'Interview moved: Cara Candidate')
        self.assertIn('Now', note.message)
        self.assertIn('11:00', note.message)

    def test_they_hear_when_it_is_cancelled(self, *_):
        self.interview.interviewers.add(self.sam)
        self.book()
        self.forget()
        self.patch(status='CANCELLED')
        self.assertEqual(self.told(self.sam), [('interview_cancelled', 'Interview cancelled: Cara Candidate')])

    def test_they_hear_when_the_candidate_is_rejected_and_the_interview_removed(self, *_):
        from api.views.recruitment_agent import bulk_update_cv_records
        from recruitment_agent.models import CVRecord, JobDescription
        job = JobDescription.objects.create(title='Backend engineer', description='Build things ' * 3,
                                            company=self.company, company_user=self.recruiter)
        cv = CVRecord.objects.create(file_name='cara.pdf', job_description=job, parsed_json='{"name": "Cara"}')
        Interview.objects.filter(pk=self.interview.pk).update(cv_record=cv)
        self.interview.interviewers.add(self.sam)
        self.book()
        self.forget()
        with mock.patch.object(scheduling.InterviewSchedulingAgent, 'send_rejection_email', return_value=True):
            code, body = self.call(bulk_update_cv_records, 'post',
                                   {'cv_record_ids': [cv.id], 'qualification_decision': 'REJECT'})
        self.assertEqual(code, 200, body)
        self.assertFalse(Interview.objects.filter(pk=self.interview.pk).exists())
        self.assertEqual(self.told(self.sam), [('interview_cancelled', 'Interview cancelled: Cara Candidate')])

    def test_cancelling_one_that_was_never_booked_tells_nobody(self, *_):
        self.interview.interviewers.add(self.sam)
        self.patch(status='CANCELLED')
        self.assertEqual(self.told(self.sam), [])

    def test_other_changes_tell_nobody(self, *_):
        self.interview.interviewers.add(self.sam)
        self.book()
        self.forget()
        self.patch(meeting_link='https://meet.example/x')
        self.patch(status='COMPLETED', outcome='PASSED')
        self.assertEqual(self.told(self.sam), [])

    def test_an_alert_that_fails_never_undoes_the_booking(self, *_):
        self.interview.interviewers.add(self.sam)
        with mock.patch.object(interviewer_alerts, '_words', side_effect=RuntimeError('boom')):
            self.assertTrue(self.book()['success'])
        self.interview.refresh_from_db()
        self.assertEqual(self.interview.status, 'SCHEDULED')

    # ---- setting a cancelled interview back to Scheduled ---------------------

    def cancelled(self):
        self.interview.interviewers.add(self.sam)
        self.book()
        self.patch(status='CANCELLED')
        self.forget()

    def status(self):
        return Interview.objects.get(pk=self.interview.pk).status

    def test_putting_it_back_is_refused_when_someone_has_since_been_booked(self, *_):
        self.cancelled()
        self.busy(self.sam, 10)                                # booked into that hour meanwhile
        code, body = self.patch(status='SCHEDULED')
        self.assertEqual((code, body['code']), (409, 'schedule_conflict'), body)
        self.assertIn('Sam', body['message'])
        self.assertEqual(self.status(), 'CANCELLED')
        self.assertFalse(CalendarBlock.objects.filter(source='recruitment').exists())
        self.assertEqual(self.told(self.sam), [])

    def test_the_recruiter_being_busy_refuses_it_too(self, *_):
        self.cancelled()
        self.busy(self.rae, 10)
        self.assertEqual(self.patch(status='RESCHEDULED')[0], 409)

    def test_putting_it_back_works_when_everyone_is_free_and_they_are_told(self, *_):
        self.cancelled()
        code, body = self.patch(status='SCHEDULED')
        self.assertEqual((code, self.status()), (200, 'SCHEDULED'), body)
        self.assertTrue(CalendarBlock.objects.filter(source='recruitment', user=self.sam).exists())
        self.assertEqual(self.told(self.sam), [('interview_booked', 'Interview booked: Cara Candidate')])

    def test_an_interview_in_the_past_can_be_restored_without_a_check(self, *_):
        from datetime import timedelta
        from django.utils import timezone
        self.cancelled()
        long_ago = timezone.now() - timedelta(days=30)
        Interview.objects.filter(pk=self.interview.pk).update(scheduled_datetime=long_ago)
        CalendarBlock.objects.create(company=self.company, user=self.sam, starts_at=long_ago,
                                     ends_at=long_ago + timedelta(hours=1), source='pm', source_id=7,
                                     role='participant', response='accepted', title='Old meeting')
        self.assertEqual(self.patch(status='SCHEDULED')[0], 200)

    def test_a_status_change_between_booked_states_is_not_checked_again(self, *_):
        self.interview.interviewers.add(self.sam)
        self.book()
        self.busy(self.sam, 10, source='hr')                   # however it got there
        self.assertEqual(self.patch(status='RESCHEDULED')[0], 200)
