from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0039_merge_20260408_1204'),
    ]

    operations = [
        migrations.AddField(
            model_name='company',
            name='frontline_allowed_origins',
            field=models.TextField(blank=True, default=''),
        ),
    ]
