"""The AI SDR's calls through its API: the Meetings screen (list, open, edit, delete, confirm a time, send a
reminder, write prep notes, resend the scheduling email), the links in the lead's emails (Yes, Suggest another time,
Unsubscribe, the booking page) and the Google Calendar setup helper. Each endpoint is checked for bad input, for
another company's or login's calls, for who may call it, and for what it changes when it works. Nothing leaves the
process: the AI, Google, and mail are mocked.
"""
import os
from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import Client, override_settings
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from ai_sdr_agent.agents import meeting_scheduling_agent as msa
from ai_sdr_agent.agents import outreach_agent as oa
from ai_sdr_agent.models import SDRCampaign, SDRLead, SDRMeeting
from ai_sdr_agent.tests import SDRBase, work_time
from api.views import ai_sdr_agent as views
from core.do_not_email import UNSUBSCRIBED, block, is_blocked
from core.models import Company, CompanyUser

NO_AI = 'ai_sdr_agent.agents.sdr_key_resolver.resolve_sdr_groq_client'


def ai_answer(text):
    return mock.MagicMock(choices=[mock.MagicMock(message=mock.MagicMock(content=text))], usage=None)


class MeetingBase(SDRBase):
    """A lead with a call, a second login in the same company and a rival company with its own call."""

    def setUp(self):
        super().setUp()
        cache.clear()                                   # the public booking links are throttled per IP
        self.rf = APIRequestFactory()
        self.lead = self.make_lead('kiran@clinic.example')
        self.enr = self.enroll(self.lead)
        self.colleague = CompanyUser.objects.create(
            company=self.company, email='colleague@test.local', full_name='Col', role='admin',
            password_hash='x', is_active=True)
        self.rival = Company.objects.create(name='Rival', email='rival@test.local')
        self.rita = CompanyUser.objects.create(
            company=self.rival, email='rita@rival.test', full_name='Rita', role='admin',
            password_hash='x', is_active=True)
        rival_campaign = SDRCampaign.objects.create(
            company_user=self.rita, name='R', status='active', smtp_host='smtp.test',
            smtp_username='u', smtp_password='p')
        rival_lead = SDRLead.objects.create(company_user=self.rita, email='zed@rival.example', first_name='Zed')
        self.theirs = SDRMeeting.objects.create(
            company_user=self.rita, lead=rival_lead, enrollment=self.enroll(rival_lead, campaign=rival_campaign),
            status='scheduled', scheduled_at=timezone.now() + timedelta(days=3), title='Their call')
        col_lead = SDRLead.objects.create(company_user=self.colleague, email='col@lead.example', first_name='C')
        self.colleagues = SDRMeeting.objects.create(
            company_user=self.colleague, lead=col_lead, status='scheduled',
            scheduled_at=timezone.now() + timedelta(days=4), title='Colleague call')

        patcher = mock.patch(NO_AI, return_value=(None, None))
        patcher.start()
        self.addCleanup(patcher.stop)

    def meeting(self, **kw):
        kw.setdefault('status', 'pending')
        return SDRMeeting.objects.create(company_user=self.cu, lead=self.lead, enrollment=self.enr, **kw)

    def call(self, view, method='post', data=None, user='me', **kw):
        req = getattr(self.rf, method)('/x', data or {}, format='json')
        if user == 'me':
            force_authenticate(req, user=self.cu)
        elif user is not None:
            force_authenticate(req, user=user)
        return view(req, **kw)

    def sender(self):
        """The one place a meeting email leaves from."""
        return mock.patch.object(msa.MeetingSchedulingAgent, '_send_email')


# ─────────────────────────────── who may call ─────────────────────────────────

class MeetingAuthTests(MeetingBase):

    def endpoints(self, m):
        return [
            (views.sdr_meetings_list, 'get', {}),
            (views.sdr_meetings_list, 'post', {}),
            (views.sdr_meeting_detail, 'get', {'meeting_id': m.id}),
            (views.sdr_meeting_detail, 'put', {'meeting_id': m.id}),
            (views.sdr_meeting_detail, 'delete', {'meeting_id': m.id}),
            (views.sdr_confirm_meeting, 'post', {'meeting_id': m.id}),
            (views.sdr_send_meeting_reminder, 'post', {'meeting_id': m.id}),
            (views.sdr_generate_meeting_prep, 'post', {'meeting_id': m.id}),
            (views.sdr_resend_scheduling_email, 'post', {'meeting_id': m.id}),
        ]

    def test_no_meeting_endpoint_answers_without_a_login(self):
        m = self.meeting(scheduled_at=timezone.now() + timedelta(days=2))
        with self.sender() as send:
            for view, method, kw in self.endpoints(m):
                with self.subTest(view=view.__name__, method=method):
                    resp = self.call(view, method, data={'scheduled_at': work_time(3).isoformat()}, user=None, **kw)
                    self.assertIn(resp.status_code, (401, 403))
        send.assert_not_called()
        self.assertTrue(SDRMeeting.objects.filter(pk=m.pk, status='pending').exists())

    def test_an_employee_login_that_is_not_a_company_user_is_refused(self):
        employee = User.objects.create_user('emp', 'emp@test.local', 'pw')
        m = self.meeting()
        for view, method, kw in self.endpoints(m):
            with self.subTest(view=view.__name__, method=method):
                self.assertEqual(self.call(view, method, user=employee, **kw).status_code, 403)

    def test_a_deactivated_company_user_is_refused(self):
        CompanyUser.objects.filter(pk=self.cu.pk).update(is_active=False)
        self.cu.refresh_from_db()
        m = self.meeting()
        self.assertEqual(self.call(views.sdr_meeting_detail, 'get', meeting_id=m.id).status_code, 403)
        self.assertEqual(self.call(views.sdr_meetings_list, 'get').status_code, 403)


