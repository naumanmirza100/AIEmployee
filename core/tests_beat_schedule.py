"""Once-a-day jobs run at a time of day, so a deploy cannot put them off.

Nine jobs were set to run 'every 86400 seconds' and two 'every 7 days', counted
from when the scheduler started. The scheduler keeps the time of each last run
in a file inside its own container, and every merge to main rebuilds that
container. So after each deploy every one of them waited a full day or week
before its next run; with a deploy most days they hardly ran at all. Among them:
adding HR leave to balances, creating recurring tasks, pausing campaigns that
are past their end date, closing old tickets.
"""
from datetime import datetime, timedelta, timezone as dt_timezone

from celery.schedules import crontab
from django.conf import settings
from django.test import SimpleTestCase

SCHEDULE = settings.CELERY_BEAT_SCHEDULE
#: Anything that runs less often than this is "once a day or rarer".
HALF_A_DAY = 12 * 3600

DAILY = ('auto-pause-expired-campaigns', 'hr-accrue-leave-balances', 'generate-recurring-tasks',
         'hr-walk-time-based-events', 'check-stale-meetings', 'frontline-auto-close-inactive-tickets',
         'frontline-prune-expired-documents', 'cleanup-old-notifications', 'exec-meeting-cleanup-notifications')
WEEKLY = ('hr-purge-audit-log', 'frontline-weekly-analytics-digest')


def runs_between(entry, start, hours):
    """How many times a crontab entry comes due in the `hours` after `start`, minute by minute."""
    schedule, due = entry['schedule'], 0
    for minute in range(hours * 60):
        moment = start + timedelta(minutes=minute)
        if (moment.minute in schedule.minute and moment.hour in schedule.hour
                and (moment.isoweekday() % 7) in schedule.day_of_week
                and moment.day in schedule.day_of_month and moment.month in schedule.month_of_year):
            due += 1
    return due


class BeatScheduleTests(SimpleTestCase):

    def test_nothing_that_runs_daily_or_weekly_is_on_an_interval(self):
        for name, entry in SCHEDULE.items():
            schedule = entry['schedule']
            if isinstance(schedule, (int, float)):
                self.assertLess(schedule, HALF_A_DAY,
                                f'{name} waits {schedule:.0f}s from when the scheduler started: give it a time of day')
            else:
                self.assertIsInstance(schedule, crontab, name)

    def test_the_daily_jobs_each_run_once_a_day(self):
        monday = datetime(2026, 10, 5, 0, 0, tzinfo=dt_timezone.utc)
        for name in DAILY:
            self.assertIsInstance(SCHEDULE[name]['schedule'], crontab, name)
            self.assertEqual(runs_between(SCHEDULE[name], monday, 24), 1, name)
            self.assertEqual(runs_between(SCHEDULE[name], monday, 24 * 7), 7, name)

    def test_the_weekly_jobs_each_run_once_a_week(self):
        monday = datetime(2026, 10, 5, 0, 0, tzinfo=dt_timezone.utc)
        for name in WEEKLY:
            self.assertIsInstance(SCHEDULE[name]['schedule'], crontab, name)
            self.assertEqual(runs_between(SCHEDULE[name], monday, 24 * 7), 1, name)

    def test_no_two_of_them_start_in_the_same_minute(self):
        starts = {}
        for name, entry in SCHEDULE.items():
            schedule = entry['schedule']
            if isinstance(schedule, crontab) and len(schedule.hour) == 1 and len(schedule.minute) == 1:
                for day in schedule.day_of_week:
                    starts.setdefault((day, min(schedule.hour), min(schedule.minute)), []).append(name)
        self.assertEqual({when: names for when, names in starts.items() if len(names) > 1}, {})

    def test_a_missed_run_is_dropped_not_queued_behind_the_next_days(self):
        for name in DAILY + WEEKLY:
            self.assertLessEqual(SCHEDULE[name]['options']['expires'], HALF_A_DAY, name)

    def test_every_job_on_the_schedule_is_a_task_that_exists(self):
        from project_manager_ai.celery import app
        app.loader.import_default_modules()
        app.autodiscover_tasks(force=True)
        missing = sorted(f'{name}: {entry["task"]}' for name, entry in SCHEDULE.items()
                         if entry['task'] not in app.tasks)
        self.assertEqual(missing, [])
