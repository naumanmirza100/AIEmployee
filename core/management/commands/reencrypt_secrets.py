"""Re-encrypt every stored API key with FIELD_ENCRYPTION_KEY.

    python manage.py reencrypt_secrets --check   # report only, writes nothing
    python manage.py reencrypt_secrets           # re-encrypt

Reads with every configured key (FIELD_ENCRYPTION_KEY, FIELD_ENCRYPTION_KEY_FALLBACKS
and the SECRET_KEY-derived key) and writes with FIELD_ENCRYPTION_KEY. Prints counts
and row ids only — never a key.

Run it after setting FIELD_ENCRYPTION_KEY, and after every rotation. Once --check
reports no 'older' rows, SECRET_KEY and any fallback keys can be changed or removed.
See core/crypto_utils.py.
"""
from cryptography.fernet import InvalidToken
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.crypto_utils import configured_keys, reencrypt_secret, secret_state
from core.models import CompanyAPIKey, PlatformAPIKey

MODELS = (CompanyAPIKey, PlatformAPIKey)


class Command(BaseCommand):
    help = 'Re-encrypt stored API keys with FIELD_ENCRYPTION_KEY (use --check to only report).'

    def add_arguments(self, parser):
        parser.add_argument('--check', action='store_true',
                            help='Report how each stored key is encrypted; change nothing.')

    def handle(self, *args, **opts):
        try:
            primary, _ = configured_keys()
            rows = self._inventory()
        except ValueError as exc:
            # Fernet() rejects a malformed key.
            raise CommandError(f'A configured encryption key is not a valid Fernet key: {exc}')

        self._report(rows)
        unreadable = [(label, pk) for label, pk, state in rows if state == 'unreadable']
        older = [(label, pk) for label, pk, state in rows if state == 'older']

        if opts['check']:
            if older and not primary:
                self.stdout.write('FIELD_ENCRYPTION_KEY is not set, so there is nothing to '
                                  're-encrypt to yet.')
            return

        if not primary:
            raise CommandError('FIELD_ENCRYPTION_KEY is not set. Set it (the same value on every '
                               'machine using this database) and run this again.')
        if not older:
            self.stdout.write(self.style.SUCCESS('Nothing to do: every readable key already '
                                                 'uses FIELD_ENCRYPTION_KEY.'))
        else:
            by_model = {m._meta.label: m for m in MODELS}
            with transaction.atomic():
                for label, pk in older:
                    model = by_model[label]
                    current = model.objects.filter(pk=pk).values_list('encrypted_key', flat=True).first()
                    if not current:
                        continue
                    # .update(): re-encrypting isn't an edit, so no signals and
                    # updated_at stays as it was.
                    model.objects.filter(pk=pk).update(encrypted_key=reencrypt_secret(current))
            self.stdout.write(self.style.SUCCESS(f'Re-encrypted {len(older)} key(s).'))

        if unreadable:
            self.stdout.write(self.style.WARNING(
                f'{len(unreadable)} key(s) could not be read with any configured key and were '
                'left as they are: ' + ', '.join(f'{label} #{pk}' for label, pk in unreadable)
                + '. Add the key they were encrypted with to FIELD_ENCRYPTION_KEY_FALLBACKS and '
                'run this again, or enter those API keys again.'))

    def _inventory(self):
        rows = []
        for model in MODELS:
            for pk, ciphertext in model.objects.values_list('pk', 'encrypted_key').order_by('pk'):
                try:
                    state = secret_state(ciphertext)
                except InvalidToken:
                    state = 'unreadable'
                rows.append((model._meta.label, pk, state))
        return rows

    def _report(self, rows):
        for model in MODELS:
            label = model._meta.label
            counts = {}
            for row_label, _pk, state in rows:
                if row_label == label:
                    counts[state] = counts.get(state, 0) + 1
            summary = ', '.join(f'{n} {state}' for state, n in sorted(counts.items())) or 'no rows'
            self.stdout.write(f'{label}: {summary}')
        self.stdout.write('  current = encrypted with FIELD_ENCRYPTION_KEY (or the SECRET_KEY '
                          'key, if FIELD_ENCRYPTION_KEY is unset)')
        self.stdout.write('  older = readable only with a fallback / the SECRET_KEY key; '
                          're-encrypted by this command')