# ─────────────────────────────── list and create ──────────────────────────────

class MeetingListTests(MeetingBase):

    def test_the_list_shows_only_this_logins_calls(self):
        mine = self.meeting()
        data = self.call(views.sdr_meetings_list, 'get').data
        self.assertEqual([r['id'] for r in data['results']], [mine.id])
        self.assertEqual(data['total'], 1)

    def test_the_status_filter_and_a_nonsense_page_number_work(self):
        self.meeting(status='pending')
        done = self.meeting(status='completed')
        req = self.rf.get('/x', {'status': 'completed', 'page': 'abc', 'page_size': 'zz'})
        force_authenticate(req, user=self.cu)
        resp = views.sdr_meetings_list(req)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual([r['id'] for r in resp.data['results']], [done.id])

    def test_creating_a_call_needs_a_lead(self):
        resp = self.call(views.sdr_meetings_list, data={'scheduled_at': work_time(3).isoformat()})
        self.assertEqual(resp.status_code, 400)
        self.assertIn('lead_id', resp.data['message'])

    def test_a_lead_that_does_not_exist_or_is_another_companys_is_not_found(self):
        rival_lead = self.theirs.lead
        for lead_id in (987654, rival_lead.id, self.colleagues.lead.id):
            with self.subTest(lead_id=lead_id):
                resp = self.call(views.sdr_meetings_list, data={'lead_id': lead_id})
                self.assertEqual(resp.status_code, 404)
                self.assertEqual(resp.data['message'], 'Lead not found.')
        self.assertFalse(SDRMeeting.objects.filter(company_user=self.cu).exists())

    def test_a_length_that_is_negative_zero_or_too_long_is_refused(self):
        for minutes in (-30, 0, 1000):
            with self.subTest(minutes=minutes):
                resp = self.call(views.sdr_meetings_list, data={'lead_id': self.lead.id, 'duration_minutes': minutes})
                self.assertEqual(resp.status_code, 400)
                self.assertIn('between 5 and 480', resp.data['message'])
        self.assertFalse(SDRMeeting.objects.filter(company_user=self.cu).exists())

    def test_a_booked_call_cannot_be_created_in_the_past(self):
        resp = self.call(views.sdr_meetings_list, data={
            'lead_id': self.lead.id, 'status': 'scheduled',
            'scheduled_at': (timezone.now() - timedelta(days=1)).isoformat()})
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(SDRMeeting.objects.filter(company_user=self.cu).exists())

    def test_a_booked_call_on_top_of_another_is_refused(self):
        when = work_time(3)
        self.meeting(status='scheduled', scheduled_at=when)
        resp = self.call(views.sdr_meetings_list, data={
            'lead_id': self.make_lead('o@o.example').id, 'status': 'scheduled',
            'scheduled_at': (when + timedelta(minutes=15)).isoformat()})
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(SDRMeeting.objects.filter(company_user=self.cu).count(), 1)

    def test_a_manual_call_is_created_with_a_default_title_and_length(self):
        resp = self.call(views.sdr_meetings_list, data={'lead_id': self.lead.id})
        self.assertEqual(resp.status_code, 201)
        m = SDRMeeting.objects.get(pk=resp.data['data']['id'])
        self.assertEqual((m.status, m.duration_minutes, m.is_manual, m.company_user_id),
                         ('pending', 30, True, self.cu.id))
        self.assertIn('Discovery Call with', m.title)


# ─────────────────────────────── open, edit, delete ───────────────────────────

