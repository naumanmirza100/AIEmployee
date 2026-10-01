"""Handing over a leaver's open work in every agent.

Offboarding someone used to leave their open tasks, support tickets, direct
reports and interview seats where they were. HR now sees all of it in one
form and gives each group to someone — nothing moves until HR confirms.
"""
from datetime import timedelta

from django.utils import timezone

from api.views import hr_agent as views
from core.models import CompanyUser, Project, Task
from Frontline_agent.models import Ticket
from hr_agent.models import Employee, HRMeeting
from project_manager_agent.models import PMNotification
from recruitment_agent.models import Interview

from .base import HRTestCase


class HandoverTests(HRTestCase):

    def setUp(self):
        super().setUp()
        self.lee = self.with_dashboard_login(self.employee_with_login('lee', 'Lee Leaver', self.company, self.admin))
        self.tom = self.with_dashboard_login(self.employee_with_login('tom', 'Tom Taker', self.company, self.admin))

        project = Project.objects.create(name='Website', company=self.company,
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
        HRMeeting.objects.create(company=self.company, title='Lee 1:1', organizer=self.lee,
                                 scheduled_at=timezone.now() + timedelta(days=3))

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

    # ---- the form ------------------------------------------------------------

    def test_the_form_lists_everything_they_still_own(self):
        code, body = self.form()
        self.assertEqual(code, 200)
        groups = {g['key']: g for g in body['data']['groups']}
        self.assertEqual(groups['tasks']['count'], 1)            # not the finished one
        self.assertEqual(groups['tickets']['count'], 1)          # found under their dashboard login
        self.assertEqual(groups['reports']['count'], 1)
        self.assertEqual(groups['interviews']['count'], 1)
        self.assertIn('Lee 1:1', [m['title'] for m in body['data']['meetings']])
        self.assertEqual([p['name'] for p in body['data']['projects_led']], ['Website'])

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
                                     'interviews': self.tom.user_id})
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
        self.assertTrue(body['data']['results']['interviews']['skipped'])
        self.assertEqual(list(self.interview.interviewers.all()), [self.lee.user])
