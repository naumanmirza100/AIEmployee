"""One "My work" list across the agents.

A person's work was spread over the agents: PM tasks in My Space, leave waiting
for a decision in HR, tickets in Frontline, feedback owed on interviews in
Recruitment, suggested meeting times in each scheduler. Nothing put it together.
"""
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.utils import timezone

from api.views import frontline_agent as frontline_views
from api.views import my_work as views
from core import my_work
from core.models import Project, Task
from Frontline_agent.models import Ticket
from hr_agent.models import (Employee, HRMeeting, HRMeetingParticipant, HRMeetingResponse, HRWorkflow,
                             HRWorkflowExecution)
from hr_agent.tests.base import HRTestCase
from project_manager_agent.models import MeetingParticipant, MeetingResponse, ScheduledMeeting
from recruitment_agent.models import Interview


class MyWorkTestCase(HRTestCase):

    def setUp(self):
        super().setUp()
        for module in ('frontline_agent', 'recruitment_agent', 'project_manager_agent'):
            self.buy_module(self.company, module)
        # HR's helper links each dashboard login to its user in the database only.
        for cu in (self.admin, self.member, self.rival_admin):
            cu.refresh_from_db()
        self.t0 = timezone.now()
        self.ali = self.employee_with_login('ali', 'Ali Staff', self.company, self.admin)
        get_user_model().objects.filter(pk=self.ali.user_id).update(first_name='Ali', last_name='Staff')
        self.ali.refresh_from_db()
        self.project = Project.objects.create(name='App', company=self.company,
                                              created_by_company_user=self.admin, owner=self.ali.user)

    def items(self, company_user):
        code, body = self.call(views.company_my_work, company_user, method='get')
        self.assertEqual(code, 200, body)
        return body['data']['items']

    def kinds(self, company_user):
        return [i['kind'] for i in self.items(company_user)]

    # ---- fixtures, one per kind of work ------------------------------------

    def ticket(self, assignee=None, **fields):
        fields.setdefault('status', 'open')
        fields.setdefault('priority', 'high')
        fields.setdefault('sla_due_at', self.t0 + timedelta(hours=2))
        assignee = assignee or self.admin
        return Ticket.objects.create(title='Export is broken', description='x', company=assignee.company,
                                     created_by=assignee.login_user, assigned_to=assignee.login_user, **fields)

    def interview(self, ended_ago=timedelta(days=2), **fields):
        fields.setdefault('company_user', self.admin)
        return Interview.objects.create(
            candidate_name='Cara Candidate', candidate_email='cara@test.local', job_role='Designer',
            status='SCHEDULED', scheduled_datetime=self.t0 - ended_ago - timedelta(minutes=30),
            duration_minutes=30, available_slots_json='[]', **fields)

    def pm_meeting(self, organizer=None, last_by='invitee'):
        meeting = ScheduledMeeting.objects.create(
            organizer=organizer or self.admin, invitee=self.ali.user, title='Kick-off',
            proposed_time=self.t0 + timedelta(days=1), status='counter_proposed')
        MeetingParticipant.objects.create(meeting=meeting, user=self.ali.user, status='counter_proposed',
                                          counter_proposed_time=self.t0 + timedelta(days=1))
        MeetingResponse.objects.create(meeting=meeting, responded_by='invitee', action='counter_proposed',
                                       proposed_time=self.t0 + timedelta(days=1))
        if last_by == 'organizer':
            MeetingResponse.objects.create(meeting=meeting, responded_by='organizer', action='accepted',
                                           created_at=self.t0 + timedelta(seconds=1))
        return meeting

    def hr_meeting(self, organizer, last_by='participant'):
        meeting = HRMeeting.objects.create(company=self.company, organizer=organizer, title='1:1',
                                           scheduled_at=self.t0 + timedelta(days=2),
                                           response_status='counter_proposed')
        HRMeetingParticipant.objects.create(meeting=meeting, employee=self.ali, status='counter_proposed',
                                            counter_proposed_time=self.t0 + timedelta(days=2))
        HRMeetingResponse.objects.create(meeting=meeting, responder=self.ali, responder_name='Ali Staff',
                                         responded_by='participant', action='counter_proposed',
                                         proposed_time=self.t0 + timedelta(days=2))
        if last_by == 'organizer':
            HRMeetingResponse.objects.create(meeting=meeting, responded_by='organizer', action='accepted',
                                             created_at=self.t0 + timedelta(seconds=1))
        return meeting

    def task(self, assignee, **fields):
        fields.setdefault('due_date', self.t0 + timedelta(days=3))
        return Task.objects.create(project=self.project, title='Ship the export fix', assignee=assignee, **fields)


