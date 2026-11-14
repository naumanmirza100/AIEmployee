from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('data_analyst_agent', '0006_sql_server'),
    ]

    operations = [
        migrations.AddField(
            model_name='dataquestion',
            name='hidden_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
