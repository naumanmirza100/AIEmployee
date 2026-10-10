"""One time zone for the company.

Leave is recorded in days and half days; the shared calendar needs hours, so it
reads a time zone. It read the one on each HR record, and every record started
as UTC. For someone in Karachi left on that default, an afternoon off blocked
6 pm to 5 am their time, and a meeting at 3 pm that afternoon was accepted.
"""
from datetime import datetime, time, timedelta
from importlib import import_module
from zoneinfo import ZoneInfo

from django.utils import timezone

from api.views import company_auth, hr_agent as views
from core.models import CalendarBlock
from core.scheduling import ScheduleConflict, ensure_free
from hr_agent import zones
from hr_agent.models import Employee, HRAuditLog
from hr_agent.workflow_engine import _step_schedule_meeting

from .base import HRTestCase

KARACHI = ZoneInfo('Asia/Karachi')
UTC = ZoneInfo('UTC')


class ZoneTestCase(HRTestCase):

    def setUp(self):
        super().setUp()
        self.ali = self.employee_with_login('ali', 'Ali Staff', self.company, self.admin)
        self.day = timezone.now().date() + timedelta(days=14)
        while self.day.weekday() >= 5:
            self.day += timedelta(days=1)

    def company_zone(self, name):
        self.company.timezone_name = name
        self.company.save()
        self.ali.refresh_from_db()

    def afternoon_off(self, employee=None, **fields):
        return self.leave_request(employee or self.ali, status='approved', start_date=self.day, end_date=self.day,
                                  days_requested=0.5, partial_day_period='afternoon', **fields)

    def block(self, employee=None):
        return CalendarBlock.objects.get(source='leave', user=(employee or self.ali).user)

    def at(self, hour, zone=KARACHI):
        return datetime.combine(self.day, time(hour), tzinfo=zone)


class WhoseClockTests(ZoneTestCase):

    def test_a_new_record_has_no_zone_of_its_own(self):
        fresh = Employee.objects.create(company=self.company, full_name='New Starter', work_email='new@test.local')
        self.assertEqual(fresh.timezone_name, '')
        self.assertEqual(self.ali.timezone_name, '')                # made through the login signal

    def test_it_follows_the_company(self):
        self.company_zone('Asia/Karachi')
        self.assertEqual(self.ali.zone, 'Asia/Karachi')

    def test_its_own_zone_wins(self):
        self.company_zone('Asia/Karachi')
        self.ali.timezone_name = 'Europe/London'
        self.assertEqual(self.ali.zone, 'Europe/London')

    def test_with_neither_it_is_utc_as_before(self):
        self.assertEqual(self.ali.zone, 'UTC')

    def test_a_name_that_is_not_a_zone_is_never_handed_out(self):
        self.company_zone('Asia/Karachi')
        self.ali.timezone_name = 'Karachi time'
        self.assertEqual(self.ali.zone, 'Asia/Karachi')             # falls back to the company's
        self.company_zone('Lahore')
        self.assertEqual(self.ali.zone, 'UTC')

    # ---- what it is for ---------------------------------------------------------------

    def test_an_afternoon_off_blocks_that_afternoon_on_the_companys_clock(self):
        self.company_zone('Asia/Karachi')
        self.afternoon_off()
        self.assertEqual((self.block().starts_at, self.block().ends_at),
                         (self.at(13), self.at(0) + timedelta(days=1)))
        with self.assertRaises(ScheduleConflict):                   # 3 pm that afternoon: they are away
            ensure_free([self.ali.user_id], self.at(15), 30)
        ensure_free([self.ali.user_id], self.at(10), 30)            # the morning is theirs to book

    def test_without_a_company_zone_it_is_read_in_utc_as_it_always_was(self):
        self.afternoon_off()
        self.assertEqual(self.block().starts_at, self.at(13, UTC))

    def test_a_workflow_books_its_meeting_on_that_clock_too(self):
        self.company_zone('Asia/Karachi')
        ok, result, _ = _step_schedule_meeting({'offset_days_from_now': 3},
                                               {'company_id': self.company.id, 'employee_id': self.ali.id}, True)
        self.assertTrue(ok, result)
        self.assertTrue(result['scheduled_at'].endswith('+05:00'), result)


