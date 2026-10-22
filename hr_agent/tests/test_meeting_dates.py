"""A calendar date in the request wins over the weekday rule.

HR corrects the model's reading of words like "next Friday" with a weekday
rule of its own (HR-BUG-07). That rule fired on "Friday 30 October" too, and
moved a meeting meant for the 30th to the coming Friday, the 23rd.
"""
from datetime import datetime, timezone

from django.test import SimpleTestCase

from api.views.hr_agent import _hr_resolve_relative_date

TUESDAY = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)


class CalendarDateWinsTests(SimpleTestCase):

    def resolve(self, message):
        return _hr_resolve_relative_date(message, TUESDAY)

    def test_a_named_date_is_left_to_the_date(self):
        for message in ('a one-to-one with Fatima on Friday 30 October at 3 pm',
                        'Friday, October 30th at 3pm', 'friday the 30th of oct at 15:00',
                        'Friday 30/10 at 3 pm', 'Friday 30-10-2026, 3 pm', 'Friday 2026-10-30 at 3 pm'):
            with self.subTest(message=message):
                self.assertIsNone(self.resolve(message))

    def test_a_weekday_alone_is_still_corrected(self):
        self.assertEqual(self.resolve('one-to-one with Fatima on Friday at 3 pm').isoformat(), '2026-10-23')
        self.assertEqual(self.resolve('next Friday at 3 pm').isoformat(), '2026-10-30')

    def test_a_time_is_not_taken_for_a_date(self):
        self.assertEqual(self.resolve('Friday at 10.30').isoformat(), '2026-10-23')
        self.assertEqual(self.resolve('Friday 3-4 pm').isoformat(), '2026-10-23')
