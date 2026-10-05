# AI SDR now reads the company's do-not-email list (core.do_not_email) instead
# of working the answer out from its own rows. Copy what it already knows onto
# the list: every address that unsubscribed or hard-bounced.

from django.db import migrations


def backfill(apps, schema_editor):
    DoNotEmail = apps.get_model('core', 'DoNotEmail')
    SDRLead = apps.get_model('ai_sdr_agent', 'SDRLead')
    Enrollment = apps.get_model('ai_sdr_agent', 'SDRCampaignEnrollment')

    found = {}      # (company id, address) -> reason; an unsubscribe wins over a bounce
    unsubscribed = (Enrollment._base_manager.filter(status='unsubscribed')
                    .values_list('campaign__company_user__company_id', 'lead__email'))
    for company_id, email in unsubscribed.iterator():
        email = (email or '').strip().lower()
        if company_id and email:
            found[(company_id, email)] = 'unsubscribed'
    # _base_manager: leads in the bin still must not be emailed if restored.
    bounced = SDRLead._base_manager.filter(email_bounced=True).values_list('company_user__company_id', 'email')
    for company_id, email in bounced.iterator():
        email = (email or '').strip().lower()
        if company_id and email:
            found.setdefault((company_id, email), 'bounced')

    already = set(DoNotEmail.objects.values_list('company_id', 'email'))
    DoNotEmail.objects.bulk_create([
        DoNotEmail(company_id=company_id, email=email, reason=reason, source='ai_sdr')
        for (company_id, email), reason in found.items() if (company_id, email) not in already
    ], batch_size=500)


class Migration(migrations.Migration):

    dependencies = [
        ('ai_sdr_agent', '0025_encrypt_campaign_smtp_password'),
        ('core', '0110_donotemail'),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
