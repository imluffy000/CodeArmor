"""Symmetric encryption for GitHub access tokens held at rest.

The encryption key is deliberately separate from SESSION_SECRET: rotating a
leaked session secret should not make every stored token undecryptable, and
a leaked session secret should not hand an attacker the tokens.

Set TOKEN_ENCRYPTION_KEY to a Fernet key:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

To rotate: move the current value to TOKEN_ENCRYPTION_KEY_OLD, put the new key
in TOKEN_ENCRYPTION_KEY, and run `python -m app.scripts.reencrypt_tokens`.
Old ciphertext keeps decrypting in the meantime; new writes use the new key.
"""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.core.config import (
    SESSION_SECRET,
    TOKEN_ENCRYPTION_KEY,
    TOKEN_ENCRYPTION_KEY_OLD,
)


class TokenDecryptionError(RuntimeError):
    """Stored ciphertext could not be decrypted with any configured key."""


def _derived_legacy_key() -> bytes:
    """The pre-TOKEN_ENCRYPTION_KEY scheme, kept so existing rows still open."""
    return base64.urlsafe_b64encode(hashlib.sha256(SESSION_SECRET.encode()).digest())


def _build_fernet() -> MultiFernet:
    # Order matters: the first key encrypts, all keys are tried on decrypt.
    keys: list[bytes] = []
    if TOKEN_ENCRYPTION_KEY:
        keys.append(TOKEN_ENCRYPTION_KEY.encode())
    if TOKEN_ENCRYPTION_KEY_OLD:
        keys.append(TOKEN_ENCRYPTION_KEY_OLD.encode())
    keys.append(_derived_legacy_key())
    return MultiFernet([Fernet(key) for key in keys])


_fernet = _build_fernet()


def encrypt_token(token: str) -> str:
    return _fernet.encrypt(token.encode()).decode()


def decrypt_token(encrypted: str) -> str:
    try:
        return _fernet.decrypt(encrypted.encode()).decode()
    except InvalidToken as exc:
        # Never echo the ciphertext - it is the secret.
        raise TokenDecryptionError(
            "Stored GitHub token could not be decrypted. The encryption key "
            "changed; the user must sign in again."
        ) from exc


def rotate_token(encrypted: str) -> str:
    """Re-encrypt existing ciphertext under the current primary key."""
    return _fernet.rotate(encrypted.encode()).decode()
