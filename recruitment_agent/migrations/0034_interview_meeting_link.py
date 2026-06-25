from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('recruitment_agent', '0033_cvrecord_s3_key'),
    ]

    operations = [
        migrations.AddField(
            model_name='interview',
            name='meeting_link',
            field=models.URLField(
                blank=True,
                max_length=500,
                null=True,
                help_text='Google Meet link generated when candidate confirms their slot',
            ),
        ),
    ]
