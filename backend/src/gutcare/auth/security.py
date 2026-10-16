"""Authentication cryptography helpers; secrets are provided through deployment settings."""

import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from email_validator import validate_email


def normalize_email(value: str) -> str:
    return validate_email(value, check_deliverability=False).normalized


def email_lookup_hash(email: str, pepper: str) -> str:
    return hmac.new(pepper.encode(), email.encode(), hashlib.sha256).hexdigest()


def _email_encryption_key(encoded_key: str) -> bytes:
    padded = encoded_key + "=" * (-len(encoded_key) % 4)
    key = base64.b64decode(padded, altchars=b"-_", validate=True)
    if len(key) != 32:
        raise ValueError("Email encryption key must decode to 32 bytes")
    return key


def encrypt_email(email: str, encoded_key: str) -> bytes:
    key = _email_encryption_key(encoded_key)
    nonce = secrets.token_bytes(12)
    return nonce + AESGCM(key).encrypt(nonce, email.encode(), None)


def decrypt_email(ciphertext: bytes, encoded_key: str) -> str:
    key = _email_encryption_key(encoded_key)
    if len(ciphertext) < 29:
        raise ValueError("Invalid encrypted email")
    return AESGCM(key).decrypt(ciphertext[:12], ciphertext[12:], None).decode()


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_opaque_token() -> str:
    return secrets.token_urlsafe(48)


def utc_now() -> datetime:
    return datetime.now(UTC)


def expires_after(minutes: int) -> datetime:
    return utc_now() + timedelta(minutes=minutes)
