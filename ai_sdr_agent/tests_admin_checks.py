"""The AI SDR checks: a platform admin, or a company's owner or admin, presses Run on a part of the AI SDR (qualification, replies …) and
sees which of its tests pass. The tests run in a separate process; here that process is not started, its
recording is tried on a small suite instead.
"""
import importlib
import io
import inspect
import shutil
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from ai_sdr_agent import admin_checks
from ai_sdr_agent.management.commands import run_sdr_checks
from ai_sdr_agent.tests import SDRBase
from api.views import sdr_checks as views
from core.models import Company, CompanyUser


class CatalogTests(SimpleTestCase):
    def test_every_label_names_tests_that_load(self):
        loader = unittest.TestLoader()
        for suite in admin_checks.SUITES:
            for label in suite['labels']:
                with self.subTest(suite=suite['key'], label=label):
                    loaded = loader.loadTestsFromName(label)
                    self.assertGreater(loaded.countTestCases(), 0)
                    self.assertNotIn('_FailedTest', repr(loaded))

    def test_every_test_class_is_in_a_part_so_none_is_left_off_the_page(self):
        loader = unittest.TestLoader()
        labels = [label for suite in admin_checks.SUITES for label in suite['labels']]
        for path in sorted(Path(admin_checks.__file__).parent.glob('tests*.py')):
            module = importlib.import_module(f'ai_sdr_agent.{path.stem}')
            for name, cls in inspect.getmembers(module, inspect.isclass):
                if cls.__module__ != module.__name__ or not issubclass(cls, unittest.TestCase):
                    continue
                if path.stem == 'tests_admin_checks' or not loader.getTestCaseNames(cls):
                    continue
                with self.subTest(test_class=f'{module.__name__}.{name}'):
                    self.assertTrue(any(admin_checks.in_label(f'{module.__name__}.{name}', label)
                                        for label in labels))

    def test_a_test_belongs_to_the_parts_whose_labels_hold_it(self):
        test_id = 'ai_sdr_agent.tests.LifecycleTests.test_qualify_queue_without_icp_fails_once_with_reason'
        self.assertEqual(admin_checks.suites_of(test_id), ['qualification', 'outreach'])
        self.assertEqual(admin_checks.suites_of('ai_sdr_agent.tests_crm_sync.MeetingTests.test_x'), ['crm'])
        self.assertEqual(admin_checks.suites_of('ai_sdr_agent.tests_admin_checks.CatalogTests.test_x'), [])

    def test_names_read_as_words(self):
        self.assertEqual(run_sdr_checks.readable('test_hot_and_warm_are_qualified'), 'Hot and warm are qualified')
        self.assertEqual(run_sdr_checks.readable('StatusFollowsTheScoreTests'), 'Status follows the score')
        self.assertEqual(run_sdr_checks.readable('LeadResearchTestCase'), 'Lead research')


class ChecksDirMixin:
    def setUp(self):
        super().setUp()
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        overridden = override_settings(SDR_CHECKS_DIR=self.dir)
        overridden.enable()
        self.addCleanup(overridden.disable)


class RecordingTests(ChecksDirMixin, SimpleTestCase):
    """What the test process writes, tried on a small suite run here."""

    def run_sample(self):
        class Sample(unittest.TestCase):
            def test_passes(self):
                """Hot leads are qualified."""

            def test_fails(self):
                self.assertEqual(1, 2)

            def test_breaks(self):
                raise RuntimeError('boom')

            @unittest.skip('not today')
            def test_skipped(self):
                pass

            def test_subtests(self):
                for i in range(3):
                    with self.subTest(i=i):
                        self.assertLess(i, 1)

        with mock.patch.object(admin_checks, '_spawn'):
            run = admin_checks.start_run('qualification', 'admin')
        path = admin_checks.run_path(run['id'])
        recorder = run_sdr_checks.Recorder(path, run)
        suite = unittest.TestLoader().loadTestsFromTestCase(Sample)
        unittest.TextTestRunner(stream=io.StringIO(),
                                resultclass=run_sdr_checks.result_class(recorder)).run(suite)
        recorder.save(force=True)
        return admin_checks.load(path)

    def test_each_outcome_is_recorded_with_its_reason(self):
        run = self.run_sample()
        by_name = {t['id'].rsplit('.', 1)[1]: t for t in run['tests']}
        self.assertEqual({k: t['outcome'] for k, t in by_name.items()}, {
            'test_passes': 'passed', 'test_fails': 'failed', 'test_breaks': 'error', 'test_skipped': 'skipped',
            'test_subtests': 'failed'})
        self.assertEqual(by_name['test_passes']['title'], 'Hot leads are qualified.')
        self.assertEqual(by_name['test_breaks']['title'], 'Breaks')
        self.assertIn('RuntimeError: boom', by_name['test_breaks']['message'])
        self.assertIn('not today', by_name['test_skipped']['message'])

    def test_two_failing_subtests_are_one_test_with_both_reasons(self):
        run = self.run_sample()
        subtests = [t for t in run['tests'] if t['id'].endswith('test_subtests')]
        self.assertEqual(len(subtests), 1)
        self.assertIn('(i=1)', subtests[0]['message'])
        self.assertIn('(i=2)', subtests[0]['message'])
        self.assertEqual((run['done'], run['passed'], run['failed'], run['errors'], run['skipped']), (5, 1, 2, 1, 1))


