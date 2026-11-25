"""Whole-system backups for the super admin: one zip with every company's data, the platform's own, and the
uploaded files.

What is in the zip:
  database.json  every row of every app (dumpdata, whatever the engine: SQLite, SQL Server or MariaDB). Loads back
                 with `manage.py loaddata database.json` into a migrated, empty database.
  media/...      the uploaded files (CVs, HR and Frontline documents, attachments, analyst sources...). The
                 database only holds their paths, so a backup without them would point at nothing.
  exports/...    each company's leads as CSVs that open in Excel (exports/<id>-<company>/sdr_leads.csv and
                 marketing_leads.csv), so a person can see what a backup holds. For reading only: the same rows are
                 in database.json, and that is what a restore loads.
  manifest.json  when, by whom, from which database, and how many rows, files and exported leads went in.

What is left out, as not data: login sessions and tokens, Django's own bookkeeping (content types, permissions, the
admin's log), the Celery schedule, the search indexes (rebuilt from the documents), logs and crash dumps, and the
backups themselves.

A backup runs in a thread of the web process, so it neither waits on a Celery worker nor holds up the request.

Every night one is also made by `manage.py make_backup`, which scripts/ppp-full-backup.sh runs from cron (21:00 UTC),
then encrypts and sends to Backblaze B2 (25 Nov 2026). Those are named backup-...-nightly.zip; the server keeps the
last seven of them. Backups made with the button stay until the admin deletes them.
"""
import csv
import io
import json
import logging
import os
import re
import shutil
import tempfile
import threading
import zipfile
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core.files import File
from django.core.files.storage import FileSystemStorage, default_storage
from django.core.management import call_command
from django.db import close_old_connections, connection, models
from django.db.models import signals as model_signals
from django.utils import timezone

logger = logging.getLogger(__name__)

# Not data: sessions and login tokens, Django's bookkeeping, and the backup list itself.
EXCLUDED_MODELS = [
    'contenttypes.contenttype', 'auth.permission', 'sessions.session', 'admin.logentry',
    'authtoken.token', 'core.usertoken', 'core.usersession', 'core.systembackup',
]
EXCLUDED_APPS = ['django_celery_beat']
# Folders under MEDIA_ROOT that are rebuilt from the documents, files that are logs or crash dumps, and CVs waiting to
# be read (recruitment_agent/cv_batches.py: each is kept in cvs/ once it is read).
SKIPPED_MEDIA_DIRS = {'hr_vector_indexes', 'operations_vector_indexes', 'backups', 'cv_batches'}
SKIPPED_SUFFIXES = ('.log', '.dmp', '.mdmp', '.tmp', '.pyc', '.part')

# A backup still "running" after this long died with the process that ran it (a restart or a deploy).
STALE_AFTER = timedelta(hours=6)
NIGHTLY_SUFFIX = '-nightly.zip'


def backup_root() -> Path:
    return Path(settings.BACKUP_ROOT)


def backup_path(backup) -> Path:
    # Only the name: a file_name in the database never reaches outside the backups folder.
    return backup_root() / Path(backup.file_name).name


def fail_stale_backups():
    """A backup whose thread died (the server restarted) would show "Running" for ever and block the next one."""
    from core.models import SystemBackup
    SystemBackup.objects.filter(status='running', created_at__lt=timezone.now() - STALE_AFTER).update(
        status='failed', error='Stopped before it finished (the server restarted). Make a new one.',
        finished_at=timezone.now())


def start_backup(user):
    """Create the backup's row and build the zip in the background. ValueError when one is already running."""
    from core.models import SystemBackup
    fail_stale_backups()
    if SystemBackup.objects.filter(status='running').exists():
        raise ValueError('A backup is already being made. Wait for it to finish.')
    backup = SystemBackup.objects.create(
        created_by=user, file_name=f"backup-{timezone.now():%Y%m%d-%H%M%S}.zip")
    threading.Thread(target=run_backup, args=(backup.pk,), name=f'system-backup-{backup.pk}', daemon=True).start()
    return backup


def is_nightly(backup) -> bool:
    return (backup.file_name or '').endswith(NIGHTLY_SUFFIX)


def make_nightly_backup(keep: int = 7):
    """The nightly backup (manage.py make_backup): made here and now, not on a thread, so the script that runs it can
    send the zip on once this returns. When it is done, nightly backups past the newest `keep` are deleted. Returns the
    backup, done or failed; ValueError when another one is being made."""
    from core.models import SystemBackup
    fail_stale_backups()
    if SystemBackup.objects.filter(status='running').exists():
        raise ValueError('A backup is already being made. Wait for it to finish.')
    backup = SystemBackup.objects.create(
        created_by=None, file_name=f"backup-{timezone.now():%Y%m%d-%H%M%S}{NIGHTLY_SUFFIX}")
    run_backup(backup.pk)
    backup.refresh_from_db()
    if backup.status == 'done':
        prune_nightly(keep)
    return backup


