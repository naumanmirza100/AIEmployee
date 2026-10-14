# A sales campaign gets a switch, "Check the AI's answers before they are sent".
# With it on, the AI's answer to a lead who asks for more is kept as a draft
# (SDRReplyDraft) until a person sends or discards it. New campaigns start with
# it on. Campaigns that exist when this runs keep answering by themselves, so
# nobody's running campaign goes quiet on a release day: the column is added as
# off for them, and only then is the default for new campaigns turned on.

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0113_calendarblock_sales_and_executive_sources'),
        ('ai_sdr_agent', '0029_campaign_paused_reason'),
    ]

    operations = [
        migrations.AddField(
            model_name='sdrcampaign',
            name='review_ai_replies',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='sdrcampaign',
            name='review_ai_replies',
            field=models.BooleanField(default=True),
        ),
        migrations.CreateModel(
            name='SDRReplyDraft',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('lead_reply', models.TextField(blank=True)),
                ('subject', models.CharField(blank=True, max_length=500)),
                ('body', models.TextField(blank=True)),
                ('status', models.CharField(choices=[('pending', 'Waiting to be checked'), ('sending', 'Being sent'), ('sent', 'Sent'), ('discarded', 'Discarded')], default='pending', max_length=20)),
                ('error', models.CharField(blank=True, default='', max_length=500)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('decided_at', models.DateTimeField(blank=True, null=True)),
                ('decided_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='core.companyuser')),
                ('enrollment', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reply_drafts', to='ai_sdr_agent.sdrcampaignenrollment')),
            ],
            options={
                'db_table': 'sdr_reply_draft',
                'ordering': ['-created_at'],
            },
        ),
    ]
