# Generated for PM Knowledge QA and Project Pilot chats

from django.db import migrations, models
import django.db.models.deletion
from django.utils import timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('core', '0035_add_frontline_agent_module'),
    ]

    operations = [
        migrations.CreateModel(
            name='PMKnowledgeQAChat',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(default='Chat', help_text='Chat title (e.g. first question snippet)', max_length=255)),
                ('created_at', models.DateTimeField(default=timezone.now)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('company_user', models.ForeignKey(help_text='Company user who owns this chat', on_delete=django.db.models.deletion.CASCADE, related_name='pm_knowledge_qa_chats', to='core.companyuser')),
            ],
            options={
                'verbose_name': 'PM Knowledge QA Chat',
                'verbose_name_plural': 'PM Knowledge QA Chats',
                'ordering': ['-updated_at'],
            },
        ),
        migrations.CreateModel(
            name='PMProjectPilotChat',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(default='Chat', help_text='Chat title (e.g. first request snippet)', max_length=255)),
                ('created_at', models.DateTimeField(default=timezone.now)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('company_user', models.ForeignKey(help_text='Company user who owns this chat', on_delete=django.db.models.deletion.CASCADE, related_name='pm_project_pilot_chats', to='core.companyuser')),
            ],
            options={
                'verbose_name': 'PM Project Pilot Chat',
                'verbose_name_plural': 'PM Project Pilot Chats',
                'ordering': ['-updated_at'],
            },
        ),
        migrations.CreateModel(
            name='PMKnowledgeQAChatMessage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(choices=[('user', 'User'), ('assistant', 'Assistant')], max_length=20)),
                ('content', models.TextField(help_text='Message content')),
                ('response_data', models.JSONField(blank=True, help_text='For assistant: { answer, project_id, project_title }', null=True)),
                ('created_at', models.DateTimeField(default=timezone.now)),
                ('chat', models.ForeignKey(help_text='Chat this message belongs to', on_delete=django.db.models.deletion.CASCADE, related_name='messages', to='project_manager_agent.pmknowledgeqachat')),
            ],
            options={
                'verbose_name': 'PM Knowledge QA Chat Message',
                'verbose_name_plural': 'PM Knowledge QA Chat Messages',
                'ordering': ['created_at'],
            },
        ),
        migrations.CreateModel(
            name='PMProjectPilotChatMessage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(choices=[('user', 'User'), ('assistant', 'Assistant')], max_length=20)),
                ('content', models.TextField(help_text='Message content (user request or assistant answer)')),
                ('response_data', models.JSONField(blank=True, help_text='For assistant: { answer, action_results, cannot_do, project_id, project_title, from_file, file_name }', null=True)),
                ('created_at', models.DateTimeField(default=timezone.now)),
                ('chat', models.ForeignKey(help_text='Chat this message belongs to', on_delete=django.db.models.deletion.CASCADE, related_name='messages', to='project_manager_agent.pmprojectpilotchat')),
            ],
            options={
                'verbose_name': 'PM Project Pilot Chat Message',
                'verbose_name_plural': 'PM Project Pilot Chat Messages',
                'ordering': ['created_at'],
            },
        ),
    ]
