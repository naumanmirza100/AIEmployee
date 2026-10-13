# When the product itself pauses a sales campaign (its mailbox refuses to send),
# it now says why on the campaign. It used to mark every lead as a dead address.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ai_sdr_agent', '0028_removed_enrollment'),
    ]

    operations = [
        migrations.AddField(
            model_name='sdrcampaign',
            name='paused_reason',
            field=models.CharField(blank=True, default='', max_length=500),
        ),
    ]
