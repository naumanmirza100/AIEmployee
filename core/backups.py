"""Whole-system backups for the super admin: one zip with every company's data, the platform's own, and the
uploaded files.

What is in the zip:
  database.json  every row of every app (dumpdata, whatever the engine: SQLite, SQL Server or MariaDB). Loads back
                 with `manage.py loaddata database.json` into a migrated, empty database.
  media/...      the uploaded files (CVs, HR and Frontline documents, attachments, analyst sources...). The
                 database only holds their paths, so a backup without them would point at nothing.
  manifest.json  when, by whom, from which database, and how many rows and files went in.

What is left out, as not data: login sessions and tokens, Django's own bookkeeping (content types, permissions, the
admin's log), the Celery schedule, the search indexes (rebuilt from the documents), logs and crash dumps, and the
backups themselves.

A backup runs in a thread of the web process, so it neither waits on a Celery worker nor holds up the request.
"""
import io
import json
import logging
import os
import shutil
import threading
import zipfile
from datetime import timedelta
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core.files.storage import FileSystemStorage, default_storage
from django.core.management import call_command
from django.db import close_old_connections, connection, models
from django.utils import timezone

logger = logging.getLogger(__name__)

# Not data: sessions and login tokens, Django's bookkeeping, and the backup list itself.
EXCLUDED_MODELS = [
    'contenttypes.contenttype', 'auth.permission', 'sessions.session', 'admin.logentry',
    'authtoken.token', 'core.usertoken', 'core.usersession', 'core.systembackup',
]
EXCLUDED_APPS = ['django_celery_beat']
# Folders under MEDIA_ROOT that are rebuilt from the documents, and files that are logs or crash dumps.
SKIPPED_MEDIA_DIRS = {'hr_vector_indexes', 'operations_vector_indexes', 'backups'}
SKIPPED_SUFFIXES = ('.log', '.dmp', '.mdmp', '.tmp', '.pyc', '.part')

# A backup still "running" after this long died with the process that ran it (a restart or a deploy).
STALE_AFTER = timedelta(hours=6)


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

        zf.writestr('manifest.json', json.dumps({
            'created_at': timezone.now().isoformat(),
            'created_by': created_by,
            'database_engine': connection.vendor,
            'records': summary['records'],
            'files': summary['files'],
            'models': summary['models'],
            'left_out': {'models': EXCLUDED_MODELS, 'apps': EXCLUDED_APPS, 'media_folders': sorted(SKIPPED_MEDIA_DIRS)},
            'restore': ('Into a new, migrated database: manage.py loaddata database.json, then copy media/ into '
                        'MEDIA_ROOT. Stored API keys and secrets only decrypt with the same FIELD_ENCRYPTION_KEY '
                        '(or SECRET_KEY) as the server the backup came from.'),
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
