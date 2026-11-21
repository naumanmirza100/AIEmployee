"""HR permissions found by Mahnoor's all-agents test (20 Nov 2026) and the review of it (21 Nov).

- HR 7: an HR-only login could make itself a company admin and demote the owner.
- HR 5: any login could open a colleague's whole HR record: released reviews, leave reasons, balances, goals, the list
  of their personal documents; the staff list gave everyone's date of birth.
- HR 8 and more: any login could change the accrual policy, the HR email templates, and add employee records.
- HR 11: anyone could open, move or cancel any HR meeting, a colleague's one-to-one included.
- HR 15: an unknown confidentiality became "all employees".
"""
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import force_authenticate

from api.views import company_logins
from api.views import hr_agent as views
from hr_agent.models import HRMeeting, HRMeetingParticipant, HRNotificationTemplate, LeaveAccrualPolicy

from .base import HRTestCase


class Logins(HRTestCase):

    def setUp(self):
        super().setUp()
        self.owner = self.login(self.company, 'olga@test.local', 'Olga Owner', 'owner')
        self.hr = self.login(self.company, 'hina@test.local', 'Hina HR', 'hr_agent')

    def role(self, actor, target, role):
        return self.call(views.set_company_user_role, actor, {'role': role}, company_user_id=target.id)

    def test_an_hr_only_login_cannot_make_itself_admin_or_touch_the_owner_or_an_admin(self):
        code, body = self.role(self.hr, self.hr, 'admin')
        self.assertEqual(code, 400, body)                                     # nobody changes their own role
        for target, role in ((self.owner, 'employee'), (self.admin, 'employee'), (self.member, 'admin')):
            with self.subTest(target=target.email, role=role):
                code, body = self.role(self.hr, target, role)
                self.assertEqual(code, 403, body)
        self.owner.refresh_from_db()
        self.hr.refresh_from_db()
        self.assertEqual((self.owner.role, self.hr.role), ('owner', 'hr_agent'))

    def test_an_hr_only_login_gives_the_roles_below_it(self):
        for role in ('manager', 'hr_agent', 'employee'):
            with self.subTest(role=role):
                self.assertEqual(self.role(self.hr, self.member, role)[0], 200)
        code, body = self.call(views.list_company_user_roles, self.hr, method='get')
        self.assertNotIn('admin', body['assignable_roles'])

    def test_an_admin_gives_admin_but_only_the_owner_changes_the_owner(self):
        self.assertEqual(self.role(self.admin, self.member, 'admin')[0], 200)
        self.assertEqual(self.role(self.admin, self.owner, 'company_user')[0], 403)
        self.assertEqual(self.role(self.owner, self.member, 'company_user')[0], 200)

    def test_nobody_changes_their_own_role(self):
        self.assertEqual(self.role(self.owner, self.owner, 'admin')[0], 400)

    def test_on_the_logins_page_an_admin_cannot_change_or_switch_off_the_owner(self):
        for change in ({'role': 'company_user'}, {'is_active': False}):
            with self.subTest(change=change):
                code, body = self.call(company_logins.company_login, self.admin, change, method='patch',
                                       login_id=self.owner.id)
                self.assertEqual(code, 403, body)
        self.owner.refresh_from_db()
        self.assertEqual((self.owner.role, self.owner.is_active), ('owner', True))


class Settings(HRTestCase):

    def test_a_member_cannot_add_employees_or_change_accrual_or_templates(self):
        policy = LeaveAccrualPolicy.objects.create(company=self.company, leave_type='vacation', period='monthly',
                                                   days_per_period=1.5)
        template = HRNotificationTemplate.objects.create(company=self.company, name='Welcome', body='Hi')
        calls = (
            (views.create_employee, {'work_email': 'new@test.local', 'full_name': 'New One'}, {}),
            (views.upsert_accrual_policy, {'leave_type': 'vacation', 'period': 'monthly', 'days_per_period': 10}, {}),
            (views.delete_accrual_policy, {}, {'policy_id': policy.id}),
            (views.create_hr_notification_template, {'name': 'Mine', 'body': 'Hello'}, {}),
            (views.update_hr_notification_template, {'body': 'Changed'}, {'template_id': template.id}),
            (views.delete_hr_notification_template, {}, {'template_id': template.id}),
        )
        for view, data, kwargs in calls:
            with self.subTest(view=view.__name__):
                method = 'patch' if view is views.update_hr_notification_template else (
                    'delete' if view in (views.delete_hr_notification_template,) else 'post')
                code, body = self.call(view, self.member, data, method=method, **kwargs)
                self.assertEqual(code, 403, body)
        policy.refresh_from_db()
        template.refresh_from_db()
        self.assertEqual((float(policy.days_per_period), template.body), (1.5, 'Hi'))
        from hr_agent.models import Employee
        self.assertFalse(Employee.objects.filter(company=self.company, work_email='new@test.local').exists())

    def test_an_hr_admin_still_can(self):
        code, body = self.call(views.upsert_accrual_policy, self.admin,
                               {'leave_type': 'vacation', 'period': 'monthly', 'days_per_period': 2})
        self.assertEqual(code, 200, body)

    def test_an_unknown_confidentiality_is_refused(self):
        request = self.factory.post('/', {'file': SimpleUploadedFile('bands.txt', b'Grade A: PKR 300,000.'),
                                          'confidentiality': 'confidential'}, format='multipart')
        force_authenticate(request, user=self.admin)
        response = views.upload_hr_document(request)
        response.render()
        self.assertEqual(response.status_code, 400)
        self.assertIn('not a confidentiality level', response.data['message'])