class MeetingDetailTests(MeetingBase):

    def test_an_unknown_call_is_not_found(self):
        for method in ('get', 'put', 'delete'):
            with self.subTest(method=method):
                resp = self.call(views.sdr_meeting_detail, method, meeting_id=987654)
                self.assertEqual(resp.status_code, 404)
                self.assertEqual(resp.data['message'], 'Meeting not found.')

    def test_another_companys_or_another_logins_call_cannot_be_read_changed_or_deleted(self):
        for other in (self.theirs, self.colleagues):
            with self.subTest(owner=other.company_user.email):
                self.assertEqual(self.call(views.sdr_meeting_detail, 'get', meeting_id=other.id).status_code, 404)
                resp = self.call(views.sdr_meeting_detail, 'put', data={'title': 'Hacked', 'status': 'cancelled'},
                                 meeting_id=other.id)
                self.assertEqual(resp.status_code, 404)
                self.assertEqual(self.call(views.sdr_meeting_detail, 'delete', meeting_id=other.id).status_code, 404)
                other.refresh_from_db()
                self.assertEqual((other.status, other.title[:5]), ('scheduled', other.title[:5]))
                self.assertNotEqual(other.title, 'Hacked')

    def test_patch_is_not_offered(self):
        m = self.meeting()
        self.assertEqual(self.call(views.sdr_meeting_detail, 'patch', data={'title': 'x'}, meeting_id=m.id)
                         .status_code, 405)

    def test_an_edit_with_a_bad_length_or_status_changes_nothing(self):
        m = self.meeting(title='Keep')
        for bad in ({'duration_minutes': -10}, {'duration_minutes': 9999}, {'status': 'done'},
                    {'title': 'Changed', 'scheduled_at': 'tomorrow-ish'}):
            with self.subTest(data=bad):
                self.assertEqual(self.call(views.sdr_meeting_detail, 'put', data=bad, meeting_id=m.id).status_code,
                                 400)
        m.refresh_from_db()
        self.assertEqual((m.title, m.duration_minutes, m.status), ('Keep', 30, 'pending'))

    def test_moving_a_booked_call_onto_another_is_refused(self):
        when = work_time(3)
        self.meeting(status='scheduled', scheduled_at=when)
        m = self.meeting(status='scheduled', scheduled_at=when + timedelta(hours=3))
        resp = self.call(views.sdr_meeting_detail, 'put', data={'scheduled_at': when.isoformat()}, meeting_id=m.id)
        self.assertEqual(resp.status_code, 409)
        m.refresh_from_db()
        self.assertEqual(m.scheduled_at, when + timedelta(hours=3))

    def test_cancelling_a_booked_call_emails_the_lead_once(self):
        m = self.meeting(status='scheduled', scheduled_at=work_time(3))
        outreach = mock.MagicMock()
        with mock.patch.object(views, '_get_outreach_agent', return_value=outreach):
            resp = self.call(views.sdr_meeting_detail, 'put', data={'status': 'cancelled'}, meeting_id=m.id)
        self.assertEqual(resp.status_code, 200)
        m.refresh_from_db()
        self.assertEqual(m.status, 'cancelled')
        outreach.send_email.assert_called_once()
        self.assertEqual(outreach.send_email.call_args[0][1], 'kiran@clinic.example')

    def test_an_edit_saves_the_fields_sent(self):
        m = self.meeting()
        resp = self.call(views.sdr_meeting_detail, 'put', meeting_id=m.id,
                         data={'title': 'Demo', 'notes': 'Bring slides', 'duration_minutes': 45})
        self.assertEqual(resp.status_code, 200)
        m.refresh_from_db()
        self.assertEqual((m.title, m.notes, m.duration_minutes), ('Demo', 'Bring slides', 45))

    def test_the_owner_can_open_and_delete_their_call(self):
        m = self.meeting(title='Mine')
        self.assertEqual(self.call(views.sdr_meeting_detail, 'get', meeting_id=m.id).data['title'], 'Mine')
        self.assertEqual(self.call(views.sdr_meeting_detail, 'delete', meeting_id=m.id).status_code, 200)
        self.assertFalse(SDRMeeting.objects.filter(pk=m.pk).exists())


# ─────────────────────────────── Set Time & Confirm ───────────────────────────