class OldDefaultTests(ZoneTestCase):
    """Records made before a zone could be blank still say 'UTC'."""

    def setUp(self):
        super().setUp()
        self.company_zone('Asia/Karachi')
        Employee.objects.filter(pk=self.ali.pk).update(timezone_name='UTC')      # as every record used to start
        self.ali.refresh_from_db()
        self.london = self.employee_with_login('lou', 'Lou London', self.company, self.admin)
        Employee.objects.filter(pk=self.london.pk).update(timezone_name='Europe/London')

    def test_they_are_left_on_utc_until_someone_asks(self):
        self.afternoon_off()
        self.assertEqual(self.ali.zone, 'UTC')
        self.assertEqual(self.block().starts_at, self.at(13, UTC))

    def test_the_leave_screen_is_told_how_many_there_are(self):
        code, body = self.call(views.hr_time_zones, self.member, method='get')
        self.assertEqual(code, 200, body)
        self.assertEqual(body['data'], {'company_zone': 'Asia/Karachi', 'on_old_default': 1,
                                        'following': Employee.objects.filter(company=self.company).count() - 2,
                                        'old_default': 'UTC'})

    def test_an_hr_admin_moves_them_onto_the_company_zone_and_their_leave_with_them(self):
        self.afternoon_off()
        code, body = self.call(views.hr_time_zones, self.admin, {'action': 'follow_company'})
        self.assertEqual((code, body['data']['moved'], body['data']['on_old_default']), (200, 1, 0), body)
        self.ali.refresh_from_db()
        self.assertEqual((self.ali.timezone_name, self.ali.zone), ('', 'Asia/Karachi'))
        self.assertEqual(self.block().starts_at, self.at(13))        # moved at once, not at the nightly rebuild

    def test_someone_with_a_zone_of_their_own_is_left_alone(self):
        self.call(views.hr_time_zones, self.admin, {'action': 'follow_company'})
        self.london.refresh_from_db()
        self.assertEqual(self.london.timezone_name, 'Europe/London')

    def test_another_companys_records_are_left_alone(self):
        Employee.objects.filter(pk=self.rival_emp.pk).update(timezone_name='UTC')
        self.call(views.hr_time_zones, self.admin, {'action': 'follow_company'})
        self.rival_emp.refresh_from_db()
        self.assertEqual(self.rival_emp.timezone_name, 'UTC')

    def test_it_is_written_to_the_audit_log(self):
        self.call(views.hr_time_zones, self.admin, {'action': 'follow_company'})
        entry = HRAuditLog.objects.get(action='employee.follow_company_zone')
        self.assertEqual((entry.actor, entry.diff['after']['records'], entry.diff['after']['company_zone']),
                         (self.admin, 1, 'Asia/Karachi'))

    def test_only_an_hr_admin_may(self):
        code, _ = self.call(views.hr_time_zones, self.member, {'action': 'follow_company'})
        self.assertEqual(code, 403)
        self.ali.refresh_from_db()
        self.assertEqual(self.ali.timezone_name, 'UTC')

    def test_not_before_the_company_has_a_zone(self):
        self.company_zone('')
        code, body = self.call(views.hr_time_zones, self.admin, {'action': 'follow_company'})
        self.assertEqual(code, 400, body)
        self.assertIn('company time zone first', body['message'])
        self.assertEqual(Employee.objects.get(pk=self.ali.pk).timezone_name, 'UTC')

    def test_and_nothing_else_can_be_asked_of_it(self):
        self.assertEqual(self.call(views.hr_time_zones, self.admin, {'action': 'reset'})[0], 400)


