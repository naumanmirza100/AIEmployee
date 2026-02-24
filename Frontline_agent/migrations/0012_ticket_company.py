# Generated migration: add company to Ticket for workflow triggers (signal)

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('Frontline_agent', '0011_notificationtemplate_use_llm_personalization'),
        ('core', '0035_add_frontline_agent_module'),
    ]

    operations = [
        migrations.AddField(
            model_name='ticket',
            name='company',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='frontline_tickets', to='core.company'),
        ),
    ]