class ConfirmMeetingTests(MeetingBase):

    def confirm(self, m, data, user='me'):
        with mock.patch.object(views, '_create_google_meet_link', return_value=None), self.sender() as send:
            resp = self.call(views.sdr_confirm_meeting, data=data, user=user, meeting_id=m.id)
        return resp, send

    def assertUnchanged(self, m):
        m.refresh_from_db()
        self.assertEqual((m.status, m.scheduled_at, m.confirmed_at), ('pending', None, None))

    def test_a_time_is_required(self):
        m = self.meeting()
        for data in ({}, {'scheduled_at': ''}):
            resp, send = self.confirm(m, data)
            self.assertEqual(resp.status_code, 400)
            self.assertEqual(resp.data['message'], 'scheduled_at is required.')
            send.assert_not_called()
        self.assertUnchanged(m)

    def test_a_time_that_is_not_a_date_is_refused_not_a_server_error(self):
        m = self.meeting()
        resp, send = self.confirm(m, {'scheduled_at': 'next tuesday'})
        self.assertEqual(resp.status_code, 400)
        send.assert_not_called()
        self.assertUnchanged(m)

    def test_a_time_in_the_past_is_refused(self):
        m = self.meeting()
        resp, send = self.confirm(m, {'scheduled_at': (timezone.now() - timedelta(days=1)).isoformat()})
        self.assertEqual(resp.status_code, 400)
        send.assert_not_called()
        self.assertUnchanged(m)

    def test_a_length_that_is_not_a_number_is_refused_not_a_server_error(self):
        m = self.meeting()
        resp, send = self.confirm(m, {'scheduled_at': work_time(3).isoformat(), 'duration_minutes': 'half an hour'})
        self.assertEqual(resp.status_code, 400)
        send.assert_not_called()
        self.assertUnchanged(m)

    def test_a_negative_length_is_refused(self):
        m = self.meeting()
        resp, send = self.confirm(m, {'scheduled_at': work_time(3).isoformat(), 'duration_minutes': -30})
        self.assertEqual(resp.status_code, 400)
        send.assert_not_called()
        self.assertUnchanged(m)

    def test_a_time_zone_that_does_not_exist_is_refused(self):
        m = self.meeting()
        resp, send = self.confirm(m, {'scheduled_at': work_time(3).isoformat(), 'browser_timezone': 'Mars/Olympus'})
        self.assertEqual(resp.status_code, 400)
        send.assert_not_called()
        m.refresh_from_db()
        self.assertEqual(m.lead_timezone, 'UTC')

    def test_an_unknown_or_someone_elses_call_cannot_be_confirmed(self):
        for meeting_id in (987654, self.theirs.id, self.colleagues.id):
            with self.subTest(meeting_id=meeting_id):
                m = SDRMeeting(id=meeting_id)
                resp, send = self.confirm(m, {'scheduled_at': work_time(5).isoformat()})
                self.assertEqual(resp.status_code, 404)
                send.assert_not_called()
        self.theirs.refresh_from_db()
        self.assertNotEqual(self.theirs.scheduled_at, work_time(5))

    def test_confirming_sets_the_time_books_the_lead_and_sends_one_email(self):
        m = self.meeting()
        when = work_time(3)
        resp, send = self.confirm(m, {'scheduled_at': when.isoformat(), 'duration_minutes': 45})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual((resp.data['mode'], resp.data['email_sent']), ('confirmed', True))
        m.refresh_from_db()
        self.lead.refresh_from_db()
        self.assertEqual((m.status, m.scheduled_at, m.duration_minutes), ('scheduled', when, 45))
        self.assertIsNotNone(m.confirmed_at)
        self.assertEqual(self.lead.status, 'meeting_scheduled')
        send.assert_called_once()
        self.assertEqual(send.call_args[0][1], 'kiran@clinic.example')
        self.assertTrue(send.call_args[0][2].startswith('Confirmed:'))

    def test_asking_the_lead_first_waits_for_them_and_sends_one_email(self):
        m = self.meeting()
        old_token = m.approval_token
        when = work_time(3)
        resp, send = self.confirm(m, {'scheduled_at': when.isoformat(), 'send_approval': True})
        self.assertEqual((resp.status_code, resp.data['mode']), (200, 'awaiting_approval'))
        m.refresh_from_db()
        self.assertEqual((m.status, m.scheduled_at), ('awaiting_approval', when))
        self.assertNotEqual(m.approval_token, old_token)
        send.assert_called_once()
        self.lead.refresh_from_db()
        self.assertNotEqual(self.lead.status, 'meeting_scheduled')

    def test_confirming_onto_another_booked_call_is_refused_and_nobody_is_emailed(self):
        when = work_time(3)
        self.meeting(status='scheduled', scheduled_at=when)
        m = self.meeting()
        resp, send = self.confirm(m, {'scheduled_at': (when + timedelta(minutes=10)).isoformat()})
        self.assertEqual(resp.status_code, 409)
        send.assert_not_called()
        self.assertUnchanged(m)

    def test_confirming_again_moves_the_call_and_its_google_event_without_a_second_event(self):
        m = self.meeting()
        first = work_time(3)
        second = first + timedelta(hours=2)
        made = {'event_id': 'ev-1', 'meet_url': 'https://meet.google.com/abc'}
        with mock.patch('core.google_calendar.create_google_event', return_value=made) as create, \
                mock.patch('core.google_calendar.update_google_event', return_value=True) as move, \
                self.sender() as send:
            self.call(views.sdr_confirm_meeting, data={'scheduled_at': first.isoformat()}, meeting_id=m.id)
            resp = self.call(views.sdr_confirm_meeting, data={'scheduled_at': second.isoformat()}, meeting_id=m.id)
        self.assertEqual(resp.status_code, 200)
        create.assert_called_once()
        move.assert_called_once()
        self.assertEqual(send.call_count, 2)                 # one confirmation per time set
        m.refresh_from_db()
        self.assertEqual((m.status, m.scheduled_at, m.google_event_id), ('scheduled', second, 'ev-1'))


# ─────────────────────────────── reminder ─────────────────────────────────────

class MeetingReminderTests(MeetingBase):

    def remind(self, m):
        with self.sender() as send:
            resp = self.call(views.sdr_send_meeting_reminder, meeting_id=m.id)
        return resp, send

    def test_an_unknown_or_someone_elses_call_gets_no_reminder(self):
        for meeting_id in (987654, self.theirs.id, self.colleagues.id):
            with self.subTest(meeting_id=meeting_id):
                resp, send = self.remind(SDRMeeting(id=meeting_id))
                self.assertEqual(resp.status_code, 404)
                send.assert_not_called()
        self.theirs.refresh_from_db()
        self.assertIsNone(self.theirs.reminder_sent_at)

    def test_a_call_without_a_campaign_mailbox_says_so(self):
        m = SDRMeeting.objects.create(company_user=self.cu, lead=self.lead, status='scheduled', is_manual=True,
                                      scheduled_at=work_time(2))
        resp, send = self.remind(m)
        self.assertEqual(resp.status_code, 400)
        self.assertIn('no associated campaign', resp.data['message'])
        send.assert_not_called()

    def test_a_reminder_sends_one_email_and_records_when(self):
        m = self.meeting(status='scheduled', scheduled_at=work_time(2))
        resp, send = self.remind(m)
        self.assertEqual(resp.status_code, 200)
        send.assert_called_once()
        campaign, to, subject = send.call_args[0][:3]
        self.assertEqual((campaign, to), (self.campaign, 'kiran@clinic.example'))
        self.assertTrue(subject.startswith('Reminder:'))
        m.refresh_from_db()
        self.assertIsNotNone(m.reminder_sent_at)

    def test_a_failed_send_is_reported_and_not_recorded_as_sent(self):
        m = self.meeting(status='scheduled', scheduled_at=work_time(2))
        with mock.patch.object(msa.MeetingSchedulingAgent, '_send_email', side_effect=ValueError('SMTP error: 535')):
            resp = self.call(views.sdr_send_meeting_reminder, meeting_id=m.id)
        self.assertGreaterEqual(resp.status_code, 400)
        self.assertIn('535', resp.data['message'])
        m.refresh_from_db()
        self.assertIsNone(m.reminder_sent_at)

    def test_a_call_with_no_time_or_that_was_cancelled_gets_no_reminder(self):
        for kw in ({'status': 'pending'}, {'status': 'cancelled', 'scheduled_at': work_time(2)}):
            with self.subTest(**{k: str(v) for k, v in kw.items()}):
                m = self.meeting(**kw)
                resp, send = self.remind(m)
                self.assertEqual(resp.status_code, 400)
                send.assert_not_called()
                m.refresh_from_db()
                self.assertIsNone(m.reminder_sent_at)

    def test_a_lead_on_the_do_not_email_list_is_not_reminded_and_it_is_not_a_server_error(self):
        m = self.meeting(status='scheduled', scheduled_at=work_time(2))
        block(self.company.id, 'kiran@clinic.example', UNSUBSCRIBED, source='test')
        with mock.patch('smtplib.SMTP') as smtp, \
                mock.patch('ai_sdr_agent.agents.outreach_agent.validate_mail_server', return_value=None):
            resp = self.call(views.sdr_send_meeting_reminder, meeting_id=m.id)
        smtp.assert_not_called()
        self.assertIn(resp.status_code, (400, 409))
        m.refresh_from_db()
        self.assertIsNone(m.reminder_sent_at)