class ApiTests(ChecksDirMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_user('platform-admin', password='x', is_staff=True)
        self.rf = APIRequestFactory()
        spawn = mock.patch.object(admin_checks, '_spawn')
        self.spawn = spawn.start()
        self.addCleanup(spawn.stop)

    def call(self, view, method='get', user=None, data=None, **kwargs):
        request = getattr(self.rf, method)('/', data or {}, format='json')
        force_authenticate(request, user=user or self.admin)
        return view(request, **kwargs)

    def finished_run(self, suite, tests, status='failed', ago=timedelta(0)):
        run = admin_checks.start_run(suite, 'platform-admin')
        run.update(status=status, tests=tests, total=len(tests), done=len(tests),
                   created_at=(timezone.now() - ago).isoformat(), finished_at=timezone.now().isoformat(),
                   **{k: sum(t['outcome'] == o for t in tests) for k, o in admin_checks.OUTCOMES.items()})
        admin_checks.save(admin_checks.run_path(run['id']), run)
        return run

    def test_only_platform_staff_may_look_or_run(self):
        someone = User.objects.create_user('not-staff', password='x')
        self.assertEqual(self.call(views.admin_overview, user=someone).status_code, 403)
        self.assertEqual(self.call(views.admin_start, 'post', user=someone, data={'suite': 'all'}).status_code, 403)
        self.spawn.assert_not_called()

    def test_running_a_part_starts_one_process_and_a_second_run_waits(self):
        response = self.call(views.admin_start, 'post', data={'suite': 'qualification'})
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data['data']['status'], 'queued')
        self.spawn.assert_called_once()
        run = admin_checks.load(self.spawn.call_args.args[0])
        self.assertEqual(run['labels'], admin_checks.SUITES_BY_KEY['qualification']['labels'])

        response = self.call(views.admin_start, 'post', data={'suite': 'crm'})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.spawn.call_count, 1)
        self.assertEqual(self.call(views.admin_overview).data['data']['current']['suite'], 'qualification')

    def test_an_unknown_part_is_refused(self):
        self.assertEqual(self.call(views.admin_start, 'post', data={'suite': '../etc'}).status_code, 400)
        self.spawn.assert_not_called()

    def test_a_run_that_never_finished_is_reported_as_stopped_and_frees_the_runner(self):
        run = admin_checks.start_run('crm', 'platform-admin')
        run['created_at'] = (timezone.now() - timedelta(minutes=20)).isoformat()
        admin_checks.save(admin_checks.run_path(run['id']), run)
        Path(admin_checks.run_path(run['id'])).with_suffix('.log').write_text('Traceback …\nImportError: x')

        detail = self.call(views.admin_run_detail, run_id=run['id']).data['data']
        self.assertEqual(detail['status'], 'error')
        self.assertIn('ImportError: x', detail['log_tail'])
        self.assertEqual(self.call(views.admin_start, 'post', data={'suite': 'crm'}).status_code, 202)

    def test_a_run_of_everything_gives_each_part_its_own_result(self):
        self.finished_run('all', [
            {'id': 'a.Q.test_1', 'outcome': 'passed', 'suites': ['qualification']},
            {'id': 'a.Q.test_2', 'outcome': 'passed', 'suites': ['qualification', 'outreach']},
            {'id': 'a.C.test_3', 'outcome': 'failed', 'suites': ['crm']},
        ])
        data = self.call(views.admin_overview).data['data']
        last = {s['key']: s['last'] for s in data['suites']}
        self.assertEqual((last['qualification']['status'], last['qualification']['passed']), ('passed', 2))
        self.assertEqual((last['crm']['status'], last['crm']['failed']), ('failed', 1))
        self.assertEqual(last['research']['status'], 'error')  # none of its tests ran
        self.assertEqual(data['all_last']['status'], 'failed')

    def test_a_parts_own_newer_run_replaces_what_the_run_of_everything_said(self):
        self.finished_run('all', [{'id': 'a.C.test_3', 'outcome': 'failed', 'suites': ['crm']}], ago=timedelta(1))
        newer = self.finished_run('crm', [{'id': 'a.C.test_3', 'outcome': 'passed', 'suites': ['crm']}],
                                  status='passed')
        last = {s['key']: s['last'] for s in self.call(views.admin_overview).data['data']['suites']}
        self.assertEqual((last['crm']['id'], last['crm']['status']), (newer['id'], 'passed'))

    def test_detail_lists_the_tests_and_can_keep_one_part(self):
        run = self.finished_run('all', [
            {'id': 'a.Q.test_1', 'outcome': 'passed', 'suites': ['qualification']},
            {'id': 'a.C.test_3', 'outcome': 'failed', 'suites': ['crm']},
        ])
        self.assertEqual(len(self.call(views.admin_run_detail, run_id=run['id']).data['data']['tests']), 2)
        request = self.rf.get('/', {'suite': 'crm'})
        force_authenticate(request, user=self.admin)
        only_crm = views.admin_run_detail(request, run_id=run['id']).data['data']
        self.assertEqual([t['id'] for t in only_crm['tests']], ['a.C.test_3'])
        self.assertEqual(only_crm['status'], 'failed')

    def test_a_run_id_cannot_name_another_file(self):
        self.assertEqual(self.call(views.admin_run_detail, run_id='../../db').status_code, 404)
        self.assertEqual(self.call(views.admin_run_detail, run_id='20261105-000000-abcdef').status_code, 404)