def prune_nightly(keep: int):
    """Keep the newest `keep` finished nightly backups and delete the older ones, with any nightly failure older than
    the oldest one kept. Backups made with the button are never touched."""
    from core.models import SystemBackup
    nightly = list(SystemBackup.objects.filter(file_name__endswith=NIGHTLY_SUFFIX).exclude(status='running')
                   .order_by('-created_at', '-pk'))
    kept = [b for b in nightly if b.status == 'done'][:max(keep, 1)]
    if not kept:
        return 0
    oldest_kept = kept[-1].created_at
    gone = [b for b in nightly if b not in kept and (b.status == 'done' or b.created_at < oldest_kept)]
    for backup in gone:
        backup_path(backup).unlink(missing_ok=True)
        backup.delete()
    return len(gone)


def _included_models():
    excluded = set(EXCLUDED_MODELS)
    return [m for m in apps.get_models()
            if m._meta.app_label not in EXCLUDED_APPS and m._meta.label_lower not in excluded
            and not m._meta.proxy and m._meta.managed]


def _media_files():
    """(path on disk, name in the zip) for every uploaded file worth keeping."""
    root = Path(settings.MEDIA_ROOT)
    if not root.is_dir():
        return
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root)
        if rel_dir == Path('.'):
            dirnames[:] = [d for d in dirnames if d not in SKIPPED_MEDIA_DIRS]
        for name in filenames:
            if name.lower().endswith(SKIPPED_SUFFIXES):
                continue
            rel = (rel_dir / name).as_posix()
            yield Path(dirpath) / name, f'media/{rel}'


def _stored_file_names():
    """The names in every FileField: with S3 on, uploads live in the bucket, not in MEDIA_ROOT."""
    for model in _included_models():
        fields = [f.name for f in model._meta.get_fields() if isinstance(f, models.FileField)]
        for field in fields:
            for name in model._base_manager.exclude(**{field: ''}).exclude(
                    **{f'{field}__isnull': True}).values_list(field, flat=True).iterator():
                yield name


SDR_LEAD_COLUMNS = [
    'id', 'full_name', 'first_name', 'last_name', 'email', 'phone', 'job_title', 'seniority_level', 'department',
    'company_name', 'company_domain', 'company_industry', 'company_size_range', 'company_location',
    'company_website', 'linkedin_url', 'company_linkedin_url', 'score', 'temperature', 'status', 'source',
    'qualification_status', 'enrichment_status', 'email_bounced', 'buying_signals', 'created_at', 'updated_at',
    'is_deleted',
]
MARKETING_LEAD_COLUMNS = [
    'id', 'email', 'first_name', 'last_name', 'phone', 'company', 'job_title', 'status', 'source', 'notes',
    'created_at', 'updated_at',
]
NO_COMPANY_FOLDER = '0-no-company'


def _cell(value):
    """One CSV cell. Lists read as "a; b"; a cell Excel would run as a formula (lead data is scraped from the web)
    is kept as text."""
    if value is None:
        return ''
    if isinstance(value, (list, tuple)):
        value = '; '.join(str(v) for v in value)
    elif isinstance(value, dict):
        value = json.dumps(value, ensure_ascii=False)
    elif hasattr(value, 'isoformat'):
        value = value.isoformat()
    value = str(value)
    return "'" + value if value[:1] in ('=', '+', '-', '@', '\t', '\r') else value


def _company_folders():
    """{company id: folder name} for every company, e.g. 65 -> '65-laskon-technologies'."""
    from core.models import Company
    folders = {}
    for pk, name in Company._base_manager.values_list('pk', 'name').iterator():
        slug = re.sub(r'[^a-z0-9]+', '-', (name or '').lower()).strip('-')[:50]
        folders[pk] = f'{pk}-{slug}' if slug else str(pk)
    return folders


def _write_csv(zf, arcname, header, rows):
    """Stream rows into the zip as a CSV Excel opens as UTF-8; returns how many went in."""
    count = 0
    with zf.open(arcname, 'w', force_zip64=True) as raw:
        out = io.TextIOWrapper(raw, encoding='utf-8-sig', newline='')
        writer = csv.writer(out)
        writer.writerow(header)
        for row in rows:
            writer.writerow([_cell(v) for v in row])
            count += 1
        out.flush()
        out.detach()
    return count


