from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from .config import get_settings


settings = get_settings()
PREFIX = "enc:v1:"


def _fernet() -> Fernet:
    key = settings.token_encryption_key.strip()
    if not key:
        raise RuntimeError("TOKEN_ENCRYPTION_KEY is not configured")
    return Fernet(key.encode("ascii"))


def encrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    if value.startswith(PREFIX):
        return value
    encrypted = _fernet().encrypt(value.encode("utf-8")).decode("ascii")
    return PREFIX + encrypted


def decrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    if not value.startswith(PREFIX):
        # Transitional compatibility for the single sandbox token created
        # before encrypted-at-rest storage existed. The next successful
        # refresh rewrites it encrypted.
        return value
    token = value[len(PREFIX):]
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError("Stored provider token could not be decrypted") from exc
