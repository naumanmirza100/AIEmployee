import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    """Test data on the super admin's page: the demo snapshots and the background runs (27 Nov 2026)."""

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('core', '0125_daily_free_tokens'),
    ]

    operations = [
        migrations.CreateModel(
            name='DemoSnapshot',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.SlugField(max_length=40, unique=True)),
                ('label', models.CharField(max_length=200)),
                ('company_pk', models.IntegerField(help_text='The company id the rows were taken with; loading keeps it.')),
                ('company_name', models.CharField(max_length=255)),
                ('data', models.BinaryField()),
                ('rows', models.IntegerField(default=0)),
                ('made_at', models.DateTimeField()),
                ('password', models.TextField(blank=True, default='')),
                ('loaded_at', models.DateTimeField(blank=True, null=True)),
            ],
            options={'verbose_name': 'Demo snapshot'},
        ),
        migrations.CreateModel(
            name='DemoDataRun',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(choices=[('load', 'Add test data'), ('remove', 'Remove test data')], max_length=10)),
                ('keys', models.JSONField(blank=True, default=list, help_text='Snapshot keys; empty = all.')),
                ('status', models.CharField(choices=[('queued', 'Queued'), ('running', 'Running'), ('done', 'Done'), ('failed', 'Failed')], default='queued', max_length=10)),
                ('done_rows', models.IntegerField(default=0)),
                ('total_rows', models.IntegerField(default=0)),
                ('step', models.CharField(blank=True, default='', max_length=200)),
                ('error', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('finished_at', models.DateTimeField(blank=True, null=True)),
                ('started_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={'verbose_name': 'Demo data run', 'ordering': ['-created_at']},
        ),
    ]