# ─────────────────────────────── prep notes ───────────────────────────────────

class MeetingPrepTests(MeetingBase):

    def test_an_unknown_or_someone_elses_call_gets_no_notes(self):
        for meeting_id in (987654, self.theirs.id, self.colleagues.id):
            with self.subTest(meeting_id=meeting_id):
                self.assertEqual(self.call(views.sdr_generate_meeting_prep, meeting_id=meeting_id).status_code, 404)
        self.theirs.refresh_from_db()
        self.assertEqual(self.theirs.prep_notes, {})

    def test_the_ais_notes_are_saved_on_the_call(self):
        m = self.meeting(reply_snippet='Yes, a demo please')
        client = mock.MagicMock()
        client.chat.completions.create.return_value = ai_answer(
            '{"summary": "Kiran wants a demo", "talking_points": ["Booking app"]}')
        with mock.patch(NO_AI, return_value=(client, None)):
            resp = self.call(views.sdr_generate_meeting_prep, meeting_id=m.id)
        self.assertEqual(resp.status_code, 200)
        m.refresh_from_db()
        self.assertEqual(m.prep_notes['summary'], 'Kiran wants a demo')
        self.assertEqual(resp.data['prep_notes'], m.prep_notes)
        self.assertIn('Yes, a demo please', client.chat.completions.create.call_args.kwargs['messages'][-1]['content'])

    def test_when_the_ai_fails_twice_plain_notes_are_saved_instead(self):
        m = self.meeting()
        client = mock.MagicMock()
        client.chat.completions.create.side_effect = RuntimeError('model down')
        with mock.patch(NO_AI, return_value=(client, None)):
            resp = self.call(views.sdr_generate_meeting_prep, meeting_id=m.id)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(client.chat.completions.create.call_count, 2)
        m.refresh_from_db()
        self.assertTrue(m.prep_notes)

    def test_a_manual_call_without_a_campaign_still_gets_notes(self):
        m = SDRMeeting.objects.create(company_user=self.cu, lead=self.lead, is_manual=True)
        resp = self.call(views.sdr_generate_meeting_prep, meeting_id=m.id)
        self.assertEqual(resp.status_code, 200)
        m.refresh_from_db()
        self.assertTrue(m.prep_notes)


# ─────────────────────────────── resend scheduling email ──────────────────────

class ResendSchedulingTests(MeetingBase):

    def test_an_unknown_or_someone_elses_call_is_not_emailed(self):
        with self.sender() as send:
            for meeting_id in (987654, self.theirs.id, self.colleagues.id):
                with self.subTest(meeting_id=meeting_id):
                    resp = self.call(views.sdr_resend_scheduling_email, meeting_id=meeting_id)
                    self.assertEqual(resp.status_code, 404)
        send.assert_not_called()

    def test_a_call_without_a_campaign_mailbox_says_so(self):
        m = SDRMeeting.objects.create(company_user=self.cu, lead=self.lead, is_manual=True)
        with self.sender() as send:
            resp = self.call(views.sdr_resend_scheduling_email, meeting_id=m.id)
        self.assertEqual(resp.status_code, 400)
        self.assertIn('no associated campaign', resp.data['message'])
        send.assert_not_called()

    def test_the_email_with_the_booking_link_goes_once_and_is_recorded(self):
        m = self.meeting()
        with self.sender() as send:
            resp = self.call(views.sdr_resend_scheduling_email, meeting_id=m.id)
        self.assertEqual(resp.status_code, 200)
        send.assert_called_once()
        _campaign, to, _subject, plain = send.call_args[0][:4]
        self.assertEqual(to, 'kiran@clinic.example')
        self.assertIn(f'/book/{m.booking_token}', plain)
        m.refresh_from_db()
        self.assertIsNotNone(m.scheduling_email_sent_at)

    def test_a_failed_send_is_reported_and_not_recorded(self):
        m = self.meeting()
        with mock.patch.object(msa.MeetingSchedulingAgent, '_send_email', side_effect=ValueError('SMTP error: 421')):
            resp = self.call(views.sdr_resend_scheduling_email, meeting_id=m.id)
        self.assertGreaterEqual(resp.status_code, 400)
        self.assertIn('421', resp.data['message'])
        m.refresh_from_db()
        self.assertIsNone(m.scheduling_email_sent_at)


