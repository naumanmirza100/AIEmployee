from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('Frontline_agent', '0025_contact_and_ticket_contact_fk'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='ticket',
            name='handoff_status',
            field=models.CharField(
                choices=[
                    ('none', 'None'),
                    ('pending', 'Pending agent'),
                    ('accepted', 'Accepted by agent'),
                    ('resolved', 'Resolved by agent'),
                ],
                db_index=True, default='none', max_length=12,
                help_text='Hand-off lifecycle state.',
            ),
        ),
        migrations.AddField(
            model_name='ticket',
            name='handoff_reason',
            field=models.CharField(
                blank=True, default='',
                choices=[
                    ('', 'N/A'),
                    ('low_confidence', 'Low QA confidence'),
                    ('customer_requested', 'Customer asked for a human'),
                    ('manual_escalation', 'Agent escalated manually'),
                    ('sla_risk', 'SLA at risk'),
                ],
                max_length=24, help_text='Why the hand-off was triggered.',
            ),
        ),
        migrations.AddField(
            model_name='ticket',
            name='handoff_context',
            field=models.JSONField(blank=True, default=dict,
                                   help_text='Snapshot at hand-off: question, AI answer, confidence, etc.'),
        ),
        migrations.AddField(
            model_name='ticket',
            name='handoff_requested_at',
            field=models.DateTimeField(blank=True, null=True,
                                       help_text='When the ticket first entered pending hand-off.'),
        ),
        migrations.AddField(
            model_name='ticket',
            name='handoff_accepted_at',
            field=models.DateTimeField(blank=True, null=True,
                                       help_text='When an agent claimed the hand-off.'),
        ),
        migrations.AddField(
            model_name='ticket',
            name='handoff_accepted_by',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='frontline_handoffs_accepted',
                to=settings.AUTH_USER_MODEL,
                help_text='Agent who accepted the hand-off.',
            ),
        ),
        migrations.AddIndex(
            model_name='ticket',
            index=models.Index(fields=['handoff_status', 'handoff_requested_at'],
                               name='fl_ticket_handoff_idx'),
        ),
    ]
