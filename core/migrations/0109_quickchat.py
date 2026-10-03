# Floating Quick Chat conversations, kept on the server instead of the browser
# (core.models.QuickChat).

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0108_notificationsetting'),
    ]

    operations = [
        migrations.CreateModel(
            name='QuickChat',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('agent', models.CharField(choices=[('pm', 'Project Manager'), ('hr', 'HR'), ('frontline', 'Frontline')],
                                           max_length=20)),
                ('mode', models.CharField(blank=True, default='', help_text="PM: 'pilot' or 'qa'", max_length=20)),
                ('client_id', models.CharField(max_length=64)),
                ('title', models.CharField(default='Chat', max_length=255)),
                ('messages', models.JSONField(default=list)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('company_user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                                   related_name='quick_chats', to='core.companyuser')),
            ],
            options={
                'unique_together': {('company_user', 'agent', 'client_id')},
                'indexes': [models.Index(fields=['company_user', 'agent', 'mode', '-updated_at'],
                                         name='core_quickchat_list_idx')],
            },
        ),
    ]
