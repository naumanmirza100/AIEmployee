from django.db import migrations


def cold_leads_back_to_new(apps, schema_editor):
    # Scoring used to mark every lead "qualified", a cold one included (SDRLead.set_status_from_score).
    SDRLead = apps.get_model('ai_sdr_agent', 'SDRLead')
    SDRLead.objects.filter(status='qualified', temperature='cold').update(status='new')


class Migration(migrations.Migration):

    dependencies = [
        ('ai_sdr_agent', '0032_sdrlead_enrichment_attempts_and_more'),
    ]

    operations = [
        migrations.RunPython(cold_leads_back_to_new, migrations.RunPython.noop),
    ]
