"""Whose money each AI call spent (22 Nov 2026): the platform's key, a managed key or the company's own."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Frontline_agent', '0050_meeting_customer_reminders_handoff_reasons'),
    ]

    operations = [
        migrations.AddField(
            model_name='llmusage',
            name='key_mode',
            field=models.CharField(blank=True, default='', max_length=10),
        ),
        migrations.AddField(
            model_name='llmusage',
            name='provider',
            field=models.CharField(blank=True, default='', max_length=20),
        ),
    ]
