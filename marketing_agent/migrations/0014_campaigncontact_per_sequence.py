from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [
        ('marketing_agent', '0013_add_campaign_contact'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='campaigncontact',
            unique_together={('campaign', 'lead', 'sequence')},
        ),
    ]