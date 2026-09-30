"""Project Pilot warns before giving work to someone on leave.

Its list of people didn't know about HR leave, so it could assign a task due
next week to someone away all next week. Now each person carries their
approved leave, the review form flags the clash, and a clash is reason enough
to show the form — a warning, not a block.
"""
from datetime import date, timedelta

from django.test import SimpleTestCase
from django.utils import timezone

from api.views.pm_agent import _with_upcoming_leave
from hr_agent.models import Employee, LeaveRequest
from project_manager_agent import drafts

from .base import PMTestCase

TODAY = date(2026, 10, 1)


def person(uid, name, *leave):
    return {'id': uid, 'name': name,
            'on_leave': [{'start': s, 'end': e, 'label': f'On leave {s}–{e}'} for s, e in leave]}


def task(assignee, due, title='Build it'):
    return {'action': 'create_task', 'title': title, 'assignee_id': assignee, 'due_date': due}


class LeaveWarningTests(SimpleTestCase):

    users = [person(1, 'Ali', ('2026-10-06', '2026-10-10')), person(2, 'Sara')]

    def inspect(self, *actions):
        return drafts.inspect(list(actions), self.users, today=TODAY)

    def test_a_task_due_after_leave_starts_is_flagged(self):
        result = self.inspect(task(1, '2026-10-08'))
        self.assertEqual(result['rows'][0]['leave'], 'On leave 2026-10-06–2026-10-10')
        self.assertEqual(result['leave_warnings'], 1)

    def test_it_opens_the_review_form_even_with_nothing_missing(self):
        # Every field is filled in, so there used to be no form at all.
        self.assertTrue(self.inspect(task(1, '2026-10-08'))['needs_input'])
        self.assertFalse(self.inspect(task(2, '2026-10-08'))['needs_input'])

    def test_leave_after_the_due_date_doesnt_matter(self):
        self.assertIsNone(self.inspect(task(1, '2026-10-05'))['rows'][0]['leave'])

    def test_leave_already_over_doesnt_matter(self):
        users = [person(1, 'Ali', ('2026-09-20', '2026-09-25'))]
        result = drafts.inspect([task(1, '2026-10-08')], users, today=TODAY)
        self.assertIsNone(result['rows'][0]['leave'])

    def test_without_hr_nothing_is_flagged(self):
        result = drafts.inspect([task(1, '2026-10-08')], [{'id': 1, 'name': 'Ali'}], today=TODAY)
        self.assertIsNone(result['rows'][0]['leave'])
        self.assertFalse(result['needs_input'])

    def test_the_chat_says_why_the_form_is_showing(self):
        gaps = self.inspect(task(1, '2026-10-08'))
        text = drafts.chat_text([task(1, '2026-10-08')], None, gaps)
        self.assertIn('on leave', text)
        self.assertNotIn('missing', text)


class UpcomingLeaveTests(PMTestCase):

    def test_people_carry_their_approved_leave_from_hr(self):
        employee = Employee.objects.get(user=self.dev)
        start = timezone.localdate() + timedelta(days=7)
        LeaveRequest.objects.create(employee=employee, leave_type='vacation', start_date=start,
                                    end_date=start + timedelta(days=2), days_requested=3, status='approved')
        LeaveRequest.objects.create(employee=employee, leave_type='sick', start_date=start + timedelta(days=20),
                                    end_date=start + timedelta(days=20), days_requested=1, status='pending')
        users = _with_upcoming_leave([{'id': self.dev.id, 'name': 'Dev'}, {'id': self.pm.id, 'name': 'Pat'}])
        [leave] = users[0]['on_leave']                      # the pending one isn't there
        self.assertEqual(leave['start'], start.isoformat())
        self.assertTrue(leave['label'].startswith('On leave'))
        self.assertNotIn('on_leave', users[1])
