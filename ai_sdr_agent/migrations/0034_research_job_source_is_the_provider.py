from django.db import migrations, models


def label_jobs_by_provider(apps, schema_editor):
    # A job was made with the default 'ai_generated' and only took its provider when the search succeeded, so
    # every failed Apify or Apollo search read as AI-generated. Each job's search_params say what was searched.
    SDRLeadResearchJob = apps.get_model('ai_sdr_agent', 'SDRLeadResearchJob')
    for job in SDRLeadResearchJob.objects.filter(source='ai_generated'):
        asked = (job.search_params or {}).get('source')
        job.source = asked if asked in ('apollo', 'apify') else ''
        job.save(update_fields=['source'])


class Migration(migrations.Migration):

    dependencies = [
        ('ai_sdr_agent', '0033_cold_leads_are_not_qualified'),
    ]

    operations = [
        migrations.AlterField(
            model_name='sdrleadresearchjob',
            name='source',
            field=models.CharField(default='', max_length=20),
        ),
        migrations.RunPython(label_jobs_by_provider, migrations.RunPython.noop),
    ]
