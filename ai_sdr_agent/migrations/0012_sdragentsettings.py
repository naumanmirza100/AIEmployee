from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('ai_sdr_agent', '0011_add_meeting_lead_timezone'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='SDRAgentSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('apollo_api_key', models.CharField(blank=True, max_length=500)),
                ('apify_api_token', models.CharField(blank=True, max_length=500)),
                ('apify_actor_id', models.CharField(blank=True, max_length=255)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('company_user', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='sdr_settings',
                    to='core.companyuser',
                )),
            ],
            options={'db_table': 'sdr_agent_settings'},
        ),
    ]
