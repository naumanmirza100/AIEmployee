from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Registers key_cost_snapshot on KeyRequest in Django's migration state.
    The column already exists in SQL Server (NOT NULL, no default), so we use
    SeparateDatabaseAndState to update state only — no DDL is emitted.
    """

    dependencies = [
        ('core', '0057_merge_20260513_2337'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AddField(
                    model_name='keyrequest',
                    name='key_cost_snapshot',
                    field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
                ),
            ],
        ),
    ]
