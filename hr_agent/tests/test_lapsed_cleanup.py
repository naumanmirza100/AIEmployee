"""A lapsed agent's leave, holidays and meetings can still be taken off the calendar.

They go on blocking bookings in the other agents after the agent that made them
lapses. The only screens that could cancel them were that agent's own, which
are locked, so a wrong entry stayed until the company subscribed again or
support edited the database. A short list of calls now gets through the lock
for a company that had the agent, and the lock screen offers them.
"""
import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, SimpleTestCase
from django.utils import timezone

from core import leftovers
from core.models import CompanyModulePurchase
from hr_agent.models import HRMeeting, HRMeetingParticipant, Holiday, LeaveRequest

from .base import HRTestCase

MODULES = sorted({c.module for c in leftovers.CLEAN_UPS} | {'ai_sdr_agent', 'operations_agent'})


class TheListTests(SimpleTestCase):
    """core.leftovers.is_clean_up: what gets through, and nothing else."""

    def through(self, module, method, path, body=None):
        raw = b'' if body is None else json.dumps(body).encode()
        return leftovers.is_clean_up(module, method, path, lambda: raw)

    def test_every_listed_call_gets_through_for_its_own_agent_only(self):
        for c in leftovers.CLEAN_UPS:
            call = c.call(7)
            path = call['path'].lstrip('/')
            self.assertTrue(self.through(c.module, call['method'], path, call['body']), c.kind)
            self.assertTrue(self.through(c.module, call['method'], path + '/', call['body']), c.kind)
            for other in MODULES:
                if other != c.module:
                    self.assertFalse(self.through(other, call['method'], path, call['body']), (c.kind, other))

    def test_nothing_else_does(self):
        others = (
            ('GET', 'hr/holidays'), ('POST', 'hr/holidays/create'), ('GET', 'hr/holidays/7/delete'),
            ('POST', 'hr/holidays/7/delete'), ('GET', 'hr/leave-requests'), ('POST', 'hr/leave-requests/submit'),
            ('POST', 'hr/leave-requests/7/decide'), ('POST', 'hr/leave-requests/7/cancel'),
            ('GET', 'hr/leave-requests/7/withdraw'), ('POST', 'hr/meetings/7/respond'), ('GET', 'hr/employees'),
            ('POST', 'hr/meetings/7/cancel/again'), ('POST', 'x/hr/meetings/7/cancel'),
            ('POST', 'hr/meetings/seven/cancel'),
            ('GET', 'project-manager/ai/meetings/respond'), ('POST', 'project-manager/ai/meetings/schedule'),
            ('DELETE', 'frontline/tickets/7/delete'), ('GET', 'frontline/meetings/7/delete'),
            ('GET', 'recruitment/interviews/7'), ('POST', 'recruitment/interviews/7/reschedule'),
            ('POST', 'marketing/campaigns/7/delete'), ('POST', 'marketing/campaigns/7/start'),
            ('GET', 'marketing/campaigns/7/stop'),
        )
        for method, path in others:
            for module in MODULES:
                self.assertFalse(self.through(module, method, path, {}), (method, path, module))

    def test_an_address_that_does_more_gets_through_for_the_cancel_alone(self):
        def meeting(body):
            return self.through('project_manager_agent', 'POST', 'project-manager/ai/meetings/respond', body)
        self.assertTrue(meeting({'meeting_id': 3, 'action': 'withdrawn'}))
        self.assertTrue(meeting({'meeting_id': 3, 'action': 'Withdrawn', 'reason': 'Client moved'}))
        for body in ({'meeting_id': 3, 'action': 'accepted'}, {'meeting_id': 3, 'action': 'rejected'},
                     {'meeting_id': 3, 'action': 'counter_proposed', 'counter_time': '2030-01-01T10:00'},
                     {'meeting_id': 3, 'action': 'withdrawn', 'counter_time': '2030-01-01T10:00'},
                     {'meeting_id': 3}, {}, [], 'withdrawn', None):
            self.assertFalse(meeting(body), body)
        not_json = leftovers.is_clean_up('project_manager_agent', 'POST', 'project-manager/ai/meetings/respond',
                                         lambda: b'action=withdrawn')
        self.assertFalse(not_json)

        def interview(body, method='PATCH'):
            return self.through('recruitment_agent', method, 'recruitment/interviews/7/update', body)
        self.assertTrue(interview({'status': 'CANCELLED'}))
        self.assertTrue(interview({'status': 'cancelled'}, 'PUT'))
        for body in ({'status': 'SCHEDULED'}, {'status': 'CANCELLED', 'interviewer_ids': [1]},
                     {'status': 'CANCELLED', 'meeting_link': 'https://x.example'}, {'outcome': 'HIRED'}, {}):
            self.assertFalse(interview(body), body)

    def test_a_call_that_does_one_thing_is_not_asked_for_its_body(self):
        def never():
            raise AssertionError('the body was read')
        self.assertTrue(leftovers.is_clean_up('hr_agent', 'DELETE', 'hr/holidays/7/delete', never))
        self.assertFalse(leftovers.is_clean_up('hr_agent', 'GET', 'hr/holidays', never))


