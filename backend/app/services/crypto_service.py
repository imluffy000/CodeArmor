"""Symmetric encryption for stored GitHub tokens.

Uses Fernet with a key derived from SESSION_SECRET so no extra env var is needed.
"""
import base64
import hashlib

from cryptography.fernet import Fernet

from app.core.config import SESSION_SECRET

_key = base64.urlsafe_b64encode(hashlib.sha256(SESSION_SECRET.encode()).digest())
_fernet = Fernet(_key)


def encrypt_token(token: str) -> str:
    return _fernet.encrypt(token.encode()).decode()


def decrypt_token(encrypted: str) -> str:
    return _fernet.decrypt(encrypted.encode()).decode()
