from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('Frontline_agent', '0024_ticket_messages_and_attachments'),
        ('core', '0042_company_inbound_email_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='Contact',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('email', models.EmailField(help_text='Stored lowercased. Unique within a company.', max_length=254)),
                ('name', models.CharField(blank=True, default='', max_length=255)),
                ('phone', models.CharField(blank=True, default='', max_length=40)),
                ('tags', models.JSONField(blank=True, default=list, help_text='List of free-form tag strings.')),
                ('custom_fields', models.JSONField(blank=True, default=dict, help_text='Tenant-defined attributes: {key: value}.')),
                ('first_seen_at', models.DateTimeField(blank=True, help_text='First time we saw this email (inbound msg or manual create).', null=True)),
                ('last_seen_at', models.DateTimeField(blank=True, help_text='Most recent inbound message from this email.', null=True)),
                ('total_tickets_count', models.IntegerField(default=0, help_text='Denormalized count of tickets linked to this contact.')),
                ('external_id', models.CharField(blank=True, db_index=True, default='', max_length=128)),
                ('external_source', models.CharField(blank=True, default='', help_text="e.g. 'hubspot', 'salesforce'.", max_length=40)),
                ('external_synced_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='contacts', to='core.company')),
            ],
            options={
                'ordering': ['-last_seen_at', '-created_at'],
                'unique_together': {('company', 'email')},
            },
        ),
        migrations.AddIndex(
            model_name='contact',
            index=models.Index(fields=['company', 'last_seen_at'], name='fl_contact_co_last_idx'),
        ),
        migrations.AddIndex(
            model_name='contact',
            index=models.Index(fields=['company', 'email'], name='fl_contact_co_em_idx'),
        ),
        migrations.AddIndex(
            model_name='contact',
            index=models.Index(fields=['external_source', 'external_id'], name='fl_contact_ext_idx'),
        ),
        migrations.AddField(
            model_name='ticket',
            name='contact',
            field=models.ForeignKey(blank=True, help_text='First-class customer record for this ticket.',
                                    null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name='tickets', to='Frontline_agent.contact'),
        ),
        migrations.AddIndex(
            model_name='ticket',
            index=models.Index(fields=['contact', 'created_at'], name='fl_ticket_contact_ct_idx'),
        ),
    ]
