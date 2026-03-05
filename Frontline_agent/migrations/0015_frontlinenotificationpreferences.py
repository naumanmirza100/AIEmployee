# Generated migration: Notification preferences per company user

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('Frontline_agent', '0014_ticket_sla_due_at_and_kbfeedback'),
        ('core', '0035_add_frontline_agent_module'),
    ]

    operations = [
        migrations.CreateModel(
            name='FrontlineNotificationPreferences',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('email_enabled', models.BooleanField(default=True, help_text='Receive notification emails')),
                ('in_app_enabled', models.BooleanField(default=True, help_text='Show in-app notifications')),
                ('ticket_created_email', models.BooleanField(default=True, help_text='Email when a ticket is created (e.g. trigger or workflow)')),
                ('ticket_updated_email', models.BooleanField(default=True, help_text='Email when a ticket is updated')),
                ('ticket_assigned_email', models.BooleanField(default=True, help_text='Email when a ticket is assigned to you')),
                ('workflow_email_enabled', models.BooleanField(default=True, help_text='Receive emails from workflow steps and template triggers')),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('company_user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='frontline_notification_preferences', to='core.companyuser')),
            ],
            options={
                'verbose_name': 'Frontline notification preferences',
                'verbose_name_plural': 'Frontline notification preferences',
            },
        ),
    ]