# ─────────────────────────────── the lead's Yes link ──────────────────────────

class LeadApprovalLinkTests(MeetingBase):

    def path(self, token, action='yes'):
        return f'/api/sdr/meeting-approval/{token}/{action}/'

    def proposed(self, **kw):
        kw.setdefault('scheduled_at', work_time(3))
        return self.meeting(status='awaiting_approval', **kw)

    def test_an_unknown_token_shows_the_expired_page_with_a_not_found_status(self):
        for method in ('get', 'post'):
            with self.subTest(method=method):
                resp = getattr(Client(), method)(self.path('11111111-2222-3333-4444-555555555555'))
                self.assertEqual(resp.status_code, 404)
                self.assertIn(b'no longer valid', resp.content)

    def test_a_malformed_token_is_not_a_server_error(self):
        for token in ('abc', 'deadbeef', '0-0-0'):
            for method in ('get', 'post'):
                with self.subTest(token=token, method=method):
                    resp = getattr(Client(raise_request_exception=False), method)(self.path(token))
                    self.assertEqual(resp.status_code, 404)

    def test_needs_no_login_and_post_confirms_with_one_email(self):
        m = self.proposed()
        with mock.patch.object(views, '_create_google_meet_link', return_value=None), self.sender() as send:
            resp = Client().post(self.path(m.approval_token))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("You're all set", resp.content.decode())
        m.refresh_from_db()
        self.lead.refresh_from_db()
        self.assertEqual((m.status, self.lead.status), ('scheduled', 'meeting_scheduled'))
        self.assertIsNotNone(m.confirmed_at)
        send.assert_called_once()
        self.assertTrue(send.call_args[0][2].startswith('Confirmed:'))

    def test_opening_an_already_confirmed_link_says_so_and_changes_nothing(self):
        m = self.meeting(status='scheduled', scheduled_at=work_time(3))
        with self.sender() as send:
            resp = Client().get(self.path(m.approval_token))
        self.assertIn(b'already confirmed', resp.content)
        send.assert_not_called()

    def test_a_cancelled_call_cannot_be_brought_back_by_the_link(self):
        m = self.meeting(status='cancelled', scheduled_at=work_time(3))
        with self.sender() as send:
            resp = Client().post(self.path(m.approval_token))
        self.assertIn(b'no longer available', resp.content)
        m.refresh_from_db()
        self.assertEqual(m.status, 'cancelled')
        send.assert_not_called()

    def test_a_link_from_an_earlier_proposal_stops_working_once_a_new_time_is_proposed(self):
        m = self.proposed()
        old = m.approval_token
        with mock.patch.object(views, '_create_google_meet_link', return_value=None), self.sender():
            self.call(views.sdr_confirm_meeting, meeting_id=m.id,
                      data={'scheduled_at': work_time(4).isoformat(), 'send_approval': True})
            Client().post(self.path(old))
        m.refresh_from_db()
        self.assertEqual(m.status, 'awaiting_approval')

    def test_other_methods_are_refused(self):
        m = self.proposed()
        self.assertEqual(Client().put(self.path(m.approval_token)).status_code, 405)
        m.refresh_from_db()
        self.assertEqual(m.status, 'awaiting_approval')


# ─────────────────────────────── the lead's Suggest link ──────────────────────

class LeadSuggestLinkTests(MeetingBase):

    def path(self, token):
        return f'/api/sdr/meeting-approval/{token}/suggest/'

    def test_with_a_frontend_it_sends_the_lead_to_the_booking_page(self):
        m = self.meeting(status='awaiting_approval', scheduled_at=work_time(3))
        with override_settings(FRONTEND_URL='https://app.example'):
            resp = Client().get(self.path(m.approval_token))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp['Location'], f'https://app.example/book/{m.booking_token}/')
        m.refresh_from_db()
        self.assertEqual(m.status, 'awaiting_approval')

    def test_without_a_frontend_it_asks_them_to_reply_with_times(self):
        m = self.meeting(status='awaiting_approval', scheduled_at=work_time(3))
        with override_settings(FRONTEND_URL=''), mock.patch.dict(os.environ, {'FRONTEND_URL': ''}):
            resp = Client().get(self.path(m.approval_token))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('reply to the original email', resp.content.decode())

    def test_a_post_is_refused_and_changes_nothing(self):
        m = self.meeting(status='awaiting_approval', scheduled_at=work_time(3))
        self.assertEqual(Client().post(self.path(m.approval_token)).status_code, 405)
        m.refresh_from_db()
        self.assertEqual(m.status, 'awaiting_approval')

    def test_an_unknown_token_shows_the_expired_page_with_a_not_found_status(self):
        resp = Client().get(self.path('11111111-2222-3333-4444-555555555555'))
        self.assertEqual(resp.status_code, 404)
        self.assertIn(b'no longer valid', resp.content)

    def test_a_malformed_token_is_not_a_server_error(self):
        resp = Client(raise_request_exception=False).get(self.path('abc'))
        self.assertEqual(resp.status_code, 404)


