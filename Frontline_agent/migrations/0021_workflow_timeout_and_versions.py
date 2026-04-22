from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('Frontline_agent', '0020_notifications_retry_and_quiet_hours'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='frontlineworkflow',
            name='timeout_seconds',
            field=models.IntegerField(default=0, help_text='Max wall-clock seconds for one run. 0 = unlimited.'),
        ),
        migrations.AddField(
            model_name='frontlineworkflow',
            name='version',
            field=models.IntegerField(default=1, help_text='Incremented when the workflow definition is changed.'),
        ),
        migrations.CreateModel(
            name='FrontlineWorkflowVersion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('version', models.IntegerField(help_text='Matches FrontlineWorkflow.version at the time of snapshot.')),
                ('snapshot', models.JSONField(help_text='Frozen copy of name/description/trigger_conditions/steps/requires_approval/is_active/timeout_seconds.')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('saved_by', models.ForeignKey(blank=True, null=True,
                                               on_delete=django.db.models.deletion.SET_NULL,
                                               related_name='frontline_workflow_versions_saved',
                                               to=settings.AUTH_USER_MODEL)),
                ('workflow', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                               related_name='versions',
                                               to='Frontline_agent.frontlineworkflow')),
            ],
            options={
                'ordering': ['-version'],
                'indexes': [models.Index(fields=['workflow', 'version'], name='fl_wf_ver_idx')],
                'unique_together': {('workflow', 'version')},
            },
        ),
    ]
