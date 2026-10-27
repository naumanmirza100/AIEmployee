"""Overdue tasks and tickets about to miss their response time tell someone (CO-62, found 5 Oct 2026).

An overdue task raised an alert only when someone pressed Scan, in their own bell; a ticket an hour from its
deadline was raised to Urgent and nobody was told.
"""
from datetime import datetime, timedelta, timezone as tz

from django.utils import timezone

from core.models import Notification, Task
from project_manager_agent.models import PMNotification
from project_manager_agent.overdue import tell_newly_overdue

from .base import PMTestCase


class OverdueTaskTests(PMTestCase):

    def setUp(self):
        super().setUp()
        self.company.timezone_name = 'Asia/Karachi'
        self.company.save(update_fields=['timezone_name'])
        # 10:00 in Lahore on 28 Oct; "yesterday" is 27 Oct there.
        self.now = datetime(2026, 10, 28, 5, 0, tzinfo=tz.utc)
        self.due_yesterday = datetime(2026, 10, 27, 0, 0, tzinfo=tz.utc)

    def make(self, title, due, **fields):
        return Task.objects.create(project=self.project, title=title, due_date=due, **fields)

    def test_the_assignee_is_told_once_about_what_was_due_yesterday(self):
        from core.logins import user_for
        self.make('Logo', self.due_yesterday, assignee=self.dev)                 # an employee login
        self.make('Menu', self.due_yesterday, assignee=user_for(self.dash))      # a dashboard login
        self.make('Done one', self.due_yesterday, assignee=self.dev, status='done')
        self.make('Older', self.due_yesterday - timedelta(days=3), assignee=self.dev)
        self.make('Nobody', self.due_yesterday)
        tell_newly_overdue(self.now)
        dev_bell = Notification.objects.filter(user=self.dev, type='pm_task_overdue')
        self.assertEqual(dev_bell.count(), 1)
        self.assertEqual(dev_bell.get().title, 'Your task is overdue: Logo')
        dash = PMNotification.objects.filter(company_user=self.dash).values_list('title', flat=True)
        self.assertIn('Your task is overdue: Menu', dash)
        self.assertIn('A task with no owner is overdue: Nobody', dash)            # to whoever made the project
        tell_newly_overdue(self.now + timedelta(days=1))                          # the next day: nothing again
        self.assertEqual(Notification.objects.filter(user=self.dev, type='pm_task_overdue').count(), 1)

    def test_a_company_without_the_agent_is_not_told(self):
        from core.models import CompanyModulePurchase
        CompanyModulePurchase.objects.filter(company=self.company).delete()
        self.make('Logo', self.due_yesterday, assignee=self.dev)
        self.assertEqual(tell_newly_overdue(self.now), 0)
