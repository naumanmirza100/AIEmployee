import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0118_project_source_fingerprint'),
        ('project_manager_agent', '0017_project_tool_results'),
    ]

    operations = [
        migrations.AddField(
            model_name='pmprojectpilotchat',
            name='project',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name='+', to='core.project'),
        ),
    ]