class DashboardLoginTests(MyWorkTestCase):

    def test_everything_waiting_in_one_list_soonest_first(self):
        self.interview()                                    # feedback was due yesterday
        self.ticket()                                       # SLA in 2 hours
        self.pm_meeting()                                   # suggested time tomorrow
        self.hr_meeting(self.admin_emp)                     # in two days
        self.task(self.admin.login_user)                    # due in three days
        self.leave_request(approver=self.admin_emp)         # starts in ten days
        items = self.items(self.admin)
        self.assertEqual([i['kind'] for i in items],
                         ['feedback', 'ticket', 'meeting_reply', 'meeting_reply', 'task', 'leave'])
        self.assertEqual([i['agent'] for i in items], ['recruitment', 'frontline', 'pm', 'hr', 'pm', 'hr'])
        by_kind = {i['kind']: i for i in items}
        self.assertEqual(by_kind['leave']['link'], '/hr/dashboard?tab=leave')
        self.assertEqual(by_kind['leave']['title'], 'Leave request from Mo Member')
        self.assertTrue(by_kind['leave']['all_day'])
        self.assertEqual(by_kind['ticket']['link'], '/frontline/dashboard?tab=tickets')
        self.assertEqual(by_kind['feedback']['link'], '/recruitment/interviews')
        self.assertEqual(by_kind['task']['link'], '/project-manager/dashboard?tab=tasks')
        self.assertEqual(items[2]['title'], 'Ali Staff suggested another time')

    def test_a_knowledge_gap_opens_where_its_answered(self):
        self.ticket(category='knowledge_gap')
        [item] = self.items(self.admin)
        self.assertEqual((item['kind'], item['link']), ('knowledge_gap', '/company/dashboard/ticket-tasks'))

    def test_finished_or_answered_work_drops_off(self):
        self.ticket(status='resolved')
        self.ticket(snoozed_until=self.t0 + timedelta(hours=5))
        self.interview(feedback_submitted_at=self.t0)
        self.interview(outcome='REJECTED')
        self.interview(ended_ago=timedelta(minutes=-5))       # still going on
        self.interview(ended_ago=timedelta(days=90))           # too long ago to chase
        self.pm_meeting(last_by='organizer')
        self.hr_meeting(self.admin_emp, last_by='organizer')
        self.task(self.admin.login_user, status='done')
        self.leave_request(status='approved')
        self.assertEqual(self.items(self.admin), [])

    def test_leave_goes_to_its_approver_and_unassigned_leave_to_hr_admins(self):
        self.leave_request(employee=self.admin_emp, approver=self.member_emp)
        zed = Employee.objects.create(company=self.company, full_name='Zed', work_email='zed@test.local')
        self.leave_request(employee=zed, approver=self.member_emp)
        self.leave_request(employee=zed, start_date=self.t0.date() + timedelta(days=20),
                           end_date=self.t0.date() + timedelta(days=20), days_requested=1)
        self.assertEqual([i['title'] for i in self.items(self.member)],
                         ['Leave request from Dana Admin', 'Leave request from Zed'])
        # The member's to decide aren't the HR admin's work; nobody's are, but
        # not their own.
        self.leave_request(employee=self.admin_emp, start_date=self.t0.date() + timedelta(days=30),
                           end_date=self.t0.date() + timedelta(days=30), days_requested=1)
        [item] = self.items(self.admin)
        self.assertEqual(item['title'], 'Leave request from Zed')
        # HR's "Pending for me" doesn't list unassigned requests, so it opens "All".
        self.assertEqual(item['link'], '/hr/dashboard?tab=leave&view=all')

    def test_workflows_waiting_for_approval_go_to_hr_admins(self):
        workflow = HRWorkflow.objects.create(company=self.company, name='Onboarding')
        HRWorkflowExecution.objects.create(workflow=workflow, workflow_name='Onboarding', status='awaiting_approval',
                                           executed_by=self.admin.login_user, context_data={'employee_name': 'Ali'})
        [item] = self.items(self.admin)
        self.assertEqual((item['title'], item['link']), ('Approve workflow: Onboarding', '/hr/dashboard?tab=workflows'))
        self.assertEqual(self.items(self.member), [])

    def test_a_suggested_time_goes_to_the_organiser_or_with_none_to_hr_admins(self):
        self.hr_meeting(self.member_emp)
        self.hr_meeting(None)
        self.assertEqual(len(self.items(self.member)), 1)
        self.assertEqual(len(self.items(self.admin)), 1)

    def test_agents_the_company_hasnt_bought_add_nothing(self):
        from core.models import CompanyModulePurchase
        self.ticket()
        self.leave_request()
        CompanyModulePurchase.objects.filter(company=self.company, module_name='frontline_agent').delete()
        self.assertEqual(self.kinds(self.admin), ['leave'])

    def test_never_another_companys_work(self):
        self.ticket(assignee=self.rival_admin)
        self.leave_request(employee=self.rival_emp)
        self.assertEqual(self.items(self.admin), [])

    def test_one_agent_failing_doesnt_hide_the_rest(self):
        self.ticket()
        self.leave_request()
        with mock.patch.object(my_work, '_tickets', side_effect=RuntimeError('boom')):
            self.assertEqual(self.kinds(self.admin), ['leave'])

    def test_through_the_url_without_any_agent_prefix(self):
        self.leave_request()
        code, body = self.send(self.http(self.admin), 'get', '/api/company/my-work')
        self.assertEqual((code, body['data']['total']), (200, 1))


