# Hand-written migration: the auto-generated AlterField calls trigger a
# Django/MSSQL backend bug ("InboxEmail has no field named '-received_at'")
# when it tries to re-evaluate the model's `Meta.indexes` during column
# alterations. Skipping the ORM-level AlterField and issuing the column
# change as raw SQL avoids that codepath. The Python-side state_operations
# still inform Django that the model's fields have changed so future
# auto-generated migrations stay consistent.

from django.db import migrations, models

_TABLE = 'ppp_replydraftagent_inboxemail'

# Same intent on every backend — let `body_html` hold NULL — but the column
# type and the ALTER spelling differ. `nvarchar(max)` is what TextField maps to
# on SQL Server; MySQL/MariaDB uses `longtext` and `MODIFY` rather than
# `ALTER COLUMN`.
_SQL = {
    'microsoft': (
        f"ALTER TABLE {_TABLE} ALTER COLUMN body_html nvarchar(max) NULL;",
        f"ALTER TABLE {_TABLE} ALTER COLUMN body_html nvarchar(max) NOT NULL;",
    ),
    'mysql': (
        f"ALTER TABLE {_TABLE} MODIFY body_html longtext NULL;",
        f"ALTER TABLE {_TABLE} MODIFY body_html longtext NOT NULL;",
    ),
}


def _apply(schema_editor, index):
    pair = _SQL.get(schema_editor.connection.vendor)
    if pair:
        schema_editor.execute(pair[index])


def _forward(apps, schema_editor):
    _apply(schema_editor, 0)


def _reverse(apps, schema_editor):
    _apply(schema_editor, 1)


class Migration(migrations.Migration):

    dependencies = [
        ('reply_draft_agent', '0004_inboxemail_body_html_alter_inboxemail_body'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                # Allow NULL on body_html so any caller (including older
                # workers that haven't reloaded the model) can insert
                # without 23000 unique-constraint violations.
                # atomic=False: MySQL can't roll back DDL, so Django refuses to
                # run this inside the transaction it would otherwise open.
                migrations.RunPython(_forward, _reverse, atomic=False),
            ],
            state_operations=[
                migrations.AlterField(
                    model_name='inboxemail',
                    name='body',
                    field=models.TextField(blank=True, default='', help_text='Plain-text body. Used for AI analysis and search; preferred over HTML when both are present in the source.'),
                ),
                migrations.AlterField(
                    model_name='inboxemail',
                    name='body_html',
                    field=models.TextField(blank=True, default='', help_text='Original HTML body if the source carried one. Rendered in the UI for fidelity (links, images, layout); plain `body` is used as fallback when this is empty.', null=True),
                ),
            ],
        ),
    ]
