"""Company holidays can be entered, by HR admins.

A holiday stops bookings in every agent and is left out when leave days are
counted, but there was no screen to enter one, and the create and delete
addresses had no role check: any dashboard login could add or remove one.
"""
from datetime import datetime, time, timedelta, timezone as dt_timezone

from django.utils import timezone

from api.views import hr_agent as views
from core.models import CalendarBlock
from hr_agent.models import Holiday

from .base import HRTestCase


class HolidayTests(HRTestCase):

    def setUp(self):
        super().setUp()
        self.day = timezone.localdate() + timedelta(days=20)

    def add(self, actor=None, **data):
        data.setdefault('name', 'Founders day')
        data.setdefault('date', self.day.isoformat())
        return self.call(views.create_holiday, actor or self.admin, data)

    def booking(self, source, source_id, title, user=None, day=None, hour=10):
        starts = datetime.combine(day or self.day, time(hour, 0), tzinfo=dt_timezone.utc)
        return CalendarBlock.objects.create(
            company=self.company, user=user or self.member_emp.user, starts_at=starts,
            ends_at=starts + timedelta(hours=1), source=source, source_id=source_id, role='participant',
            response='accepted', title=title)

    # ---- who may ---------------------------------------------------------------

    def test_an_hr_admin_adds_and_removes_a_holiday(self):
        code, body = self.add()
        self.assertEqual(code, 201, body)
        holiday = Holiday.objects.get(company=self.company)
        self.assertEqual((holiday.name, holiday.date, holiday.region, holiday.is_working_day),
                         ('Founders day', self.day, '', False))
        code, _ = self.call(views.delete_holiday, self.admin, method='delete', holiday_id=holiday.id)
        self.assertEqual((code, Holiday.objects.count()), (200, 0))

    def test_a_login_that_is_not_an_hr_admin_cannot(self):
        code, body = self.add(self.member)
        self.assertEqual((code, Holiday.objects.count()), (403, 0), body)
        holiday = Holiday.objects.create(company=self.company, name='Founders day', date=self.day)
        code, _ = self.call(views.delete_holiday, self.member, method='delete', holiday_id=holiday.id)
        self.assertEqual((code, Holiday.objects.count()), (403, 1))

    def test_everyone_can_see_them_and_is_told_whether_they_can_change_them(self):
        Holiday.objects.create(company=self.company, name='Founders day', date=self.day)
        Holiday.objects.create(company=self.rival, name='Theirs', date=self.day)
        code, body = self.call(views.list_holidays, self.member, method='get')
        self.assertEqual((code, [h['name'] for h in body['data']], body['can_manage']), (200, ['Founders day'], False))
        self.assertTrue(self.call(views.list_holidays, self.admin, method='get')[1]['can_manage'])

    def test_another_companys_holiday_cannot_be_removed(self):
        theirs = Holiday.objects.create(company=self.rival, name='Theirs', date=self.day)
        code, _ = self.call(views.delete_holiday, self.admin, method='delete', holiday_id=theirs.id)
        self.assertEqual((code, Holiday.objects.count()), (404, 1))

    # ---- what is already booked that day -----------------------------------------

    def test_adding_one_says_what_is_already_booked_that_day(self):
        self.booking('pm', 1, 'Roadmap review')
        self.booking('pm', 1, 'Roadmap review', user=self.admin_emp.user)       # the same meeting, another person
        self.booking('recruitment', 7, 'Interview: Cara', hour=14)
        self.booking('leave', 3, 'Approved leave')                              # not a booking
        self.booking('pm', 2, 'Another day', day=self.day + timedelta(days=1))
        code, body = self.add()
        self.assertEqual(code, 201, body)
        self.assertEqual([b['title'] for b in body['already_booked']], ['Roadmap review', 'Interview: Cara'])

    def test_a_clear_day_says_nothing_is_booked(self):
        self.assertEqual(self.add()[1]['already_booked'], [])

    def test_another_companys_bookings_are_not_shown(self):
        other = self.booking('pm', 5, 'Their meeting')
        CalendarBlock.objects.filter(pk=other.pk).update(company=self.rival)
        self.assertEqual(self.add()[1]['already_booked'], [])

    def test_a_regional_holiday_does_not_block_the_calendar_so_lists_nothing(self):
        self.booking('pm', 1, 'Roadmap review')
        self.assertEqual(self.add(region='Scotland')[1]['already_booked'], [])


class AuditLogCallTests(HRTestCase):
    """Seven HR actions saved their change, then crashed writing the audit log."""

    def test_adding_a_holiday_is_logged_and_does_not_fail(self):
        from hr_agent.models import HRAuditLog
        code, _ = self.call(views.create_holiday, self.admin,
                            {'name': 'Founders day', 'date': (timezone.localdate() + timedelta(days=9)).isoformat()})
        self.assertEqual(code, 201)
        entry = HRAuditLog.objects.get(action='holiday.create')
        self.assertEqual(entry.diff['after']['name'], 'Founders day')

    def test_before_and_after_can_be_given_by_position(self):
        from hr_agent.models import HRAuditLog
        views._write_audit_log(self.admin, self.company, 'thing.update', 'Thing', 1, {'a': 1}, {'a': 2})
        self.assertEqual(HRAuditLog.objects.get(action='thing.update').diff, {'before': {'a': 1}, 'after': {'a': 2}})

    def test_no_caller_passes_more_than_the_helper_takes(self):
        import ast
        import inspect
        tree = ast.parse(inspect.getsource(views))
        too_many = [node.lineno for node in ast.walk(tree)
                    if isinstance(node, ast.Call) and getattr(node.func, 'id', '') == '_write_audit_log'
                    and len(node.args) > 7]
        self.assertEqual(too_many, [])
