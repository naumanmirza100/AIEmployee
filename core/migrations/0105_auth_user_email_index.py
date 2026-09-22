"""Index `auth_user.email` (FL-PERF-6).

Django's stock `User.email` carries no index, and several agents resolve a
dashboard login to an `auth.User` by email — so each of those calls was a full
scan of `auth_user`, on the first query of a page load.

Frontline no longer does this (FL-SEC-3 gave `CompanyUser` an explicit
`login_user` FK), but `api/views/hr_agent.py`, `marketing_agent.py` and
`reply_draft_agent.py` still do, and `core.tenancy` matches on email in
places. The index is small and helps all of them.

Written through the schema editor rather than as raw SQL so it works on both
MariaDB and the SQLite used by the tests, and so a pre-existing index (someone
added it by hand) doesn't fail the deploy.
"""
from django.db import migrations

INDEX_NAME = 'idx_auth_user_email'


def create_index(apps, schema_editor):
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        try:
            if connection.vendor == 'mysql':
                cursor.execute(f"CREATE INDEX {INDEX_NAME} ON auth_user (email)")
            else:
                cursor.execute(f"CREATE INDEX IF NOT EXISTS {INDEX_NAME} ON auth_user (email)")
        except Exception as exc:  # already there, or insufficient privileges
            if 'exist' not in str(exc).lower() and 'duplicate' not in str(exc).lower():
                raise


def drop_index(apps, schema_editor):
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        try:
            if connection.vendor == 'mysql':
                cursor.execute(f"DROP INDEX {INDEX_NAME} ON auth_user")
            else:
                cursor.execute(f"DROP INDEX IF EXISTS {INDEX_NAME}")
        except Exception:
            pass


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0104_encrypt_hubspot_tokens'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.RunPython(create_index, drop_index),
    ]
