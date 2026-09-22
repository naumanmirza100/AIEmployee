"""Company-leading indexes for the query shapes the views actually use
(FL-PERF-12).

Every declared index started with something other than `company`
— `(status, priority)`, `(created_at)`, `(handoff_status, handoff_requested_at)`
— while every tenant-scoped query filters on `company` first and then sorts.
MariaDB could use one single-column index and then sorted the rest by hand, and
the hand-off index was cross-tenant: one tenant's queue walked every tenant's
pending hand-offs before filtering.

Index creation locks the table briefly. These are small, but on a busy
deployment run them in a quiet window.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Frontline_agent', '0045_ticket_state_constraints'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='ticket',
            index=models.Index(fields=['company', '-created_at'],
                               name='fl_ticket_company_created'),
        ),
        migrations.AddIndex(
            model_name='ticket',
            index=models.Index(fields=['company', 'created_by', '-created_at'],
                               name='fl_ticket_company_creator'),
        ),
        migrations.AddIndex(
            model_name='ticket',
            index=models.Index(fields=['company', 'handoff_status', '-handoff_requested_at'],
                               name='fl_ticket_company_handoff'),
        ),
        migrations.AddIndex(
            model_name='ticket',
            index=models.Index(fields=['company', 'category', '-created_at'],
                               name='fl_ticket_company_category'),
        ),
        migrations.AddIndex(
            model_name='document',
            index=models.Index(fields=['company', '-created_at'],
                               name='fl_document_company_created'),
        ),
    ]