class CompanyZoneTests(ZoneTestCase):
    """Set in the company profile, by an owner or admin."""

    def save(self, actor, **data):
        return self.call(company_auth.update_company_profile, actor, data, method='put')

    def test_an_admin_sets_it_and_the_profile_shows_it(self):
        code, body = self.save(self.admin, timezoneName='Asia/Karachi')
        self.assertEqual((code, body['data']['company']['timezoneName']), (200, 'Asia/Karachi'), body)
        self.company.refresh_from_db()
        self.assertEqual(self.company.timezone_name, 'Asia/Karachi')
        code, body = self.call(company_auth.get_company_profile, self.member, method='get')
        self.assertEqual(body['data']['company']['timezoneName'], 'Asia/Karachi')

    def test_leave_already_approved_moves_at_once_for_everyone_who_follows_it(self):
        own = self.employee_with_login('lou', 'Lou London', self.company, self.admin)
        Employee.objects.filter(pk=own.pk).update(timezone_name='Europe/London')
        own.refresh_from_db()
        self.afternoon_off(), self.afternoon_off(own)
        was = self.block(own).starts_at
        self.save(self.admin, timezoneName='Asia/Karachi')
        self.assertEqual(self.block().starts_at, self.at(13))
        self.assertEqual(self.block(own).starts_at, was)             # their own zone: nothing to move

    def test_leave_that_is_over_is_left_where_it_was(self):
        past = self.leave_request(self.ali, status='approved', start_date=self.day - timedelta(days=60),
                                  end_date=self.day - timedelta(days=60), days_requested=1)
        row = CalendarBlock.objects.get(source='leave', source_id=past.id)
        self.save(self.admin, timezoneName='Asia/Karachi')
        self.assertEqual(CalendarBlock.objects.get(pk=row.pk).starts_at, row.starts_at)

    def test_a_login_that_is_not_an_admin_cannot_change_it(self):
        code, body = self.save(self.member, timezoneName='Asia/Karachi')
        self.assertEqual(code, 403, body)
        self.company.refresh_from_db()
        self.assertEqual(self.company.timezone_name, '')

    def test_but_can_save_the_rest_of_the_profile_with_the_zone_unchanged(self):
        self.company_zone('Asia/Karachi')
        code, body = self.save(self.member, timezoneName='Asia/Karachi', phone='042 111')
        self.assertEqual(code, 200, body)
        self.company.refresh_from_db()
        self.assertEqual((self.company.phone, self.company.timezone_name), ('042 111', 'Asia/Karachi'))

    def test_a_name_that_is_not_a_zone_is_refused_and_nothing_is_saved(self):
        code, body = self.save(self.admin, timezoneName='Karachi', phone='042 111')
        self.assertEqual(code, 400, body)
        self.assertIn('not a time zone', body['message'])
        self.company.refresh_from_db()
        self.assertEqual((self.company.timezone_name, self.company.phone), ('', None))

    def test_an_admin_can_clear_it(self):
        self.company_zone('Asia/Karachi')
        self.assertEqual(self.save(self.admin, timezoneName='')[0], 200)
        self.company.refresh_from_db()
        self.assertEqual(self.company.timezone_name, '')

    def test_another_companys_admin_changes_only_their_own(self):
        self.save(self.rival_admin, timezoneName='Europe/Paris')
        self.company.refresh_from_db()
        self.rival.refresh_from_db()
        self.assertEqual((self.company.timezone_name, self.rival.timezone_name), ('', 'Europe/Paris'))


class RecordZoneTests(ZoneTestCase):
    """The zone on one person's HR record: a list now, not a free-text box."""

    def edit(self, **data):
        return self.call(views.update_employee, self.admin, data, employee_id=self.ali.id)

    def test_a_name_that_is_not_a_zone_is_refused(self):
        code, body = self.edit(timezone_name='Karachi time', job_title='Engineer')
        self.assertEqual(code, 400, body)
        self.assertIn('not a time zone', body['message'])
        self.ali.refresh_from_db()
        self.assertEqual((self.ali.timezone_name, self.ali.job_title), ('', ''))   # it used to be saved, and read as UTC

    def test_a_real_zone_is_saved_and_their_leave_moves_at_once(self):
        self.afternoon_off()
        self.assertEqual(self.block().starts_at, self.at(13, UTC))
        code, body = self.edit(timezone_name='Asia/Karachi')
        self.assertEqual((code, body['data']['timezone_name']), (200, 'Asia/Karachi'), body)
        self.assertEqual(self.block().starts_at, self.at(13))

    def test_empty_means_follow_the_company(self):
        self.company_zone('Asia/Karachi')
        Employee.objects.filter(pk=self.ali.pk).update(timezone_name='Europe/London')
        self.afternoon_off()
        code, body = self.edit(timezone_name='')
        self.assertEqual((code, body['data']['timezone_name']), (200, ''), body)
        self.assertEqual(self.block().starts_at, self.at(13))

    def test_saving_the_same_zone_again_moves_nothing(self):
        self.afternoon_off()
        row = self.block()
        self.edit(timezone_name='', job_title='Engineer')
        self.assertEqual(self.block().pk, row.pk)                    # the calendar row was not rewritten


class MigrationTests(ZoneTestCase):

    def test_the_two_migrations_are_the_ones_the_models_describe(self):
        core = import_module('core.migrations.0112_company_timezone_name').Migration
        hr = import_module('hr_agent.migrations.0021_employee_zone_follows_company').Migration
        [added], [altered] = core.operations, hr.operations
        self.assertEqual((added.model_name, added.name, added.field.default, added.field.blank),
                         ('company', 'timezone_name', '', True))
        self.assertEqual((altered.model_name, altered.name, altered.field.default, altered.field.blank),
                         ('employee', 'timezone_name', '', True))
        self.assertIn(('core', '0112_company_timezone_name'), hr.dependencies)
