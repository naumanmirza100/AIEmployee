"""Test data for the platform (27 Nov 2026).

The super admin's Test data page adds and removes two demo companies:
  * Margalla Software, the company the per-agent demo videos were made with, built up on the live site;
  * Crestline Technologies, the company the client showcase was given with.

Each is kept as a snapshot: every row that belongs to the company (what the database deletes with it, plus the PM
projects, job adverts, applications and profiles that only point at it, and the employee logins), serialized,
compressed and stored in DemoSnapshot. Secrets are never kept: passwords, mailbox and CRM credentials and API keys
are blanked when the snapshot is made, and loading sets one new password per company, shown on the page.

Loading moves every date forward by the time since the snapshot was taken, so the demo looks current, and leaves the
demo's mailboxes, CRM connections and campaigns switched off, so nothing is emailed or synced from it.

`sweep()` clears every customer's data, keeping the super admins and the platform's own setup (PLATFORM_MODELS).
"""
from __future__ import annotations

import json
import secrets
import string
import zlib
from datetime import timedelta

from django.apps import apps
from django.contrib.admin.utils import NestedObjects
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core import serializers
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection, models, transaction
from django.utils import timezone

#: The platform's own setup and the public site's content: kept by the sweep, never part of a company.
PLATFORM_MODELS = {
    'auth.permission', 'auth.group', 'auth.group_permissions', 'contenttypes.contenttype', 'sessions.session',
    'admin.logentry', 'core.agent', 'core.agentplan', 'core.adminpricingconfig', 'core.platformapikey',
    'core.sentalert', 'core.stripewebhookevent', 'core.systembackup', 'core.demosnapshot', 'core.demodatarun',
    # The public site: blog, FAQ, industries, plans, and the platform's email templates.
    'core.blogpost', 'core.blogtag', 'core.blogposttag', 'core.faq', 'core.industry', 'core.industrychallenge',
    'core.pricingplan', 'core.emailtemplate',
    # What visitors sent through the public site (messages, complaints, the cost estimator, the quiz): possible
    # customers, so the sweep leaves them for the admins to deal with.
    'core.contactmessage', 'core.complaint', 'core.aipredictorsubmission', 'core.quizresponse',
}
PLATFORM_APPS = {'django_celery_beat', 'django_celery_results'}
#: Rows of these belong to a login; a super admin's are kept.
SUPERUSER_OWNED = {'auth.user', 'auth.user_groups', 'auth.user_user_permissions', 'core.userprofile',
                   'authtoken.token', 'core.usertoken', 'core.notification'}
#: Never in a snapshot: sign-in sessions and one-off links.
NOT_SNAPSHOTTED = {'core.companyusertoken', 'authtoken.token', 'core.usertoken', 'core.companyregistrationtoken',
                   'ai_sdr_agent.sdrjoblock', 'sessions.session'}
#: A field holding a secret is blanked in a snapshot (names, lower case, exact or by these markers).
SECRET_MARKERS = ('password', 'passwd', 'secret', 'api_key', 'apikey', 'credential', 'private_key',
                  'refresh_token', 'encrypted')
SECRET_KEEP = {'is_gmail_app_password'}


def _user_model():
    return get_user_model()


# ---------------------------------------------------------------------------------------------------------------- #
# What belongs to a company
# ---------------------------------------------------------------------------------------------------------------- #

def _flatten(nested, out):
    for item in nested:
        if isinstance(item, list):
            _flatten(item, out)
        else:
            out.append(item)


def _is_platform(model) -> bool:
    return model._meta.label_lower in PLATFORM_MODELS or model._meta.app_label in PLATFORM_APPS


def _collect(objs, into: dict) -> None:
    """Add `objs` (one model) and everything the database would delete with them (never the platform's rows)."""
    objs = list(objs)
    if not objs:
        return
    collector = NestedObjects(using='default')
    collector.collect(objs)
    flat = []
    _flatten(collector.nested(), flat)
    for o in flat:
        if not _is_platform(type(o)):
            into[(o._meta.label_lower, o.pk)] = o


