"""Handing over a leaver's open work in every agent.

Offboarding someone used to leave their open tasks, support tickets, direct
reports and interview seats where they were. HR now sees all of it in one
form and gives each group to someone — nothing moves until HR confirms.
Projects they lead, meetings they organise, interviews they run and leave
waiting for their decision used to be listed at best, and are now handed over
too.
"""
from datetime import timedelta

from django.utils import timezone

from api.views import hr_agent as views
from core.models import CalendarBlock, CompanyUser, Project, Task
from Frontline_agent.models import FrontlineMeeting, Ticket
from hr_agent.models import Employee, HRMeeting
from project_manager_agent.models import PMAuditLog, PMNotification, ScheduledMeeting
from recruitment_agent.models import Interview

from .base import HRTestCase


class HandoverTestCase(HRTestCase):
    """A leaver, Lee, who owns something in every agent; and Tom, who can take it."""

    def setUp(self):
        super().setUp()
        self.lee = self.with_dashboard_login(self.employee_with_login('lee', 'Lee Leaver', self.company, self.admin))
        self.tom = self.with_dashboard_login(self.employee_with_login('tom', 'Tom Taker', self.company, self.admin))

        self.project = project = Project.objects.create(name='Website', company=self.company,
                                         created_by_company_user=self.admin, owner=self.lee.user,
                                         project_manager=self.lee.user)
        self.open_task = Task.objects.create(title='Build the header', project=project,
                                             assignee=self.lee.user, status='in_progress')
        self.done_task = Task.objects.create(title='Old work', project=project,
                                             assignee=self.lee.user, status='done')

        # Frontline stores the dashboard login's own user on tickets.
        self.ticket = Ticket.objects.create(title='Printer on fire', description='x', company=self.company,
                                            created_by=self.lee.company_user.login_user,
                                            assigned_to=self.lee.company_user.login_user, status='open')
        self.report = Employee.objects.create(company=self.company, full_name='Rita Report',
                                              work_email='rita@test.local', manager=self.lee)

        self.interview = Interview.objects.create(candidate_name='Cara', candidate_email='cara@test.local',
                                                  job_role='Backend', available_slots_json='[]',
                                                  company_user=self.admin, status='PENDING')
        self.interview.interviewers.add(self.lee.user)
        self.hr_meeting = HRMeeting.objects.create(company=self.company, title='Lee 1:1', organizer=self.lee,
                                                   scheduled_at=timezone.now() + timedelta(days=3))
        self.pm_meeting = ScheduledMeeting.objects.create(organizer=self.lee.company_user, title='Sprint review',
                                                          proposed_time=timezone.now() + timedelta(days=4))
        self.frontline_meeting = FrontlineMeeting.objects.create(
            company=self.company, organizer=self.lee.company_user.login_user, title='Customer call',
            scheduled_at=timezone.now() + timedelta(days=5))
        # They run this interview, as the recruiter.
        self.their_interview = Interview.objects.create(
            candidate_name='Dev', candidate_email='dev@test.local', job_role='Frontend', available_slots_json='[]',
            company_user=self.lee.company_user, status='SCHEDULED', timezone_name='UTC',
            scheduled_datetime=timezone.now() + timedelta(days=6))
        # And this leave is waiting for their decision.
        self.leave = self.leave_request(employee=self.report, approver=self.lee)

    def with_dashboard_login(self, employee):
        from api.views.frontline_agent import _get_or_create_user_for_company_user
        cu = CompanyUser.objects.create(company=self.company, email=employee.work_email,
                                        full_name=employee.full_name, role='company_user',
                                        password_hash='x', is_active=True)
        _get_or_create_user_for_company_user(cu)
        employee.company_user = cu
        employee.save()
        return employee

    def form(self, actor=None):
        return self.call(views.employee_handover, actor or self.admin, method='get', employee_id=self.lee.id)

    def hand_over(self, assignments, actor=None):
        return self.call(views.employee_handover, actor or self.admin, {'assignments': assignments},
                         employee_id=self.lee.id)


