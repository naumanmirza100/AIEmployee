from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('recruitment_agent', '0036_remove_old_candidate_index_state'),
    ]

    operations = [
        migrations.AddField(
            model_name='jobapplication',
            name='access_token',
            field=models.CharField(blank=True, max_length=64, null=True, unique=True),
        ),
    ]