def _company_field(model):
    """The model's link to a company (a foreign key, or a bare company_id number), or None."""
    from core.models import Company
    for f in model._meta.concrete_fields:
        if (f.is_relation and f.related_model is Company) or (f.name == 'company_id' and not f.is_relation):
            return f
    return None


def _not_elsewhere(model, pks, company) -> set:
    """Of `pks`, the rows that don't belong to another company (a row of company B is never company A's)."""
    from core.models import Company, UserProfile
    pks = set(pks)
    if model is Company:
        return pks & {company.pk}
    if model is _user_model():
        elsewhere = UserProfile._base_manager.filter(user_id__in=pks, company_id__isnull=False) \
            .exclude(company_id=company.pk).values_list('user_id', flat=True)
        superusers = model._base_manager.filter(pk__in=pks, is_superuser=True).values_list('pk', flat=True)
        return pks - set(elsewhere) - set(superusers)
    field = _company_field(model)
    if field is None:
        return pks
    elsewhere = model._base_manager.filter(pk__in=pks, **{f'{field.attname}__isnull': False}) \
        .exclude(**{field.attname: company.pk}).values_list('pk', flat=True)
    return pks - set(elsewhere)


def company_graph(company) -> dict:
    """Every row that belongs to `company`, as {(label, pk): instance}."""
    from core.models import Project, UserProfile
    from recruitment_agent.models import CareerApplication, JobDescription
    graph: dict = {}
    _collect([company], graph)
    # These point at the company with SET_NULL, so deleting it would leave them behind.
    for model in (Project, JobDescription, CareerApplication, UserProfile):
        _collect(model._base_manager.filter(company=company), graph)
    # Kept as a bare number.
    try:
        from project_manager_agent.models import ProjectPilotJob
        _collect(ProjectPilotJob._base_manager.filter(company_id=company.pk), graph)
    except LookupError:
        pass
    # The company's employee logins (never a super admin, never another company's) and what belongs to them.
    User = _user_model()
    user_ids = {getattr(o, f.attname) for o in list(graph.values()) for f in o._meta.concrete_fields
                if f.is_relation and f.related_model is User and getattr(o, f.attname, None)}
    _collect(User._base_manager.filter(pk__in=_not_elsewhere(User, user_ids, company)), graph)
    # Rows the company's rows point at that nothing above reached (an older CV, an interview): theirs too, unless
    # they belong to another company or to the platform.
    for _ in range(3):
        missing = {}
        for o in list(graph.values()):
            for f in o._meta.concrete_fields:
                if not f.is_relation:
                    continue
                target = f.related_model
                value = getattr(o, f.attname, None)
                if value is None or (target._meta.label_lower, value) in graph or _is_platform(target):
                    continue
                missing.setdefault(target, set()).add(value)
        added = 0
        for target, pks in missing.items():
            keep = _not_elsewhere(target, pks, company)
            if keep:
                before = len(graph)
                _collect(target._base_manager.filter(pk__in=keep), graph)
                added += len(graph) - before
        if not added:
            break
    # Last guard: nothing that names another company as its own.
    for key, obj in list(graph.items()):
        field = _company_field(type(obj))
        value = getattr(obj, field.attname, None) if field is not None else None
        if value is not None and value != company.pk:
            del graph[key]
    return graph


# ---------------------------------------------------------------------------------------------------------------- #
# Snapshots
# ---------------------------------------------------------------------------------------------------------------- #

def _is_secret(field) -> bool:
    name = field.name.lower()
    return name not in SECRET_KEEP and any(m in name for m in SECRET_MARKERS)


def _blank(field):
    if isinstance(field, models.JSONField):
        return {}
    if field.null:
        return None
    return ''


