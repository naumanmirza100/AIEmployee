"""One notification settings page, which every alert and email asks first.

Each agent used to decide on its own: Frontline had email switches (one that
nothing read), PM had channels, and the alerts reaching the shared bell — and
several emails to dashboard logins — couldn't be turned off at all.
"""
from datetime import timedelta
from importlib import import_module

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core import mail
from django.utils import timezone

from api.views import frontline_agent as frontline_views
from api.views import notification as meeting_views
from api.views import notification_settings as views
from core import notification_settings as ns
from core.models import NotificationSetting, UserProfile
from core.notification_utils import notify_company_users
from Frontline_agent.models import FrontlineNotificationPreferences
from hr_agent.tests.base import HRTestCase
from project_manager_agent.models import MeetingParticipant, PMNotification, ScheduledMeeting


class SettingsTestCase(HRTestCase):

    def setUp(self):
        super().setUp()
        for module in ('frontline_agent', 'project_manager_agent'):
            self.buy_module(self.company, module)

    def page(self, actor=None):
        code, body = self.call(views.company_notification_settings, actor or self.member, method='get')
        self.assertEqual(code, 200, body)
        return {t['key']: t for t in body['data']['topics']}, body['data']

    def change(self, data, actor=None):
        return self.call(views.company_notification_settings, actor or self.member, data, method='patch')

    def alert(self, kind='hr_leave_request', who=None):
        with self.captureOnCommitCallbacks(execute=True):
            return notify_company_users([who or self.member], title='Leave request from Zed',
                                        message='Vacation, 12 Oct.', link='/hr/dashboard?tab=leave', kind=kind)

    def bell(self, who=None):
        return PMNotification.objects.filter(company_user=who or self.member)


class TheSettingsPageTests(SettingsTestCase):

    def test_defaults_keep_what_each_topic_did_before(self):
        topics, data = self.page()
        self.assertFalse(data['email_paused'])
        # Already emailed: still does. Bell-only: doesn't start emailing.
        self.assertTrue(topics['meeting_replies']['email'])
        self.assertTrue(topics['weekly_digest']['email'])
        self.assertFalse(topics['leave_requests']['email'])
        self.assertFalse(topics['handoffs']['email'])
        self.assertTrue(all(t['in_app'] for t in topics.values() if t['offers_in_app']))

    def test_only_the_agents_the_company_uses(self):
        topics, _ = self.page()
        self.assertIn('handoffs', topics)                 # Frontline: bought
        self.assertIn('leave_requests', topics)           # HR: bought
        self.assertNotIn('interviews_booked', topics)     # Recruitment: not bought
        self.assertIn('handover', topics)                 # everyone
        self.assertEqual(topics['handover']['agent_label'], 'Everyone')

    def test_a_choice_is_saved_and_shown(self):
        code, body = self.change({'topic': 'leave_requests', 'email': True})
        self.assertEqual(code, 200, body)
        topics, _ = self.page()
        self.assertTrue(topics['leave_requests']['email'])
        self.assertTrue(topics['leave_requests']['in_app'])        # the other half kept

    def test_billing_alerts_stay_in_the_bell(self):
        self.change({'topic': 'account', 'in_app': False})
        topics, _ = self.page()
        self.assertTrue(topics['account']['in_app'])
        # Even if a row says otherwise.
        NotificationSetting.objects.filter(company_user=self.member, topic='account').update(in_app=False)
        self.alert(kind='key_request_rejected')
        self.assertEqual(self.bell().count(), 1)

    def test_unknown_topics_are_refused(self):
        self.assertEqual(self.change({'topic': 'nope', 'email': True})[0], 400)

    def test_through_the_url(self):
        code, body = self.send(self.http(self.member), 'patch', '/api/company/notification-settings',
                               {'email_paused': True})
        self.assertEqual((code, body['data']['email_paused']), (200, True))


class AlertsAskFirstTests(SettingsTestCase):

    def test_an_alert_goes_where_its_owner_wants_it(self):
        self.change({'topic': 'leave_requests', 'email': True})
        self.alert()
        self.assertEqual(self.bell().count(), 1)
        [email] = mail.outbox
        self.assertEqual((email.to, email.subject), ([self.member.email], 'Leave request from Zed'))
        self.assertIn('/hr/dashboard?tab=leave', email.body)
        self.assertIn('Leave requests waiting for a decision', email.body)      # why they got it
        self.assertIn(ns.SETTINGS_PATH, email.body)                            # and where to change it

    def test_by_default_it_is_bell_only(self):
        self.alert()
        self.assertEqual((self.bell().count(), len(mail.outbox)), (1, 0))

    def test_out_of_the_bell(self):
        self.change({'topic': 'leave_requests', 'in_app': False, 'email': True})
        self.alert()
        self.assertEqual((self.bell().count(), len(mail.outbox)), (0, 1))

    def test_pausing_email_stops_every_email_but_not_the_bell(self):
        self.change({'topic': 'leave_requests', 'email': True})
        self.change({'email_paused': True})
        self.alert()
        self.assertEqual((self.bell().count(), len(mail.outbox)), (1, 0))
        topics, data = self.page()
        self.assertTrue(data['email_paused'])
        self.assertTrue(topics['leave_requests']['email'])           # remembered for when it's unpaused

    def test_each_person_is_asked_for_themselves(self):
        self.change({'topic': 'leave_requests', 'in_app': False})
        with self.captureOnCommitCallbacks(execute=True):
            notify_company_users([self.member, self.admin], title='Leave', message='x', kind='hr_leave_request')
        self.assertEqual((self.bell(self.member).count(), self.bell(self.admin).count()), (0, 1))

    def test_handover_kinds_share_one_topic(self):
        self.change({'topic': 'handover', 'in_app': False})
        self.alert(kind='handover_projects')
        self.assertEqual(self.bell().count(), 0)

    def test_an_alert_with_no_topic_is_always_in_the_bell_and_never_emailed(self):
        self.change({'email_paused': False})
        self.alert(kind='something_new')
        self.assertEqual((self.bell().count(), len(mail.outbox)), (1, 0))

    def test_the_setting_is_read_again_when_the_email_goes_out(self):
        self.change({'topic': 'leave_requests', 'email': True})
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            notify_company_users([self.member], title='Leave', message='x', kind='hr_leave_request')
        self.change({'topic': 'leave_requests', 'email': False})
        for callback in callbacks:
            callback()
        self.assertEqual(len(mail.outbox), 0)


