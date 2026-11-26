"""One company's backups (core.backups.build_company_zip, api.views.company_backups, manage.py make_company_backups):
only its rows and its uploads go in, its secrets stay out, only its owners and admins get in, and each company has
its own nightly ones."""
import json
import zipfile
from pathlib import Path
from unittest import mock

from django.contrib.auth.models import User

from api.views import company_backups as views
from core import backups
from core.models import Company, CompanyUser, SystemBackup
from core.tests_backups import BackupBase


class CompanyBackupBase(BackupBase):
    def setUp(self):
        super().setUp()
        self.login = User.objects.create_user('acme-login', 'owner@acme.test', 'secret-pass')
        self.owner = CompanyUser.objects.create(company=self.company, email='owner@acme.test', full_name='Owner',
                                                role='owner', password_hash='HASH-ACME', is_active=True,
                                                login_user=self.login)
        self.other = Company.objects.create(name='Beta Co', email='beta@test.local')
        self.beta = CompanyUser.objects.create(company=self.other, email='b@beta.test', full_name='B', role='owner',
                                               password_hash='HASH-BETA', is_active=True)

    def company_backup(self, company=None):
        backup = SystemBackup.objects.create(company=company or self.company, company_user=self.owner,
                                             file_name='backup-company.zip')
        backups.run_backup(backup.pk)
        backup.refresh_from_db()
        return backup

    def read(self, backup):
        with zipfile.ZipFile(backups.backup_path(backup)) as zf:
            return (set(zf.namelist()), json.loads(zf.read('database.json')), json.loads(zf.read('manifest.json')),
                    zf)


class WhatGoesInTests(CompanyBackupBase):
    def test_only_the_companys_rows_and_files_go_in_and_its_secrets_stay_out(self):
        from ai_sdr_agent.models import SDRCampaign, SDRLead
        from Frontline_agent.models import Document
        from marketing_agent.models import Campaign, CampaignLead, Lead
        SDRLead.objects.create(company_user=self.owner, full_name='Ali Khan', email='ali@x.test')
        SDRLead.objects.create(company_user=self.beta, full_name='Sara Beta')
        SDRCampaign.objects.create(company_user=self.owner, name='Spring', smtp_password='MAILBOX-PASS')
        lead = Lead.objects.create(email='lina@x.test', first_name='Lina', owner=self.login)
        CampaignLead.objects.create(campaign=Campaign.objects.create(name='Mkt', owner=self.login), lead=lead)
        Lead.objects.create(email='boss-lead@x.test', owner=self.admin)
        self.write('frontline_documents/acme/faq.pdf', b'%PDF-acme')
        self.write('frontline_documents/beta/faq.pdf', b'%PDF-beta')
        Document.objects.create(company=self.company, title='FAQ', uploaded_by=self.login,
                                file_path='frontline_documents/acme/faq.pdf')
        Document.objects.create(company=self.other, title='FAQ', uploaded_by=self.admin,
                                file_path=str(self.media / 'frontline_documents' / 'beta' / 'faq.pdf'))

        backup = self.company_backup()
        self.assertEqual(backup.status, 'done', backup.error)
        self.assertTrue(str(backups.backup_path(backup)).startswith(str(self.root / 'companies' / str(self.company.pk))))
        names, rows, manifest, _ = self.read(backup)

        raw = json.dumps(rows)
        self.assertIn('Ali Khan', raw)
        self.assertIn('lina@x.test', raw)
        for leaked in ('Sara Beta', 'HASH-BETA', 'Beta Co', 'boss-lead@x.test', 'boss@test.local'):
            self.assertNotIn(leaked, raw)
        for secret in ('HASH-ACME', 'MAILBOX-PASS', 'pbkdf2'):
            self.assertNotIn(secret, raw)
        by_model = {}
        for r in rows:
            by_model.setdefault(r['model'], []).append(r)
        self.assertEqual([r['pk'] for r in by_model['core.company']], [self.company.pk])
        self.assertNotIn('password_hash', by_model['core.companyuser'][0]['fields'])
        self.assertNotIn('password', by_model['auth.user'][0]['fields'])
        self.assertIn('marketing_agent.campaignlead', by_model)
        self.assertNotIn('core.systembackup', by_model)

        self.assertIn('media/frontline_documents/acme/faq.pdf', names)
        self.assertNotIn('media/frontline_documents/beta/faq.pdf', names)
        self.assertIn('exports/sdr_leads.csv', names)
        self.assertEqual((manifest['kind'], manifest['company']['id']), ('company', self.company.pk))
        self.assertEqual(manifest['exports'], {'sdr_leads.csv': 1, 'marketing_leads.csv': 1})
        self.assertEqual(backup.summary['files'], 1)

    def test_a_path_outside_the_media_folder_is_never_read(self):
        from Frontline_agent.models import Document
        outside = self.tmp / 'not-media.txt'
        outside.write_bytes(b'server file')
        Document.objects.create(company=self.company, title='x', uploaded_by=self.login, file_path=str(outside))
        Document.objects.create(company=self.company, title='y', uploaded_by=self.login, file_path='../not-media.txt')
        backup = self.company_backup()
        names, _, _, _ = self.read(backup)
        self.assertEqual([n for n in names if n.startswith('media/')], [])

    def test_restore_backup_refuses_a_company_backup(self):
        backup = self.company_backup()
        with self.assertRaisesMessage(backups.RestoreError, "one company's backup"):
            backups.restore(backups.backup_path(backup))
        self.assertTrue(Company.objects.filter(pk=self.other.pk).exists())


