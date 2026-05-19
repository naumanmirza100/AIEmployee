from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0052_quota_notification_flags'),
    ]

    operations = [
        migrations.AddField(
            model_name='agenttokenquota',
            name='notified_90pct',
            field=models.BooleanField(default=False),
        ),
    ]
