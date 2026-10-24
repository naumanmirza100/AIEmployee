"""An HR notification sent "In-app" reaches the person's bell, and SMS is no longer offered.

The template screen offered SMS and In-app. The server dropped every notification on either ("not implemented yet
— notification dropped"), so a birthday or probation reminder set to In-app reached nobody, and nobody was told.
"""
from django.utils import timezone

from api.views import hr_agent as views
from core.models import Notification
from hr_agent.models import HRNotificationTemplate, HRScheduledNotification
from hr_agent.tasks import process_hr_scheduled_notifications
from project_manager_agent.models import PMNotification

from .base import HRTestCase


class InAppTests(HRTestCase):

    def template(self, channel='in_app'):
        return HRNotificationTemplate.objects.create(
            company=self.company, name='Probation ending', channel=channel, subject='Your probation ends soon',
            body='Hi {employee_name}, your probation ends next week.', trigger_config={'on': 'probation_ending'})

    def test_in_app_reaches_a_member_of_staff_in_my_space(self):
        staff = self.employee_with_login('ayesha', 'Ayesha Khan', self.company, self.admin)
        ok, used = views._dispatch_hr_notification(self.template(), staff.work_email, 'Probation', 'Ends soon',
                                                   self.company)
        self.assertEqual((ok, used), (True, 'in_app'))
        self.assertTrue(Notification.objects.filter(user=staff.user, title='Probation').exists())

    def test_in_app_reaches_a_dashboard_login_in_its_bell(self):
        ok, _ = views._dispatch_hr_notification(self.template(), self.member.email, 'Review due', 'This Friday',
                                                self.company)
        self.assertTrue(ok)
        self.assertTrue(PMNotification.objects.filter(company_user=self.member, title='Review due').exists())

    def test_nobody_with_that_address_is_not_a_success(self):
        ok, _ = views._dispatch_hr_notification(self.template(), 'nobody@test.local', 'Hi', 'There', self.company)
        self.assertFalse(ok)

    def test_another_companys_person_with_the_address_is_not_told(self):
        ok, _ = views._dispatch_hr_notification(self.template(), self.rival_admin.email, 'Hi', 'There', self.company)
        self.assertFalse(ok)
        self.assertFalse(PMNotification.objects.filter(company_user=self.rival_admin).exists())

    def test_a_scheduled_in_app_notification_is_sent(self):
        staff = self.employee_with_login('bilal', 'Bilal Ahmed', self.company, self.admin)
        notif = HRScheduledNotification.objects.create(
            company=self.company, template=self.template(), recipient_employee=staff,
            recipient_email=staff.work_email, scheduled_at=timezone.now(), status='pending', context={})
        process_hr_scheduled_notifications()
        notif.refresh_from_db()
        self.assertEqual(notif.status, 'sent', notif.error_message)
        self.assertTrue(Notification.objects.filter(user=staff.user).exists())


class NoSMSTests(HRTestCase):

    def request(self, view, method, data, **kwargs):
        from rest_framework.test import force_authenticate
        request = getattr(self.factory, method)('/', data, format='json')
        force_authenticate(request, user=self.admin)
        response = view(request, **kwargs)
        return response.status_code, response.data

    def test_a_template_cannot_be_saved_with_sms(self):
        code, body = self.request(views.create_hr_notification_template, 'post', {
            'name': 'Birthday', 'channel': 'sms', 'body': 'Happy birthday {employee_name}',
            'trigger_config': {'on': 'birthday'}})
        self.assertEqual(code, 400, body)
        self.assertIn('SMS', body['message'])
        self.assertFalse(HRNotificationTemplate.objects.filter(name='Birthday').exists())

    def test_in_app_can_be_saved(self):
        code, body = self.request(views.create_hr_notification_template, 'post', {
            'name': 'Birthday', 'channel': 'in_app', 'body': 'Happy birthday {employee_name}',
            'trigger_config': {'on': 'birthday'}})
        self.assertIn(code, (200, 201), body)

    def test_a_template_cannot_be_changed_to_sms(self):
        tpl = HRNotificationTemplate.objects.create(company=self.company, name='Birthday', channel='email',
                                                    body='Happy birthday', trigger_config={'on': 'birthday'})
        code, body = self.request(views.update_hr_notification_template, 'patch', {'channel': 'sms'},
                                  template_id=tpl.id)
        self.assertEqual(code, 400, body)
        tpl.refresh_from_db()
        self.assertEqual(tpl.channel, 'email')
