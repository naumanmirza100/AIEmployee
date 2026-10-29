"""Alerts someone deleted, remembered so the monitor does not raise them again at once (CO-133)."""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('marketing_agent', '0044_checked_inbox_message'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='DismissedMarketingAlert',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.CharField(max_length=160)),
                ('dismissed_at', models.DateTimeField(auto_now_add=True)),
                ('campaign', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                                               related_name='dismissed_alerts', to='marketing_agent.campaign')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                           related_name='dismissed_marketing_alerts', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'ppp_marketingagent_dismissedalert',
                'indexes': [models.Index(fields=['user', 'campaign', 'key'], name='ppp_marketi_dismiss_key_idx')],
            },
        ),
    ]
