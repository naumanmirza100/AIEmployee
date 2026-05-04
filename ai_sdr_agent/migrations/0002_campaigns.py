from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('ai_sdr_agent', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='SDRCampaign',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True)),
                ('status', models.CharField(
                    choices=[('draft', 'Draft'), ('active', 'Active'), ('paused', 'Paused'), ('completed', 'Completed')],
                    default='draft', max_length=20,
                )),
                ('sender_name', models.CharField(blank=True, max_length=255)),
                ('sender_title', models.CharField(blank=True, max_length=255)),
                ('sender_company', models.CharField(blank=True, max_length=255)),
                ('from_email', models.CharField(blank=True, max_length=255)),
                ('smtp_host', models.CharField(blank=True, max_length=255)),
                ('smtp_port', models.IntegerField(default=587)),
                ('smtp_username', models.CharField(blank=True, max_length=255)),
                ('smtp_password', models.CharField(blank=True, max_length=500)),
                ('smtp_use_tls', models.BooleanField(default=True)),
                ('total_leads', models.IntegerField(default=0)),
                ('emails_sent', models.IntegerField(default=0)),
                ('replies_received', models.IntegerField(default=0)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('company_user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='sdr_campaigns',
                    to='core.companyuser',
                )),
            ],
            options={'db_table': 'sdr_campaign', 'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='SDRCampaignStep',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('step_order', models.IntegerField(default=1)),
                ('step_type', models.CharField(
                    choices=[('email', 'Email'), ('linkedin', 'LinkedIn Request')],
                    default='email', max_length=30,
                )),
                ('delay_days', models.IntegerField(default=1)),
                ('name', models.CharField(blank=True, max_length=255)),
                ('subject_template', models.CharField(blank=True, max_length=500)),
                ('body_template', models.TextField(blank=True)),
                ('ai_personalize', models.BooleanField(default=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('campaign', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='steps',
                    to='ai_sdr_agent.sdrcampaign',
                )),
            ],
            options={'db_table': 'sdr_campaign_step', 'ordering': ['step_order']},
        ),
        migrations.CreateModel(
            name='SDRCampaignEnrollment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(
                    choices=[
                        ('active', 'Active'), ('paused', 'Paused'), ('replied', 'Replied'),
                        ('completed', 'Completed'), ('unsubscribed', 'Unsubscribed'), ('bounced', 'Bounced'),
                    ],
                    default='active', max_length=20,
                )),
                ('current_step', models.IntegerField(default=0)),
                ('next_action_at', models.DateTimeField(blank=True, null=True)),
                ('replied_at', models.DateTimeField(blank=True, null=True)),
                ('reply_content', models.TextField(blank=True)),
                ('reply_sentiment', models.CharField(blank=True, max_length=20)),
                ('enrolled_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('campaign', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='enrollments',
                    to='ai_sdr_agent.sdrcampaign',
                )),
                ('lead', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='campaign_enrollments',
                    to='ai_sdr_agent.sdrlead',
                )),
            ],
            options={
                'db_table': 'sdr_campaign_enrollment',
                'ordering': ['-enrolled_at'],
                'unique_together': {('campaign', 'lead')},
            },
        ),
        migrations.CreateModel(
            name='SDROutreachLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('step_order', models.IntegerField(default=1)),
                ('action_type', models.CharField(max_length=30)),
                ('status', models.CharField(
                    choices=[('sent', 'Sent'), ('failed', 'Failed'), ('skipped', 'Skipped')],
                    default='sent', max_length=20,
                )),
                ('subject_sent', models.CharField(blank=True, max_length=500)),
                ('body_sent', models.TextField(blank=True)),
                ('error_message', models.TextField(blank=True)),
                ('sent_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('enrollment', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='logs',
                    to='ai_sdr_agent.sdrcampaignenrollment',
                )),
                ('step', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to='ai_sdr_agent.sdrcampaignstep',
                )),
            ],
            options={'db_table': 'sdr_outreach_log', 'ordering': ['-created_at']},
        ),
    ]
