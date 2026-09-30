"""Encrypted-at-rest model field for SDR credentials.

Uses the project's existing key management (core/crypto_utils.py):
FIELD_ENCRYPTION_KEY, FIELD_ENCRYPTION_KEY_FALLBACKS, and the SECRET_KEY-derived
key as a last resort. Nothing new to configure.

Python code sees plaintext (``campaign.smtp_password`` is the password); the
database only ever holds a Fernet token. Legacy plaintext rows are still read
correctly, and are encrypted the next time they are written (the data migration
does that for existing rows).
"""
import logging

from cryptography.fernet import InvalidToken
from django.db import models

from core.crypto_utils import decryption_fernet, encrypt_secret

logger = logging.getLogger(__name__)

# Every Fernet token starts with the base64 of its version byte + timestamp.
_TOKEN_PREFIX = 'gAAAA'


def looks_encrypted(value: str) -> bool:
    return isinstance(value, str) and value.startswith(_TOKEN_PREFIX)


def decrypt_or_passthrough(value: str) -> str:
    """Plaintext for a stored value: decrypts tokens, passes legacy plaintext through."""
    if not value or not looks_encrypted(value):
        return value
    try:
        return decryption_fernet().decrypt(value.encode('utf-8')).decode('utf-8')
    except InvalidToken:
        # Either a (very unlikely) real password that starts with the token prefix,
        # or a value encrypted with a key this server no longer has. Returning it
        # unchanged keeps the first case working; the second fails at SMTP login.
        logger.error(
            "A stored SDR credential looks encrypted but no configured key can read it. "
            "Check FIELD_ENCRYPTION_KEY / FIELD_ENCRYPTION_KEY_FALLBACKS, or enter it again."
        )
        return value


class EncryptedCharField(models.CharField):
    """CharField stored as a Fernet token; plaintext in Python."""

    description = "Encrypted string"

    def from_db_value(self, value, expression, connection):
        return decrypt_or_passthrough(value)

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if not value:
            return value
        return encrypt_secret(value)
