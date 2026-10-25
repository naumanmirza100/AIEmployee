from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0117_company_pm_auto_confirm'),
    ]

    operations = [
        migrations.AddField(
            model_name='project',
            name='source_fingerprint',
            field=models.CharField(blank=True, db_index=True, default='', max_length=64),
        ),
    ]
