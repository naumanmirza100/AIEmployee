from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('operations_agent', '0002_increase_file_max_length'),
    ]

    operations = [
        migrations.AddField(
            model_name='operationsdocument',
            name='summary',
            field=models.TextField(blank=True, help_text='AI-generated document summary'),
        ),
        migrations.AddField(
            model_name='operationsdocument',
            name='key_insights',
            field=models.JSONField(blank=True, default=list, help_text='List of key insights/findings'),
        ),
    ]
