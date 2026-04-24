from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Frontline_agent', '0026_ticket_handoff_fields'),
        # Unify with the index-rename leaf so the migration graph has a single head.
        ('Frontline_agent', '0019_rename_fl_llm_usage_co_ct_idx_frontline_a_company_2538e5_idx_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='frontlineworkflowexecution',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', 'Pending'),
                    ('in_progress', 'In Progress'),
                    ('paused', 'Paused (waiting)'),
                    ('completed', 'Completed'),
                    ('failed', 'Failed'),
                    ('cancelled', 'Cancelled'),
                    ('awaiting_approval', 'Awaiting Approval'),
                    ('rejected', 'Rejected'),
                ],
                default='pending',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='frontlineworkflowexecution',
            name='resume_at',
            field=models.DateTimeField(
                blank=True, db_index=True, null=True,
                help_text='When a paused execution is due to resume.',
            ),
        ),
        migrations.AddField(
            model_name='frontlineworkflowexecution',
            name='pause_state',
            field=models.JSONField(
                blank=True, default=dict,
                help_text='Serialized remaining-work snapshot for a paused execution.',
            ),
        ),
    ]
