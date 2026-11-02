"""Sessions per sign-in (CO-270) and the Google Calendar token encrypted (CO-97).

- A dashboard login may now have a token per device (CompanyUserToken.company_user becomes a
  ForeignKey) and a token remembers when it was last used. Tokens already handed out are marked
  as used now, so nobody is signed out by this release; they end after SESSION_IDLE_DAYS unused.
- Employee and platform logins get their own session table (UserToken). DRF's tokens keep working:
  each becomes a UserToken the first time it is used (api/authentication.py).
- Each company's stored Google refresh token is encrypted, as the CRM passwords are.
"""
from django.conf import settings
from django.db import migrations, models
from django.utils import timezone
import django.db.models.deletion

SEALED_PREFIX = 'gAAAAA'


def mark_tokens_used_now(apps, schema_editor):
    apps.get_model('core', 'CompanyUserToken').objects.filter(last_used__isnull=True).update(last_used=timezone.now())


def seal_google_tokens(apps, schema_editor):
    from core.crypto_utils import encrypt_secret
    Company = apps.get_model('core', 'Company')
    for company in Company.objects.only('id', 'google_calendar_config'):
        cfg = dict(company.google_calendar_config or {})
        token = cfg.get('refresh_token') or ''
        if token and not token.startswith(SEALED_PREFIX):
            cfg['refresh_token'] = encrypt_secret(token)
            Company.objects.filter(pk=company.pk).update(google_calendar_config=cfg)


def unseal_google_tokens(apps, schema_editor):
    from core.crypto_utils import decrypt_secret
    Company = apps.get_model('core', 'Company')
    for company in Company.objects.only('id', 'google_calendar_config'):
        cfg = dict(company.google_calendar_config or {})
        token = cfg.get('refresh_token') or ''
        if token.startswith(SEALED_PREFIX):
            cfg['refresh_token'] = decrypt_secret(token)
            Company.objects.filter(pk=company.pk).update(google_calendar_config=cfg)


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('core', '0119_free_tokens_ten_million'),
    ]

    operations = [
        migrations.AddField(
            model_name='companyusertoken',
            name='last_used',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='companyusertoken',
            name='company_user',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='auth_tokens', to='core.companyuser'),
        ),
        migrations.CreateModel(
            name='UserToken',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.CharField(db_index=True, max_length=40, unique=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('last_used', models.DateTimeField(blank=True, null=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='session_tokens', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'User session token',
            },
        ),
        migrations.RunPython(mark_tokens_used_now, migrations.RunPython.noop),
        migrations.RunPython(seal_google_tokens, unseal_google_tokens),
    ]
