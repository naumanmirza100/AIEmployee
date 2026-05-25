from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='CRMIntegration',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('provider', models.CharField(
                    choices=[('hubspot', 'HubSpot'), ('salesforce', 'Salesforce'), ('pipedrive', 'Pipedrive')],
                    max_length=20,
                )),
                ('credentials', models.JSONField(default=dict)),
                ('field_mappings', models.JSONField(default=dict)),
                ('sync_contacts', models.BooleanField(default=True)),
                ('sync_emails', models.BooleanField(default=True)),
                ('sync_meetings', models.BooleanField(default=True)),
                ('sync_notes', models.BooleanField(default=True)),
                ('is_active', models.BooleanField(default=True)),
                ('last_ping_at', models.DateTimeField(blank=True, null=True)),
                ('last_ping_ok', models.BooleanField(blank=True, null=True)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('company', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='crm_integrations',
                    to='core.company',
                )),
            ],
            options={
                'db_table': 'crm_integration',
                'ordering': ['provider'],
            },
        ),
        migrations.AddConstraint(
            model_name='crmintegration',
            constraint=models.UniqueConstraint(
                fields=['company', 'provider'],
                name='unique_company_provider',
            ),
        ),
        migrations.CreateModel(
            name='CRMContactMapping',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('source_type', models.CharField(
                    choices=[('sdr_lead', 'SDR Lead'), ('frontline_contact', 'Frontline Contact')],
                    max_length=30,
                )),
                ('source_id', models.PositiveBigIntegerField()),
                ('crm_contact_id', models.CharField(max_length=255)),
                ('crm_deal_id', models.CharField(blank=True, max_length=255)),
                ('last_synced_at', models.DateTimeField(auto_now=True)),
                ('company', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='crm_contact_mappings',
                    to='core.company',
                )),
                ('integration', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='contact_mappings',
                    to='crm_sync_agent.crmintegration',
                )),
            ],
            options={
                'db_table': 'crm_contact_mapping',
            },
        ),
        migrations.AddConstraint(
            model_name='crmcontactmapping',
            constraint=models.UniqueConstraint(
                fields=['integration', 'source_type', 'source_id'],
                name='unique_integration_source',
            ),
        ),
        migrations.AddIndex(
            model_name='crmcontactmapping',
            index=models.Index(
                fields=['integration', 'source_type', 'source_id'],
                name='crm_contact_map_idx',
            ),
        ),
        migrations.CreateModel(
            name='CRMSyncLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('object_type', models.CharField(
                    choices=[('contact', 'Contact'), ('email_activity', 'Email Activity'),
                              ('meeting', 'Meeting'), ('note', 'Note')],
                    max_length=30,
                )),
                ('object_id', models.CharField(blank=True, max_length=200)),
                ('crm_object_id', models.CharField(blank=True, max_length=255)),
                ('operation', models.CharField(
                    choices=[('create', 'Create'), ('update', 'Update')],
                    max_length=20,
                )),
                ('status', models.CharField(
                    choices=[('success', 'Success'), ('failed', 'Failed'), ('skipped', 'Skipped')],
                    max_length=20,
                )),
                ('error_message', models.TextField(blank=True)),
                ('payload', models.JSONField(default=dict)),
                ('response', models.JSONField(default=dict)),
                ('attempted_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('company', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='crm_sync_logs',
                    to='core.company',
                )),
                ('integration', models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='sync_logs',
                    to='crm_sync_agent.crmintegration',
                )),
            ],
            options={
                'db_table': 'crm_sync_log',
                'ordering': ['-attempted_at'],
            },
        ),
        migrations.AddIndex(
            model_name='crmsynclog',
            index=models.Index(
                fields=['company', 'attempted_at'],
                name='crm_log_company_time_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='crmsynclog',
            index=models.Index(
                fields=['integration', 'status'],
                name='crm_log_integration_status_idx',
            ),
        ),
        migrations.CreateModel(
            name='CRMSyncQueue',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('object_type', models.CharField(
                    choices=[('contact', 'Contact'), ('email_activity', 'Email Activity'),
                              ('meeting', 'Meeting'), ('note', 'Note')],
                    max_length=30,
                )),
                ('operation', models.CharField(
                    choices=[('create', 'Create'), ('update', 'Update')],
                    default='create',
                    max_length=20,
                )),
                ('source_type', models.CharField(
                    choices=[('sdr_lead', 'SDR Lead'), ('sdr_email', 'SDR Email'),
                              ('sdr_meeting', 'SDR Meeting'), ('sdr_note', 'SDR Note'),
                              ('frontline_contact', 'Frontline Contact')],
                    max_length=30,
                )),
                ('source_id', models.PositiveBigIntegerField()),
                ('priority', models.SmallIntegerField(default=5)),
                ('payload', models.JSONField(default=dict)),
                ('status', models.CharField(
                    choices=[('pending', 'Pending'), ('processing', 'Processing'),
                              ('done', 'Done'), ('failed', 'Failed')],
                    default='pending',
                    max_length=20,
                )),
                ('attempts', models.PositiveSmallIntegerField(default=0)),
                ('max_attempts', models.PositiveSmallIntegerField(default=3)),
                ('last_attempted_at', models.DateTimeField(blank=True, null=True)),
                ('scheduled_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('error_message', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('company', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='crm_sync_queue',
                    to='core.company',
                )),
                ('integration', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='sync_queue',
                    to='crm_sync_agent.crmintegration',
                )),
            ],
            options={
                'db_table': 'crm_sync_queue',
                'ordering': ['priority', 'scheduled_at'],
            },
        ),
        migrations.AddIndex(
            model_name='crmsyncqueue',
            index=models.Index(
                fields=['status', 'priority', 'scheduled_at'],
                name='crm_queue_status_pri_time_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='crmsyncqueue',
            index=models.Index(
                fields=['company', 'status'],
                name='crm_queue_company_status_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='crmsyncqueue',
            index=models.Index(
                fields=['integration', 'status'],
                name='crm_queue_integration_status_idx',
            ),
        ),
    ]