# ─────────────────────────────── Unsubscribe link ─────────────────────────────

class UnsubscribeEndpointTests(MeetingBase):
    """Adds to tests_unsubscribe_link.py: methods, repeat clicks, neighbours, booked calls."""

    def link(self, enrollment=None):
        url = oa.build_unsubscribe_url(enrollment or self.enr)
        return '/api/sdr/unsubscribe/' + url.split('/api/sdr/unsubscribe/')[1]

    def test_only_get_and_post_are_answered(self):
        for method in ('put', 'delete', 'patch'):
            with self.subTest(method=method):
                self.assertEqual(getattr(Client(), method)(self.link()).status_code, 405)
        self.assertFalse(is_blocked(self.company.id, 'kiran@clinic.example'))

    def test_a_token_with_odd_characters_is_refused_not_a_server_error(self):
        for token in ('a:b:c', '---', 'x' * 400, ':'):
            with self.subTest(token=token[:10]):
                resp = Client(raise_request_exception=False).post(f'/api/sdr/unsubscribe/{token}/')
                self.assertEqual(resp.status_code, 404)

    def test_clicking_twice_still_says_done_and_blocks_once(self):
        self.assertEqual(Client().post(self.link()).status_code, 200)
        self.assertEqual(Client().post(self.link()).status_code, 200)
        self.assertTrue(is_blocked(self.company.id, 'kiran@clinic.example'))

    def test_another_lead_of_the_same_company_keeps_getting_emails(self):
        neighbour = self.enroll(self.make_lead('sara@clinic.example'))
        Client().post(self.link())
        neighbour.refresh_from_db()
        self.assertEqual(neighbour.status, 'active')
        self.assertFalse(is_blocked(self.company.id, 'sara@clinic.example'))

    def test_the_link_cancels_the_leads_booked_call(self):
        booked = self.meeting(status='scheduled', scheduled_at=work_time(3))
        self.assertEqual(Client().get(self.link()).status_code, 200)
        booked.refresh_from_db()
        self.assertEqual(booked.status, 'scheduled')                     # opening the link cancels nothing
        Client().post(self.link())
        booked.refresh_from_db()
        self.enr.refresh_from_db()
        self.assertEqual((booked.status, self.enr.status), ('cancelled', 'unsubscribed'))

    def test_after_unsubscribing_no_meeting_email_reaches_them(self):
        m = self.meeting(status='scheduled', scheduled_at=work_time(2))
        Client().post(self.link())
        SDRMeeting.objects.filter(pk=m.pk).update(status='scheduled')   # even if the call were put back
        with mock.patch('smtplib.SMTP') as smtp, \
                mock.patch('ai_sdr_agent.agents.outreach_agent.validate_mail_server', return_value=None):
            self.call(views.sdr_send_meeting_reminder, meeting_id=m.id)
        smtp.assert_not_called()


# ─────────────────────────────── booking page ─────────────────────────────────

