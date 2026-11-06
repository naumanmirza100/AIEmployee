"""Lead categories are going (0037): a lead's industry is its company_industry alone, and the Leads tab filters on
that. A category was mostly a copy of the lead's own industry; where a lead has no industry, its category's name
becomes its industry so the filter still finds it. A lead that has an industry keeps it, even when its category
said something else (a Generate Leads search filed "Medical Practice" leads under "Dentistry"): the ICP filter still
groups the leads a search found."""
from django.db import migrations


def fill_blank_industries(apps, schema_editor):
    SDRLead = apps.get_model('ai_sdr_agent', 'SDRLead')
    for lead in (SDRLead.objects.filter(company_industry='', category__isnull=False)
                 .select_related('category').iterator(chunk_size=500)):
        lead.company_industry = lead.category.name[:255]
        lead.save(update_fields=['company_industry'])


class Migration(migrations.Migration):

    dependencies = [
        ('ai_sdr_agent', '0035_lead_categories'),
    ]

    operations = [
        migrations.RunPython(fill_blank_industries, migrations.RunPython.noop),
    ]
