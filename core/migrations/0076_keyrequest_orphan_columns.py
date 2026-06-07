from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Registers two more KeyRequest columns that already exist in SQL Server
    (NOT NULL) but were missing from the Django model state:

      - preferred_duration  nvarchar(10) NOT NULL
      - is_renewal          bit NOT NULL

    Same SeparateDatabaseAndState pattern as 0059 and 0075 — no DDL is emitted
    because the columns are already on the live table. The model fields get
    safe defaults ('monthly' and False) so INSERTs satisfy the NOT NULL
    constraint without callers having to know about these orphan columns.
    """

    dependencies = [
        ('core', '0075_keyrequest_discount_pct_snapshot'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AddField(
                    model_name='keyrequest',
                    name='preferred_duration',
                    field=models.CharField(default='monthly', max_length=10),
                ),
                migrations.AddField(
                    model_name='keyrequest',
                    name='is_renewal',
                    field=models.BooleanField(default=False),
                ),
            ],
        ),
    ]
