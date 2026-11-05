"""Run one AI SDR check that an admin asked for from the dashboard, and write its results to the run's file.

Started by ai_sdr_agent.admin_checks in its own process with the test settings; not meant to be run by hand,
though it can be:

    python manage.py run_sdr_checks logs/sdr_checks/<run id>.json --settings=project_manager_ai.settings_test
"""
import os
import re
import time
import unittest

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.test.runner import DiscoverRunner
from django.utils import timezone

from ai_sdr_agent import admin_checks

WRITE_EVERY = 0.5  # seconds; the page asks every two


def readable(name):
    """test_qualify_queue_retries_stuck -> 'Qualify queue retries stuck'; LifecycleTests -> 'Lifecycle'."""
    if name.startswith('test_'):
        words = name[5:].replace('_', ' ')
    else:
        words = re.sub(r'(?<=[a-z0-9])(?=[A-Z])', ' ', re.sub(r'(TestCase|Tests?)$', '', name)).lower()
    return words[:1].upper() + words[1:]


class Recorder:
    """Keeps the run's results and writes them to its file as the tests go."""

    def __init__(self, path, run):
        self.path, self.run, self.by_id, self.written = path, run, {}, 0.0

    def add(self, test, outcome, message=''):
        test_id = test.id()
        entry = self.by_id.get(test_id)
        if entry is None:
            parts = test_id.split('.')
            method = getattr(test, '_testMethodName', '')
            if isinstance(test, unittest.loader._FailedTest):  # a label that would not load
                group, title = 'Could not load', parts[-1]
            else:
                group, title = readable(parts[-2]) if len(parts) > 1 else '', readable(method) if method else str(test)
            entry = {
                'id': test_id, 'module': '.'.join(parts[:-2]), 'class': group,
                'title': (test.shortDescription() if method else None) or title, 'outcome': outcome,
                'message': message,
                'duration': round(time.monotonic() - getattr(test, '_check_started', time.monotonic()), 3),
                # A test that would not load is not under any label; it belongs to the part that asked for it.
                'suites': admin_checks.suites_of(test_id) or [s for s in [self.run['suite']] if s != 'all'],
            }
            self.by_id[test_id] = entry
            self.run['tests'].append(entry)
            self.run['done'] += 1
        elif outcome in ('failed', 'error'):  # a second failing subtest of the same test
            entry['outcome'] = 'error' if 'error' in (outcome, entry['outcome']) else 'failed'
            entry['message'] = '\n\n'.join(m for m in (entry['message'], message) if m)
        self.run.update({k: sum(t['outcome'] == o for t in self.run['tests'])
                         for k, o in admin_checks.OUTCOMES.items()})
        self.save()

    def save(self, force=False):
        if force or time.monotonic() - self.written >= WRITE_EVERY:
            admin_checks.save(self.path, self.run)
            self.written = time.monotonic()


def result_class(recorder):
    class RecordingResult(unittest.TextTestResult):
        def startTest(self, test):
            test._check_started = time.monotonic()
            super().startTest(test)

        def addSuccess(self, test):
            super().addSuccess(test)
            recorder.add(test, 'passed')

        def addFailure(self, test, err):
            super().addFailure(test, err)
            recorder.add(test, 'failed', self._exc_info_to_string(err, test))

        def addError(self, test, err):
            super().addError(test, err)
            recorder.add(test, 'error', self._exc_info_to_string(err, test))

        def addSkip(self, test, reason):
            super().addSkip(test, reason)
            recorder.add(test, 'skipped', reason)

        def addExpectedFailure(self, test, err):
            super().addExpectedFailure(test, err)
            recorder.add(test, 'passed')

        def addUnexpectedSuccess(self, test):
            super().addUnexpectedSuccess(test)
            recorder.add(test, 'failed', 'Expected to fail, but passed.')

        def addSubTest(self, test, subtest, err):
            super().addSubTest(test, subtest, err)
            if err is not None:
                failed = issubclass(err[0], test.failureException)
                recorder.add(test, 'failed' if failed else 'error',
                             f'{subtest._subDescription()}\n{self._exc_info_to_string(err, test)}')

    return RecordingResult


class CheckRunner(DiscoverRunner):
    def __init__(self, recorder, **kwargs):
        super().__init__(verbosity=0, interactive=False, parallel=1, **kwargs)
        self.recorder = recorder

    def get_resultclass(self):
        return result_class(self.recorder)

    def run_suite(self, suite, **kwargs):
        self.recorder.run['total'] = suite.countTestCases()
        self.recorder.save(force=True)
        return super().run_suite(suite, **kwargs)


class Command(BaseCommand):
    help = 'Run the AI SDR tests of one run asked for from the admin dashboard and record the results.'

    def add_arguments(self, parser):
        parser.add_argument('run_file')

    def handle(self, run_file, **options):
        if not str(settings.DATABASES['default'].get('NAME', '')).startswith((':memory:', 'file:memorydb')):
            raise CommandError('Run this with --settings=project_manager_ai.settings_test only.')
        run = admin_checks.load(run_file)
        run.update(status='running', started_at=timezone.now().isoformat(), pid=os.getpid())
        recorder = Recorder(run_file, run)
        recorder.save(force=True)
        try:
            CheckRunner(recorder).run_tests(run['labels'])
            failed = run['failed'] or run['errors'] or not run['total']
            run['status'] = 'failed' if failed else 'passed'
            if not run['total']:
                run['error'] = 'No tests were found.'
        except BaseException as exc:  # noqa: BLE001 — whatever stopped it, the page must hear of it
            run.update(status='error', error=f'{type(exc).__name__}: {exc}')
            raise
        finally:
            run['finished_at'] = timezone.now().isoformat()
            recorder.save(force=True)