class MeetingRepliesTests(SettingsTestCase):

    def setUp(self):
        super().setUp()
        self.ali = get_user_model().objects.create_user(username='ali', password='x', email='ali@test.local')
        UserProfile.objects.update_or_create(user=self.ali, defaults={'company': self.company, 'role': 'team_member'})
        self.ali = get_user_model().objects.get(pk=self.ali.pk)
        self.meeting = ScheduledMeeting.objects.create(organizer=self.member, invitee=self.ali, title='Planning',
                                                       proposed_time=timezone.now() + timedelta(days=2))
        MeetingParticipant.objects.create(meeting=self.meeting, user=self.ali, status='pending')

    def reply(self):
        with self.captureOnCommitCallbacks(execute=True):
            code, body = self.call(meeting_views.meeting_respond, self.ali, {'action': 'accepted'},
                                   meeting_id=self.meeting.id)
        self.assertEqual(code, 200, body)

    def test_the_organiser_hears_with_a_link_and_by_email(self):
        self.reply()
        [row] = self.bell()
        self.assertEqual(row.data['link'], '/project-manager/dashboard?tab=meeting-scheduler')
        self.assertEqual([m.to for m in mail.outbox], [[self.member.email]])       # one email, not two

    def test_and_can_turn_the_email_off(self):
        self.change({'topic': 'meeting_replies', 'email': False})
        self.reply()
        self.assertEqual((self.bell().count(), len(mail.outbox)), (1, 0))


class FrontlineMergedTests(SettingsTestCase):

    def test_its_emails_ask_the_one_settings_page(self):
        check = frontline_views._should_send_notification_to_recipient
        self.assertTrue(check(self.company.id, self.member.email, 'email', 'ticket_created'))
        self.change({'topic': 'ticket_created', 'email': False})
        self.assertFalse(check(self.company.id, self.member.email.upper(), 'email', 'ticket_created'))
        self.assertTrue(check(self.company.id, self.member.email, 'email', 'ticket_updated'))
        self.assertTrue(check(self.company.id, 'customer@elsewhere.test', 'email', 'ticket_created'))

    def test_its_old_switches_read_and_write_the_same_settings(self):
        code, _ = self.call(frontline_views.update_notification_preferences, self.member,
                            {'workflow_email_enabled': False}, method='patch')
        self.assertEqual(code, 200)
        topics, _ = self.page()
        self.assertFalse(topics['automation_emails']['email'])
        code, body = self.call(frontline_views.get_notification_preferences, self.member, method='get')
        self.assertFalse(body['data']['workflow_email_enabled'])
        self.assertTrue(body['data']['ticket_created_email'])

    def test_unsubscribing_turns_off_its_automation_emails_only(self):
        from Frontline_agent.notification_utils import make_unsubscribe_token
        token = make_unsubscribe_token(self.member.id)
        code, _ = self.call(frontline_views.public_unsubscribe, None, {'t': token})
        self.assertEqual(code, 200)
        topics, _ = self.page()
        self.assertEqual([k for k in ns.FRONTLINE_AUTOMATION if topics[k]['email']], [])
        self.assertTrue(topics['meeting_replies']['email'])

    def test_the_weekly_summary_goes_to_those_who_want_it(self):
        from Frontline_agent.models import Ticket
        from Frontline_agent.tasks import send_weekly_analytics_digest
        self.admin.refresh_from_db()
        Ticket.objects.create(title='T', description='x', company=self.company, created_by=self.admin.login_user)
        self.change({'topic': 'weekly_digest', 'email': False})
        send_weekly_analytics_digest()
        [email] = [m for m in mail.outbox if 'weekly digest' in m.subject]
        self.assertIn(self.admin.email, email.to)
        self.assertNotIn(self.member.email, email.to)

    def test_switches_turned_off_before_carry_over(self):
        FrontlineNotificationPreferences.objects.create(company_user=self.member, email_enabled=False)
        FrontlineNotificationPreferences.objects.create(company_user=self.admin, ticket_updated_email=False)
        import_module('Frontline_agent.migrations.0048_preferences_to_notification_settings').carry_over(apps, None)
        self.assertEqual(set(NotificationSetting.objects.filter(company_user=self.member, email=False)
                             .values_list('topic', flat=True)), set(ns.FRONTLINE_AUTOMATION))
        self.assertEqual(list(NotificationSetting.objects.filter(company_user=self.admin)
                              .values_list('topic', flat=True)), ['ticket_updated'])
