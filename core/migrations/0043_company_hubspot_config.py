from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0042_company_inbound_email_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='company',
            name='hubspot_config',
            field=models.JSONField(blank=True, default=dict,
                                   help_text='HubSpot private-app config: {enabled, access_token, portal_id, last_error}.'),
        ),
    ]
