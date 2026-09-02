"""Symmetric encryption for tenant secrets at rest (MASTER PROMPT §43: SMSGate
credentials must be "encrypted/protected at rest").

Derives a Fernet key from JWT_SECRET_KEY via SHA-256 rather than requiring a
second secret to provision — JWT_SECRET_KEY is already required to be a
strong, random 32+ character value in every environment (see config.py), so
this rides on the same guarantee instead of introducing a new one that could
be left unset.
"""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


def _fernet() -> Fernet:
    settings = get_settings()
    digest = hashlib.sha256(settings.jwt_secret_key.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(ciphertext: str) -> str | None:
    """Returns None instead of raising on a corrupt/foreign-key value —
    callers treat that as "not configured" rather than crashing a request."""
    try:
        return _fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        return None


def mask_secret(plaintext: str) -> str:
    if len(plaintext) <= 4:
        return "*" * len(plaintext)
    return "*" * (len(plaintext) - 4) + plaintext[-4:]
