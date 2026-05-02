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
            name='SDRIcpProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(default='Default ICP', max_length=255)),
                ('industries', models.JSONField(default=list)),
                ('job_titles', models.JSONField(default=list)),
                ('locations', models.JSONField(default=list)),
                ('keywords', models.JSONField(default=list)),
                ('company_size_min', models.IntegerField(blank=True, null=True)),
                ('company_size_max', models.IntegerField(blank=True, null=True)),
                ('hot_threshold', models.IntegerField(default=70)),
                ('warm_threshold', models.IntegerField(default=40)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('company_user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='sdr_icp_profiles',
                    to='core.companyuser',
                )),
            ],
            options={
                'db_table': 'sdr_icp_profile',
            },
        ),
        migrations.CreateModel(
            name='SDRLeadResearchJob',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(
                    choices=[('pending', 'Pending'), ('running', 'Running'), ('completed', 'Completed'), ('failed', 'Failed')],
                    default='pending', max_length=20,
                )),
                ('source', models.CharField(default='ai_generated', max_length=20)),
                ('search_params', models.JSONField(default=dict)),
                ('total_found', models.IntegerField(default=0)),
                ('leads_created', models.IntegerField(default=0)),
                ('leads_qualified', models.IntegerField(default=0)),
                ('error_message', models.TextField(blank=True)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('company_user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    to='core.companyuser',
                )),
                ('icp_profile', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to='ai_sdr_agent.sdricpprofile',
                )),
            ],
            options={
                'db_table': 'sdr_lead_research_job',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='SDRLead',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('first_name', models.CharField(blank=True, max_length=255)),
                ('last_name', models.CharField(blank=True, max_length=255)),
                ('full_name', models.CharField(blank=True, max_length=255)),
                ('email', models.CharField(blank=True, max_length=255)),
                ('phone', models.CharField(blank=True, max_length=100)),
                ('job_title', models.CharField(blank=True, max_length=255)),
                ('seniority_level', models.CharField(blank=True, max_length=100)),
                ('department', models.CharField(blank=True, max_length=100)),
                ('company_name', models.CharField(blank=True, max_length=255)),
                ('company_domain', models.CharField(blank=True, max_length=255)),
                ('company_industry', models.CharField(blank=True, max_length=255)),
                ('company_size', models.IntegerField(blank=True, null=True)),
                ('company_size_range', models.CharField(blank=True, max_length=100)),
                ('company_location', models.CharField(blank=True, max_length=255)),
                ('company_technologies', models.JSONField(default=list)),
                ('linkedin_url', models.CharField(blank=True, max_length=500)),
                ('company_linkedin_url', models.CharField(blank=True, max_length=500)),
                ('company_website', models.CharField(blank=True, max_length=500)),
                ('recent_news', models.JSONField(default=list)),
                ('buying_signals', models.JSONField(default=list)),
                ('apollo_id', models.CharField(blank=True, max_length=255)),
                ('raw_data', models.JSONField(default=dict)),
                ('score', models.IntegerField(blank=True, null=True)),
                ('temperature', models.CharField(
                    blank=True, max_length=10,
                    choices=[('hot', 'Hot'), ('warm', 'Warm'), ('cold', 'Cold')],
                )),
                ('score_breakdown', models.JSONField(default=dict)),
                ('qualification_reasoning', models.TextField(blank=True)),
                ('status', models.CharField(
                    choices=[
                        ('new', 'New'), ('qualified', 'Qualified'), ('contacted', 'Contacted'),
                        ('replied', 'Replied'), ('meeting_scheduled', 'Meeting Scheduled'),
                        ('converted', 'Converted'), ('disqualified', 'Disqualified'),
                    ],
                    default='new', max_length=30,
                )),
                ('source', models.CharField(
                    choices=[
                        ('apollo', 'Apollo.io'), ('manual', 'Manual'),
                        ('csv_import', 'CSV Import'), ('ai_generated', 'AI Generated'),
                    ],
                    default='manual', max_length=30,
                )),
                ('qualified_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('company_user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='sdr_leads',
                    to='core.companyuser',
                )),
                ('icp_profile', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to='ai_sdr_agent.sdricpprofile',
                )),
            ],
            options={
                'db_table': 'sdr_lead',
                'ordering': ['-score', '-created_at'],
            },
        ),
    ]
