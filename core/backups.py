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

One company's backup (Company dashboard → Backups, 27 Nov 2026) is the same zip for that company alone: its rows
(company_querysets: every table, by the links that lead from it to the company), the files those rows point at, and
its leads as CSVs. Passwords, API keys and sign-in tokens are left out (COMPANY_SECRET_FIELDS), since any owner or
admin of the company can download it. It is the company's copy to keep and read; restore_backup does not load one,
as it puts back a whole server. Each company's is also made every night by `manage.py make_company_backups`, which
scripts/ppp-full-backup.sh runs right after the whole-system one (21:00 UTC, 02:00 in Pakistan), then encrypts and
sends to Backblaze B2 (companies/<company id>/), as it does the whole-system one. The server keeps the newest seven
nightly ones of each company, in BACKUP_ROOT/companies/<company id>/.
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
from django.core.serializers.json import Serializer as JSONSerializer
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
    if backup.company_id:
        return backup_root() / 'companies' / str(backup.company_id) / Path(backup.file_name).name
    return backup_root() / Path(backup.file_name).name


def fail_stale_backups():
    """A backup whose thread died (the server restarted) would show "Running" for ever and block the next one."""
    from core.models import SystemBackup
    SystemBackup.objects.filter(status='running', created_at__lt=timezone.now() - STALE_AFTER).update(
        status='failed', error='Stopped before it finished (the server restarted). Make a new one.',
        finished_at=timezone.now())


def _new_backup(company=None, suffix='.zip', **who):
    """The row for a new backup, whole-system (no company) or one company's. ValueError when one of the same kind is
    already being made: one at a time for the system, and one at a time for each company."""
    from core.models import SystemBackup
    fail_stale_backups()
    if SystemBackup.objects.filter(status='running', company=company).exists():
        raise ValueError('A backup is already being made. Wait for it to finish.')
    return SystemBackup.objects.create(
        company=company, file_name=f"backup-{timezone.now():%Y%m%d-%H%M%S}{suffix}", **who)


def start_backup(user, company=None, company_user=None):
    """Create the backup's row and build the zip in the background. ValueError when one is already running.
    With a company, it is that company's backup, made by `company_user` (one of its dashboard logins)."""
    backup = _new_backup(company, created_by=user, company_user=company_user)
    threading.Thread(target=run_backup, args=(backup.pk,), name=f'system-backup-{backup.pk}', daemon=True).start()
    return backup


def is_nightly(backup) -> bool:
    return (backup.file_name or '').endswith(NIGHTLY_SUFFIX)


def make_nightly_backup(keep: int = 7, company=None):
    """The nightly backup (manage.py make_backup, or one company's from make_company_backups): made here and
    now, not on a thread, so the script that runs it can send the zip on once this returns. When it is done, nightly
    backups (of the same company, or the system's) past the newest `keep` are deleted. Returns the backup, done or
    failed; ValueError when another one is being made."""
    backup = _new_backup(company, suffix=NIGHTLY_SUFFIX, created_by=None)
    run_backup(backup.pk)
    backup.refresh_from_db()
    if backup.status == 'done':
        prune_nightly(keep, company=company)
    return backup


def make_nightly_company_backups(keep: int = 7):
    """Each active company's nightly backup, one after another (manage.py make_company_backups, which the nightly
    script runs after the whole-system one). Returns [(company, backup or None, error)]: a company whose backup fails,
    or is already being made, does not stop the others, and keeps its older nightly ones until one succeeds."""
    from core.models import Company
    results = []
    for company in Company.objects.filter(is_active=True).order_by('pk').iterator():
        try:
            backup = make_nightly_backup(keep=keep, company=company)
        except Exception as exc:  # noqa: BLE001 - one company must not stop the others
            logger.exception('Company %s nightly backup failed', company.pk)
            results.append((company, None, str(exc) or type(exc).__name__))
            continue
        results.append((company, backup, '' if backup.status == 'done' else backup.error))
    return results