def make_snapshot(company, *, key: str, label: str):
    """Store `company` as the DemoSnapshot `key`, secrets blanked. Returns it."""
    from core.models import DemoSnapshot
    graph = company_graph(company)
    by_model: dict = {}
    for (lbl, _pk), obj in graph.items():
        if lbl in NOT_SNAPSHOTTED or _is_platform(type(obj)):
            continue
        by_model.setdefault(type(obj), []).append(obj)
    records = []
    for model, objs in by_model.items():
        secret = [f.name for f in model._meta.concrete_fields if not f.is_relation and _is_secret(f)]
        for rec in serializers.serialize('python', objs):
            for name in secret:
                if name in rec['fields']:
                    rec['fields'][name] = _blank(model._meta.get_field(name))
            records.append(rec)
    raw = json.dumps(records, cls=DjangoJSONEncoder).encode('utf-8')
    snap, _ = DemoSnapshot.objects.update_or_create(key=key, defaults={
        'label': label, 'company_pk': company.pk, 'company_name': company.name,
        'data': zlib.compress(raw, 9), 'rows': len(records), 'made_at': timezone.now(),
    })
    return snap


def snapshot_records(snap) -> list:
    return json.loads(zlib.decompress(bytes(snap.data)).decode('utf-8'))


# ---------------------------------------------------------------------------------------------------------------- #
# Loading and removing
# ---------------------------------------------------------------------------------------------------------------- #

def new_password() -> str:
    alphabet = string.ascii_letters + string.digits
    return 'Demo-' + ''.join(secrets.choice(alphabet) for _ in range(10))


def _progress(run, done, total, step):
    from core.models import DemoDataRun
    DemoDataRun.objects.filter(pk=run.pk).update(done_rows=done, total_rows=total, step=step[:200])


def _shift(obj, days: int) -> None:
    if not days:
        return
    delta = timedelta(days=days)
    for f in obj._meta.concrete_fields:
        if isinstance(f, (models.DateTimeField, models.DateField)):
            value = getattr(obj, f.attname, None)
            if value:
                setattr(obj, f.attname, value + delta)


def _switch_off(company_pk: int) -> None:
    """The demo's mailboxes, CRM connections and campaigns stay off: nothing is sent or synced from it."""
    from core.models import Company
    company = Company.objects.filter(pk=company_pk).first()
    if company is None:
        return
    graph = company_graph(company)
    pks = {}
    for (label, pk) in graph:
        pks.setdefault(label, []).append(pk)
    for label, updates in (('marketing_agent.emailaccount', {'is_active': False}),
                           ('crm_sync_agent.crmintegration', {'is_active': False})):
        if label in pks:
            apps.get_model(label)._base_manager.filter(pk__in=pks[label]).update(**updates)
    for label in ('ai_sdr_agent.sdrcampaign', 'marketing_agent.campaign'):
        if label in pks:
            apps.get_model(label)._base_manager.filter(pk__in=pks[label], status__in=['active', 'scheduled']) \
                .update(status='paused')


#: One insert stays well under the database's statement limit (16 MB on the live server): documents keep their
#: whole text, so 200 of them can be far bigger than 200 tasks.
BATCH_ROWS = 200
BATCH_BYTES = 4 * 1024 * 1024


def _batches(items):
    batch, size = [], 0
    for d in items:
        if batch and (len(batch) >= BATCH_ROWS or size + d.size > BATCH_BYTES):
            yield batch
            batch, size = [], 0
        batch.append(d)
        size += d.size
    if batch:
        yield batch


class TestDataError(Exception):
    """Something that stops the test data being added; the page shows the message."""


