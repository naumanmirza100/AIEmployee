from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('recruitment_agent', '0032_cvrecorddecisionlog'),
    ]

    operations = [
        migrations.AddField(
            model_name='cvrecord',
            name='s3_key',
            field=models.CharField(
                blank=True,
                max_length=1024,
                null=True,
                help_text='S3 object key for the original CV file (cvs/{company_id}/{job_id}/{filename})',
            ),
        ),
    ]