class EndpointTests(CompanyBackupBase):
    def test_only_the_companys_owners_and_admins_get_in(self):
        staff = CompanyUser.objects.create(company=self.company, email='rec@acme.test', full_name='R',
                                           role='recruiter', password_hash='x', is_active=True)
        self.assertEqual(self.call(views.company_backups, user=staff).status_code, 403)
        self.assertEqual(self.call(views.company_backups, 'post', user=staff).status_code, 403)
        self.assertIn(self.call(views.company_backups, user=self.admin).status_code, (401, 403))
        self.assertIn(self.call(views.company_backups, user=None).status_code, (401, 403))

    def test_a_company_sees_only_its_own_and_the_super_admin_list_leaves_them_out(self):
        from api.views import admin_backups
        mine = self.company_backup()
        theirs = self.company_backup(company=self.other)
        listed = [b['id'] for b in self.call(views.company_backups, user=self.owner).data['data']]
        self.assertEqual(listed, [mine.id])
        self.assertEqual(self.call(views.company_backup_delete, 'delete', user=self.owner,
                                   backup_id=theirs.id).status_code, 404)
        self.assertEqual(self.call(views.company_backup_download_link, 'post', user=self.owner,
                                   backup_id=theirs.id).status_code, 404)
        self.assertEqual(self.call(admin_backups.backups_list).data['data'], [])

    def test_starting_one_runs_in_the_background_one_at_a_time_per_company(self):
        with mock.patch.object(backups.threading, 'Thread') as thread:
            r = self.call(views.company_backups, 'post', user=self.owner)
            self.assertEqual((r.status_code, r.data['data']['created_by']), (201, 'Owner'), r.data)
            thread.return_value.start.assert_called_once()
            self.assertEqual(self.call(views.company_backups, 'post', user=self.owner).status_code, 409)
            self.assertEqual(self.call(views.company_backups, 'post', user=self.beta).status_code, 201)
            # The super admin's whole-system one is not held up by a company's.
            self.assertEqual(backups.start_backup(self.admin).company, None)

    def test_the_download_link_is_for_this_company_and_this_backup(self):
        backup = self.company_backup()
        ticket = self.call(views.company_backup_download_link, 'post', user=self.owner,
                           backup_id=backup.id).data['ticket']
        ok = views.company_backup_download(self.rf.get('/x', {'ticket': ticket}), backup_id=backup.id)
        self.assertEqual(ok.status_code, 200)
        ok.close()
        theirs = self.company_backup(company=self.other)
        self.assertEqual(views.company_backup_download(self.rf.get('/x', {'ticket': ticket}),
                                                       backup_id=theirs.id).status_code, 403)
        self.assertEqual(views.company_backup_download(self.rf.get('/x', {'ticket': 'forged'}),
                                                       backup_id=backup.id).status_code, 403)


class NightlyTests(CompanyBackupBase):
    """manage.py make_company_backups, run each night by scripts/ppp-full-backup.sh after the whole-system backup,
    which then encrypts each zip it prints and sends it to Backblaze B2."""

    def run_command(self, *args):
        from io import StringIO
        from django.core.management import call_command
        out, err = StringIO(), StringIO()
        call_command('make_company_backups', *args, stdout=out, stderr=err)
        return out.getvalue().strip().splitlines(), err.getvalue()

    def test_each_active_company_gets_one_and_keeps_only_its_newest(self):
        Company.objects.create(name='Gone Co', email='g@test.local', is_active=False)
        old = SystemBackup.objects.create(company=self.company, status='done',
                                          file_name='backup-20261101-210000-nightly.zip')
        system = SystemBackup.objects.create(status='done', file_name='backup-20261101-210000-nightly.zip')

        lines, _ = self.run_command('--keep', '1')

        mine = SystemBackup.objects.get(company=self.company)
        theirs = SystemBackup.objects.get(company=self.other)
        # One line per backup, its path under BACKUP_ROOT, for the script to encrypt and send.
        self.assertEqual(lines, [f'companies/{self.company.pk}/{mine.file_name}',
                                 f'companies/{self.other.pk}/{theirs.file_name}'])
        for line in lines:
            self.assertTrue((self.root / line).is_file())
        self.assertTrue(mine.file_name.endswith('-nightly.zip'))
        self.assertFalse(SystemBackup.objects.filter(pk=old.pk).exists())
        self.assertTrue(SystemBackup.objects.filter(pk=system.pk).exists())     # the system's own are not touched
        self.assertFalse(SystemBackup.objects.filter(company__is_active=False).exists())

    def test_one_company_failing_does_not_stop_the_others_and_the_command_says_so(self):
        from django.core.management.base import CommandError
        real = backups.build_company_zip

        def flaky(path, company, created_by=''):
            if company.pk == self.company.pk:
                raise RuntimeError('disk full')
            return real(path, company, created_by)

        from io import StringIO
        from django.core.management import call_command
        out, err = StringIO(), StringIO()
        with mock.patch.object(backups, 'build_company_zip', side_effect=flaky),                 self.assertRaisesMessage(CommandError, '1 company backup(s) failed'):
            call_command('make_company_backups', stdout=out, stderr=err)
        theirs = SystemBackup.objects.get(company=self.other)
        self.assertEqual(out.getvalue().strip(), f'companies/{self.other.pk}/{theirs.file_name}')
        self.assertIn('disk full', err.getvalue())
        self.assertEqual(SystemBackup.objects.get(company=self.company).error, 'disk full')

    def test_the_nightly_script_encrypts_and_sends_each_company_backup(self):
        from django.conf import settings
        script = (Path(settings.BASE_DIR) / 'scripts' / 'ppp-full-backup.sh').read_text(encoding='utf-8')
        self.assertIn('manage.py make_company_backups --keep', script)
        self.assertIn('ship "$CENC" "$DIR"', script)
        self.assertNotIn('make-company-backups', settings.CELERY_BEAT_SCHEDULE)   # cron makes them, as the system one
