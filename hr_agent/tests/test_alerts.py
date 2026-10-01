"""HR events that need someone reach the bell of the people who act on them.

HR raised no in-app alerts at all: a new leave request, or a workflow stopped
for approval, waited in the dashboard until someone happened to look.
"""

from datetime import timedelta

from django.utils import timezone

from hr_agent.models import HRWorkflow, LeaveRequest
from hr_agent.workflow_templates import get_template
from project_manager_agent.models import PMNotification

from .base import HRTestCase


def bell(company_user):
    return list(PMNotification.objects.filter(company_user=company_user))


class HRAlertTests(HRTestCase):

    def ask_for_leave(self, employee):
        start = timezone.now().date() + timedelta(days=10)
        return LeaveRequest.objects.create(
            employee=employee, leave_type='vacation', start_date=start,
            end_date=start + timedelta(days=2), days_requested=3, status='pending')

    def test_a_leave_request_reaches_hr_admins_with_a_link_to_leave(self):
        self.ask_for_leave(self.member_emp)
        [alert] = bell(self.admin)
        self.assertIn('Mo Member', alert.title)
        self.assertIn('3 days', alert.message)
        self.assertEqual(alert.data['link'], '/hr/dashboard?tab=leave')

    def test_it_reaches_the_employees_manager_too(self):
        manager = self.login(self.company, 'meg@test.local', 'Meg Manager', 'manager')
        self.member_emp.manager = self.employee(manager, 'Meg Manager')
        self.member_emp.save()
        self.ask_for_leave(self.member_emp)
        self.assertEqual(len(bell(manager)), 1)

    def test_not_to_ordinary_colleagues_or_the_person_asking(self):
        self.ask_for_leave(self.member_emp)
        self.assertEqual(bell(self.member), [])          # the requester, not an HR admin
        self.ask_for_leave(self.admin_emp)               # an HR admin asking for themselves
        self.assertEqual(len(bell(self.admin)), 1)       # only the earlier request

    def test_other_companies_hear_nothing(self):
        self.ask_for_leave(self.member_emp)
        self.assertEqual(bell(self.rival_admin), [])

    def test_a_workflow_waiting_for_approval_reaches_hr_admins(self):
        spec = get_template('offboarding')                       # needs approval to start
        HRWorkflow.objects.create(company=self.company, name=spec['name'],
                                  trigger_conditions=spec['trigger_conditions'],
                                  steps=spec['steps'], requires_approval=True)
        self.member_emp.employment_status = 'notice'
        self.member_emp.save()
        [alert] = bell(self.admin)
        self.assertIn('Employee offboarding', alert.title)
        self.assertIn('Mo Member', alert.message)
        self.assertEqual(alert.data['link'], '/hr/dashboard?tab=workflows')
