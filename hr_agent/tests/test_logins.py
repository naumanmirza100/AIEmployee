"""A person's dashboard login and employee login can be joined into one person.

The calendar, My work and HR self-service treat a dashboard login as a person
through `Employee.company_user`. Nothing set it. So leave approved for someone
who works from a dashboard login blocked nothing: the other agents still booked
them. An HR admin can now set it from the employee's record, and it sets itself
when the two logins have the same address.
"""
from datetime import timedelta
from importlib import import_module

from django.apps import apps
from django.contrib.auth import get_user_model
from django.utils import timezone

from api.views import hr_agent as views
from core import logins as core_logins
from core.models import CompanyUser, UserProfile
from core.scheduling import ScheduleConflict, ensure_free, login_user_id_for_company_user
from hr_agent import logins
from hr_agent.models import Employee, HRAuditLog

from .base import HRTestCase

User = get_user_model()
backfill = import_module('hr_agent.migrations.0019_link_dashboard_logins').link_by_email


class LinkTests(HRTestCase):

    def setUp(self):
        super().setUp()
        # Sam has an employee login. Bo is a dashboard login with another address.
        self.sam = self.employee_with_login('sam', 'Sam Staff', self.company, self.admin)
        self.bo = self.login(self.company, 'bo@test.local', 'Bo Boss', 'company_user')
        self.contractor = Employee.objects.create(company=self.company, full_name='Con Tractor',
                                                  work_email='con@elsewhere.example', employment_status='active')

    def set_login(self, employee, login, actor=None):
        return self.call(views.set_employee_dashboard_login, actor or self.admin,
                         {'company_user_id': login.id if login else None}, employee_id=employee.id)

    # ---- what the link is for -----------------------------------------------------

    def test_a_linked_dashboard_login_is_that_person_on_the_calendar(self):
        self.assertIsNone(login_user_id_for_company_user(self.bo))             # nobody, until linked
        code, body = self.set_login(self.sam, self.bo)
        self.assertEqual((code, body['warning']), (200, ''), body)
        self.assertEqual(login_user_id_for_company_user(self.bo), self.sam.user_id)

    def test_so_their_leave_blocks_a_booking(self):
        self.set_login(self.sam, self.bo)
        day = timezone.localdate() + timedelta(days=10)
        self.leave_request(self.sam, status='approved', start_date=day, end_date=day, days_requested=1)
        when = timezone.now().replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=10)
        with self.assertRaises(ScheduleConflict):
            ensure_free([login_user_id_for_company_user(self.bo)], when, 30)

    # ---- who may, and what is refused -------------------------------------------------

    def test_only_an_hr_admin_can_link_or_see_the_list(self):
        code, body = self.set_login(self.sam, self.bo, actor=self.member)
        self.assertEqual(code, 403, body)
        self.sam.refresh_from_db()
        self.assertIsNone(self.sam.company_user_id)
        self.assertEqual(self.call(views.list_dashboard_logins, self.member, method='get')[0], 403)

    def test_a_login_belongs_to_one_record(self):
        self.set_login(self.sam, self.bo)
        code, body = self.set_login(self.contractor, self.bo)
        self.assertEqual(code, 409)
        self.assertIn('already linked to Sam Staff', body['message'])
        self.contractor.refresh_from_db()
        self.assertIsNone(self.contractor.company_user_id)
        self.assertEqual(self.set_login(self.sam, self.bo)[0], 200)             # choosing it again is fine

    def test_another_companys_login_or_record_cannot_be_used(self):
        self.assertEqual(self.set_login(self.sam, self.rival_admin)[0], 404)
        self.assertEqual(self.set_login(self.rival_emp, self.bo)[0], 404)
        code, _ = self.call(views.set_employee_dashboard_login, self.admin, {'company_user_id': 'x'},
                            employee_id=self.sam.id)
        self.assertEqual(code, 404)

    def test_a_record_with_no_employee_login_can_be_linked_and_is_told_what_that_means(self):
        code, body = self.set_login(self.contractor, self.bo)
        self.assertEqual(code, 200, body)
        self.assertIn('no employee login yet', body['warning'])
        self.assertEqual((body['data']['on_calendar'], body['data']['dashboard_login']['email']),
                         (False, 'bo@test.local'))
        self.assertIsNone(login_user_id_for_company_user(self.bo))             # the calendar still cannot place them
        code, body = self.set_login(self.contractor, None)
        self.assertEqual((code, body['warning']), (200, ''))                    # nothing to warn about once it is off

    def test_the_link_can_be_taken_off_and_both_changes_are_logged(self):
        self.set_login(self.sam, self.bo)
        code, body = self.set_login(self.sam, None)
        self.assertEqual((code, body['data']['dashboard_login']), (200, None))
        self.assertIsNone(login_user_id_for_company_user(self.bo))
        diffs = list(HRAuditLog.objects.filter(action='employee.dashboard_login').order_by('id')
                     .values_list('diff', flat=True))
        self.assertEqual([d['after']['company_user_id'] for d in diffs], [self.bo.id, None])

    def test_linking_does_not_start_a_workflow_or_touch_the_person(self):
        before = Employee.objects.get(pk=self.sam.pk).updated_at
        self.set_login(self.sam, self.bo)
        self.assertEqual(Employee.objects.get(pk=self.sam.pk).updated_at, before)

    # ---- what the screens are told ------------------------------------------------------

    def test_the_record_shows_its_logins_and_who_may_change_them(self):
        self.set_login(self.sam, self.bo)
        for actor, may in ((self.admin, True), (self.member, False)):
            code, body = self.call(views.get_employee_detail, actor, method='get', employee_id=self.sam.id)
            self.assertEqual(code, 200, body)
            found = body['data']['logins']
            self.assertEqual((found['employee_login']['username'], found['dashboard_login']['full_name'],
                              found['on_calendar'], found['can_manage']), ('sam', 'Bo Boss', True, may))

    def test_the_picker_lists_this_companys_logins_and_what_each_is_linked_to(self):
        self.set_login(self.sam, self.bo)
        code, body = self.call(views.list_dashboard_logins, self.admin, method='get')
        self.assertEqual(code, 200, body)
        linked = {row['email']: row['linked_to'] for row in body['data']}
        self.assertEqual(linked, {'bo@test.local': 'Sam Staff', 'dana@test.local': 'Dana Admin',
                                  'mo@test.local': 'Mo Member'})


