# CRM credentials (the HubSpot key, or the Salesforce user name, password and
# secret) were stored in clear text. They are now kept encrypted, as
# {"enc": "<Fernet token>"} (CRMIntegration.set_credentials). This encrypts the
# rows already saved. Reads accept both shapes, so it is safe to run twice.
#
# Not reversed: writing the passwords back in clear text is what this stops.

import json

from django.db import migrations


def encrypt_saved_credentials(apps, schema_editor):
    from core.crypto_utils import encrypt_secret
    CRMIntegration = apps.get_model('crm_sync_agent', 'CRMIntegration')
    for integration in CRMIntegration.objects.all():
        stored = integration.credentials or {}
        if not stored or set(stored) == {'enc'}:
            continue
        CRMIntegration.objects.filter(pk=integration.pk).update(
            credentials={'enc': encrypt_secret(json.dumps(stored))})


class Migration(migrations.Migration):

    dependencies = [
        ('crm_sync_agent', '0003_crmintegration_limit_message_and_more'),
    ]

    operations = [
        migrations.RunPython(encrypt_saved_credentials, migrations.RunPython.noop),
    ]