def _lead_exports():
    """(file name, header, {company folder: [rows]}) for each kind of lead. A kind whose app is not installed is
    skipped."""
    folders = _company_folders()

    try:
        SDRLead = apps.get_model('ai_sdr_agent', 'SDRLead')
    except LookupError:
        SDRLead = None
    if SDRLead is not None:
        by_company = {}
        for row in SDRLead._base_manager.order_by('pk').values_list(
                'company_user__company_id', 'company_user__email', *SDR_LEAD_COLUMNS).iterator():
            company_id, added_by, values = row[0], row[1], row[2:]
            by_company.setdefault(folders.get(company_id, NO_COMPANY_FOLDER), []).append([*values, added_by])
        yield 'sdr_leads.csv', SDR_LEAD_COLUMNS + ['added_by'], by_company

    try:
        Lead = apps.get_model('marketing_agent', 'Lead')
        CampaignLead = apps.get_model('marketing_agent', 'CampaignLead')
    except LookupError:
        Lead = None
    if Lead is not None:
        # A marketing lead belongs to a login (auth.User); its company is the dashboard login that acts as it.
        from core.models import CompanyUser
        user_company = {}
        for user_id, company_id in CompanyUser._base_manager.filter(login_user__isnull=False).order_by(
                'pk').values_list('login_user_id', 'company_id').iterator():
            user_company.setdefault(user_id, company_id)
        campaigns = {}
        for lead_id, name in CampaignLead._base_manager.order_by('pk').values_list(
                'lead_id', 'campaign__name').iterator():
            campaigns.setdefault(lead_id, []).append(name)
        by_company = {}
        for row in Lead._base_manager.order_by('pk').values_list(
                'owner_id', 'owner__email', *MARKETING_LEAD_COLUMNS).iterator():
            owner_id, owner_email, values = row[0], row[1], row[2:]
            folder = folders.get(user_company.get(owner_id), NO_COMPANY_FOLDER)
            by_company.setdefault(folder, []).append([*values, campaigns.get(values[0], []), owner_email])
        yield 'marketing_leads.csv', MARKETING_LEAD_COLUMNS + ['campaigns', 'owner'], by_company


def build_zip(path: Path, created_by: str = '') -> dict:
    """Write the backup to `path`; returns what went in."""
    counts = {m._meta.label_lower: m._base_manager.count() for m in _included_models()}
    summary = {'records': sum(counts.values()), 'files': 0, 'models': {k: v for k, v in counts.items() if v}}

    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        # dumpdata writes to a stream: straight into the zip, so a big database never sits in memory.
        with zf.open('database.json', 'w', force_zip64=True) as raw:
            out = io.TextIOWrapper(raw, encoding='utf-8')
            call_command('dumpdata', exclude=EXCLUDED_APPS + EXCLUDED_MODELS, natural_foreign=True,
                         use_base_manager=True, verbosity=0, stdout=out)
            out.flush()
            out.detach()

        added = set()
        for disk_path, arcname in _media_files():
            zf.write(disk_path, arcname)
            added.add(arcname)
        if not isinstance(default_storage, FileSystemStorage):
            for name in _stored_file_names():
                arcname = f'media/{name}'
                if arcname in added:
                    continue
                try:
                    with default_storage.open(name, 'rb') as src, zf.open(arcname, 'w', force_zip64=True) as dst:
                        shutil.copyfileobj(src, dst)
                    added.add(arcname)
                except Exception as exc:  # noqa: BLE001 - one missing upload must not lose the whole backup
                    logger.warning('Backup: could not read uploaded file %s: %s', name, exc)
        summary['files'] = len(added)

        exports = {}
        for file_name, header, by_company in _lead_exports():
            for folder, rows in sorted(by_company.items()):
                exports.setdefault(folder, {})[file_name] = _write_csv(
                    zf, f'exports/{folder}/{file_name}', header, rows)
        summary['exported_leads'] = sum(n for files in exports.values() for n in files.values())

        zf.writestr('manifest.json', json.dumps({
            'created_at': timezone.now().isoformat(),
            'created_by': created_by,
            'database_engine': connection.vendor,
            'records': summary['records'],
            'files': summary['files'],
            'models': summary['models'],
            'exports': exports,
            'left_out': {'models': EXCLUDED_MODELS, 'apps': EXCLUDED_APPS, 'media_folders': sorted(SKIPPED_MEDIA_DIRS)},
            'restore': ('On a new server, after migrate: manage.py restore_backup <this zip>. It loads the database '
                        'and puts media/ back (exports/ is for reading only and is not loaded). Not plain loaddata: '
                        'the app\'s save hooks would run during the load, fail on rows not loaded yet and change '
                        'others. Stored API keys and secrets only decrypt with the same FIELD_ENCRYPTION_KEY (or '
                        'SECRET_KEY) as the server the backup came from.'),
        }, indent=2))
    return summary


