from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('data_analyst_agent', '0007_question_hidden_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='dataquestion',
            name='chart',
            field=models.JSONField(blank=True, null=True),
        ),
    ]
