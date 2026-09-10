"""Helper for the state-only migrations in this app.

Several `core` migrations were written as `SeparateDatabaseAndState` with
`database_operations=[]` because the columns they describe had already been
added to the production SQL Server out-of-band. That works for *that* database
and only that one — on any fresh database the column is never created, so
Django's model state claims a field the table doesn't have, and the next query
touching it dies with "Unknown column".

`ensure_columns()` closes the gap: it inspects the live table and issues an
ADD COLUMN only for fields that are genuinely missing. On the legacy SQL Server
every column is already there, so it's a no-op; on a fresh MySQL/SQL Server
database it creates them.

Files beginning with an underscore are skipped by Django's migration loader,
so this module can live here safely.
"""
from django.db import migrations


def _existing_columns(schema_editor, table):
    with schema_editor.connection.cursor() as cursor:
        return {
            col.name
            for col in schema_editor.connection.introspection.get_table_description(
                cursor, table
            )
        }


def ensure_columns(app_label, model_name, field_names):
    """Build a RunPython operation that adds `field_names` if they're absent.

    Place it *after* the `SeparateDatabaseAndState` that declares the fields —
    by then the historical model carries them, so we can hand the real field
    objects to the schema editor and get correct per-backend column types.
    """

    def _forward(apps, schema_editor):
        model = apps.get_model(app_label, model_name)
        table = model._meta.db_table
        try:
            present = _existing_columns(schema_editor, table)
        except Exception:
            # Table missing entirely is not our problem to solve here — let a
            # later operation surface it with a clearer error.
            return
        for name in field_names:
            field = model._meta.get_field(name)
            # `column` differs from `name` for FKs (linked_key -> linked_key_id).
            if field.column in present:
                continue
            schema_editor.add_field(model, field)

    return migrations.RunPython(_forward, migrations.RunPython.noop)


def _rename_column(schema_editor, table, old_column, field):
    """Rename a column in place, preserving its data, per backend."""
    connection = schema_editor.connection
    qn = schema_editor.quote_name
    if connection.vendor == 'mysql':
        # MySQL's CHANGE needs the full column definition restated.
        col_type = field.db_parameters(connection)['type']
        nullability = 'NULL' if field.null else 'NOT NULL'
        schema_editor.execute(
            f"ALTER TABLE {qn(table)} CHANGE {qn(old_column)} "
            f"{qn(field.column)} {col_type} {nullability}"
        )
    elif connection.vendor == 'microsoft':
        schema_editor.execute(
            f"EXEC sp_rename '{table}.{old_column}', '{field.column}', 'COLUMN'")
    else:
        schema_editor.execute(
            f"ALTER TABLE {qn(table)} RENAME COLUMN "
            f"{qn(old_column)} TO {qn(field.column)}"
        )


def rename_or_ensure_columns(app_label, model_name, mapping):
    """For fields whose column was renamed out-of-band on production.

    `mapping` is ``{legacy_column_name: model_field_name}``. For each entry:

      * target column already there  -> nothing to do
      * legacy column there instead  -> rename it, keeping the data
      * neither                      -> create the target column

    The middle case is the one that matters on a fresh database. Simply adding
    the target column would leave the legacy one behind, and since it is
    ``NOT NULL`` with no default — while Django, now mapped to the new name,
    never writes to it — every INSERT fails under STRICT_TRANS_TABLES with
    "Field 'x' doesn't have a default value".
    """

    def _forward(apps, schema_editor):
        model = apps.get_model(app_label, model_name)
        table = model._meta.db_table
        try:
            present = _existing_columns(schema_editor, table)
        except Exception:
            return
        for legacy_column, field_name in mapping.items():
            field = model._meta.get_field(field_name)
            if field.column in present:
                continue
            if legacy_column in present:
                _rename_column(schema_editor, table, legacy_column, field)
            else:
                schema_editor.add_field(model, field)

    return migrations.RunPython(_forward, migrations.RunPython.noop)
