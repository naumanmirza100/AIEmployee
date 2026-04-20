from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('Frontline_agent', '0017_frontlineworkflow_requires_approval_ticket_entities_and_more'),
        ('core', '0040_company_frontline_allowed_origins'),
    ]

    operations = [
        migrations.CreateModel(
            name='LLMUsage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('agent_name', models.CharField(db_index=True, max_length=100)),
                ('model', models.CharField(db_index=True, max_length=100)),
                ('prompt_tokens', models.IntegerField(default=0)),
                ('completion_tokens', models.IntegerField(default=0)),
                ('total_tokens', models.IntegerField(default=0)),
                ('duration_ms', models.IntegerField(default=0)),
                ('success', models.BooleanField(default=True)),
                ('estimated_cost_usd', models.DecimalField(decimal_places=6, default=0, max_digits=10)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='llm_usage', to='core.company')),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [
                    models.Index(fields=['company', 'created_at'], name='fl_llm_usage_co_ct_idx'),
                    models.Index(fields=['company', 'agent_name', 'created_at'], name='fl_llm_usage_co_ag_ct_idx'),
                ],
            },
        ),
    ]
