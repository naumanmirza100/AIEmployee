"""The admin's Test data page (27 Nov 2026): snapshots of a demo company, adding and removing it, and the sweep that
clears every customer's data. See core/demo_data.py."""
from datetime import timedelta

from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from api.views import admin_test_data as views
from core import demo_data
from core.crypto_utils import decrypt_secret
from core.models import (
    Agent, BlogPost, Company, CompanyAPIKey, CompanyModulePurchase, CompanyUser, ContactMessage, DemoDataRun,
    DemoSnapshot, FAQ, Project, Task, UserProfile, UserToken,
)
from crm_sync_agent.models import CRMIntegration


class DemoDataBase(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user('boss', 'boss@test.local', 'x', is_staff=True, is_superuser=True)
        UserProfile.objects.get_or_create(user=self.admin)
        UserToken.objects.create(user=self.admin, key='k' * 40)
        Agent.objects.get_or_create(slug='project_manager_agent', defaults={'name': 'Project Manager Agent'})

        # The demo company: a dashboard login, an employee, a project with a task, a key and a CRM link.
        self.demo = Company.objects.create(name='Margalla Software', email='hello@margalla.test')
        self.owner = CompanyUser.objects.create(company=self.demo, email='owner@margalla.test', full_name='Sana Malik',
                                                role='owner', password_hash=make_password('old-secret'))
        self.employee = User.objects.create_user('ali', 'ali@margalla.test', 'old-secret', first_name='Ali')
        UserProfile.objects.update_or_create(user=self.employee, defaults={'company': self.demo})
        self.project = Project.objects.create(name='Website', owner=self.employee, company=self.demo)
        self.task = Task.objects.create(title='Design the home page', project=self.project, assignee=self.employee)
        CompanyAPIKey.objects.create(company=self.demo, provider='openai', mode='own', encrypted_key='secret-key-value')
        CRMIntegration.objects.create(company=self.demo, provider='hubspot', credentials={'enc': 'secret-token'},
                                      is_active=True)
        CompanyModulePurchase.objects.create(company=self.demo, module_name='project_manager_agent', status='active')

        # Another company, which must never be touched by the demo's add or remove.
        self.other = Company.objects.create(name='Real Customer', email='it@real.test')
        self.other_user = User.objects.create_user('omar', 'omar@real.test', 'x')
        UserProfile.objects.update_or_create(user=self.other_user, defaults={'company': self.other})
        self.other_project = Project.objects.create(name='Real work', owner=self.other_user, company=self.other)

    def labels(self, snap):
        return {(r['model'], r['pk']) for r in demo_data.snapshot_records(snap)}

    def do(self, action):
        run = DemoDataRun.objects.create(action=action)
        demo_data.run_job(run.id)
        run.refresh_from_db()
        return run


class SnapshotTests(DemoDataBase):
    def test_snapshot_holds_the_company_and_nothing_else(self):
        snap = demo_data.make_snapshot(self.demo, key='margalla', label='Demo videos')
        got = self.labels(snap)
        self.assertIn(('core.company', self.demo.pk), got)
        self.assertIn(('core.companyuser', self.owner.pk), got)
        self.assertIn(('auth.user', self.employee.pk), got)
        self.assertIn(('core.project', self.project.pk), got)
        self.assertIn(('core.task', self.task.pk), got)
        self.assertNotIn(('core.company', self.other.pk), got)
        self.assertNotIn(('core.project', self.other_project.pk), got)
        self.assertNotIn(('auth.user', self.other_user.pk), got)
        self.assertNotIn(('auth.user', self.admin.pk), got)
        self.assertFalse(any(m in ('core.usertoken', 'core.agent') for m, _ in got))
        self.assertEqual(snap.rows, len(got))

    def test_secrets_are_blanked(self):
        snap = demo_data.make_snapshot(self.demo, key='margalla', label='Demo videos')
        by = {(r['model'], r['pk']): r['fields'] for r in demo_data.snapshot_records(snap)}
        self.assertEqual(by[('core.companyuser', self.owner.pk)]['password_hash'], '')
        self.assertEqual(by[('auth.user', self.employee.pk)]['password'], '')
        key = next(f for (m, _), f in by.items() if m == 'core.companyapikey')
        self.assertEqual(key['encrypted_key'], '')
        crm = next(f for (m, _), f in by.items() if m == 'crm_sync_agent.crmintegration')
        self.assertEqual(crm['credentials'], {})
        raw = str(demo_data.snapshot_records(snap))
        self.assertNotIn('secret-key-value', raw)
        self.assertNotIn('secret-token', raw)

    def test_a_link_to_another_company_does_not_pull_it_in(self):
        # A task of the demo given to the other company's person: the person and their company stay out.
        Task.objects.create(title='Shared', project=self.project, assignee=self.other_user)
        got = self.labels(demo_data.make_snapshot(self.demo, key='margalla', label='Demo'))
        self.assertNotIn(('auth.user', self.other_user.pk), got)
        self.assertNotIn(('core.company', self.other.pk), got)
        self.assertNotIn(('core.project', self.other_project.pk), got)


class AddAndRemoveTests(DemoDataBase):
    def setUp(self):
        super().setUp()
        self.snap = demo_data.make_snapshot(self.demo, key='margalla', label='Demo videos')

    def test_remove_takes_only_the_demo(self):
        run = self.do('remove')
        self.assertEqual(run.status, 'done')
        self.assertFalse(Company.objects.filter(pk=self.demo.pk).exists())
        self.assertFalse(User.objects.filter(pk=self.employee.pk).exists())
        self.assertFalse(Project.objects.filter(pk=self.project.pk).exists())
        self.assertFalse(CRMIntegration.objects.filter(company_id=self.demo.pk).exists())
        # The other company, its person and the super admin are untouched.
        self.assertTrue(Company.objects.filter(pk=self.other.pk).exists())
        self.assertTrue(Project.objects.filter(pk=self.other_project.pk).exists())
        self.assertTrue(User.objects.filter(pk=self.other_user.pk).exists())
        self.assertTrue(User.objects.filter(pk=self.admin.pk).exists())

    def test_add_brings_it_back_as_it_was_with_a_new_password(self):
        self.do('remove')
        DemoSnapshot.objects.filter(pk=self.snap.pk).update(made_at=timezone.now() - timedelta(days=10))
        created = self.project.created_at
        run = self.do('load')
        self.assertEqual(run.status, 'done')
        self.assertEqual(run.done_rows, run.total_rows)
        self.assertEqual(run.total_rows, self.snap.rows)

        project = Project.objects.get(pk=self.project.pk)
        self.assertEqual(project.company_id, self.demo.pk)
        self.assertEqual(project.created_at.date(), (created + timedelta(days=10)).date())
        self.assertTrue(Task.objects.filter(pk=self.task.pk, assignee_id=self.employee.pk).exists())

        snap = DemoSnapshot.objects.get(pk=self.snap.pk)
        password = decrypt_secret(snap.password)
        self.assertTrue(password.startswith('Demo-'))
        self.assertIsNotNone(snap.loaded_at)
        self.assertTrue(check_password(password, CompanyUser.objects.get(pk=self.owner.pk).password_hash))
        self.assertTrue(User.objects.get(pk=self.employee.pk).check_password(password))
        # Nothing is synced from the demo.
        self.assertFalse(CRMIntegration.objects.get(company_id=self.demo.pk).is_active)

    def test_add_skips_a_company_already_there(self):
        run = self.do('load')
        self.assertEqual(run.status, 'done')
        self.assertEqual(run.total_rows, 0)

    def test_add_refuses_when_an_id_is_taken_and_writes_nothing(self):
        self.do('remove')
        # Someone new now has the demo project's id.
        Project.objects.create(pk=self.project.pk, name='New', owner=self.other_user, company=self.other)
        run = DemoDataRun.objects.create(action='load')
        with self.assertRaises(demo_data.TestDataError):
            demo_data.run_job(run.id)
        run.refresh_from_db()
        self.assertEqual(run.status, 'failed')
        self.assertIn('same ids', run.error)
        self.assertFalse(Company.objects.filter(pk=self.demo.pk).exists())
        self.assertFalse(User.objects.filter(pk=self.employee.pk).exists())

    def test_a_failed_add_removes_what_it_wrote(self):
        self.do('remove')
        real_progress = demo_data._progress
        calls = {'n': 0}

        def fail_halfway(run, done, total, step):
            calls['n'] += 1
            if calls['n'] == 4:
                raise RuntimeError('disk full')
            real_progress(run, done, total, step)

        demo_data._progress = fail_halfway
        try:
            with self.assertRaises(RuntimeError):
                demo_data.run_job(DemoDataRun.objects.create(action='load').id)
        finally:
            demo_data._progress = real_progress
        self.assertFalse(Company.objects.filter(pk=self.demo.pk).exists())
        self.assertFalse(CompanyUser.objects.filter(pk=self.owner.pk).exists())
        self.assertFalse(User.objects.filter(pk=self.employee.pk).exists())

    def test_overview_lists_logins_password_and_agents(self):
        self.do('remove')
        self.do('load')
        item = next(i for i in demo_data.overview() if i['key'] == 'margalla')
        self.assertTrue(item['loaded'])
        self.assertTrue(item['password'].startswith('Demo-'))
        self.assertEqual([d['email'] for d in item['dashboard_logins']], ['owner@margalla.test'])
        self.assertEqual([e['email'] for e in item['employee_logins']], ['ali@margalla.test'])
        self.assertEqual(item['agents'], ['Project Manager Agent'])


class SweepTests(DemoDataBase):
    def test_sweep_keeps_admins_setup_and_public_site(self):
        author = User.objects.create_user('writer', 'writer@test.local', 'x')
        post = BlogPost.objects.create(title='Hello', slug='hello', description='D', content='Text', category='News', author=author)
        faq = FAQ.objects.create(question='Q?', answer='A.')
        message = ContactMessage.objects.create(full_name='Visitor', email='v@test.local', message='Hi')
        snap = demo_data.make_snapshot(self.demo, key='margalla', label='Demo')

        dry = demo_data.sweep(commit=False)
        self.assertIn('core.Company', dry)
        self.assertTrue(Company.objects.exists())

        demo_data.sweep(commit=True)
        self.assertFalse(Company.objects.exists())
        self.assertFalse(Project.objects.exists())
        self.assertFalse(CompanyUser.objects.exists())
        self.assertEqual(set(User.objects.values_list('username', flat=True)), {'boss', 'writer'})
        self.assertTrue(UserToken.objects.filter(user=self.admin).exists())
        self.assertTrue(UserProfile.objects.filter(user=self.admin).exists())
        self.assertTrue(BlogPost.objects.filter(pk=post.pk, author=author).exists())
        self.assertTrue(FAQ.objects.filter(pk=faq.pk).exists())
        self.assertTrue(ContactMessage.objects.filter(pk=message.pk).exists())
        self.assertTrue(Agent.objects.filter(slug='project_manager_agent').exists())
        self.assertTrue(DemoSnapshot.objects.filter(pk=snap.pk).exists())

    def test_the_demo_can_be_added_after_a_sweep(self):
        demo_data.make_snapshot(self.demo, key='margalla', label='Demo')
        demo_data.sweep(commit=True)
        self.assertEqual(self.do('load').status, 'done')
        self.assertTrue(Company.objects.filter(pk=self.demo.pk, name='Margalla Software').exists())
        self.assertFalse(Company.objects.filter(pk=self.other.pk).exists())


class ApiTests(DemoDataBase):
    def setUp(self):
        super().setUp()
        self.rf = APIRequestFactory()

    def call(self, view, method='get', user=None, data=None, **kw):
        req = getattr(self.rf, method)('/x', data or {}, format='json')
        force_authenticate(req, user=user or self.admin)
        return view(req, **kw)

    def test_only_platform_admins(self):
        resp = self.call(views.test_data_overview, user=self.employee)
        self.assertEqual(resp.status_code, 403)
        resp = self.call(views.test_data_start, 'post', user=self.employee, action='load')
        self.assertEqual(resp.status_code, 403)

    def test_no_snapshot_yet(self):
        resp = self.call(views.test_data_start, 'post', action='load')
        self.assertEqual(resp.status_code, 400)

    def test_remove_then_add_through_the_page(self):
        demo_data.make_snapshot(self.demo, key='margalla', label='Demo')
        # The worker runs it straight away in tests (CELERY_TASK_ALWAYS_EAGER).
        resp = self.call(views.test_data_start, 'post', action='remove')
        self.assertEqual(resp.status_code, 202)
        self.assertFalse(Company.objects.filter(pk=self.demo.pk).exists())

        resp = self.call(views.test_data_start, 'post', action='load')
        self.assertEqual(resp.status_code, 202)
        run = self.call(views.test_data_run, run_id=resp.data['data']['id']).data['data']
        self.assertEqual(run['processing_status'], 'ready')
        self.assertEqual(run['percent'], 100)
        self.assertEqual(run['chunks_processed'], run['chunks_total'])

        data = self.call(views.test_data_overview).data
        self.assertIsNone(data['running'])
        self.assertTrue(data['snapshots'][0]['loaded'])
        self.assertTrue(data['snapshots'][0]['password'])

    def test_one_run_at_a_time(self):
        demo_data.make_snapshot(self.demo, key='margalla', label='Demo')
        DemoDataRun.objects.create(action='load', status='running')
        resp = self.call(views.test_data_start, 'post', action='remove')
        self.assertEqual(resp.status_code, 409)

    def test_an_abandoned_run_does_not_block(self):
        demo_data.make_snapshot(self.demo, key='margalla', label='Demo')
        old = DemoDataRun.objects.create(action='load', status='running')
        DemoDataRun.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(hours=3))
        resp = self.call(views.test_data_start, 'post', action='remove')
        self.assertEqual(resp.status_code, 202)
