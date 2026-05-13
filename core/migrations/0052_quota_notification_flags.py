from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0051_add_agent_provider_usage'),
    ]

    operations = [
        migrations.AddField(
            model_name='agenttokenquota',
            name='notified_80pct',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='agenttokenquota',
            name='notified_100pct',
            field=models.BooleanField(default=False),
        ),
    ]
