"""'Pause all emails' stops every email, and a hand-over sends one email, not thirty.

The switch only stopped emails that went through the shared notification
settings. HR and Frontline meeting reminders, every Executive Meeting email and
Project Manager's 'New Task Assigned' email never asked, so a paused person
still got them. Handing a leaver's tasks to someone reassigned them one at a
time, each with its own email and alert, and the link in that email pointed at a
page that does not exist.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import override_settings
from django.utils import timezone

from api.views import meeting_agent as executive
from api.views import notification_settings as settings_views
from core import notification_settings as ns
from core.models import Notification, Project, Task, UserProfile
from core.signals import one_notice_per_assignee
from Frontline_agent.models import FrontlineMeeting
from Frontline_agent.tasks import send_meeting_reminders
from hr_agent.models import HRMeeting, HRMeetingParticipant
from hr_agent.tasks import send_hr_meeting_reminders
from hr_agent.tests.base import HRTestCase
from meeting_agent.models import ExecutiveMeeting, ExecutiveTask


class PauseTestCase(HRTestCase):

    def pause(self, login):
        ns.set_choice(login, ns.ALL, email=False)

    def turn_off(self, login, topic):
        ns.set_choice(login, topic, email=False)

    def to(self):
        return sorted(address for message in mail.outbox for address in message.to)

    def employee_login(self, username, company=None):
        """An employee login whose address is `<username>@test.local`."""
        user = get_user_model().objects.create_user(username, email=f'{username}@test.local', password='x',
                                                    first_name=username.title())
        UserProfile.objects.update_or_create(user=user, defaults={'company': company or self.company,
                                                                  'role': 'team_member'})
        return get_user_model().objects.get(pk=user.pk)


class AddressTests(PauseTestCase):
    """The question the senders below ask: an address, in a company, about a topic."""

    def test_an_address_with_no_dashboard_login_is_always_sent_to(self):
        self.assertTrue(ns.address_wants_email(self.company.id, 'someone.else@test.local', 'meeting_reminders'))

    def test_a_dashboard_logins_address_follows_that_logins_settings(self):
        self.assertTrue(ns.address_wants_email(self.company.id, 'MO@test.local', 'meeting_reminders'))
        self.turn_off(self.member, 'meeting_reminders')
        self.assertFalse(ns.address_wants_email(self.company.id, 'MO@test.local', 'meeting_reminders'))
        self.assertTrue(ns.address_wants_email(self.company.id, 'mo@test.local', 'tasks_assigned'))
        self.pause(self.member)
        self.assertFalse(ns.address_wants_email(self.company.id, 'mo@test.local', 'tasks_assigned'))

    def test_pausing_in_one_company_does_not_silence_the_same_address_in_another(self):
        twin = self.login(self.rival, 'mo@test.local', 'Mo Elsewhere', 'company_user')
        self.pause(twin)
        self.assertTrue(ns.address_wants_email(self.company.id, 'mo@test.local', 'meeting_reminders'))
        self.assertFalse(ns.address_wants_email(self.rival.id, 'mo@test.local', 'meeting_reminders'))

    def test_no_address_is_never_sent_to_and_no_company_is_not_guessed(self):
        self.assertFalse(ns.address_wants_email(self.company.id, '  ', 'meeting_reminders'))
        self.pause(self.member)
        self.assertTrue(ns.address_wants_email(None, 'mo@test.local', 'meeting_reminders'))


class SettingsPageTests(PauseTestCase):

    def topics(self, actor=None):
        code, body = self.call(settings_views.company_notification_settings, actor or self.member, method='get')
        self.assertEqual(code, 200, body)
        return {t['key']: t for t in body['data']['topics']}

    def test_reminders_are_offered_to_a_company_with_hr_alone(self):
        topics = self.topics()
        self.assertIn('meeting_reminders', topics)
        self.assertEqual(topics['meeting_reminders']['agent_label'], 'Meetings and tasks')
        self.assertTrue(topics['meeting_reminders']['email'])
        self.assertNotIn('tasks_assigned', topics)            # no Project Manager, no Executive Meeting
        self.assertNotIn('exec_meetings', topics)

    def test_task_and_executive_meeting_emails_can_be_turned_off(self):
        self.buy_module(self.company, 'exec_meeting_agent')
        topics = self.topics()
        for key in ('tasks_assigned', 'exec_meetings'):
            self.assertEqual((topics[key]['email'], topics[key]['offers_email'], topics[key]['offers_in_app']),
                             (True, True, False), key)
        self.assertEqual(topics['exec_meetings']['agent_label'], 'Executive Meeting')
        code, _ = self.call(settings_views.company_notification_settings, self.member,
                            {'topic': 'tasks_assigned', 'email': False}, method='patch')
        self.assertEqual(code, 200)
        self.assertFalse(self.topics()['tasks_assigned']['email'])
        self.assertFalse(ns.wants_email(self.member, 'tasks_assigned'))

    def test_a_company_with_none_of_the_agents_is_not_shown_them(self):
        self.assertNotIn('meeting_reminders', self.topics(self.login(
            self.company_without_agents(), 'una@test.local', 'Una', 'admin')))

    def company_without_agents(self):
        from core.models import Company
        return Company.objects.create(name='Bare', email='bare@test.local')


class HRReminderTests(PauseTestCase):

    def setUp(self):
        super().setUp()
        self.outsider = self.employee_with_login('olga', 'Olga Outside', self.company, self.admin)
        self.meeting = HRMeeting.objects.create(
            company=self.company, title='Probation review', organizer=self.admin_emp,
            scheduled_at=timezone.now() + timedelta(hours=24), status='scheduled')
        for employee in (self.member_emp, self.outsider):
            HRMeetingParticipant.objects.create(meeting=self.meeting, employee=employee)

    def stamped(self):
        return HRMeeting.objects.get(pk=self.meeting.pk).reminder_24h_sent_at is not None

    def test_everyone_gets_it_by_default(self):
        with self.captureOnCommitCallbacks(execute=True):     # emails go once the reminder is saved
            send_hr_meeting_reminders()
        self.assertEqual(self.to(), ['dana@test.local', 'mo@test.local', 'olga@test.local'])

    def test_a_paused_person_does_not(self):
        self.pause(self.member)
        with self.captureOnCommitCallbacks(execute=True):     # emails go once the reminder is saved
            send_hr_meeting_reminders()
        self.assertEqual(self.to(), ['dana@test.local', 'olga@test.local'])
        self.assertTrue(self.stamped())

    def test_nor_someone_who_turned_reminders_off(self):
        self.turn_off(self.admin, 'meeting_reminders')
        with self.captureOnCommitCallbacks(execute=True):     # emails go once the reminder is saved
            send_hr_meeting_reminders()
        self.assertEqual(self.to(), ['mo@test.local', 'olga@test.local'])

    def test_when_nobody_wants_it_nothing_is_sent_and_it_is_not_tried_again(self):
        self.meeting.participants.through.objects.filter(employee=self.outsider).delete()
        self.pause(self.member)
        self.pause(self.admin)
        with self.captureOnCommitCallbacks(execute=True):     # emails go once the reminder is saved
            send_hr_meeting_reminders()
        self.assertEqual(mail.outbox, [])
        self.assertTrue(self.stamped())


class FrontlineReminderTests(PauseTestCase):

    def setUp(self):
        super().setUp()
        self.buy_module(self.company, 'frontline_agent')
        from api.views.frontline_agent import _get_or_create_user_for_company_user
        organiser = _get_or_create_user_for_company_user(self.admin)      # the dashboard login's own user
        self.meeting = FrontlineMeeting.objects.create(
            company=self.company, organizer=organiser, title='Customer call',
            scheduled_at=timezone.now() + timedelta(minutes=60), status='scheduled')     # the hour-before one
        self.meeting.participants.add(self.employee_login('pat'), self.member_emp.user)

    def remind(self):
        with self.captureOnCommitCallbacks(execute=True):      # staff emails go once the stamps are saved
            send_meeting_reminders()

    def test_everyone_gets_it_by_default(self):
        self.remind()
        self.assertEqual(self.to(), ['dana@test.local', 'mo@test.local', 'pat@test.local'])

    def test_a_paused_person_does_not(self):
        self.pause(self.admin)
        self.remind()
        self.assertEqual(self.to(), ['mo@test.local', 'pat@test.local'])

    def test_when_nobody_wants_it_the_reminder_is_still_marked_dealt_with(self):
        self.meeting.participants.clear()
        self.pause(self.admin)
        self.remind()
        self.assertEqual(mail.outbox, [])
        self.assertIsNotNone(FrontlineMeeting.objects.get(pk=self.meeting.pk).reminder_60m_sent_at)


class ExecutiveMeetingEmailTests(PauseTestCase):

    def setUp(self):
        super().setUp()
        self.meeting = ExecutiveMeeting.objects.create(organizer=self.admin, title='Board meeting',
                                                       scheduled_at=timezone.now() + timedelta(days=2),
                                                       duration_minutes=30)
        self.task = ExecutiveTask.objects.create(company_user=self.admin, title='Send the minutes',
                                                 priority='high')

    def every_email_to(self, login):
        executive._send_meeting_invite_email(login, self.meeting, 'Dana Admin')
        executive._send_meeting_update_email(login, self.meeting, 'Dana Admin', ['time'])
        executive._send_meeting_removal_email(login, self.meeting, 'Dana Admin')
        executive._send_task_assignment_email(login, self.task, 'Dana Admin')
        executive._send_subtask_added_email(login, self.task, self.task, 'Dana Admin')
        executive._send_task_removal_email(login, self.task, 'Dana Admin')
        executive._send_task_deleted_email(login, 'Send the minutes', 'high', 'Dana Admin')
        return [message.subject.split(':')[0] for message in mail.outbox]

    def test_all_seven_go_by_default(self):
        subjects = self.every_email_to(self.member)
        self.assertEqual(len(subjects), 7, subjects)
        self.assertEqual(self.to(), ['mo@test.local'] * 7)

    def test_none_go_to_someone_who_paused_all_emails(self):
        self.pause(self.member)
        self.assertEqual(self.every_email_to(self.member), [])

    def test_meeting_emails_and_task_emails_are_turned_off_separately(self):
        self.turn_off(self.member, 'tasks_assigned')
        self.assertEqual(self.every_email_to(self.member),
                         ['Meeting Invitation', 'Meeting Updated', 'Removed from Meeting'])
        mail.outbox.clear()
        ns.set_choice(self.member, 'tasks_assigned', email=True)
        self.turn_off(self.member, 'exec_meetings')
        self.assertEqual(len(self.every_email_to(self.member)), 4)


@override_settings(FRONTEND_URL='https://app.example.test')
class TaskAssignedEmailTests(PauseTestCase):

    def setUp(self):
        super().setUp()
        self.project = Project.objects.create(name='Website', company=self.company,
                                              created_by_company_user=self.admin, owner=self.admin_emp.user)
        self.pat = self.employee_login('pat')               # an employee with no dashboard login
        self.mo = self.employee_login('mo')                 # the same address as Mo's dashboard login

    def assign(self, title, to):
        return Task.objects.create(title=title, project=self.project, assignee=to, status='todo')

    def test_an_employee_gets_the_email_with_a_link_that_opens(self):
        self.assign('Build the header', self.pat)
        [message] = mail.outbox
        self.assertEqual((message.to, message.subject), (['pat@test.local'], 'New Task Assigned: Build the header'))
        self.assertIn('https://app.example.test/me/tasks', message.body)
        self.assertNotIn('/projects/', message.body)

    def test_someone_who_paused_all_emails_on_their_dashboard_login_does_not(self):
        self.pause(self.member)
        self.assign('Build the header', self.mo)
        self.assertEqual(mail.outbox, [])
        # The alert in My Space is not an email and still appears.
        self.assertEqual(Notification.objects.filter(user=self.mo, type='task_assigned').count(), 1)

    def test_nor_someone_who_turned_task_emails_off(self):
        self.turn_off(self.member, 'tasks_assigned')
        self.assign('Build the header', self.mo)
        self.assertEqual(mail.outbox, [])

    def test_a_dashboard_login_that_has_not_paused_gets_it(self):
        self.assign('Build the header', self.mo)
        self.assertEqual(self.to(), ['mo@test.local'])


@override_settings(FRONTEND_URL='https://app.example.test')
class OneNoticeForManyTasksTests(PauseTestCase):

    def setUp(self):
        super().setUp()
        self.project = Project.objects.create(name='Website', company=self.company,
                                              created_by_company_user=self.admin, owner=self.admin_emp.user)
        self.lee = self.employee_login('lee')
        self.tom = self.employee_login('tom')
        self.tasks = [Task.objects.create(title=title, project=self.project, assignee=self.lee, status='todo')
                      for title in ('Header', 'Footer', 'Sitemap')]
        mail.outbox.clear()
        Notification.objects.all().delete()

    def give(self, tasks, to):
        for task in tasks:
            task.assignee = to
            task.save()

    def alerts(self, user):
        return list(Notification.objects.filter(user=user, type='task_assigned').values_list('title', flat=True))

    def test_three_tasks_handed_over_make_one_email_and_one_alert(self):
        with one_notice_per_assignee('From Lee Leaver, who is leaving.'):
            self.give(self.tasks, self.tom)
            self.assertEqual(mail.outbox, [])                # nothing until it has all moved
        [message] = mail.outbox
        self.assertEqual((message.to, message.subject), (['tom@test.local'], '3 tasks assigned to you'))
        for expected in ('Header', 'Footer', 'Sitemap', 'From Lee Leaver, who is leaving.',
                         'https://app.example.test/me/tasks'):
            self.assertIn(expected, message.body)
        self.assertEqual(self.alerts(self.tom), ['3 tasks assigned to you'])

    def test_outside_a_hand_over_each_task_still_tells_its_new_owner(self):
        self.give(self.tasks, self.tom)
        self.assertEqual(len(mail.outbox), 3)
        self.assertEqual(len(self.alerts(self.tom)), 3)

    def test_and_so_does_the_next_assignment_after_a_hand_over(self):
        with one_notice_per_assignee():
            self.give(self.tasks[:2], self.tom)
        mail.outbox.clear()
        self.give(self.tasks[2:], self.tom)
        self.assertEqual([m.subject for m in mail.outbox], ['New Task Assigned: Sitemap'])

    def test_one_task_handed_over_reads_like_any_other_assignment(self):
        with one_notice_per_assignee('From Lee Leaver, who is leaving.'):
            self.give(self.tasks[:1], self.tom)
        self.assertEqual([m.subject for m in mail.outbox], ['New Task Assigned: Header'])
        self.assertEqual(self.alerts(self.tom), ['New Task Assigned: Header'])

    def test_each_person_is_told_about_their_own(self):
        pat = self.employee_login('pat')
        with one_notice_per_assignee():
            self.give(self.tasks[:2], self.tom)
            self.give(self.tasks[2:], pat)
        self.assertEqual(sorted((m.to[0], m.subject) for m in mail.outbox),
                         [('pat@test.local', 'New Task Assigned: Sitemap'),
                          ('tom@test.local', '2 tasks assigned to you')])

    def test_if_the_hand_over_fails_nobody_is_told_and_nothing_is_left_switched_on(self):
        with self.assertRaises(RuntimeError):
            with one_notice_per_assignee():
                self.give(self.tasks[:2], self.tom)
                raise RuntimeError('the move was rolled back')
        self.assertEqual(mail.outbox, [])
        self.assertEqual(self.alerts(self.tom), [])
        self.give(self.tasks[2:], self.tom)                  # an ordinary assignment afterwards
        self.assertEqual(len(mail.outbox), 1)

    def test_the_summary_obeys_pause_all_emails(self):
        mo = self.employee_login('mo')
        self.pause(self.member)
        with one_notice_per_assignee():
            self.give(self.tasks, mo)
        self.assertEqual(mail.outbox, [])
        self.assertEqual(self.alerts(mo), ['3 tasks assigned to you'])