class Colleagues(HRTestCase):

    def setUp(self):
        super().setUp()
        self.zara_login = self.login(self.company, 'zara@test.local', 'Zara Z', 'company_user')
        self.zara = self.employee(self.zara_login, 'Zara Z')
        self.ali = self.employee(self.login(self.company, 'ali@test.local', 'Ali A', 'company_user'), 'Ali A')
        self.ali.employment_status = 'notice'
        self.ali.date_of_birth = self.now().date() - timedelta(days=30 * 365)
        self.ali.save()

    def detail(self, actor, employee):
        return self.call(views.get_employee_detail, actor, method='get', employee_id=employee.id)

    def test_a_colleague_sees_a_directory_entry_only(self):
        code, body = self.detail(self.member, self.ali)
        self.assertEqual(code, 200)
        data = body['data']
        self.assertTrue(data['limited'])
        self.assertEqual(data['employee']['employment_status'], 'active')      # not "notice"
        self.assertNotIn('date_of_birth', data['employee'])
        for key in ('leave_balances', 'leave_requests', 'personal_documents', 'goals', 'released_reviews'):
            self.assertEqual(data[key], [], key)
        code, _ = self.call(views.list_employee_reviews, self.member, method='get', employee_id=self.ali.id)
        self.assertEqual(code, 403)

    def test_the_person_their_manager_and_hr_see_the_whole_record(self):
        self.zara.manager = self.member_emp
        self.zara.save()
        for actor in (self.zara_login, self.member, self.admin):
            with self.subTest(actor=actor.email):
                code, body = self.detail(actor, self.zara)
                self.assertEqual(code, 200)
                self.assertNotIn('limited', body['data'])
                self.assertIn('date_of_birth', body['data']['employee'])

    def test_the_staff_list_gives_colleagues_directory_entries_and_does_not_name_who_is_on_notice(self):
        code, body = self.call(views.list_employees, self.member, method='get')
        rows = {r['full_name']: r for r in body['data']}
        self.assertNotIn('date_of_birth', rows['Ali A'])
        self.assertEqual(rows['Ali A']['employment_status'], 'active')
        self.assertIn('date_of_birth', rows['Mo Member'])                     # their own entry is whole
        request = self.factory.get('/', {'status': 'notice'})
        force_authenticate(request, user=self.member)
        response = views.list_employees(request)
        response.render()
        self.assertEqual(response.data['data'], [])


class Meetings(HRTestCase):

    def setUp(self):
        super().setUp()
        self.zara_login = self.login(self.company, 'zara@test.local', 'Zara Z', 'company_user')
        self.zara = self.employee(self.zara_login, 'Zara Z')
        at = self.now() + timedelta(days=3)
        self.one_to_one = self.meeting('Zara 1:1', 'one_on_one', at)
        self.training = self.meeting('Security training', 'training_session', at + timedelta(hours=2))

    def meeting(self, title, kind, at):
        m = HRMeeting.objects.create(company=self.company, title=title, meeting_type=kind, visibility='company',
                                     organizer=self.admin_emp, scheduled_at=at, duration_minutes=30)
        HRMeetingParticipant.objects.create(meeting=m, employee=self.zara)
        return m

    def test_a_colleagues_one_to_one_is_hidden_from_others(self):
        code, _ = self.call(views.get_hr_meeting, self.member, method='get', meeting_id=self.one_to_one.id)
        self.assertEqual(code, 404)
        code, _ = self.call(views.cancel_hr_meeting, self.member, {}, meeting_id=self.one_to_one.id)
        self.assertEqual(code, 404)
        code, body = self.call(views.list_hr_meetings, self.member, method='get')
        self.assertEqual([m['title'] for m in body['data']], ['Security training'])

    def test_only_whoever_runs_it_or_hr_moves_or_cancels_a_meeting(self):
        code, _ = self.call(views.get_hr_meeting, self.member, method='get', meeting_id=self.training.id)
        self.assertEqual(code, 200)
        for actor in (self.member, self.zara_login):
            with self.subTest(actor=actor.email):
                code, body = self.call(views.cancel_hr_meeting, actor, {}, meeting_id=self.training.id)
                self.assertEqual(code, 403, body)
                code, body = self.call(views.update_hr_meeting, actor, {'title': 'Moved'}, method='patch',
                                       meeting_id=self.training.id)
                self.assertEqual(code, 403, body)
        self.training.refresh_from_db()
        self.assertEqual((self.training.status, self.training.title), ('scheduled', 'Security training'))
        code, _ = self.call(views.cancel_hr_meeting, self.admin, {}, meeting_id=self.training.id)
        self.assertEqual(code, 200)
        code, _ = self.call(views.get_hr_meeting, self.zara_login, method='get', meeting_id=self.one_to_one.id)
        self.assertEqual(code, 200)                                           # her own one-to-one
