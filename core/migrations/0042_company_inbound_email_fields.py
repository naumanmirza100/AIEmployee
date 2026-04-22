from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0041_company_frontline_widget_config'),
        # Also depend on the parallel leaf so this migration unifies the graph.
        ('core', '0039_merge_20260415_1021'),
    ]

    operations = [
        migrations.AddField(
            model_name='company',
            name='support_inbox_slug',
            field=models.CharField(blank=True, db_index=True, help_text='Unique slug for inbound email routing (e.g. "acme" → support+acme@<domain>).', max_length=64, null=True, unique=True),
        ),
        migrations.AddField(
            model_name='company',
            name='support_from_email',
            field=models.EmailField(blank=True, default='', help_text='Outbound "From" address for ticket replies. Falls back to DEFAULT_FROM_EMAIL.', max_length=254),
        ),
        migrations.AddField(
            model_name='company',
            name='inbound_email_config',
            field=models.JSONField(blank=True, default=dict, help_text='Per-tenant inbound/outbound email config: {"reply_to": "...", "signature_html": "..."}.'),
        ),
    ]
