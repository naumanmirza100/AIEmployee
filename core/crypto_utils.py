"""Symmetric encryption for sensitive company secrets (API keys).

Fernet key is derived from Django SECRET_KEY so no extra env var is required.
If you ever rotate SECRET_KEY, existing encrypted blobs become unreadable —
re-encrypt with a management command before rotating.
"""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(plaintext: str) -> str:
    if plaintext is None or plaintext == "":
        return ""
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(ciphertext: str) -> str:
    if not ciphertext:
        return ""
    try:
        return _fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return ""


def mask_secret(plaintext: str, visible_prefix: int = 4, visible_suffix: int = 4) -> str:
    """Return `sk-12****cdef`-style preview safe to show in UI."""
    if not plaintext:
        return ""
    if len(plaintext) <= visible_prefix + visible_suffix:
        return "*" * len(plaintext)
    return f"{plaintext[:visible_prefix]}{'*' * 8}{plaintext[-visible_suffix:]}"
