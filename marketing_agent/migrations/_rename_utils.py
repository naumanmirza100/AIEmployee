"""Helper for 0022_rename_tables_to_ppp_prefix.

That migration renames every `marketing_agent_*` table to `ppp_marketingagent_*`.
A plain `AlterModelTable` issues the rename unconditionally, which is fine on the
database the migration was written against but fails on a fresh one where the
tables were created under their final names to begin with — the source table
simply isn't there ("Table ... doesn't exist").

`alter_table_if_exists()` keeps the state change (so Django's model state still
learns the new name) while making the DB-side rename conditional. It leans on
`schema_editor.alter_db_table()` and the introspection API, so it stays correct
on SQL Server, MySQL and SQLite alike.

Files beginning with an underscore are skipped by Django's migration loader.
"""
from django.db import migrations

APP_LABEL = 'marketing_agent'


def _tables(schema_editor):
    with schema_editor.connection.cursor() as cursor:
        return set(schema_editor.connection.introspection.table_names(cursor))


def alter_table_if_exists(model_name, new_table, old_table=None):
    """AlterModelTable that skips the rename when there's nothing to rename."""
    old_table = old_table or f'{APP_LABEL}_{model_name}'

    def _forward(apps, schema_editor):
        present = _tables(schema_editor)
        if old_table in present and new_table not in present:
            model = apps.get_model(APP_LABEL, model_name)
            schema_editor.alter_db_table(model, old_table, new_table)

    def _reverse(apps, schema_editor):
        present = _tables(schema_editor)
        if new_table in present and old_table not in present:
            model = apps.get_model(APP_LABEL, model_name)
            schema_editor.alter_db_table(model, new_table, old_table)

    return migrations.SeparateDatabaseAndState(
        state_operations=[
            migrations.AlterModelTable(name=model_name, table=new_table),
        ],
        database_operations=[migrations.RunPython(_forward, _reverse)],
    )