class HandoverTests(HandoverTestCase):

    # ---- the form ------------------------------------------------------------

    def test_the_form_lists_everything_they_still_own(self):
        code, body = self.form()
        self.assertEqual(code, 200)
        groups = {g['key']: g for g in body['data']['groups']}
        self.assertEqual(groups['tasks']['count'], 1)            # not the finished one
        self.assertEqual(groups['tickets']['count'], 1)          # found under their dashboard login
        self.assertEqual(groups['reports']['count'], 1)
        self.assertEqual(groups['interviews']['count'], 1)
        self.assertEqual([i['title'] for i in groups['projects']['items']], ['Website'])
        self.assertEqual([i['title'] for i in groups['meetings']['items']],
                         ['HR: Lee 1:1', 'Project Manager: Sprint review', 'Frontline: Customer call'])
        self.assertEqual([i['title'] for i in groups['interviews_run']['items']], ['Dev — Frontend'])
        self.assertEqual([i['title'] for i in groups['leave']['items']], ['Rita Report'])

    def test_they_arent_offered_their_own_work(self):
        groups = {g['key']: g for g in self.form()[1]['data']['groups']}
        self.assertNotIn(self.lee.user_id, [t['id'] for t in groups['tasks']['targets']])
        self.assertNotIn(self.lee.id, [t['id'] for t in groups['reports']['targets']])

    def test_hr_admins_only(self):
        self.assertEqual(self.form(actor=self.member)[0], 403)
        self.assertEqual(self.hand_over({'tasks': self.tom.user_id}, actor=self.member)[0], 403)

    # ---- handing over -------------------------------------------------------

    def test_each_group_goes_to_the_person_chosen(self):
        code, body = self.hand_over({'tasks': self.tom.user_id,
                                     'tickets': self.tom.company_user_id,
                                     'reports': self.tom.id,
                                     'interviews': self.tom.user_id,
                                     'projects': self.tom.user_id,
                                     'meetings': self.tom.company_user_id,
                                     'interviews_run': self.tom.company_user_id,
                                     'leave': self.tom.id})
        self.assertEqual(code, 200, body)
        self.open_task.refresh_from_db(); self.done_task.refresh_from_db()
        self.ticket.refresh_from_db(); self.report.refresh_from_db()
        self.assertEqual(self.open_task.assignee, self.tom.user)
        self.assertEqual(self.done_task.assignee, self.lee.user)       # finished work stays as it was
        self.assertEqual(self.ticket.assigned_to, self.tom.company_user.login_user)
        self.assertEqual(self.report.manager, self.tom)
        self.assertEqual(list(self.interview.interviewers.all()), [self.tom.user])
        self.assertEqual(body['data']['remaining']['groups'], [])

    def test_only_the_groups_chosen_move(self):
        self.hand_over({'tasks': self.tom.user_id})
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.assigned_to, self.lee.company_user.login_user)

    def test_the_new_owner_is_told(self):
        self.hand_over({'tasks': self.tom.user_id, 'tickets': self.tom.company_user_id})
        titles = set(PMNotification.objects.filter(company_user=self.tom.company_user)
                     .values_list('title', flat=True))
        self.assertIn('1 task handed over to you', titles)
        self.assertTrue(any('assigned to you' in t for t in titles))

    def test_someone_outside_the_company_is_refused_and_nothing_moves(self):
        outsider = self.employee_with_login('oz', 'Oz Outside', self.rival, self.rival_admin)
        code, _ = self.hand_over({'tasks': self.tom.user_id, 'interviews': outsider.user_id})
        self.assertEqual(code, 400)
        self.open_task.refresh_from_db()
        self.assertEqual(self.open_task.assignee, self.lee.user)

    def test_a_busy_replacement_doesnt_take_a_booked_interview_seat(self):
        from core.scheduling import ensure_free  # noqa: F401 — the check used inside
        from core.models import CalendarBlock
        when = timezone.now() + timedelta(days=5)
        self.interview.scheduled_datetime = when
        self.interview.status = 'SCHEDULED'
        self.interview.timezone_name = 'UTC'
        self.interview.save()
        CalendarBlock.objects.create(company=self.company, user=self.tom.user, starts_at=when,
                                     ends_at=when + timedelta(hours=1), source='pm', source_id=1,
                                     role='participant', response='accepted', title='Busy')
        code, body = self.hand_over({'interviews': self.tom.user_id})
        self.assertEqual(code, 200)
        self.assertEqual(body['data']['results']['interviews']['moved'], 0)
        [reason] = body['data']['results']['interviews']['skipped']
        self.assertIn('is busy', reason)                       # says why, not just "busy then"
        self.assertIn('Project Manager meeting', reason)
        self.assertEqual(list(self.interview.interviewers.all()), [self.lee.user])