def _check_free(snap, by_model) -> None:
    """Every id the snapshot uses must be free, and its login names unused, or nothing is added."""
    User = _user_model()
    for model, items in by_model.items():
        pks = [d.object.pk for d in items]
        for start in range(0, len(pks), 500):
            taken = list(model._base_manager.filter(pk__in=pks[start:start + 500]).values_list('pk', flat=True)[:3])
            if taken:
                raise TestDataError(
                    f'{snap.company_name} can\'t be added: this database already has {model._meta.verbose_name_plural} '
                    f'with the same ids ({", ".join(map(str, taken))}). Remove the test data, or the rows using '
                    f'those ids, first.')
        if model is User:
            names = [d.object.username for d in items]
            used = list(User._base_manager.filter(username__in=names).values_list('username', flat=True)[:3])
            if used:
                raise TestDataError(f'{snap.company_name} can\'t be added: these logins already exist: '
                                    f'{", ".join(used)}.')


def load_snapshot(snap, run, *, done_before=0, total=0) -> int:
    """Insert the snapshot's rows as they were (their own ids), dates moved forward; returns rows written.

    All or nothing: if a row can't be written, the rows already written for this company are removed again."""
    from core.crypto_utils import encrypt_secret
    from core.models import CompanyUser
    records = snapshot_records(snap)
    days = max(0, (timezone.now().date() - snap.made_at.date()).days)
    sizes = [len(json.dumps(r['fields'], cls=DjangoJSONEncoder)) for r in records]
    objects = list(serializers.deserialize('python', records, ignorenonexistent=True))
    by_model: dict = {}
    for d, size in zip(objects, sizes):
        d.size = size
        by_model.setdefault(type(d.object), []).append(d)
    _check_free(snap, by_model)
    done = done_before
    written: dict = {}
    try:
        for model, items in by_model.items():
            fields = [f for f in model._meta.concrete_fields]
            for batch in _batches(items):
                objs = []
                for d in batch:
                    _shift(d.object, days)
                    objs.append(d.object)
                with transaction.atomic():
                    model._base_manager._insert(objs, fields=fields, raw=True)
                    for d in batch:
                        for name, values in (d.m2m_data or {}).items():
                            field = model._meta.get_field(name)
                            through = field.remote_field.through
                            if not through._meta.auto_created or not values:
                                continue
                            src = field.m2m_field_name()
                            dst = field.m2m_reverse_field_name()
                            rows = [through(**{f'{src}_id': d.object.pk, f'{dst}_id': v}) for v in values]
                            through._base_manager.bulk_create(rows, ignore_conflicts=True)
                for d in batch:
                    written[(model._meta.label_lower, d.object.pk)] = d.object
                done += len(batch)
                _progress(run, done, total, f'Adding {snap.company_name}: {model._meta.verbose_name_plural}')
    except Exception:
        delete_rows(written)
        raise
    # One new password for the company's logins, shown on the Test data page.
    password = new_password()
    hashed = make_password(password)
    CompanyUser._base_manager.filter(company_id=snap.company_pk).update(password_hash=hashed)
    User = _user_model()
    user_pks = [d.object.pk for d in objects if isinstance(d.object, User)]
    User._base_manager.filter(pk__in=user_pks, is_superuser=False).update(password=hashed)
    _switch_off(snap.company_pk)
    type(snap)._base_manager.filter(pk=snap.pk).update(password=encrypt_secret(password), loaded_at=timezone.now())
    return done


def delete_rows(graph: dict) -> int:
    """Delete exactly these rows, without signals (nothing is called outside), keys checked off meanwhile."""
    by_model: dict = {}
    for (label, pk), obj in graph.items():
        if _is_platform(type(obj)):
            continue
        by_model.setdefault(type(obj), []).append(pk)
    n = 0
    with transaction.atomic():
        for model, pks in by_model.items():
            for start in range(0, len(pks), 500):
                qs = model._base_manager.filter(pk__in=pks[start:start + 500])
                n += qs._raw_delete(qs.db)
            # Auto-created many-to-many rows of these objects.
            for f in model._meta.many_to_many:
                through = f.remote_field.through
                if through._meta.auto_created:
                    for start in range(0, len(pks), 500):
                        qs = through._base_manager.filter(**{f'{f.m2m_field_name()}_id__in': pks[start:start + 500]})
                        qs._raw_delete(qs.db)
    return n


