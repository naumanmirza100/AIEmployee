"""Encrypt HubSpot Private App tokens already stored in `Company.hubspot_config`.

FL-SEC-5 in MDS/FRONTLINE_AGENT_AUDIT.md: the token was written to a JSON
column in clear text while every other stored credential went through
`core/crypto_utils.py`. It reads and writes the tenant's whole CRM, so anyone
with a database backup or console had it.

Only values that still look like a raw token (`pat-...`) are touched, so the
migration is safe to re-run. It does not reverse: re-writing plaintext back
into the database is the thing this exists to stop. Reading is
version-tolerant either way — `decrypt_access_token()` passes legacy values
through — so a rollback of the code keeps working against encrypted rows only
while the key is configured.
"""
from django.db import migrations


def encrypt_existing_tokens(apps, schema_editor):
    Company = apps.get_model('core', 'Company')
    from core.crypto_utils import encrypt_secret

    for company in Company.objects.all().only('id', 'hubspot_config').iterator():
        cfg = company.hubspot_config or {}
        if not isinstance(cfg, dict):
            continue
        token = (cfg.get('access_token') or '').strip()
        if not token or not token.startswith(('pat-', 'Bearer ')):
            continue  # empty, or already encrypted
        cfg = dict(cfg)
        cfg['access_token'] = encrypt_secret(token)
        Company.objects.filter(pk=company.pk).update(hubspot_config=cfg)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0103_companyuser_login_user_and_admin'),
    ]

    operations = [
        migrations.RunPython(encrypt_existing_tokens, migrations.RunPython.noop),
    ]
