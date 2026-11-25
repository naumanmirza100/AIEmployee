"""Whole-system backups (core.backups, api.views.admin_backups): what goes in the zip and what is left out, the
admin-only endpoints, and the signed download link."""
import csv
import io
import json
import shutil
import tempfile
import zipfile
from datetime import timedelta
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

    def test_each_companys_leads_are_exported_as_csvs(self):
        from ai_sdr_agent.models import SDRLead
        from marketing_agent.models import Campaign, CampaignLead, Lead
        login = User.objects.create_user('acme-login', 'owner@acme.test', 'x')
        owner = CompanyUser.objects.create(company=self.company, email='owner@acme.test', full_name='Owner',
                                           role='owner', password_hash='x', is_active=True, login_user=login)
        other = Company.objects.create(name='Beta Co', email='beta@test.local')
        beta = CompanyUser.objects.create(company=other, email='b@beta.test', full_name='B', role='owner',
                                          password_hash='x', is_active=True)
        SDRLead.objects.create(company_user=owner, full_name='Ali Khan', email='ali@x.test',
                               buying_signals=['Raised a Series A', 'Hiring'])
        SDRLead.objects.create(company_user=owner, full_name='=HYPERLINK("http://evil")', is_deleted=True)
        SDRLead.objects.create(company_user=beta, full_name='Sara')
        lead = Lead.objects.create(email='lead@x.test', first_name='Lina', owner=login)
        CampaignLead.objects.create(campaign=Campaign.objects.create(name='Spring', owner=login), lead=lead)
        Lead.objects.create(email='orphan@x.test', owner=self.admin)

        backup = self.made_backup()
        self.assertEqual(backup.status, 'done', backup.error)
        acme, beta_dir = f'exports/{self.company.pk}-acme-dental', f'exports/{other.pk}-beta-co'
        with zipfile.ZipFile(backups.backup_path(backup)) as zf:
            names = set(zf.namelist())
            sdr = list(csv.DictReader(io.StringIO(zf.read(f'{acme}/sdr_leads.csv').decode('utf-8-sig'))))
            mkt = list(csv.DictReader(io.StringIO(zf.read(f'{acme}/marketing_leads.csv').decode('utf-8-sig'))))
            manifest = json.loads(zf.read('manifest.json'))

        self.assertIn(f'{beta_dir}/sdr_leads.csv', names)
        self.assertIn('exports/0-no-company/marketing_leads.csv', names)   # its owner is no company's login
        self.assertEqual([r['full_name'] for r in sdr], ['Ali Khan', '\'=HYPERLINK("http://evil")'])
        self.assertEqual((sdr[0]['buying_signals'], sdr[0]['added_by'], sdr[1]['is_deleted']),
                         ('Raised a Series A; Hiring', 'owner@acme.test', 'True'))
        self.assertEqual((mkt[0]['email'], mkt[0]['campaigns'], mkt[0]['owner']),
                         ('lead@x.test', 'Spring', 'owner@acme.test'))
        self.assertEqual(manifest['exports'][f'{self.company.pk}-acme-dental'],
                         {'sdr_leads.csv': 2, 'marketing_leads.csv': 1})
        self.assertEqual(backup.summary['exported_leads'], 5)

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