def loaded_company(snap):
    from core.models import Company
    return Company.objects.filter(pk=snap.company_pk, name=snap.company_name).first()


def run_job(run_id: int) -> None:
    """The background work behind the Test data page's buttons (DemoDataRun.action 'load' or 'remove')."""
    from core.models import DemoDataRun, DemoSnapshot
    run = DemoDataRun.objects.get(pk=run_id)
    DemoDataRun.objects.filter(pk=run.pk).update(status='running', started_at=timezone.now())
    connection.disable_constraint_checking()
    try:
        snaps = list(DemoSnapshot.objects.filter(key__in=run.keys).order_by('key')) if run.keys else \
            list(DemoSnapshot.objects.order_by('key'))
        if run.action == 'load':
            todo = [s for s in snaps if loaded_company(s) is None]
            total = sum(s.rows for s in todo)
            _progress(run, 0, total, 'Starting')
            done = 0
            for snap in todo:
                done = load_snapshot(snap, run, done_before=done, total=total)
        else:
            graphs = [(s, company_graph(c)) for s in snaps if (c := loaded_company(s)) is not None]
            total = sum(len(g) for _, g in graphs)
            done = 0
            _progress(run, 0, total, 'Starting')
            for snap, graph in graphs:
                _progress(run, done, total, f'Removing {snap.company_name}')
                done += delete_rows(graph)
                DemoSnapshot.objects.filter(pk=snap.pk).update(password='', loaded_at=None)
                _progress(run, done, total, f'{snap.company_name} removed')
        DemoDataRun.objects.filter(pk=run.pk).update(status='done', finished_at=timezone.now(), step='Done')
    except Exception as exc:  # noqa: BLE001 - the page shows what went wrong
        DemoDataRun.objects.filter(pk=run.pk).update(status='failed', finished_at=timezone.now(),
                                                     error=str(exc)[:2000])
        raise
    finally:
        connection.enable_constraint_checking()


# ---------------------------------------------------------------------------------------------------------------- #
# The sweep
# ---------------------------------------------------------------------------------------------------------------- #

def kept_users() -> list:
    """The logins the sweep keeps: the super admins, and anyone the platform's own rows name (a blog post's author)."""
    User = _user_model()
    keep = set(User._base_manager.filter(is_superuser=True).values_list('pk', flat=True))
    for model in apps.get_models(include_auto_created=True):
        if not _is_platform(model) or model._meta.proxy or not model._meta.managed:
            continue
        for f in model._meta.concrete_fields:
            if f.is_relation and f.related_model is User:
                keep.update(v for v in model._base_manager.exclude(**{f'{f.attname}__isnull': True})
                            .values_list(f.attname, flat=True).distinct())
    return sorted(keep)


def _not_kept(model, keep):
    """A queryset of `model`'s rows that are NOT a kept login's (only for SUPERUSER_OWNED models)."""
    User = _user_model()
    qs = model._base_manager.all()
    if model is User:
        return qs.exclude(pk__in=keep)
    for f in model._meta.concrete_fields:
        if f.is_relation and f.related_model is User:
            return qs.exclude(**{f'{f.attname}__in': keep})
    return qs.none()


def _is_kept_table(model) -> bool:
    opts = model._meta
    if opts.proxy or not opts.managed or _is_platform(model):
        return True
    # A many-to-many table of a kept table (a blog post's tags).
    return bool(opts.auto_created) and _is_platform(opts.auto_created)


def _kept_rows(keep_companies) -> dict:
    """{label: [pk, ...]}: the companies the sweep is told to keep, each with everything that belongs to it."""
    rows: dict = {}
    for company in keep_companies:
        for label, pk in company_graph(company):
            rows.setdefault(label, set()).add(pk)
    return {label: sorted(pks) for label, pks in rows.items()}


