from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Registers the KeyRequest.discount_pct_snapshot field that already exists in
    SQL Server (NOT NULL column 'discount_pct_snapshot' on core_keyrequest) but
    was missing from the Django model state, causing INSERTs to fail because
    Django omitted the column from the statement.

    Uses SeparateDatabaseAndState so no DDL is emitted — the column is already
    there on the live table. Also serves as the merge point for the two 0074
    leaves so we go back to a single migration head.
    """

    dependencies = [
        ('core', '0074_ai_sdr_pricing_and_preferred_pool_free'),
        ('core', '0074_task_recurrence'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AddField(
                    model_name='keyrequest',
                    name='discount_pct_snapshot',
                    field=models.DecimalField(decimal_places=2, default=0, max_digits=5),
                ),
            ],
        ),
    ]