class HandoverOfWhatTheyLeadTests(HandoverTestCase):
    """Projects they lead, meetings they organise, interviews they run, leave
    waiting for their decision."""

    def test_projects_get_a_new_manager_through_project_managers_rules(self):
        code, body = self.hand_over({'projects': self.tom.user_id})
        self.assertEqual(code, 200, body)
        self.project.refresh_from_db()
        self.assertEqual(self.project.project_manager, self.tom.user)
        self.assertTrue(PMAuditLog.objects.filter(action='project_updated', object_id=self.project.id).exists())

    def test_meetings_get_a_new_organiser_in_each_agents_terms(self):
        code, body = self.hand_over({'meetings': self.tom.company_user_id})
        self.assertEqual((code, body['data']['results']['meetings']['moved']), (200, 3), body)
        for m in (self.pm_meeting, self.hr_meeting, self.frontline_meeting):
            m.refresh_from_db()
        self.assertEqual(self.pm_meeting.organizer, self.tom.company_user)      # a dashboard login
        self.assertEqual(self.hr_meeting.organizer, self.tom)                    # an HR record
        self.assertEqual(self.frontline_meeting.organizer, self.tom.company_user.login_user)
        # The shared calendar follows: the organiser's time is now Tom's.
        organiser_blocks = CalendarBlock.objects.filter(source='pm', source_id=self.pm_meeting.id, role='organizer')
        self.assertEqual([b.user_id for b in organiser_blocks], [self.tom.user_id])

    def test_a_meeting_is_skipped_if_the_new_organiser_is_busy_and_says_why(self):
        when = self.pm_meeting.proposed_time
        CalendarBlock.objects.create(company=self.company, user=self.tom.user, starts_at=when,
                                     ends_at=when + timedelta(hours=1), source='hr', source_id=999,
                                     role='participant', response='accepted', title='Busy')
        code, body = self.hand_over({'meetings': self.tom.company_user_id})
        result = body['data']['results']['meetings']
        self.assertEqual((code, result['moved']), (200, 2))
        [reason] = result['skipped']
        self.assertTrue(reason.startswith('Sprint review:'), reason)
        self.assertIn('is busy', reason)
        self.pm_meeting.refresh_from_db()
        self.assertEqual(self.pm_meeting.organizer, self.lee.company_user)

    def test_an_hr_meeting_needs_an_organiser_with_an_hr_record(self):
        no_record = CompanyUser.objects.create(company=self.company, email='nora@test.local', full_name='Nora',
                                               role='company_user', password_hash='x', is_active=True)
        code, body = self.hand_over({'meetings': no_record.id})
        result = body['data']['results']['meetings']
        self.assertEqual(result['moved'], 2)
        self.assertIn('no HR record', result['skipped'][0])
        self.hr_meeting.refresh_from_db()
        self.assertEqual(self.hr_meeting.organizer, self.lee)

    def test_interviews_they_run_get_a_new_recruiter(self):
        code, body = self.hand_over({'interviews_run': self.tom.company_user_id})
        self.assertEqual((code, body['data']['results']['interviews_run']['moved']), (200, 1), body)
        self.their_interview.refresh_from_db()
        self.assertEqual(self.their_interview.company_user, self.tom.company_user)
        blocks = CalendarBlock.objects.filter(source='recruitment', source_id=self.their_interview.id)
        self.assertEqual([b.user_id for b in blocks], [self.tom.user_id])

    def test_a_booked_interview_isnt_given_to_a_recruiter_busy_then(self):
        when = self.their_interview.scheduled_datetime
        CalendarBlock.objects.create(company=self.company, user=self.tom.user, starts_at=when,
                                     ends_at=when + timedelta(hours=1), source='hr', source_id=999,
                                     role='participant', response='accepted', title='Busy')
        code, body = self.hand_over({'interviews_run': self.tom.company_user_id})
        result = body['data']['results']['interviews_run']
        self.assertEqual((code, result['moved']), (200, 0))
        self.assertIn('is busy', result['skipped'][0])
        self.their_interview.refresh_from_db()
        self.assertEqual(self.their_interview.company_user, self.lee.company_user)

    def test_leave_waiting_on_them_goes_to_the_new_approver(self):
        code, body = self.hand_over({'leave': self.tom.id})
        self.assertEqual(code, 200, body)
        self.leave.refresh_from_db()
        self.assertEqual((self.leave.approver, self.leave.status), (self.tom, 'pending'))
        # Who can decide leave: only colleagues with a dashboard login.
        self.assertEqual(self.hand_over({'leave': self.report.id})[0], 400)

    def test_each_new_owner_is_told_where_to_find_it(self):
        self.hand_over({'projects': self.tom.user_id, 'meetings': self.tom.company_user_id,
                        'interviews_run': self.tom.company_user_id, 'leave': self.tom.id})
        alerts = dict(PMNotification.objects.filter(company_user=self.tom.company_user)
                      .values_list('title', 'data__link'))
        self.assertEqual(alerts, {
            '1 project for you to lead': '/project-manager/dashboard?tab=projects',
            '3 meetings for you to organise': '/hr/dashboard?tab=meetings',
            '1 interview for you to run': '/recruitment/interviews',
            '1 leave request for you to decide': '/hr/dashboard?tab=leave',
        })

    def test_jobs_they_posted_get_a_new_owner_with_their_slots(self):
        from recruitment_agent.models import JobDescription, RecruiterInterviewSettings
        job = JobDescription.objects.create(title='Designer', description='x' * 30, company=self.company,
                                            company_user=self.lee.company_user)
        slots = RecruiterInterviewSettings.objects.create(company_user=self.lee.company_user, job=job)
        # Tom's own defaults (no job) mustn't stop the job's slots moving.
        RecruiterInterviewSettings.objects.create(company_user=self.tom.company_user, job=None)
        groups = {g['key']: g for g in self.form()[1]['data']['groups']}
        self.assertEqual([i['title'] for i in groups['jobs']['items']], ['Designer'])

        code, body = self.hand_over({'jobs': self.tom.company_user_id})
        self.assertEqual((code, body['data']['results']['jobs']['moved']), (200, 1), body)
        job.refresh_from_db(); slots.refresh_from_db()
        self.assertEqual((job.company_user, slots.company_user), (self.tom.company_user, self.tom.company_user))
        alerts = dict(PMNotification.objects.filter(company_user=self.tom.company_user)
                      .values_list('title', 'data__link'))
        self.assertEqual(alerts, {'1 job handed over to you': '/recruitment/job-descriptions'})
        # Jobs go to a dashboard login of the company only.
        self.assertEqual(self.hand_over({'jobs': self.tom.user_id + 10_000})[0], 400)
