"""Symmetric encryption for stored API keys (CompanyAPIKey, PlatformAPIKey).

Keys (audit item SEC-5)
-----------------------
FIELD_ENCRYPTION_KEY            New values are encrypted with this Fernet key.
FIELD_ENCRYPTION_KEY_FALLBACKS  Comma-separated older Fernet keys. Still accepted
                                for decryption, never used to encrypt.
key derived from SECRET_KEY     Always accepted for decryption: everything stored
                                before FIELD_ENCRYPTION_KEY existed was encrypted
                                with it. Used to encrypt only while
                                FIELD_ENCRYPTION_KEY is unset — the old behaviour.

Why separate: with the key derived from SECRET_KEY, changing SECRET_KEY made every
stored key unreadable, and decryption failures returned "" silently, surfacing as
"no API key available" in every agent.

Every machine that uses the same database must have the same
FIELD_ENCRYPTION_KEY (and fallbacks), or it can't read what the others wrote.

Switching over:
    1. put the same FIELD_ENCRYPTION_KEY in every .env that uses this database
       python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    2. python manage.py reencrypt_secrets --check    # reports only
    3. python manage.py reencrypt_secrets            # rewrites stored keys with it
    4. SECRET_KEY can now change (DJANGO_SECRET_KEY) without losing stored keys.

Rotating later: new key in FIELD_ENCRYPTION_KEY, previous one in
FIELD_ENCRYPTION_KEY_FALLBACKS, run reencrypt_secrets, then drop the fallback.
"""
import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings

logger = logging.getLogger(__name__)


def _secret_key_fernet_key() -> bytes:
    digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def configured_keys():
    """(FIELD_ENCRYPTION_KEY or '', [fallback keys]) as configured in settings."""
    primary = (getattr(settings, "FIELD_ENCRYPTION_KEY", "") or "").strip()
    fallbacks = [k.strip() for k in
                 (getattr(settings, "FIELD_ENCRYPTION_KEY_FALLBACKS", "") or "").split(",")
                 if k.strip()]
    return primary, fallbacks


def encryption_fernet() -> Fernet:
    """The one key new values are encrypted with."""
    primary, _ = configured_keys()
    return Fernet(primary.encode("utf-8") if primary else _secret_key_fernet_key())


def decryption_fernet() -> MultiFernet:
    """Every accepted key, the encryption key first (so `rotate()` re-encrypts with it)."""
    primary, fallbacks = configured_keys()
    keys = [k.encode("utf-8") for k in ([primary] if primary else []) + fallbacks]
    keys.append(_secret_key_fernet_key())
    unique = list(dict.fromkeys(keys))
    return MultiFernet([Fernet(k) for k in unique])


def encrypt_secret(plaintext: str) -> str:
    if plaintext is None or plaintext == "":
        return ""
    return encryption_fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(ciphertext: str) -> str:
    if not ciphertext:
        return ""
    try:
        return decryption_fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        # Still "" for callers (they treat it as "no key"), but never silently:
        # this means the key that encrypted it is no longer configured.
        logger.error(
            "A stored API key could not be decrypted with any configured key. It was "
            "encrypted with a key this server no longer has: SECRET_KEY changed, "
            "FIELD_ENCRYPTION_KEY differs from the other machines using this database, "
            "or a key was rotated without re-encrypting. Put the old key in "
            "FIELD_ENCRYPTION_KEY_FALLBACKS and run `manage.py reencrypt_secrets`, "
            "or enter the API key again."
        )
        return ""


def secret_state(ciphertext: str) -> str:
    """How a stored value relates to the configured keys, without revealing it:
    'empty', 'current' (encrypted with the encryption key), 'older' (readable
    only with a fallback or the SECRET_KEY-derived key) or 'unreadable'."""
    if not ciphertext:
        return "empty"
    token = ciphertext.encode("utf-8")
    try:
        encryption_fernet().decrypt(token)
        return "current"
    except InvalidToken:
        pass
    try:
        decryption_fernet().decrypt(token)
        return "older"
    except InvalidToken:
        return "unreadable"


def reencrypt_secret(ciphertext: str) -> str:
    """Re-encrypt a stored value with the encryption key. Raises InvalidToken
    if no configured key can read it."""
    return decryption_fernet().rotate(ciphertext.encode("utf-8")).decode("utf-8")


def mask_secret(plaintext: str, visible_prefix: int = 4, visible_suffix: int = 4) -> str:
    """Return `sk-12****cdef`-style preview safe to show in UI."""
    if not plaintext:
        return ""
    if len(plaintext) <= visible_prefix + visible_suffix:
        return "*" * len(plaintext)
    return f"{plaintext[:visible_prefix]}{'*' * 8}{plaintext[-visible_suffix:]}"
