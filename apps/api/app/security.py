"""Password hashing and opaque token helpers.

Argon2id for passwords (OWASP-recommended default). Session/reset/invite
tokens are high-entropy random strings; only their SHA-256 hash is
persisted, so a database read alone never yields a usable credential.
"""

from __future__ import annotations

import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_hasher = PasswordHasher()


def hash_password(plain_password: str) -> str:
    return _hasher.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return _hasher.verify(hashed_password, plain_password)
    except VerifyMismatchError:
        return False


def generate_token(num_bytes: int = 32) -> str:
    return secrets.token_urlsafe(num_bytes)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