class SameAddressTests(HRTestCase):
    """Same company, same address: the same person. Linked without anyone asking."""

    def test_an_employee_login_made_for_someone_with_a_dashboard_login_is_joined_to_it(self):
        eve = self.login(self.company, 'eve@test.local', 'Eve Both', 'company_user')
        record = self.employee_with_login('eve', 'Eve Both', self.company, self.admin)
        record.refresh_from_db()
        self.assertEqual(record.company_user_id, eve.id)
        self.assertEqual(login_user_id_for_company_user(eve), record.user_id)

    def test_a_dashboard_login_made_for_someone_hr_has_a_record_of_is_joined_to_it(self):
        record = self.employee_with_login('fay', 'Fay First', self.company, self.admin)
        self.assertIsNone(record.company_user_id)
        fay = self.login(self.company, 'FAY@test.local', 'Fay First', 'company_user')   # however it is typed
        record.refresh_from_db()
        self.assertEqual(record.company_user_id, fay.id)

    def test_never_across_companies_and_never_over_an_existing_link(self):
        theirs = self.employee_with_login('gus', 'Gus Rival', self.rival, self.rival_admin)
        gus = self.login(self.company, 'gus@test.local', 'Gus Acme', 'company_user')
        theirs.refresh_from_db()
        self.assertIsNone(theirs.company_user_id)
        # The other way round: their dashboard login, our new employee.
        self.login(self.rival, 'liv@test.local', 'Liv Rival', 'company_user')
        ours = self.employee_with_login('liv', 'Liv Acme', self.company, self.admin)
        ours.refresh_from_db()
        self.assertIsNone(ours.company_user_id)
        # A record already linked to one login is not moved to another.
        other = self.login(self.company, 'other@test.local', 'Other Login', 'company_user')
        record = Employee.objects.create(company=self.company, full_name='Gus Acme', work_email='gus@test.local',
                                         employment_status='active', company_user=other)
        self.assertFalse(logins.link_by_email(record))
        self.assertFalse(logins.link_login_by_email(gus))
        record.refresh_from_db()
        self.assertEqual(record.company_user_id, other.id)
        # ...and a login already on one record is not put on a second.
        twin = Employee.objects.create(company=self.company, full_name='Other Login', work_email='other@test.local',
                                       employment_status='active')
        self.assertFalse(logins.link_by_email(twin))

    def test_records_that_matched_before_this_are_linked_once(self):
        a = self.login(self.company, 'ann@test.local', 'Ann', 'company_user')
        b = self.login(self.rival, 'ann@test.local', 'Ann Rival', 'company_user')
        ours = Employee.objects.create(company=self.company, full_name='Ann', work_email='Ann@Test.Local',
                                       employment_status='active')
        other = Employee.objects.create(company=self.company, full_name='Zed', work_email='zed@test.local',
                                        employment_status='active')
        Employee.objects.filter(pk=ours.pk).update(company_user=None)          # as it was before the fix
        # Linked by hand to one login, with the address of another: the hand-made link stays.
        c = self.login(self.company, 'cy@test.local', 'Cy', 'company_user')
        self.login(self.company, 'cy.work@test.local', 'Cy Work', 'company_user')
        by_hand = Employee.objects.create(company=self.company, full_name='Cy', work_email='cy.work@test.local',
                                          employment_status='active')
        Employee.objects.filter(pk=by_hand.pk).update(company_user=c)
        backfill(apps, None)
        backfill(apps, None)
        ours.refresh_from_db(), other.refresh_from_db()
        self.assertEqual((ours.company_user_id, other.company_user_id), (a.id, None))
        self.assertEqual(Employee.objects.get(pk=by_hand.pk).company_user_id, c.id)
        self.assertFalse(Employee.objects.filter(company_user=b).exists())
        self.assertEqual(Employee.objects.get(pk=self.admin_emp.pk).company_user_id, self.admin.id)   # left alone


