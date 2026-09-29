from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ai_sdr_agent', '0022_alter_sdrlead_source'),
    ]

    operations = [
        migrations.AddField(
            model_name='sdrcampaignenrollment',
            name='last_reply_message_id',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='sdrcampaign',
            name='postal_address',
            field=models.CharField(blank=True, default='', max_length=500),
        ),
    ]
