# Migration: Rename recruitment_agent tables to ppp_recruitment_agent_* (match marketing prefix)
#
# 2026-09-10: made engine-aware. The original body issued `EXEC sp_rename`
# unconditionally, which only exists on SQL Server. It now renames through
# `schema_editor.alter_db_table()` — Django's per-backend implementation — and
# skips any table that has already been renamed, so it is safe to run against a
# fresh database as well as the legacy one.
#
# `atomic=False` is required: MySQL/MariaDB cannot roll back DDL, so Django
# would otherwise wrap this RunPython in a transaction and then refuse to
# execute DDL inside it (TransactionManagementError).

from django.db import migrations

RENAMES = [
    ('recruiteremailsettings', 'recruitment_agent_recruiteremailsettings',
     'ppp_recruitment_agent_recruiteremailsettings'),
    ('recruiterqualificationsettings', 'recruitment_agent_recruiterqualificationsettings',
     'ppp_recruitment_agent_recruiterqualificationsettings'),
    ('recruiterinterviewsettings', 'recruitment_agent_recruiterinterviewsettings',
     'ppp_recruitment_agent_recruiterinterviewsettings'),
    ('jobdescription', 'recruitment_agent_jobdescription',
     'ppp_recruitment_agent_jobdescription'),
    ('cvrecord', 'ppp_cv_records',
     'ppp_recruitment_agent_cvrecord'),
    ('interview', 'recruitment_agent_interview',
     'ppp_recruitment_agent_interview'),
    ('careerapplication', 'recruitment_agent_careerapplication',
     'ppp_recruitment_agent_careerapplication'),
]


def _tables(schema_editor):
    with schema_editor.connection.cursor() as cursor:
        return set(schema_editor.connection.introspection.table_names(cursor))


def _rename(apps, schema_editor, pairs):
    present = _tables(schema_editor)
    for model_name, old_name, new_name in pairs:
        if old_name not in present or new_name in present:
            continue  # already renamed, or nothing to rename
        model = apps.get_model('recruitment_agent', model_name)
        schema_editor.alter_db_table(model, old_name, new_name)


def rename_tables(apps, schema_editor):
    _rename(apps, schema_editor, RENAMES)


def reverse_rename_tables(apps, schema_editor):
    _rename(apps, schema_editor,
            [(m, new, old) for m, old, new in RENAMES])


class Migration(migrations.Migration):

    dependencies = [
        ('recruitment_agent', '0021_recruiterinterviewsettings_default_interview_type'),
    ]

    operations = [
        migrations.RunPython(rename_tables, reverse_rename_tables, atomic=False),
    ]
