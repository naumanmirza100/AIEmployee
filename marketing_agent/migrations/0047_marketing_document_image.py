"""Pictures made for social posts and ad copy, kept with their document (the user's decision of 29 Oct 2026)."""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('marketing_agent', '0046_send_history_email_account'),
    ]

    operations = [
        migrations.CreateModel(
            name='MarketingDocumentImage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('idea', models.TextField(help_text='What the picture shows, as asked for')),
                ('shape', models.CharField(choices=[('square', 'Square'), ('landscape', 'Landscape'),
                                                    ('portrait', 'Portrait')], default='square', max_length=10)),
                ('image', models.FileField(upload_to='marketing/images/%Y/%m/')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('document', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='images',
                                               to='marketing_agent.marketingdocument')),
            ],
            options={
                'db_table': 'ppp_marketingagent_documentimage',
                'ordering': ['created_at'],
            },
        ),
    ]
