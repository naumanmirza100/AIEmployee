from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hr_agent', '0022_meeting_link_reminders_booked_by'),
    ]

    operations = [
        migrations.AddField(
            model_name='hrdocument',
            name='ai_results',
            field=models.JSONField(blank=True, default=dict,
                                   help_text='Kept AI summaries and extractions, until the text changes.'),
        ),
    ]
