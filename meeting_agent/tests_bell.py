"""Executive Meeting's alerts reach the bell, once (the demo plan's "Ready?" column; CO-169, CO-257, CO-259).

Its reminders and due and overdue alerts were written only to its own Notifications tab, and invitations to nobody's
bell. Overdue alerts came twice a day for as long as a task stayed open, and came back when deleted.
"""
from datetime import timedelta
from unittest import mock
from zoneinfo import ZoneInfo

from django.utils import timezone

from api.views import meeting_agent as views
from core.models import CompanyUser, Notification
from meeting_agent import tasks
from meeting_agent.ai_agents import ProactiveNotificationAgent
from meeting_agent.models import ExecNotification, ExecutiveMeetingParticipant, ExecutiveTask
from meeting_agent import tests_time_and_answers as base
from project_manager_agent.models import PMNotification

KARACHI = ZoneInfo('Asia/Karachi')


def bell(who, kind):
    return PMNotification.objects.filter(company_user=who, data__kind=kind)


typed = base.typed


class BellTests(base.ExecCase):

    def setUp(self):
        super().setUp()
        self.omar = CompanyUser.objects.create(company=self.company, email='omar@margalla.test', full_name='Omar Farooq',
                                               role='company_user', password_hash='x', is_active=True)

    def scan(self):
        return ProactiveNotificationAgent(company_id=self.company.id).scan_and_create_notifications(self.nadia.id)

    def test_a_reminder_reaches_the_bell_of_the_organiser_and_the_people_coming(self):
        m = self.meeting(typed(timezone.now().astimezone(KARACHI) + timedelta(minutes=10)))
        ExecutiveMeetingParticipant.objects.create(meeting=m, company_user=self.omar, response='accepted')
        tasks.send_meeting_reminders()
        self.assertEqual(bell(self.nadia, 'exec_meeting_reminder').count(), 1)
        self.assertIn('Asia/Karachi', bell(self.omar, 'exec_meeting_reminder').get().message)
        tasks.send_meeting_reminders()                                        # five minutes later: not again
        self.assertEqual(bell(self.omar, 'exec_meeting_reminder').count(), 1)

    def test_an_overdue_task_is_raised_once_for_its_owner_and_assignees(self):
        task = ExecutiveTask.objects.create(company_user=self.nadia, title='Send the lease notice', status='todo',
                                            due_date=timezone.now().date() - timedelta(days=2))
        task.assignees.add(self.omar)
        self.scan()
        self.scan()
        self.assertEqual(ExecNotification.objects.filter(notification_type='task_overdue').count(), 1)
        self.assertEqual((bell(self.nadia, 'exec_task_overdue').count(), bell(self.omar, 'exec_task_overdue').count()),
                         (1, 1))
        ExecNotification.objects.all().delete()                               # deleted: it does not come back
        self.scan()
        self.assertFalse(ExecNotification.objects.exists())
        task.due_date = timezone.now().date() - timedelta(days=1)            # a new due date, missed again
        task.save()
        self.scan()
        self.assertEqual(ExecNotification.objects.filter(notification_type='task_overdue').count(), 1)

    def test_the_scan_raises_no_meeting_reminders_of_its_own(self):                # CO-259
        self.meeting(typed(timezone.now().astimezone(KARACHI) + timedelta(minutes=10)))
        self.scan()
        self.assertFalse(ExecNotification.objects.filter(notification_type='meeting_reminder').exists())

    def test_every_owner_is_scanned(self):                                         # CO-260
        for i in range(3):
            owner = CompanyUser.objects.create(company=self.company, email=f'p{i}@margalla.test', full_name=f'P {i}',
                                               role='company_user', password_hash='x', is_active=True)
            ExecutiveTask.objects.create(company_user=owner, title=f'Task {i}', status='todo',
                                         due_date=timezone.now().date() - timedelta(days=1))
        result = tasks.run_proactive_notifications()
        self.assertEqual(result['scanned'], 3)

    def test_an_invitation_reaches_the_bell_and_is_sent_once(self):                # CO-257
        m = self.meeting(typed(timezone.now().astimezone(KARACHI) + timedelta(days=1)))
        with mock.patch.object(views, '_send_meeting_invite_email') as emailed:
            for _ in range(2):
                code, body = self.call(views.meeting_participants, self.nadia, meeting_id=m.id,
                                       data={'user_id': self.omar.id})
                self.assertIn(code, (200, 201), body)
        self.assertEqual(emailed.call_count, 1)
        self.assertEqual(bell(self.omar, 'exec_meeting_invite').count(), 1)

    def test_a_cancelled_meeting_invites_nobody_and_people_who_declined_hear_nothing(self):
        m = self.meeting(typed(timezone.now().astimezone(KARACHI) + timedelta(days=1)), status='cancelled')
        with mock.patch.object(views, '_send_meeting_invite_email') as emailed:
            self.call(views.meeting_participants, self.nadia, meeting_id=m.id, data={'user_id': self.omar.id})
        emailed.assert_not_called()
        on = self.meeting(typed(timezone.now().astimezone(KARACHI) + timedelta(days=1)), title='On')
        ExecutiveMeetingParticipant.objects.create(meeting=on, company_user=self.omar, response='rejected')
        with mock.patch.object(views, '_send_meeting_update_email') as told:
            self.call(views.meeting_detail, self.nadia, method='delete', meeting_id=on.id)
        told.assert_not_called()


class EmployeeBellTests(base.EmployeeCase):

    def test_an_employee_gets_the_invitation_and_the_reminder_in_their_own_bell(self):
        views._bell_invited([self.seat_login], self.board, 'Nadia Rehman')
        self.assertTrue(Notification.objects.filter(user=self.sana, type='exec_meeting_invite').exists())
        self.seat.response = 'accepted'
        self.seat.save()
        self.board.scheduled_at = typed(timezone.now().astimezone(KARACHI) + timedelta(minutes=10))
        self.board.save()
        tasks.send_meeting_reminders()
        self.assertTrue(Notification.objects.filter(user=self.sana, type='exec_meeting_reminder').exists())