class CompanyApiTests(ChecksDirMixin, SDRBase):
    """AI SDR → Tests, for a company's owner or admin."""

    def setUp(self):
        super().setUp()
        self.rf = APIRequestFactory()
        spawn = mock.patch.object(admin_checks, '_spawn')
        self.spawn = spawn.start()
        self.addCleanup(spawn.stop)

    def call(self, view, user, method='get', data=None, **kwargs):
        request = getattr(self.rf, method)('/', data or {}, format='json')
        force_authenticate(request, user=user)
        return view(request, **kwargs)

    def login(self, company, role, email):
        return CompanyUser.objects.create(company=company, email=email, full_name=email.split('@')[0],
                                          role=role, password_hash='x', is_active=True)

    def test_an_owner_or_admin_runs_the_tests_and_is_named_on_the_run(self):
        response = self.call(views.company_start, self.cu, 'post', {'suite': 'qualification'})
        self.assertEqual(response.status_code, 202)
        self.spawn.assert_called_once()
        run = admin_checks.load(self.spawn.call_args.args[0])
        self.assertEqual((run['company_id'], run['started_by']), (self.company.id, 'CU'))
        self.assertEqual(self.call(views.company_overview, self.cu).data['data']['current']['started_by'], 'CU')

    def test_a_salesperson_may_not_look_or_run(self):
        seller = self.login(self.company, 'company_user', 'seller@test.local')
        self.assertEqual(self.call(views.company_overview, seller).status_code, 403)
        self.assertEqual(self.call(views.company_start, seller, 'post', {'suite': 'all'}).status_code, 403)
        self.spawn.assert_not_called()

    def test_another_company_sees_the_run_but_not_who_started_it(self):
        run = self.call(views.company_start, self.cu, 'post', {'suite': 'crm'}).data['data']
        other = self.login(Company.objects.create(name='Other', email='o@test.local'), 'owner', 'boss@other.local')

        self.assertIsNone(self.call(views.company_overview, other).data['data']['current']['started_by'])
        self.assertIsNone(self.call(views.company_run_detail, other, run_id=run['id']).data['data']['started_by'])
        busy = self.call(views.company_start, other, 'post', {'suite': 'all'})
        self.assertEqual(busy.status_code, 409)
        self.assertIsNone(busy.data['data']['started_by'])
        # A platform admin sees who it was.
        admin = User.objects.create_user('platform-admin', password='x', is_staff=True)
        request = self.rf.get('/')
        force_authenticate(request, user=admin)
        self.assertEqual(views.admin_overview(request).data['data']['current']['started_by'], 'CU')