class BookingEndpointTests(MeetingBase):
    """Adds to BookingTests and BookingPageTests: bad links, expiry, bad times, the one email."""

    def info(self, token):
        return Client(raise_request_exception=False).get(f'/api/sdr/book/{token}/')

    def book(self, token, data):
        return Client(raise_request_exception=False).post(
            f'/api/sdr/book/{token}/confirm/', data, content_type='application/json')

    def test_an_unknown_link_is_not_found(self):
        token = '11111111-2222-3333-4444-555555555555'
        self.assertEqual(self.info(token).status_code, 404)
        resp = self.book(token, {'scheduled_at': work_time(3).isoformat()})
        self.assertEqual((resp.status_code, resp.json()['error']), (404, 'Booking link not found.'))

    def test_a_malformed_link_is_not_found_not_a_server_error(self):
        for token in ('abc', 'deadbeef'):
            with self.subTest(token=token):
                self.assertEqual(self.info(token).status_code, 404)
                self.assertEqual(self.book(token, {'scheduled_at': work_time(3).isoformat()}).status_code, 404)

    def test_an_old_unbooked_link_has_expired(self):
        m = self.meeting(created_at=timezone.now() - timedelta(days=views.BOOKING_LINK_TTL_DAYS + 1))
        self.assertEqual(self.info(m.booking_token).status_code, 410)
        resp = self.book(m.booking_token, {'scheduled_at': work_time(3).isoformat()})
        self.assertEqual((resp.status_code, resp.json()['error']), (410, 'expired'))
        m.refresh_from_db()
        self.assertEqual(m.status, 'pending')

    def test_an_old_link_to_a_booked_call_still_shows_it(self):
        when = work_time(2)
        m = self.meeting(status='scheduled', scheduled_at=when, calendar_link='https://meet.jit.si/SDR-x',
                         created_at=timezone.now() - timedelta(days=60))
        data = self.info(m.booking_token).json()
        self.assertTrue(data['already_booked'])
        self.assertEqual((data['free_slots'], data['meet_link']), ([], 'https://meet.jit.si/SDR-x'))

    def test_opening_the_page_changes_nothing(self):
        m = self.meeting()
        resp = self.info(m.booking_token)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()['already_booked'])
        m.refresh_from_db()
        self.assertEqual((m.status, m.scheduled_at), ('pending', None))

    def test_the_page_does_not_offer_another_salespersons_busy_time_as_taken(self):
        m = self.meeting()
        slots = self.info(m.booking_token).json()['free_slots']
        self.theirs.scheduled_at = timezone.datetime.fromisoformat(slots[0])
        self.theirs.save()
        self.assertIn(slots[0], self.info(m.booking_token).json()['free_slots'])   # another company's call

    def test_a_missing_bad_or_past_time_is_refused(self):
        m = self.meeting()
        cases = [({}, 'scheduled_at is required.'),
                 ({'scheduled_at': ''}, 'scheduled_at is required.'),
                 ({'scheduled_at': '31/12/2030 10am'}, 'Invalid date format. Use ISO 8601.'),
                 ({'scheduled_at': (timezone.now() - timedelta(hours=1)).isoformat()},
                  'Please select a future date and time.')]
        for data, message in cases:
            with self.subTest(data=data):
                resp = self.book(m.booking_token, data)
                self.assertEqual((resp.status_code, resp.json()['error']), (400, message))
        m.refresh_from_db()
        self.assertEqual((m.status, m.scheduled_at), ('pending', None))

    def test_the_page_only_accepts_post_to_book(self):
        m = self.meeting()
        resp = Client().get(f'/api/sdr/book/{m.booking_token}/confirm/')
        self.assertEqual(resp.status_code, 405)

    def test_a_cancelled_call_cannot_be_booked_from_its_old_link(self):
        m = self.meeting(status='cancelled')
        resp = self.book(m.booking_token, {'scheduled_at': work_time(3).isoformat()})
        self.assertEqual(resp.status_code, 400)
        m.refresh_from_db()
        self.assertEqual(m.status, 'cancelled')

    def test_booking_needs_no_login_sets_the_time_and_sends_one_email(self):
        m = self.meeting()
        when = work_time(3)
        with mock.patch('core.google_calendar.create_google_event', return_value=None), self.sender() as send:
            resp = self.book(m.booking_token, {'scheduled_at': when.isoformat()})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['status'], 'confirmed')
        m.refresh_from_db()
        self.assertEqual((m.status, m.scheduled_at), ('scheduled', when))
        send.assert_called_once()
        self.assertEqual(send.call_args[0][1], 'kiran@clinic.example')

    def test_another_companys_booked_call_does_not_block_the_slot(self):
        when = work_time(3)
        SDRMeeting.objects.filter(pk=self.theirs.pk).update(scheduled_at=when)
        m = self.meeting()
        with mock.patch('core.google_calendar.create_google_event', return_value=None), self.sender():
            self.assertEqual(self.book(m.booking_token, {'scheduled_at': when.isoformat()}).status_code, 200)


# ─────────────────────────────── Google Calendar setup helper ─────────────────

@override_settings(DEBUG=True)
class GoogleAuthTests(MeetingBase):
    """The one-time helper that hands back a refresh token; ApiTests checks it is off outside DEBUG."""

    @override_settings(GOOGLE_CLIENT_ID='', GOOGLE_CLIENT_SECRET='')
    def test_start_without_google_keys_says_what_is_missing(self):
        resp = views.sdr_google_auth_start(self.rf.get('/api/sdr/google-auth/'))
        self.assertEqual(resp.status_code, 400)
        self.assertIn('GOOGLE_CLIENT_ID', resp.data['error'])

    @override_settings(GOOGLE_CLIENT_ID='cid.apps.googleusercontent.com', GOOGLE_CLIENT_SECRET='sec')
    def test_start_sends_the_browser_to_google_for_calendar_access(self):
        resp = views.sdr_google_auth_start(self.rf.get('/api/sdr/google-auth/'))
        self.assertEqual(resp.status_code, 302)
        location = resp['Location']
        self.assertTrue(location.startswith('https://accounts.google.com/o/oauth2/auth?'))
        for part in ('client_id=cid.apps.googleusercontent.com', 'access_type=offline',
                     'auth%2Fcalendar', 'google-auth%2Fcallback'):
            self.assertIn(part, location)
        self.assertNotIn('client_secret', location)

    def test_the_callback_without_a_code_is_refused_without_calling_google(self):
        with mock.patch('requests.post') as post:
            resp = views.sdr_google_auth_callback(self.rf.get('/api/sdr/google-auth/callback/'))
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data['error'], 'No code in callback')
        post.assert_not_called()

    @override_settings(GOOGLE_CLIENT_ID='cid', GOOGLE_CLIENT_SECRET='sec')
    def test_the_callback_exchanges_the_code_and_shows_the_refresh_token(self):
        with mock.patch('requests.post') as post:
            post.return_value.json.return_value = {'access_token': 'a', 'refresh_token': 'r-123'}
            resp = views.sdr_google_auth_callback(self.rf.get('/api/sdr/google-auth/callback/', {'code': 'c-1'}))
        self.assertEqual((resp.status_code, resp.data['refresh_token']), (200, 'r-123'))
        post.assert_called_once()
        sent = post.call_args.kwargs['data']
        self.assertEqual((sent['code'], sent['grant_type'], sent['client_id']), ('c-1', 'authorization_code', 'cid'))

    def test_google_returning_no_refresh_token_is_reported(self):
        with mock.patch('requests.post') as post:
            post.return_value.json.return_value = {'error': 'invalid_grant'}
            resp = views.sdr_google_auth_callback(self.rf.get('/api/sdr/google-auth/callback/', {'code': 'old'}))
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data['error'], 'No refresh_token returned')
