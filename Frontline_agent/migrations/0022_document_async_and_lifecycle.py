from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('Frontline_agent', '0021_workflow_timeout_and_versions'),
        ('core', '0040_company_frontline_allowed_origins'),
    ]

    operations = [
        migrations.AddField(
            model_name='document',
            name='processing_status',
            field=models.CharField(
                choices=[('pending', 'Pending'), ('processing', 'Processing'),
                         ('ready', 'Ready'), ('failed', 'Failed')],
                db_index=True, default='ready', max_length=20,
                help_text="Async processing state. Defaults 'ready' for back-compat.",
            ),
        ),
        migrations.AddField(
            model_name='document',
            name='processing_error',
            field=models.TextField(blank=True, default='',
                                   help_text='Last error from background processing.'),
        ),
        migrations.AddField(
            model_name='document',
            name='chunks_processed',
            field=models.IntegerField(default=0,
                                      help_text='Chunks indexed so far (for progress display).'),
        ),
        migrations.AddField(
            model_name='document',
            name='chunks_total',
            field=models.IntegerField(default=0,
                                      help_text='Total chunks to index (for progress display).'),
        ),
        migrations.AddField(
            model_name='document',
            name='version',
            field=models.IntegerField(default=1),
        ),
        migrations.AddField(
            model_name='document',
            name='parent_document',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='revisions', to='Frontline_agent.document',
                help_text='Original document if this is a newer revision.',
            ),
        ),
        migrations.AddField(
            model_name='document',
            name='superseded_by',
            field=models.ForeignKey(
                blank=True, db_index=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='superseded_revisions', to='Frontline_agent.document',
                help_text='Points to the newer revision. Set → excluded from retrieval.',
            ),
        ),
        migrations.AddField(
            model_name='document',
            name='visibility',
            field=models.CharField(
                choices=[('company', 'Company (all users in the company)'),
                         ('private', 'Private (allowed_users only)')],
                default='company', max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='document',
            name='allowed_users',
            field=models.ManyToManyField(
                blank=True, related_name='frontline_accessible_documents',
                to='core.companyuser',
                help_text="When visibility='private', only these users can retrieve the doc.",
            ),
        ),
        migrations.AddField(
            model_name='document',
            name='retention_days',
            field=models.IntegerField(
                blank=True, null=True,
                help_text='Delete this document after N days from created_at. Blank/0 = keep forever.',
            ),
        ),
        migrations.AddIndex(
            model_name='document',
            index=models.Index(fields=['processing_status'], name='fl_doc_proc_status_idx'),
        ),
        migrations.AddIndex(
            model_name='document',
            index=models.Index(fields=['superseded_by'], name='fl_doc_superseded_idx'),
        ),
    ]
