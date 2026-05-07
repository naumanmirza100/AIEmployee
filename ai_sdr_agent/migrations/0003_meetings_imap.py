from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('ai_sdr_agent', '0002_campaigns'),
        ('core', '0052_merge_20260501_2356'),
    ]

    operations = [
        # Add imap_host, imap_port, calendar_link, meetings_booked to sdr_campaign
        migrations.AddField(
            model_name='sdrcampaign',
            name='imap_host',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name='sdrcampaign',
            name='imap_port',
            field=models.IntegerField(default=993),
        ),
        migrations.AddField(
            model_name='sdrcampaign',
            name='calendar_link',
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name='sdrcampaign',
            name='meetings_booked',
            field=models.IntegerField(default=0),
        ),
        # Create sdr_meeting table
        migrations.CreateModel(
            name='SDRMeeting',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ('title', models.CharField(default='Discovery Call', max_length=255)),
                ('notes', models.TextField(blank=True)),
                ('reply_snippet', models.TextField(blank=True)),
                ('scheduled_at', models.DateTimeField(blank=True, null=True)),
                ('duration_minutes', models.IntegerField(default=30)),
                ('status', models.CharField(
                    choices=[
                        ('pending', 'Pending'),
                        ('scheduled', 'Scheduled'),
                        ('completed', 'Completed'),
                        ('cancelled', 'Cancelled'),
                        ('no_show', 'No Show'),
                    ],
                    default='pending',
                    max_length=20,
                )),
                ('calendar_link', models.CharField(blank=True, max_length=500)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('company_user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='sdr_meetings',
                    to='core.companyuser',
                )),
                ('enrollment', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='meetings',
                    to='ai_sdr_agent.sdrcampaignenrollment',
                )),
                ('lead', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='meetings',
                    to='ai_sdr_agent.sdrlead',
                )),
            ],
            options={
                'db_table': 'sdr_meeting',
                'ordering': ['-created_at'],
            },
        ),
    ]