def run_backup(backup_id):
    from core.models import SystemBackup
    backup = SystemBackup.objects.select_related('created_by').get(pk=backup_id)
    final = backup_path(backup)
    part = final.with_name(final.name + '.part')
    try:
        backup_root().mkdir(parents=True, exist_ok=True)
        summary = build_zip(part, created_by=backup.created_by.username if backup.created_by else '')
        os.replace(part, final)
        backup.status, backup.summary, backup.size_bytes = 'done', summary, final.stat().st_size
    except Exception as exc:  # noqa: BLE001 - shown to the admin on the backup's row
        logger.exception('System backup %s failed', backup_id)
        part.unlink(missing_ok=True)
        backup.status, backup.error = 'failed', str(exc) or type(exc).__name__
    backup.finished_at = timezone.now()
    backup.save(update_fields=['status', 'summary', 'size_bytes', 'error', 'finished_at'])
    close_old_connections()


# ---- Restore (manage.py restore_backup) ------------------------------------------------------------------------
# Tried on the live backup of 24 Nov 2026: plain `loaddata database.json` stopped on the first Reply, whose save hook
# moves its lead on before the leads were loaded. The app has dozens of such hooks (a new login gets a profile, a
# reply moves a lead, a document is queued for reading). A backup is the database as it already was, so they are off
# while it loads: run again they fail on rows not loaded yet, or change the data being put back.
MUTED_SIGNALS = (model_signals.pre_save, model_signals.post_save, model_signals.m2m_changed,
                 model_signals.pre_delete, model_signals.post_delete)


class RestoreError(Exception):
    """A restore refused before anything was changed."""


def _no_receivers(*args, **kwargs):
    return []


@contextmanager
def model_hooks_off():
    for signal in MUTED_SIGNALS:
        signal.send = _no_receivers
    try:
        yield
    finally:
        for signal in MUTED_SIGNALS:
            del signal.send          # back to Signal.send


def database_is_new() -> bool:
    """No logins and no companies: a server just set up, never one in use."""
    from django.contrib.auth.models import User
    from core.models import Company, CompanyUser
    return not (User.objects.exists() or Company.objects.exists() or CompanyUser.objects.exists())


def restore(zip_path, media=True) -> dict:
    """Put a backup back into this server's database, which must be new (migrated, no logins, no companies), and its
    uploaded files back where the database expects them. Returns {'records': n, 'files': n}.

    The database is emptied first: migrations add starter rows (the agent plans, prices) that would clash with the
    backup's own. Then everything loads in one transaction with the save hooks off, so a failure leaves it empty."""
    zip_path = Path(zip_path)
    if not zip_path.is_file():
        raise RestoreError(f'No file at {zip_path}.')
    if not database_is_new():
        raise RestoreError('This database already has logins or companies. A backup goes into a new, migrated, empty '
                           'database; it never merges into one in use. Nothing was changed.')
    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        if not {'database.json', 'manifest.json'} <= names:
            raise RestoreError('This is not a backup from Admin → Backups: it has no database.json and manifest.json.')
        damaged = zf.testzip()
        if damaged:
            raise RestoreError(f'The zip is damaged: {damaged} does not match its checksum. Nothing was changed.')
        manifest = json.loads(zf.read('manifest.json'))
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / 'database.json'
            with zf.open('database.json') as src, open(fixture, 'wb') as dst:
                shutil.copyfileobj(src, dst)
            call_command('flush', interactive=False, verbosity=0)   # also puts back content types and permissions
            with model_hooks_off():
                call_command('loaddata', str(fixture), verbosity=0)
        files = _restore_media(zf, names) if media else 0
    return {'records': manifest.get('records'), 'files': files}


def _restore_media(zf, names) -> int:
    """Each media/ file back under MEDIA_ROOT, as build_zip found it. When uploads live in other storage (S3), the
    ones the database points at go there too, where the app reads them."""
    root = Path(settings.MEDIA_ROOT).resolve()
    remote = not isinstance(default_storage, FileSystemStorage)
    wanted = set(_stored_file_names()) if remote else set()
    count = 0
    for name in sorted(n for n in names if n.startswith('media/') and not n.endswith('/')):
        rel = name[len('media/'):]
        target = (root / rel).resolve()
        if root not in target.parents:
            logger.warning('Restore: left out %s, which points outside MEDIA_ROOT', name)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(name) as src, open(target, 'wb') as dst:
            shutil.copyfileobj(src, dst)
        if rel in wanted and not default_storage.exists(rel):
            with open(target, 'rb') as fh:
                default_storage.save(rel, File(fh, name=rel))
        count += 1
    return count
