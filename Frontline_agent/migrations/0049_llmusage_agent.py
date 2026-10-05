# Which agent each logged AI call was for, so usage can be shown per agent
# (project_manager_agent.ai_agents.base_agent._record_llm_usage).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Frontline_agent', '0048_preferences_to_notification_settings'),
    ]

    operations = [
        migrations.AddField(
            model_name='llmusage',
            name='agent',
            field=models.CharField(blank=True, default='', max_length=40),
        ),
        migrations.AddIndex(
            model_name='llmusage',
            index=models.Index(fields=['company', 'agent', 'created_at'], name='frontline_llmusage_agent_idx'),
        ),
    ]