class OneRecordTests(HRTestCase):
    """core.logins.user_for: a dashboard login whose person already has an
    employee login in the company acts as that login, not as a second record."""

    def test_a_new_dashboard_login_acts_as_the_persons_own_employee_login(self):
        record = self.employee_with_login('hal', 'Hal Both', self.company, self.admin)
        hal = self.login(self.company, 'hal@test.local', 'Hal Both', 'company_user')
        self.assertEqual(core_logins.user_for(hal).id, record.user_id)
        self.assertFalse(User.objects.filter(username=f'company_user_{hal.id}').exists())

    def test_not_another_companys_employee_and_not_one_already_spoken_for(self):
        self.employee_with_login('ivy', 'Ivy Rival', self.rival, self.rival_admin)
        ivy = self.login(self.company, 'ivy@test.local', 'Ivy Acme', 'company_user')
        self.assertEqual(core_logins.user_for(ivy).username, f'company_user_{ivy.id}')

        record = self.employee_with_login('jon', 'Jon', self.company, self.admin)
        first = self.login(self.company, 'jon@test.local', 'Jon', 'company_user')
        self.assertEqual(core_logins.user_for(first).id, record.user_id)
        CompanyUser.objects.filter(pk=first.pk).update(email='jon.old@test.local')
        second = self.login(self.company, 'jon@test.local', 'Jon Again', 'company_user')
        self.assertEqual(core_logins.user_for(second).username, f'company_user_{second.id}')

    def test_someone_who_left_is_not_taken_up(self):
        record = self.employee_with_login('kim', 'Kim', self.company, self.admin)
        User.objects.filter(pk=record.user_id).update(is_active=False)
        kim = self.login(self.company, 'kim@test.local', 'Kim', 'company_user')
        self.assertEqual(core_logins.user_for(kim).username, f'company_user_{kim.id}')
        self.assertTrue(UserProfile.objects.filter(user_id=record.user_id).exists())
