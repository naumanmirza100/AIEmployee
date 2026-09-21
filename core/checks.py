"""Deployment sanity checks surfaced through `manage.py check`.

These exist because the failure they describe is silent. A Stripe webhook endpoint
with no signing secret returns 503 to every delivery; Stripe retries for about three
days and then drops the event for good. Nothing in the product looks broken — the
Billing tab still reads live from Stripe — but renewals, cancellations and failed
payments stop reaching the database, so subscribers keep access after they stop
paying and cancellations never take effect.

`manage.py check` runs in CI and on every `runserver`, so this is the earliest place
the problem can be made visible.
"""
import os

from django.conf import settings
from django.core.checks import Error as CheckError, Warning as CheckWarning, register

PLACEHOLDERS = {
    'STRIPE_SECRET_KEY': 'sk_test_placeholder',
    'STRIPE_PUBLISHABLE_KEY': 'pk_test_placeholder',
    'STRIPE_WEBHOOK_SECRET': 'whsec_placeholder',
}


@register('stripe')
def check_stripe_configuration(app_configs, **kwargs):
    """Warn when Stripe is half-configured. Silent when it is not configured at all."""
    issues = []

    def is_set(name):
        value = getattr(settings, name, None) or ''
        return bool(value) and value != PLACEHOLDERS[name]

    secret_set = is_set('STRIPE_SECRET_KEY')

    # Stripe is optional. Only complain once the secret key says it is meant to work.
    if not secret_set:
        return issues

    if not is_set('STRIPE_WEBHOOK_SECRET'):
        issues.append(CheckWarning(
            'STRIPE_WEBHOOK_SECRET is not set, but Stripe is configured.',
            hint=(
                'Every webhook will be rejected with 503, so subscription renewals, '
                'cancellations and payment failures will NOT sync — subscribers keep '
                'access after they stop paying. For local dev run `stripe listen '
                '--forward-to localhost:8000/api/modules/stripe-webhook` and use the '
                'secret it prints. For a deployed environment register a destination '
                'in the Stripe dashboard and use ITS secret. See docs/STRIPE.md.'
            ),
            id='stripe.W001',
        ))

    if not is_set('STRIPE_PUBLISHABLE_KEY'):
        issues.append(CheckWarning(
            'STRIPE_PUBLISHABLE_KEY is not set, but Stripe is configured.',
            hint=(
                'The in-app card form cannot load without it; Billing falls back to '
                'the hosted Stripe portal. See docs/STRIPE.md.'
            ),
            id='stripe.W002',
        ))

    frontend_url = getattr(settings, 'FRONTEND_URL', '') or ''
    if not frontend_url:
        issues.append(CheckWarning(
            'FRONTEND_URL is empty, but Stripe is configured.',
            hint=(
                'Checkout success/cancel URLs and the billing portal return URL are '
                'built from it, so they will be malformed and Stripe will reject them. '
                'Set FRONTEND_URL (e.g. http://localhost:3000).'
            ),
            id='stripe.W003',
        ))
    elif frontend_url != frontend_url.strip():
        # settings.py does .rstrip('/'), which does not strip whitespace.
        issues.append(CheckWarning(
            'FRONTEND_URL has leading or trailing whitespace.',
            hint=(
                f'Got {frontend_url!r}. Every Stripe redirect URL is built by '
                'concatenation, so the space ends up inside the URL and Stripe '
                'rejects it. Remove the whitespace in .env.'
            ),
            id='stripe.W004',
        ))

    return issues


@register('security')
def check_encryption_keys(app_configs, **kwargs):
    """Stored API keys (core/crypto_utils.py). A malformed key is an error so the
    server refuses to start, rather than every agent failing with "no API key"."""
    from cryptography.fernet import Fernet

    issues = []
    primary = (getattr(settings, 'FIELD_ENCRYPTION_KEY', '') or '').strip()
    fallbacks = [k.strip() for k in
                 (getattr(settings, 'FIELD_ENCRYPTION_KEY_FALLBACKS', '') or '').split(',') if k.strip()]

    named = [('FIELD_ENCRYPTION_KEY', primary)] + [
        (f'FIELD_ENCRYPTION_KEY_FALLBACKS entry {i + 1}', key) for i, key in enumerate(fallbacks)]
    for name, key in named:
        if not key:
            continue
        try:
            Fernet(key.encode('utf-8'))
        except (ValueError, TypeError):
            issues.append(CheckError(
                f'{name} is not a valid Fernet key.',
                hint=('Generate one with: python -c "from cryptography.fernet import Fernet; '
                      'print(Fernet.generate_key().decode())"'),
                id='crypto.E001',
            ))

    if os.getenv('DJANGO_SECRET_KEY', '').strip() and not primary:
        issues.append(CheckWarning(
            'SECRET_KEY comes from DJANGO_SECRET_KEY, but FIELD_ENCRYPTION_KEY is not set.',
            hint=('Stored API keys are encrypted with a key derived from SECRET_KEY, so any '
                  'saved under the previous SECRET_KEY can no longer be read. Set '
                  'FIELD_ENCRYPTION_KEY (see core/crypto_utils.py) and run '
                  '`manage.py reencrypt_secrets`.'),
            id='crypto.W001',
        ))
    return issues


@register('security', deploy=True)
def check_encryption_key_for_deploy(app_configs, **kwargs):
    """`manage.py check --deploy` only: every command runs with DEBUG off, so
    as a normal check this would print on every local migrate/shell."""
    if (getattr(settings, 'FIELD_ENCRYPTION_KEY', '') or '').strip():
        return []
    if os.getenv('DJANGO_SECRET_KEY', '').strip():
        return []  # crypto.W001 already says it, more urgently
    return [CheckWarning(
        'FIELD_ENCRYPTION_KEY is not set.',
        hint=('Stored API keys are encrypted with a key derived from SECRET_KEY, so changing '
              'SECRET_KEY would make them all unreadable. Set FIELD_ENCRYPTION_KEY (the same '
              'value on every machine using this database) and run '
              '`manage.py reencrypt_secrets`. See core/crypto_utils.py.'),
        id='crypto.W002',
    )]