class LapsedCleanUpTests(HRTestCase):

    def setUp(self):
        super().setUp()
        self.day = timezone.localdate() + timedelta(days=20)
        self.soon = timezone.now() + timedelta(days=5)

    def lapse(self, module='hr_agent', status='cancelled', company=None):
        CompanyModulePurchase.objects.update_or_create(
            company=company or self.company, module_name=module,
            defaults={'status': status, 'is_complimentary': True})

    def found(self, login=None, module='hr_agent'):
        return leftovers.upcoming(login or self.admin, module)

    def kinds(self, login=None, module='hr_agent'):
        return [(e['kind'], e['id'], e['title']) for e in self.found(login, module)['items']]

    def remove(self, entry, login=None):
        call = entry['call']
        return self.send(self.http(login or self.admin), call['method'].lower(), '/api' + call['path'], call['body'])

    def with_calendars(self):
        """Dana and Mo also sign in as employees of the company, so each has a calendar that a sales
        call or an executive meeting of theirs occupies."""
        from core.models import UserProfile
        for record in (self.admin_emp, self.member_emp):
            UserProfile.objects.update_or_create(user=record.user, defaults={
                'company': self.company, 'role': 'team_member'})

    def hr_meeting(self, title='Review', **fields):
        meeting = HRMeeting.objects.create(company=self.company, title=title, organizer=self.admin_emp,
                                           scheduled_at=self.soon, **fields)
        HRMeetingParticipant.objects.create(meeting=meeting, employee=self.member_emp, status='accepted')
        return meeting

    # ---- through the lock ------------------------------------------------------

    def test_a_wrong_holiday_can_be_removed_after_hr_lapses_and_nothing_else_opens(self):
        holiday = Holiday.objects.create(company=self.company, name='Founders day', date=self.day)
        self.lapse()
        client = self.http(self.admin)
        self.assertEqual(self.send(client, 'get', '/api/hr/holidays')[0], 403)
        self.assertEqual(self.send(client, 'post', '/api/hr/holidays/create',
                                   {'name': 'Another', 'date': self.day.isoformat()})[0], 403)
        self.assertEqual(self.send(client, 'get', '/api/hr/employees')[0], 403)
        code, body = self.send(client, 'delete', f'/api/hr/holidays/{holiday.id}/delete')
        self.assertEqual(code, 200, body)
        self.assertFalse(Holiday.objects.filter(company=self.company).exists())

    def test_a_failed_card_counts_as_lapsed(self):
        holiday = Holiday.objects.create(company=self.company, name='Founders day', date=self.day)
        self.lapse(status='past_due')
        code, body = self.send(self.http(self.admin), 'delete', f'/api/hr/holidays/{holiday.id}/delete')
        self.assertEqual(code, 200, body)

    def test_the_versioned_address_of_frontline_works_the_same(self):
        from Frontline_agent.models import FrontlineMeeting
        meeting = FrontlineMeeting.objects.create(title='Customer call', company=self.company,
                                                  organizer=self.admin_emp.user, scheduled_at=self.soon)
        self.lapse('frontline_agent')
        client = self.http(self.admin)
        self.assertEqual(self.send(client, 'get', '/api/v1/frontline/meetings')[0], 403)
        code, body = self.send(client, 'delete', f'/api/v1/frontline/meetings/{meeting.id}/delete')
        self.assertEqual(code, 200, body)
        self.assertFalse(FrontlineMeeting.objects.exists())

    def test_a_company_that_never_had_the_agent_gets_nothing(self):
        holiday = Holiday.objects.create(company=self.company, name='Founders day', date=self.day)
        CompanyModulePurchase.objects.filter(company=self.company).delete()
        code, body = self.send(self.http(self.admin), 'delete', f'/api/hr/holidays/{holiday.id}/delete')
        self.assertEqual((code, body['reason']), (403, 'not_bought'))
        self.assertTrue(Holiday.objects.filter(pk=holiday.pk).exists())
        self.assertEqual(self.found(), {'items': [], 'others': 0, 'more': 0, 'note': ''})

    def test_who_may_remove_what_has_not_changed(self):
        holiday = Holiday.objects.create(company=self.company, name='Founders day', date=self.day)
        self.lapse()
        self.lapse(company=self.rival)
        code, body = self.send(self.http(self.member), 'delete', f'/api/hr/holidays/{holiday.id}/delete')
        self.assertEqual(code, 403)                                   # not an HR admin
        self.assertNotIn('reason', body)                              # ...said by HR, not by the lock
        code, _ = self.send(self.http(self.rival_admin), 'delete', f'/api/hr/holidays/{holiday.id}/delete')
        self.assertEqual(code, 404)                                   # another company's
        self.assertTrue(Holiday.objects.filter(pk=holiday.pk).exists())

    def test_the_gate_reads_the_body_and_the_view_still_gets_it(self):
        from project_manager_agent.models import MeetingParticipant, ScheduledMeeting
        meeting = ScheduledMeeting.objects.create(organizer=self.admin, invitee=self.member_emp.user,
                                                  title='Planning', proposed_time=self.soon, status='accepted')
        MeetingParticipant.objects.create(meeting=meeting, user=self.member_emp.user, status='accepted')
        self.lapse('project_manager_agent')
        client = self.http(self.admin)
        url = '/api/project-manager/ai/meetings/respond'
        code, body = self.send(client, 'post', url, {'meeting_id': meeting.id, 'action': 'rejected'})
        self.assertEqual((code, body.get('error')), (403, 'subscription_required'))
        code, body = self.send(client, 'post', url, {'meeting_id': meeting.id, 'action': 'withdrawn',
                                                     'reason': 'Client moved the deadline'})
        self.assertEqual(code, 200, body)
        meeting.refresh_from_db()
        self.assertEqual(meeting.status, 'withdrawn')

    # ---- what the lock screen offers ---------------------------------------------

    def test_it_lists_what_still_blocks_bookings_soonest_first(self):
        leave = self.leave_request(status='approved')                 # Mo, 10 to 12 days out
        self.leave_request(status='pending', start_date=self.day, end_date=self.day)    # may yet be refused
        holiday = Holiday.objects.create(company=self.company, name='Founders day', date=self.day)
        Holiday.objects.create(company=self.company, name='Lahore only', date=self.day, region='Lahore')
        Holiday.objects.create(company=self.company, name='Working Saturday', date=self.day + timedelta(days=1),
                               is_working_day=True)
        Holiday.objects.create(company=self.company, name='Last week', date=timezone.localdate() - timedelta(days=7))
        Holiday.objects.create(company=self.rival, name='Theirs', date=self.day)
        meeting = self.hr_meeting()
        self.hr_meeting('Called off', status='cancelled')
        HRMeeting.objects.create(company=self.company, title='Earlier today', organizer=self.admin_emp,
                                 scheduled_at=timezone.now() - timedelta(hours=6))
        HRMeeting.objects.create(company=self.company, title='Nobody with a login', scheduled_at=self.soon)

        self.assertEqual(self.kinds(), [])                            # HR is open: it has its own screens
        self.lapse()
        self.assertEqual(self.kinds(), [('hr_meeting', meeting.id, 'Review'), ('leave', leave.id, 'Mo Member'),
                                        ('holiday', holiday.id, 'Founders day')])
        found = self.found()
        self.assertEqual((found['others'], found['more']), (0, 0))
        on_leave = found['items'][1]
        self.assertEqual((on_leave['label'], on_leave['button'], on_leave['on'], on_leave['until']),
                         ('Leave', 'Withdraw leave', leave.start_date.isoformat(), leave.end_date.isoformat()))
        self.assertEqual(found['items'][0]['starts_at'], self.soon.isoformat())
        self.assertEqual(self.found(module='frontline_agent')['items'], [])      # never had it

    def test_every_entry_it_offers_can_be_removed_with_the_call_it_gives(self):
        leave = self.leave_request(status='approved')
        Holiday.objects.create(company=self.company, name='Founders day', date=self.day)
        meeting = self.hr_meeting()
        self.lapse()
        entries = self.found()['items']
        self.assertEqual(len(entries), 3)
        for entry in entries:
            code, body = self.remove(entry)
            self.assertEqual(code, 200, (entry['kind'], body))
        self.assertEqual(self.kinds(), [])
        leave.refresh_from_db()
        meeting.refresh_from_db()
        self.assertEqual((leave.status, meeting.status, Holiday.objects.filter(company=self.company).count()),
                         ('withdrawn', 'cancelled', 0))

    def test_a_login_sees_only_what_it_may_remove_and_how_many_more_there_are(self):
        mine = self.leave_request(status='approved')                                  # Mo's own
        self.leave_request(self.admin_emp, status='approved')                          # Dana's
        Holiday.objects.create(company=self.company, name='Founders day', date=self.day)
        private = self.hr_meeting('Exit interview', visibility='private')
        self.lapse()
        self.assertEqual(self.kinds(self.member), [('hr_meeting', private.id, 'Private meeting'),
                                                   ('leave', mine.id, 'Mo Member')])
        self.assertEqual(self.found(self.member)['others'], 2)
        self.assertIn(('hr_meeting', private.id, 'Exit interview'), self.kinds(self.admin))
        self.assertEqual(self.found(self.admin)['others'], 0)
        # ...and the call is refused for the rest, as it always was.
        theirs = next(e for e in self.found(self.admin)['items'] if e['kind'] == 'holiday')
        self.assertEqual(self.remove(theirs, self.member)[0], 403)

    def test_the_screen_asks_one_address_which_is_not_behind_the_lock(self):
        Holiday.objects.create(company=self.company, name='Founders day', date=self.day)
        self.lapse()
        code, body = self.send(self.http(self.admin), 'get', '/api/modules/hr_agent/leftovers')
        self.assertEqual((code, [e['title'] for e in body['items']], body['others']), (200, ['Founders day'], 0))
        self.assertIn('still block meeting bookings', body['note'])
        self.assertEqual(body['items'][0]['call'], {'method': 'DELETE', 'body': {},
                                                    'path': f"/hr/holidays/{body['items'][0]['id']}/delete"})
        self.assertIn(Client().get('/api/modules/hr_agent/leftovers').status_code, (401, 403))

    def test_only_so_many_are_listed(self):
        for offset in range(leftovers.LIMIT + 3):
            Holiday.objects.create(company=self.company, name=f'Day {offset}', date=self.day + timedelta(days=offset))
        self.lapse()
        found = self.found()
        self.assertEqual((len(found['items']), found['more']), (leftovers.LIMIT, 3))
        self.assertEqual(found['items'][0]['title'], 'Day 0')

    # ---- the other agents ----------------------------------------------------------

    def test_project_manager_meetings_are_for_their_organiser(self):
        from project_manager_agent.models import MeetingParticipant, ScheduledMeeting
        ids = {}
        for organiser in (self.admin, self.member):
            meeting = ScheduledMeeting.objects.create(organizer=organiser, invitee=self.member_emp.user,
                                                      title=f"{organiser.full_name}'s planning",
                                                      proposed_time=self.soon, status='accepted')
            MeetingParticipant.objects.create(meeting=meeting, user=self.member_emp.user, status='accepted')
            ids[organiser.id] = meeting.id
        ScheduledMeeting.objects.create(organizer=self.admin, title='Called off', proposed_time=self.soon,
                                        status='withdrawn')
        self.lapse('project_manager_agent')
        module = 'project_manager_agent'
        self.assertEqual(self.kinds(self.admin, module), [('pm_meeting', ids[self.admin.id], "Dana Admin's planning")])
        self.assertEqual(self.found(self.admin, module)['others'], 1)
        code, body = self.remove(self.found(self.admin, module)['items'][0])
        self.assertEqual(code, 200, body)
        self.assertEqual(self.kinds(self.admin, module), [])

    def test_a_frontline_meeting_an_interview_and_a_campaign(self):
        from Frontline_agent.models import FrontlineMeeting
        from marketing_agent.models import Campaign
        from recruitment_agent.models import Interview
        dana = self.admin_emp.user
        meeting = FrontlineMeeting.objects.create(title='Customer call', company=self.company, organizer=dana,
                                                  scheduled_at=self.soon)
        meeting.participants.add(self.member_emp.user)
        interview = Interview.objects.create(
            candidate_name='Cara Candidate', candidate_email='cara@test.local', job_role='Welder',
            available_slots_json='[]', company_user=self.admin, confirmation_token='tok-cara',
            status='SCHEDULED', scheduled_datetime=self.soon, timezone_name='UTC')
        interview.interviewers.add(self.member_emp.user)        # somebody whose calendar it is on
        Interview.objects.create(
            candidate_name='Not Booked', candidate_email='nb@test.local', job_role='Welder',
            available_slots_json='[]', company_user=self.admin, confirmation_token='tok-nb')
        owner = get_user_model().objects.get(email=self.admin.email)
        campaign = Campaign.objects.create(name='Spring', owner=owner)
        paused = Campaign.objects.create(name='Autumn', owner=owner)
        Campaign.objects.filter(pk=campaign.pk).update(status='active')
        Campaign.objects.filter(pk=paused.pk).update(status='paused')
        for module in ('frontline_agent', 'recruitment_agent', 'marketing_agent'):
            self.lapse(module)

        self.assertEqual(self.kinds(module='frontline_agent'), [('frontline_meeting', meeting.id, 'Customer call')])
        self.assertEqual(self.kinds(module='recruitment_agent'),
                         [('interview', interview.id, 'Cara Candidate (Welder)')])
        self.assertEqual(self.kinds(module='marketing_agent'), [('campaign', campaign.id, 'Spring')])
        self.assertEqual(self.kinds(self.member, 'marketing_agent'), [])       # a campaign is its owner's

        for module in ('frontline_agent', 'recruitment_agent', 'marketing_agent'):
            [entry] = self.found(module=module)['items']
            code, body = self.remove(entry)
            self.assertEqual(code, 200, (module, body))
            self.assertEqual(self.kinds(module=module), [])
        interview.refresh_from_db()
        campaign.refresh_from_db()
        self.assertEqual((interview.status, campaign.status, FrontlineMeeting.objects.count()),
                         ('CANCELLED', 'paused', 0))

    def test_an_executive_meeting_is_for_its_organiser_and_only_the_cancel_gets_through(self):
        # Executive meetings joined the shared calendar on 9 October and were not on this list: a lapsed
        # agent's meetings went on blocking the people in them with no way to clear one.
        from unittest import mock
        from meeting_agent.models import ExecutiveMeeting
        self.with_calendars()
        mine = ExecutiveMeeting.objects.create(organizer=self.admin, title='Board prep', scheduled_at=self.soon)
        ExecutiveMeeting.objects.create(organizer=self.member, title="Mo's review",
                                        scheduled_at=self.soon + timedelta(hours=3))
        ExecutiveMeeting.objects.create(organizer=self.admin, title='Called off', scheduled_at=self.soon,
                                        status='cancelled')
        module = 'exec_meeting_agent'
        self.lapse(module)
        self.assertEqual(self.kinds(self.admin, module), [('exec_meeting', mine.id, 'Board prep')])
        self.assertEqual(self.found(self.admin, module)['others'], 1)
        client = self.http(self.admin)
        address = f'/api/exec-meeting/meetings/{mine.id}'
        self.assertEqual(self.send(client, 'get', '/api/exec-meeting/meetings')[0], 403)
        self.assertEqual(self.send(client, 'patch', address, {'title': 'Renamed'})[0], 403)
        self.assertEqual(self.send(client, 'patch', address, {'status': 'cancelled', 'title': 'Renamed'})[0], 403)
        self.assertEqual(self.send(client, 'patch', address, {'status': 'scheduled'})[0], 403)
        with mock.patch('threading.Thread'):                # the people invited are emailed from a thread
            code, body = self.remove(self.found(self.admin, module)['items'][0])
        self.assertEqual(code, 200, body)
        mine.refresh_from_db()
        self.assertEqual((mine.status, mine.title), ('cancelled', 'Board prep'))
        self.assertEqual(self.kinds(self.admin, module), [])

    def test_a_sales_call_is_for_the_login_whose_call_it_is(self):
        from ai_sdr_agent.models import SDRLead, SDRMeeting
        self.with_calendars()
        lead = SDRLead.objects.create(company_user=self.admin, email='bob@lead.example', first_name='Bob')
        call = SDRMeeting.objects.create(company_user=self.admin, lead=lead, title='Discovery call',
                                         status='scheduled', scheduled_at=self.soon)
        SDRMeeting.objects.create(company_user=self.admin, lead=lead, title='No time yet', status='pending')
        theirs = SDRLead.objects.create(company_user=self.member, email='amy@lead.example', first_name='Amy')
        SDRMeeting.objects.create(company_user=self.member, lead=theirs, title="Mo's call", status='scheduled',
                                  scheduled_at=self.soon + timedelta(hours=3))
        module = 'ai_sdr_agent'
        self.lapse(module)
        self.assertEqual(self.kinds(self.admin, module), [('sales_call', call.id, 'Discovery call')])
        self.assertEqual(self.found(self.admin, module)['others'], 1)
        client = self.http(self.admin)
        address = f'/api/sdr/meetings/{call.id}'
        self.assertEqual(self.send(client, 'get', '/api/sdr/meetings')[0], 403)
        self.assertEqual(self.send(client, 'put', address, {'notes': 'x'})[0], 403)
        self.assertEqual(self.send(client, 'put', address, {'status': 'completed'})[0], 403)
        self.assertEqual(self.send(client, 'delete', address)[0], 403)
        self.assertEqual(self.send(client, 'delete', address, {'status': 'cancelled'})[0], 403)   # cancel, not delete
        code, body = self.remove(self.found(self.admin, module)['items'][0])
        self.assertEqual(code, 200, body)
        call.refresh_from_db()
        self.assertEqual(call.status, 'cancelled')
        self.assertEqual(self.kinds(self.admin, module), [])

    # ---- the candidate's emailed link --------------------------------------------------

    def test_a_candidate_cannot_book_with_a_company_that_lost_recruitment(self):
        from recruitment_agent.models import Interview
        interview = Interview.objects.create(
            candidate_name='Cara Candidate', candidate_email='cara@test.local', job_role='Welder',
            available_slots_json='[]', company_user=self.admin, confirmation_token='tok-cara')
        page, slots = '/recruitment/interview/select/tok-cara/', '/recruitment/api/interview/available-slots/tok-cara/'
        closed = 'not available at the moment. Please contact the recruiter.'

        self.buy_module(self.company, 'recruitment_agent')
        self.assertNotContains(Client().get(page), closed)
        self.assertEqual(Client().get(slots).status_code, 200)

        self.lapse('recruitment_agent')
        self.assertContains(Client().get(page), closed)
        self.assertContains(Client().post(page, {'selected_slot_datetime': f'{self.day}T10:00'}), closed)
        self.assertEqual(Client().get(slots).status_code, 410)
        interview.refresh_from_db()
        self.assertEqual((interview.status, interview.scheduled_datetime), ('PENDING', None))

        # Someone who booked while it was open still sees their booking.
        Interview.objects.filter(pk=interview.pk).update(status='SCHEDULED', scheduled_datetime=self.soon)
        self.assertNotContains(Client().get(page), closed)
