"""An alert to the site's team that has gone out, so it goes once across workers (22 Nov 2026, core/ai_spend.py)."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0121_company_assistant'),
    ]

    operations = [
        migrations.CreateModel(
            name='SentAlert',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.CharField(max_length=120, unique=True)),
                ('sent_at', models.DateTimeField(auto_now_add=True)),
            ],
        ),
    ]
