from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Registers four more orphan columns that exist on SQL Server but were missing
    from the Django model state:

      CompanyAPIKey:
        - renewal_period      nvarchar(10) NOT NULL
        - tokens_per_period   bigint       NOT NULL
        - valid_until         datetimeoffset NULL

      AgentTokenQuota:
        - next_reset_at       datetimeoffset NULL

    Same SeparateDatabaseAndState pattern as 0059, 0075, 0076 — no DDL is
    emitted because the columns are already on the live tables. Safe defaults
    on the NOT NULL fields ('monthly' / 0) so existing INSERT call sites
    (e.g. admin_api_keys.assign_managed_key) start succeeding again without
    callers having to know about these orphans.
    """

    dependencies = [
        ('core', '0076_keyrequest_orphan_columns'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AddField(
                    model_name='companyapikey',
                    name='renewal_period',
                    field=models.CharField(default='monthly', max_length=10),
                ),
                migrations.AddField(
                    model_name='companyapikey',
                    name='tokens_per_period',
                    field=models.BigIntegerField(default=0),
                ),
                migrations.AddField(
                    model_name='companyapikey',
                    name='valid_until',
                    field=models.DateTimeField(blank=True, null=True),
                ),
                migrations.AddField(
                    model_name='agenttokenquota',
                    name='next_reset_at',
                    field=models.DateTimeField(blank=True, null=True),
                ),
            ],
        ),
    ]
