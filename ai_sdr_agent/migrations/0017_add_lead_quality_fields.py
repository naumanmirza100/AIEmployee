from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ai_sdr_agent', '0016_meeting_approval_flow'),
    ]

    operations = [
        migrations.AddField(
            model_name='sdrlead',
            name='key_strengths',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='sdrlead',
            name='concerns',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='sdrlead',
            name='outreach_strategy',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='sdrlead',
            name='confidence_score',
            field=models.IntegerField(blank=True, null=True, help_text='Data accuracy confidence 0-100'),
        ),
        migrations.AddField(
            model_name='sdrlead',
            name='data_quality_flags',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
