from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('recruitment_agent', '0031_cvrecord_job_application_link'),
    ]

    operations = [
        migrations.CreateModel(
            name='CVRecordDecisionLog',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('from_decision', models.CharField(blank=True, max_length=32, null=True)),
                ('to_decision', models.CharField(max_length=32)),
                ('changed_by', models.CharField(blank=True, help_text='Email/name of the user who made the change', max_length=255, null=True)),
                ('source', models.CharField(choices=[('AI', 'AI Processing'), ('Manual', 'Manual Override')], default='Manual', max_length=20)),
                ('changed_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('cv_record', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='decision_logs', to='recruitment_agent.cvrecord')),
            ],
            options={
                'verbose_name': 'CV Record Decision Log',
                'verbose_name_plural': 'CV Record Decision Logs',
                'db_table': 'ppp_recruitment_agent_cvrecorddecisionlog',
                'ordering': ['changed_at'],
            },
        ),
    ]
