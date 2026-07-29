"""Symmetric encryption at rest for stored OAuth tokens (Fernet).

Key resolution: `TOKEN_ENCRYPTION_KEY` if set (a real Fernet key — 32
url-safe base64-encoded bytes, e.g. `Fernet.generate_key()`). If unset, a
key is deterministically derived from `SECRET_KEY` via SHA-256 so the app
still boots and encrypts/decrypts correctly in dev/test without a second
secret to configure (spec §C2 — never crash on a missing optional key).

Deriving from SECRET_KEY is a development convenience, not a production
security boundary: a real deployment must set a dedicated
TOKEN_ENCRYPTION_KEY so rotating SECRET_KEY (e.g. to revoke sessions)
doesn't also silently break every stored OAuth token. See
docs/KNOWN_LIMITATIONS.md.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


def _resolve_key() -> bytes:
    if settings.token_encryption_key:
        return settings.token_encryption_key.encode("utf-8")
    derived = hashlib.sha256(settings.secret_key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(derived)


_fernet = Fernet(_resolve_key())


def encrypt_token(plaintext: str) -> str:
    return _fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_token(ciphertext: str) -> str:
    try:
        return _fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError(
            "Could not decrypt stored token — the encryption key may have changed"
        ) from exc
