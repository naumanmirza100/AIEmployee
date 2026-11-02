# A campaign keeps what its inbox said the last time it could not be read (CO-197).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ai_sdr_agent', '0030_review_ai_replies'),
    ]

    operations = [
        migrations.AddField(
            model_name='sdrcampaign',
            name='inbox_error',
            field=models.CharField(blank=True, default='', max_length=500),
        ),
        migrations.AddField(
            model_name='sdrcampaign',
            name='inbox_error_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
