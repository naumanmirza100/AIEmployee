# State-only migration. The `managed_included_tokens` / `managed_used_tokens`
# columns already exist in the DB (added out-of-band earlier) as NOT NULL with
# no default, which made every Django-driven INSERT fail. We're adding the
# fields to the model so Django populates them — but SeparateDatabaseAndState
# leaves the DB schema alone to avoid a "column already exists" error.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0048_merge_20260424_1601'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='agenttokenquota',
                    name='managed_included_tokens',
                    field=models.BigIntegerField(default=0),
                ),
                migrations.AddField(
                    model_name='agenttokenquota',
                    name='managed_used_tokens',
                    field=models.BigIntegerField(default=0),
                ),
            ],
            database_operations=[],  # columns already exist in the DB; no-op
        ),
    ]
