"""State-only migration that records the `db_column='platform_*'` mapping on
AgentTokenQuota.included_tokens / used_tokens without touching the database.

Background: the real columns were renamed to `platform_included_tokens` and
`platform_used_tokens` out-of-band (not via a Django migration). The model has
been updated to declare db_column pointing at those columns. This migration
exists so Django's migration state matches the model, but it runs SeparateDatabaseAndState
with an empty database_operations list so the DB itself is left alone.
"""

from django.db import migrations, models
from core.models import DEFAULT_FREE_TOKENS


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0046_alter_adminpricingconfig_agent_name_and_more'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterField(
                    model_name='agenttokenquota',
                    name='included_tokens',
                    field=models.BigIntegerField(default=DEFAULT_FREE_TOKENS, db_column='platform_included_tokens'),
                ),
                migrations.AlterField(
                    model_name='agenttokenquota',
                    name='used_tokens',
                    field=models.BigIntegerField(default=0, db_column='platform_used_tokens'),
                ),
            ],
        ),
    ]
