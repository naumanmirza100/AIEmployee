# The index ppp_recruit_candida_265a0e_idx was never created in this DB
# (it was removed from the previous model state before the index existed).
# We update Django's migration state only, without touching the database.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('recruitment_agent', '0035_add_indexes_validators_clean'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],  # no DB change — index never existed
            state_operations=[
                migrations.RemoveIndex(
                    model_name='interview',
                    name='ppp_recruit_candida_265a0e_idx',
                ),
            ],
        ),
    ]
