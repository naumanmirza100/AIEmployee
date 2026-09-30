"""Approved leave and company holidays are busy time in every agent.

Leave lived only in HR: the meeting schedulers could book someone on holiday,
and suggested free times on company holidays. Now approved leave is busy time
on the shared calendar, and a company-wide holiday is a day off for everyone.
"""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone

from core.models import CalendarBlock
from core.scheduling import ScheduleConflict, busy_intervals, ensure_free, find_conflicts, free_slots
from hr_agent.models import Holiday, LeaveRequest

from .base import HRTestCase

KARACHI = ZoneInfo('Asia/Karachi')


class LeaveOnTheCalendarTests(HRTestCase):

    def setUp(self):
        super().setUp()
        self.ali = self.employee_with_login('ali', 'Ali Staff', self.company, self.admin)
        self.ali.timezone_name = 'Asia/Karachi'
        self.ali.save()
        self.day = timezone.now().astimezone(KARACHI).date() + timedelta(days=14)
        while self.day.weekday() >= 5:
            self.day += timedelta(days=1)

    def at(self, day, hour):
        return datetime.combine(day, time(hour), tzinfo=KARACHI)

    def leave(self, days=1, status='approved', part=''):
        return LeaveRequest.objects.create(
            employee=self.ali, leave_type='vacation', start_date=self.day,
            end_date=self.day + timedelta(days=days - 1), days_requested=0.5 if part else days,
            status=status, partial_day_period=part)

    def blocks(self):
        return CalendarBlock.objects.filter(source='leave', user=self.ali.user)

    # ---- leave -----------------------------------------------------------------

    def test_approved_leave_is_busy_time_for_whole_days_on_their_clock(self):
        self.leave(days=3)
        [block] = self.blocks()
        self.assertEqual(block.starts_at, self.at(self.day, 0))
        self.assertEqual(block.ends_at, self.at(self.day + timedelta(days=3), 0))
        self.assertTrue(block.is_private)
        self.assertEqual(block.title, 'On leave')

    def test_pending_leave_is_not(self):
        self.leave(status='pending')
        self.assertFalse(self.blocks().exists())

    def test_approving_adds_it_and_withdrawing_removes_it(self):
        request = self.leave(status='pending')
        request.status = 'approved'
        request.save(update_fields=['status', 'updated_at'])
        self.assertTrue(self.blocks().exists())
        request.status = 'withdrawn'
        request.save(update_fields=['status', 'updated_at'])
        self.assertFalse(self.blocks().exists())

    def test_a_morning_off_blocks_the_morning_only(self):
        self.leave(part='morning')
        [block] = self.blocks()
        self.assertEqual((block.starts_at, block.ends_at), (self.at(self.day, 0), self.at(self.day, 13)))

    def test_leave_by_the_hour_blocks_nothing_since_it_doesnt_say_which_hours(self):
        self.leave(part='hours')
        self.assertFalse(self.blocks().exists())

    def test_a_meeting_during_leave_is_refused_and_says_so(self):
        self.leave(days=2)
        with self.assertRaises(ScheduleConflict) as caught:
            ensure_free([self.ali.user_id], self.at(self.day, 11), 30, tz_name='Asia/Karachi',
                        viewer_source='pm', suggest=False)
        self.assertIn('ali is on leave', caught.exception.text().lower())
        self.assertNotIn('vacation', caught.exception.text())        # the type stays private

    def test_no_free_time_is_suggested_while_on_leave(self):
        self.leave()
        self.assertEqual(free_slots([self.ali.user_id], self.day, 30, 'Asia/Karachi'), [])
        self.assertTrue(free_slots([self.ali.user_id], self.day + timedelta(days=1), 30, 'Asia/Karachi')
                        or (self.day + timedelta(days=1)).weekday() >= 5)

    # ---- company holidays --------------------------------------------------

    def holiday(self, **extra):
        return Holiday.objects.create(company=self.company, name='Founders Day', date=self.day, **extra)

    def test_a_company_holiday_refuses_bookings_for_everyone(self):
        self.holiday()
        with self.assertRaises(ScheduleConflict) as caught:
            ensure_free([self.ali.user_id], self.at(self.day, 11), 30, tz_name='Asia/Karachi',
                        suggest=False)
        self.assertIn('is a company holiday (Founders Day)', caught.exception.text())

    def test_and_offers_no_free_time_that_day(self):
        self.holiday()
        self.assertEqual(free_slots([self.ali.user_id], self.day, 30, 'Asia/Karachi'), [])

    def test_the_day_is_read_in_the_bookings_zone(self):
        self.holiday()
        # 23:00 the evening before, in Karachi — still a working day there.
        before = self.at(self.day - timedelta(days=1), 23)
        ensure_free([self.ali.user_id], before, 30, tz_name='Asia/Karachi', suggest=False)
        self.assertTrue(busy_intervals([self.ali.user_id], self.at(self.day, 10), self.at(self.day, 11),
                                       tz_name='Asia/Karachi'))

    def test_regional_holidays_and_working_bridge_days_dont_count(self):
        self.holiday(region='US-CA')
        Holiday.objects.create(company=self.company, name='Bridge', date=self.day, is_working_day=True)
        ensure_free([self.ali.user_id], self.at(self.day, 11), 30, tz_name='Asia/Karachi', suggest=False)

    def test_another_companys_holiday_doesnt_count(self):
        Holiday.objects.create(company=self.rival, name='Their day', date=self.day)
        ensure_free([self.ali.user_id], self.at(self.day, 11), 30, tz_name='Asia/Karachi', suggest=False)

    def test_without_a_zone_holidays_are_not_guessed(self):
        # find_conflicts with no zone can't know which day it is; callers that
        # book always pass one (ensure_free does).
        self.holiday()
        self.assertEqual(find_conflicts([self.ali.user_id], self.at(self.day, 11), self.at(self.day, 12)), [])
