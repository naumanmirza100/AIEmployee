"""Whole-system backups (core.backups, api.views.admin_backups): what goes in the zip and what is left out, the
admin-only endpoints, and the signed download link."""
import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from api.views import admin_backups as views
from core import backups
from core.models import Company, CompanyUser, SystemBackup, UserToken


class BackupBase(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.media, self.root = self.tmp / 'media', self.tmp / 'backups'
        settings_patch = override_settings(MEDIA_ROOT=str(self.media), BACKUP_ROOT=str(self.root))
        settings_patch.enable()
        self.addCleanup(settings_patch.disable)
        self.admin = User.objects.create_user('boss', 'boss@test.local', 'x', is_staff=True)
        self.company = Company.objects.create(name='Acme Dental', email='acme@test.local')
        self.rf = APIRequestFactory()

    def call(self, view, method='get', path='/x', user='admin', **kw):
        req = getattr(self.rf, method)(path, format='json')
        if user is not None:
            force_authenticate(req, user=self.admin if user == 'admin' else user)
        return view(req, **kw)

    def write(self, rel, data=b'x'):
        path = self.media / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def made_backup(self):
        """A finished backup, built the way the background thread builds it."""
        backup = SystemBackup.objects.create(created_by=self.admin, file_name='backup-test.zip')
        backups.run_backup(backup.pk)
        backup.refresh_from_db()
        return backup


class WhatGoesInTests(BackupBase):
    def test_the_database_and_the_uploads_go_in_and_the_rest_stays_out(self):
        self.write('cvs/ali.pdf', b'%PDF')
        self.write('hr_documents/7/handbook.docx')
        self.write('hr_vector_indexes/7/index.faiss')
        self.write('cvs/worker.log')
        UserToken.objects.create(user=self.admin, key='k' * 40)
        backup = self.made_backup()
        self.assertEqual(backup.status, 'done', backup.error)

        with zipfile.ZipFile(backups.backup_path(backup)) as zf:
            names = set(zf.namelist())
            rows = json.loads(zf.read('database.json'))
            manifest = json.loads(zf.read('manifest.json'))
        self.assertEqual(names, {'database.json', 'manifest.json', 'media/cvs/ali.pdf',
                                 'media/hr_documents/7/handbook.docx'})
        models = {r['model'] for r in rows}
        self.assertIn('core.company', models)
        self.assertIn('auth.user', models)
        self.assertFalse(models & {'core.usertoken', 'core.systembackup', 'contenttypes.contenttype', 'auth.permission'})
        self.assertEqual(manifest['files'], 2)
        self.assertEqual((backup.summary['files'], backup.size_bytes > 0), (2, True))
        self.assertEqual(backup.summary['models']['core.company'], 1)

    def test_a_failure_is_recorded_and_leaves_no_half_file(self):
        backup = SystemBackup.objects.create(created_by=self.admin, file_name='backup-bad.zip')
        with mock.patch.object(backups, 'call_command', side_effect=RuntimeError('disk full')):
            backups.run_backup(backup.pk)
        backup.refresh_from_db()
        self.assertEqual((backup.status, backup.error), ('failed', 'disk full'))
        self.assertEqual(list(self.root.iterdir()), [])


class EndpointTests(BackupBase):
    def test_only_platform_admins_get_in(self):
        plain = User.objects.create_user('plain', 'p@test.local', 'x')
        company_login = CompanyUser.objects.create(company=self.company, email='c@test.local', full_name='C',
                                                   role='admin', password_hash='x', is_active=True)
        for user in (None, plain, company_login):
            with self.subTest(user):
                self.assertIn(self.call(views.backups_list, user=user).status_code, (401, 403))
                self.assertIn(self.call(views.backups_list, 'post', user=user).status_code, (401, 403))

    def test_starting_one_runs_it_in_the_background_and_only_one_at_a_time(self):
        with mock.patch.object(backups.threading, 'Thread') as thread:
            r = self.call(views.backups_list, 'post')
            self.assertEqual((r.status_code, r.data['data']['status']), (201, 'running'), r.data)
            thread.return_value.start.assert_called_once()
            self.assertEqual(self.call(views.backups_list, 'post').status_code, 409)
        self.assertEqual([b['status'] for b in self.call(views.backups_list).data['data']], ['running'])

    def test_a_backup_left_running_by_a_restart_is_failed(self):
        old = SystemBackup.objects.create(created_by=self.admin, file_name='backup-old.zip')
        SystemBackup.objects.filter(pk=old.pk).update(created_at=old.created_at - backups.STALE_AFTER * 2)
        self.assertEqual(self.call(views.backups_list).data['data'][0]['status'], 'failed')

    def test_download_needs_a_fresh_ticket_for_that_backup(self):
        backup = self.made_backup()
        other = self.made_backup()
        ticket = self.call(views.backup_download_link, 'post', backup_id=backup.id).data['ticket']

        r = self.call(views.backup_download, path=f'/x?ticket={ticket}', user=None, backup_id=backup.id)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(b''.join(r.streaming_content).startswith(b'PK'))
        r.close()
        for path, backup_id in ((f'/x?ticket={ticket}', other.id), ('/x?ticket=forged', backup.id), ('/x', backup.id)):
            with self.subTest(path=path, backup_id=backup_id):
                self.assertEqual(self.call(views.backup_download, path=path, user=None, backup_id=backup_id).status_code, 403)

    def test_delete_removes_the_file_but_not_a_running_one(self):
        backup = self.made_backup()
        path = backups.backup_path(backup)
        self.assertEqual(self.call(views.backup_delete, 'delete', backup_id=backup.id).status_code, 200)
        self.assertFalse(path.exists() or SystemBackup.objects.filter(pk=backup.pk).exists())
        running = SystemBackup.objects.create(created_by=self.admin, file_name='backup-run.zip')
        self.assertEqual(self.call(views.backup_delete, 'delete', backup_id=running.id).status_code, 409)