def prune_nightly(keep: int, company=None):
    """Keep the newest `keep` finished nightly backups and delete the older ones, with any nightly failure older than
    the oldest one kept. Backups made with the button are never touched. With a company, only that company's."""
    from core.models import SystemBackup
    nightly = list(SystemBackup.objects.filter(file_name__endswith=NIGHTLY_SUFFIX, company=company)
                   .exclude(status='running').order_by('-created_at', '-pk'))
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


def _lead_exports(company_id=None):
    """(file name, header, {company folder: [rows]}) for each kind of lead. A kind whose app is not installed is
    skipped. With a company, only its leads."""
    folders = _company_folders()

    try:
        SDRLead = apps.get_model('ai_sdr_agent', 'SDRLead')
    except LookupError:
        SDRLead = None
    if SDRLead is not None:
        by_company = {}
        sdr_leads = SDRLead._base_manager.all()
        if company_id is not None:
            sdr_leads = sdr_leads.filter(company_user__company_id=company_id)
        for row in sdr_leads.order_by('pk').values_list(
                'company_user__company_id', 'company_user__email', *SDR_LEAD_COLUMNS).iterator():
            lead_company, added_by, values = row[0], row[1], row[2:]
            by_company.setdefault(folders.get(lead_company, NO_COMPANY_FOLDER), []).append([*values, added_by])
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
        for user_id, owner_company in CompanyUser._base_manager.filter(login_user__isnull=False).order_by(
                'pk').values_list('login_user_id', 'company_id').iterator():
            user_company.setdefault(user_id, owner_company)
        leads, links = Lead._base_manager.all(), CampaignLead._base_manager.all()
        if company_id is not None:
            owners = [u for u, c in user_company.items() if c == company_id]
            leads, links = leads.filter(owner_id__in=owners), links.filter(lead__owner_id__in=owners)
        campaigns = {}
        for lead_id, name in links.order_by('pk').values_list('lead_id', 'campaign__name').iterator():
            campaigns.setdefault(lead_id, []).append(name)
        by_company = {}
        for row in leads.order_by('pk').values_list(
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


# ---- One company's backup ---------------------------------------------------------------------------------------
# On top of EXCLUDED_MODELS: the company's sign-in tokens, and the platform's own settings a company login reaches.
COMPANY_EXCLUDED_MODELS = {
    'core.companyusertoken', 'core.companyregistrationtoken', 'core.platformapikey', 'core.adminpricingconfig',
}
# Any owner or admin of the company can download its backup, so what would let someone sign in or act as the
# company is left out: passwords, API keys, mailbox and CRM credentials, and the links sent to candidates and
# customers. Fields of an Encrypted...Field type are left out wherever they are.
COMPANY_SECRET_FIELDS = {
    'auth.user': {'password'},
    'core.companyuser': {'password_hash', 'reset_otp', 'reset_otp_expires', 'reset_otp_attempts'},
    'core.userverification': {'token'},
    'core.companyapikey': {'encrypted_key'},
    'core.personalcalendar': {'refresh_token'},
    'marketing_agent.emailaccount': {'smtp_password', 'imap_password'},
    'marketing_agent.emailsendhistory': {'tracking_token'},
    'ai_sdr_agent.sdrcampaign': {'smtp_password'},
    'ai_sdr_agent.sdragentsettings': {'apollo_api_key', 'apify_api_token'},
    'ai_sdr_agent.sdrmeeting': {'booking_token', 'approval_token'},
    'crm_sync_agent.crmintegration': {'credentials'},
    'data_analyst_agent.datasource': {'password_encrypted'},
    'recruitment_agent.jobapplication': {'access_token'},
    'recruitment_agent.interview': {'confirmation_token'},
    'recruitment_agent.careerapplication': {'application_token'},
    'Frontline_agent.ticketsatisfaction': {'token'},
}


# Uploads whose place is kept in a text field rather than a FileField: a path under MEDIA_ROOT (most are relative to
# it, some written as the full path), or the file's key in S3. The whole-system backup takes all of MEDIA_ROOT, so
# only a company's backup needs to know these.
COMPANY_PATH_FIELDS = {
    'core.projectdocument': ['file_path'],
    'core.taskattachment': ['file_path'],
    'core.commentattachment': ['file_path'],
    'recruitment_agent.cvrecord': ['s3_key'],
    'recruitment_agent.careerapplication': ['resume_path'],
    'marketing_agent.marketingdocument': ['file_path'],
    'Frontline_agent.document': ['file_path'],
    'Frontline_agent.ticketattachment': ['storage_path'],
    'hr_agent.hrdocument': ['file_path'],
    'data_analyst_agent.datasource': ['file_path'],
}


def _file_fields(model):
    names = [f.name for f in model._meta.concrete_fields if isinstance(f, models.FileField)]
    return names + [n for n in COMPANY_PATH_FIELDS.get(model._meta.label_lower, []) if n not in names]


def _media_name(value, media_root: Path):
    """The file's name under MEDIA_ROOT (as in the zip's media/), or None for a path outside it."""
    value = str(value or '').strip().replace('\\', '/')
    if not value:
        return None
    path = Path(value)
    if path.is_absolute() or (len(value) > 1 and value[1] == ':'):
        try:
            value = path.resolve().relative_to(media_root).as_posix()
        except (ValueError, OSError):
            return None
    value = value.lstrip('/')
    return None if '..' in Path(value).parts else value


def _is_secret(model, field) -> bool:
    return (field.name in COMPANY_SECRET_FIELDS.get(model._meta.label_lower, ())
            or type(field).__name__.startswith('Encrypted'))


def company_querysets(company_id):
    """[(model, queryset of the company's rows)] for every table that leads to the company.

    A table belongs to it through its foreign keys, one step at a time: the company, then each table with a key to
    it (its logins, tickets, employees...), then each table with a key to one of those (a ticket's messages), and
    so on. A row is the company's when any of its keys points at a row already found to be. Only then the logins
    (auth.User) of the company, its dashboard logins and its employees, are a way in, for the tables that have no
    other (Marketing, whose campaigns and leads belong to a login): a key to a login is the weakest link, as a
    person can be in two companies. Querysets, not lists of ids, so no database's limit on parameters is reached."""
    from django.contrib.auth.models import User
    from django.db.models import Q
    from core.models import Company, CompanyUser, UserProfile

    skip = set(EXCLUDED_MODELS) | COMPANY_EXCLUDED_MODELS
    candidates = [m for m in _included_models() if m._meta.label_lower not in skip]
    found = {Company: Company._base_manager.filter(pk=company_id)}
    pending = [m for m in candidates if m is not Company and m is not User]

    def keys(model):
        return [f for f in model._meta.concrete_fields
                if f.is_relation and (f.many_to_one or f.one_to_one) and f.related_model not in (None, model)]

    users_added = False
    while pending:
        # One step: what has a key to a table found in an earlier step (never this one, so no loop).
        reached = {}
        for model in pending:
            links = [f for f in keys(model) if f.related_model in found]
            if links:
                q = Q()
                for f in links:
                    q |= Q(**{f'{f.attname}__in': found[f.related_model].values(f.target_field.attname)})
                reached[model] = model._base_manager.filter(q)
        if not reached:
            if users_added:
                break
            found[User] = User._base_manager.filter(
                Q(pk__in=CompanyUser._base_manager.filter(company_id=company_id, login_user__isnull=False)
                  .values('login_user_id'))
                | Q(pk__in=UserProfile._base_manager.filter(company_id=company_id).values('user_id')))
            users_added = True
            continue
        found.update(reached)
        pending = [m for m in pending if m not in reached]
    return [(m, found[m]) for m in candidates if m in found]


class _CompanySerializer(JSONSerializer):
    """Django's JSON serializer, leaving out the secret fields (COMPANY_SECRET_FIELDS)."""

    def handle_field(self, obj, field):
        if not _is_secret(type(obj), field):
            super().handle_field(obj, field)


def build_company_zip(path: Path, company, created_by: str = '') -> dict:
    """Write one company's backup to `path`; returns what went in."""
    scope = company_querysets(company.pk)
    counts = {}

    def rows():
        for model, qs in scope:
            label = model._meta.label_lower
            for obj in qs.order_by('pk').iterator():
                counts[label] = counts.get(label, 0) + 1
                yield obj

    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        with zf.open('database.json', 'w', force_zip64=True) as raw:
            out = io.TextIOWrapper(raw, encoding='utf-8')
            _CompanySerializer().serialize(rows(), stream=out, use_natural_foreign_keys=True, indent=None)
            out.flush()
            out.detach()

        # The company's uploads are the files its rows point at, wherever they are stored.
        added = set()
        media_root = Path(settings.MEDIA_ROOT).resolve()
        for model, qs in scope:
            for field in _file_fields(model):
                for value in qs.exclude(**{field: ''}).exclude(**{f'{field}__isnull': True}).values_list(
                        field, flat=True).iterator():
                    name = _media_name(value, media_root)
                    arcname = f'media/{name}'
                    if not name or arcname in added or name.split('/', 1)[0] in SKIPPED_MEDIA_DIRS:
                        continue
                    try:
                        local = media_root / name
                        src = open(local, 'rb') if local.is_file() else default_storage.open(name, 'rb')
                        with src, zf.open(arcname, 'w', force_zip64=True) as dst:
                            shutil.copyfileobj(src, dst)
                        added.add(arcname)
                    except Exception as exc:  # noqa: BLE001 - one missing upload must not lose the whole backup
                        logger.warning('Company %s backup: could not read uploaded file %s: %s', company.pk, name, exc)

        exports = {}
        folder = _company_folders().get(company.pk)
        for file_name, header, by_company in _lead_exports(company_id=company.pk):
            exports[file_name] = _write_csv(zf, f'exports/{file_name}', header, by_company.get(folder, []))

        summary = {'records': sum(counts.values()), 'files': len(added),
                   'models': {k: v for k, v in sorted(counts.items())},
                   'exported_leads': sum(exports.values())}
        zf.writestr('manifest.json', json.dumps({
            'kind': 'company',
            'company': {'id': company.pk, 'name': company.name},
            'created_at': timezone.now().isoformat(),
            'created_by': created_by,
            'records': summary['records'],
            'files': summary['files'],
            'models': summary['models'],
            'exports': exports,
            'left_out': {
                'models': sorted(set(EXCLUDED_MODELS) | COMPANY_EXCLUDED_MODELS),
                'fields': {k: sorted(v) for k, v in sorted(COMPANY_SECRET_FIELDS.items())},
                'note': 'Passwords, API keys, mailbox and CRM credentials and sign-in links are not in this backup.',
            },
            'about': ('This company\'s data on its own, to keep and to read: database.json has its rows, media/ the '
                      'files they point at, and exports/ its leads as CSVs that open in Excel. It is not loaded '
                      'with restore_backup, which puts back a whole server from the super admin\'s backups.'),
        }, indent=2))
    return summary


def run_backup(backup_id):
    from core.models import SystemBackup
    backup = SystemBackup.objects.select_related('created_by', 'company', 'company_user').get(pk=backup_id)
    final = backup_path(backup)
    part = final.with_name(final.name + '.part')
    try:
        final.parent.mkdir(parents=True, exist_ok=True)
        if backup.company_id:
            who = backup.company_user.email if backup.company_user else ''
            summary = build_company_zip(part, backup.company, created_by=who)
        else:
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
    with zipfile.ZipFile(zip_path) as zf:
        if 'manifest.json' in zf.namelist() and json.loads(zf.read('manifest.json')).get('kind') == 'company':
            raise RestoreError('This is one company\'s backup (Company dashboard → Backups), with its passwords and '
                               'keys left out. restore_backup puts back a whole server, from a backup in Admin → '
                               'Backups. Nothing was changed.')
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
