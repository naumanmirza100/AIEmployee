from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0116_agent_choices_kept_in_the_table'),
    ]

    operations = [
        migrations.AddField(
            model_name='company',
            name='pm_auto_confirm',
            field=models.BooleanField(
                default=False,
                help_text='Make projects, tasks and meetings asked for in the PM chat without asking to confirm.'),
        ),
    ]
