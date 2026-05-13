from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ai_sdr_agent', '0003_meetings_imap'),
    ]

    operations = [
        migrations.AddField(
            model_name='sdrcampaign',
            name='start_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='sdrcampaign',
            name='end_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='sdrcampaign',
            name='auto_check_replies',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='sdrcampaign',
            name='last_replies_checked_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='sdrcampaign',
            name='activated_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='sdrcampaign',
            name='status',
            field=models.CharField(
                choices=[
                    ('draft', 'Draft'),
                    ('scheduled', 'Scheduled'),
                    ('active', 'Active'),
                    ('paused', 'Paused'),
                    ('completed', 'Completed'),
                ],
                default='draft',
                max_length=20,
            ),
        ),
    ]