def sweep_plan(keep_companies=()) -> list:
    """[(model, queryset, rows)] the sweep deletes: every customer's data; the kept logins, the setup and any company
    in `keep_companies` stay."""
    keep = kept_users()
    kept_rows = _kept_rows(keep_companies)
    plan = []
    for model in apps.get_models(include_auto_created=True):
        if _is_kept_table(model):
            continue
        label = model._meta.label_lower
        qs = _not_kept(model, keep) if label in SUPERUSER_OWNED else model._base_manager.all()
        if label in kept_rows:
            qs = qs.exclude(pk__in=kept_rows[label])
        n = qs.count()
        if n:
            plan.append((model, qs, n))
    return plan


def sweep(*, commit: bool, keep_companies=()) -> dict:
    """{label: rows} the sweep deletes (or would, with commit=False)."""
    from core.models import DemoSnapshot, UserProfile
    keep = kept_users()
    plan = sweep_plan(keep_companies)
    report = {m._meta.label: n for m, _, n in plan}
    if commit:
        connection.disable_constraint_checking()
        try:
            with transaction.atomic():
                for _model, qs, _n in plan:
                    qs._raw_delete(qs.db)
                # A kept login's profile no longer belongs to a company that is gone.
                UserProfile._base_manager.filter(user_id__in=keep).update(company=None, created_by_company_user=None)
        finally:
            connection.enable_constraint_checking()
        DemoSnapshot.objects.update(password='', loaded_at=None)
    return report


# ---------------------------------------------------------------------------------------------------------------- #
# The page
# ---------------------------------------------------------------------------------------------------------------- #

def _employee_logins(snap, company) -> list:
    """The company's people who sign in at /login: everyone in the snapshot and anyone added since, but not the
    accounts that only stand behind a dashboard login (CompanyUser.login_user)."""
    from core.models import CompanyUser, UserProfile
    User = _user_model()
    ids = {r['pk'] for r in snapshot_records(snap) if r['model'] == 'auth.user'}
    ids |= set(UserProfile._base_manager.filter(company=company).values_list('user_id', flat=True))
    ids -= set(CompanyUser._base_manager.filter(company=company, login_user__isnull=False)
               .values_list('login_user_id', flat=True))
    roles = dict(UserProfile._base_manager.filter(user_id__in=ids).values_list('user_id', 'role'))
    role_names = dict(UserProfile._meta.get_field('role').choices)
    return [{'name': u.get_full_name() or u.username, 'email': u.email, 'username': u.username,
             'role': role_names.get(roles.get(u.pk), roles.get(u.pk) or ''), 'active': u.is_active}
            for u in User._base_manager.filter(pk__in=ids, is_superuser=False).order_by('first_name', 'id')]


def overview() -> list:
    """Each snapshot, and, while it is loaded, its logins (with the password), employees and agents."""
    from core.crypto_utils import decrypt_secret
    from core.models import Agent, CompanyModulePurchase, CompanyUser, DemoSnapshot
    agent_names = dict(Agent.objects.values_list('slug', 'name'))
    out = []
    for snap in DemoSnapshot.objects.order_by('key'):
        item = {'key': snap.key, 'label': snap.label, 'company_name': snap.company_name, 'rows': snap.rows,
                'made_at': snap.made_at, 'loaded': False}
        company = loaded_company(snap)
        if company is not None:
            try:
                password = decrypt_secret(snap.password) if snap.password else ''
            except Exception:  # noqa: BLE001 - a password the server can't read shows as unknown
                password = ''
            item.update({
                'loaded': True, 'loaded_at': snap.loaded_at, 'password': password,
                'dashboard_logins': [
                    {'name': cu.full_name, 'email': cu.email, 'role': cu.get_role_display(), 'active': cu.is_active}
                    for cu in CompanyUser.objects.filter(company=company).order_by('id')],
                'employee_logins': _employee_logins(snap, company),
                'agents': sorted(agent_names.get(m, m) for m in CompanyModulePurchase.objects
                                 .filter(company=company, status='active').values_list('module_name', flat=True)),
            })
        out.append(item)
    return out