class EmployeeLoginTests(MyWorkTestCase):

    def employee_items(self, user):
        request = self.factory.get('/')
        from rest_framework.test import force_authenticate
        # Fresh, as a request would load it: not with a profile cached before it had a company.
        force_authenticate(request, user=get_user_model().objects.get(pk=user.pk))
        response = views.user_my_work(request)
        self.assertEqual(response.status_code, 200)
        return response.data['data']['items']

    def test_tasks_and_invites_waiting_for_a_reply(self):
        self.task(self.ali.user)
        self.task(self.ali.user, status='done')
        pm = ScheduledMeeting.objects.create(organizer=self.admin, invitee=self.ali.user, title='Planning',
                                             proposed_time=self.t0 + timedelta(days=1))
        MeetingParticipant.objects.create(meeting=pm, user=self.ali.user, status='pending')
        answered = ScheduledMeeting.objects.create(organizer=self.admin, invitee=self.ali.user, title='Done',
                                                   proposed_time=self.t0 + timedelta(days=1))
        MeetingParticipant.objects.create(meeting=answered, user=self.ali.user, status='accepted')
        hr = HRMeeting.objects.create(company=self.company, organizer=self.admin_emp, title='Review',
                                      scheduled_at=self.t0 + timedelta(days=5))
        HRMeetingParticipant.objects.create(meeting=hr, employee=self.ali, status='pending')
        items = self.employee_items(self.ali.user)
        self.assertEqual([(i['agent'], i['kind']) for i in items],
                         [('pm', 'invite'), ('pm', 'task'), ('hr', 'invite')])
        self.assertEqual({i['link'] for i in items}, {'/me/meetings', '/me/tasks'})

    def test_a_dashboard_token_is_turned_away_with_a_reason(self):
        code, body = self.send(self.http(self.admin), 'get', '/api/user/my-work')
        self.assertEqual(code, 401)
        self.assertIn('dashboard login', body.get('detail', ''))


class TicketListTests(MyWorkTestCase):

    def test_a_ticket_handed_to_you_is_in_your_ticket_list(self):
        """My work links tickets to the Frontline list, which used to show only
        tickets you created — so a hand-off or a leaver's handover was invisible."""
        ticket = Ticket.objects.create(title='Handed over', description='x', company=self.company,
                                       created_by=self.admin.login_user, assigned_to=self.member.login_user)
        code, body = self.call(frontline_views.list_tickets, self.member, method='get')
        self.assertEqual(code, 200, body)
        self.assertIn(ticket.id, [t['id'] for t in body['data']])
        code, body = self.call(frontline_views.list_tickets, self.rival_admin, method='get')
        self.assertNotIn(ticket.id, [t['id'] for t in body['data']])