class NightlyTests(BackupBase):
    """manage.py make_backup, run each night by scripts/ppp-full-backup.sh (25 Nov 2026)."""

    def old_backup(self, name, status='done', days_ago=1):
        backup = SystemBackup.objects.create(file_name=name, status=status, created_by=self.admin)
        SystemBackup.objects.filter(pk=backup.pk).update(
            created_at=backup.created_at - timedelta(days=days_ago))
        if status == 'done':
            self.root.mkdir(parents=True, exist_ok=True)
            (self.root / name).write_bytes(b'PK')
        return backup

    def test_the_command_makes_one_and_prints_its_name_last(self):
        from io import StringIO
        from django.core.management import call_command
        out, err = StringIO(), StringIO()
        call_command('make_backup', stdout=out, stderr=err)
        backup = SystemBackup.objects.get()
        self.assertEqual((backup.status, backup.created_by), ('done', None))
        self.assertTrue(backup.file_name.endswith('-nightly.zip'))
        self.assertEqual(out.getvalue().strip().splitlines()[-1], backup.file_name)
        self.assertTrue(backups.backup_path(backup).is_file())
        self.assertIn('records', err.getvalue())
        row = self.call(views.backups_list).data['data'][0]
        self.assertEqual((row['nightly'], row['created_by']), (True, ''))

    def test_only_the_newest_nightly_ones_are_kept_and_hand_made_ones_never_go(self):
        nightly = [self.old_backup(f'backup-2026110{d}-210000-nightly.zip', days_ago=10 - d) for d in range(1, 6)]
        failed_old = self.old_backup('backup-20261020-210000-nightly.zip', status='failed', days_ago=30)
        by_hand = self.old_backup('backup-20261001-101010.zip', days_ago=50)

        new = backups.make_nightly_backup(keep=3)

        left = set(SystemBackup.objects.values_list('file_name', flat=True))
        self.assertEqual(left, {new.file_name, nightly[-1].file_name, nightly[-2].file_name, by_hand.file_name})
        self.assertFalse((self.root / nightly[0].file_name).exists())
        self.assertTrue((self.root / by_hand.file_name).exists())
        self.assertNotIn(failed_old.file_name, left)

    def test_a_failed_night_deletes_nothing(self):
        nightly = [self.old_backup(f'backup-2026110{d}-210000-nightly.zip', days_ago=10 - d) for d in range(1, 4)]
        with mock.patch.object(backups, 'call_command', side_effect=RuntimeError('disk full')):
            new = backups.make_nightly_backup(keep=1)
        self.assertEqual(new.status, 'failed')
        self.assertEqual(SystemBackup.objects.filter(status='done').count(), len(nightly))

    def test_it_waits_its_turn_when_one_is_being_made(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError
        SystemBackup.objects.create(created_by=self.admin, file_name='backup-run.zip')
        with self.assertRaisesMessage(CommandError, 'already being made'):
            call_command('make_backup')
        self.assertEqual(SystemBackup.objects.count(), 1)


class RestoreTests(BackupBase):
    """manage.py restore_backup. Plain loaddata of the live backup (24 Nov 2026) stopped on the first Reply: its save
    hook moves the lead on before the leads were loaded."""

    def backup_with_hooks_in_it(self):
        from core.models import UserProfile
        from marketing_agent.models import Campaign, CampaignContact, Lead, Reply
        UserProfile.objects.filter(user=self.admin).update(phone_number='+92 300 0000000')
        campaign = Campaign.objects.create(owner=self.admin, name='Spring', status='active')
        lead = Lead.objects.create(owner=self.admin, email='sara@clinic.example')
        contact = CampaignContact.objects.create(campaign=campaign, lead=lead)
        Reply.objects.create(contact=contact, campaign=campaign, lead=lead, interest_level='positive')
        Lead.objects.filter(pk=lead.pk).update(status='contacted')     # set by a person after the reply
        self.write('cvs/ali.pdf', b'%PDF-ali')
        backup = self.made_backup()
        self.assertEqual(backup.status, 'done', backup.error)
        return backups.backup_path(backup), lead.pk

    def new_server(self):
        """The database of a server just set up, and no uploads yet."""
        from django.core.management import call_command
        call_command('flush', interactive=False, verbosity=0)
        shutil.rmtree(self.media, ignore_errors=True)

    def test_a_backup_comes_back_as_it_was_and_the_save_hooks_do_not_run(self):
        from core.models import UserProfile
        from marketing_agent.models import Lead, Reply
        zip_path, lead_id = self.backup_with_hooks_in_it()
        self.new_server()

        result = backups.restore(zip_path)

        self.assertEqual(result['files'], 1)
        self.assertEqual((self.media / 'cvs' / 'ali.pdf').read_bytes(), b'%PDF-ali')
        boss = User.objects.get(username='boss')
        self.assertTrue(boss.check_password('x'))
        self.assertEqual(list(UserProfile.objects.filter(user=boss).values_list('phone_number', flat=True)),
                         ['+92 300 0000000'])                            # one profile, the backup's, not a new one
        self.assertEqual(Company.objects.get().name, 'Acme Dental')
        self.assertEqual(Reply.objects.count(), 1)
        self.assertEqual(Lead.objects.get(pk=lead_id).status, 'contacted')   # the reply's hook did not move it on
        from django.db.models import signals
        self.assertNotIn('send', vars(signals.post_save))                  # the hooks are on again afterwards

    def test_plain_loaddata_is_what_fails(self):
        """Why the command exists: the same backup through plain loaddata does not load."""
        from django.core.management import call_command
        zip_path, _ = self.backup_with_hooks_in_it()
        self.new_server()
        fixture = self.tmp / 'database.json'
        with zipfile.ZipFile(zip_path) as zf:
            fixture.write_bytes(zf.read('database.json'))
        with self.assertRaises(Exception):
            call_command('loaddata', str(fixture), verbosity=0)

    def test_a_database_in_use_is_refused_and_left_alone(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError
        zip_path, _ = self.backup_with_hooks_in_it()
        CompanyUser.objects.create(company=self.company, email='ann@acme.test', full_name='Ann', role='admin',
                                   password_hash='x', is_active=True)
        with self.assertRaisesMessage(CommandError, 'already has logins or companies'):
            call_command('restore_backup', str(zip_path))
        self.assertEqual((User.objects.count(), CompanyUser.objects.count()), (1, 1))

    def test_a_zip_that_is_not_a_backup_or_no_file_is_refused(self):
        self.new_server()
        not_ours = self.tmp / 'photos.zip'
        with zipfile.ZipFile(not_ours, 'w') as zf:
            zf.writestr('photo.jpg', b'x')
        with self.assertRaisesMessage(backups.RestoreError, 'not a backup'):
            backups.restore(not_ours)
        with self.assertRaisesMessage(backups.RestoreError, 'No file'):
            backups.restore(self.tmp / 'missing.zip')

    def test_an_upload_name_cannot_write_outside_the_media_folder(self):
        zip_path, _ = self.backup_with_hooks_in_it()
        self.new_server()
        with zipfile.ZipFile(zip_path, 'a') as zf:
            zf.writestr('media/../escaped.txt', b'x')
        result = backups.restore(zip_path)
        self.assertEqual(result['files'], 1)
        self.assertFalse((self.tmp / 'escaped.txt').exists())
