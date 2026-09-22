"""Re-encrypt every stored GitHub token under the current primary key.

Run this after a *planned* key rotation:

    1. Move the current TOKEN_ENCRYPTION_KEY to TOKEN_ENCRYPTION_KEY_OLD
    2. Put a freshly generated key in TOKEN_ENCRYPTION_KEY
    3. python -m app.scripts.reencrypt_tokens
    4. Remove TOKEN_ENCRYPTION_KEY_OLD

Old ciphertext keeps decrypting in the meantime, so there is no downtime and
nobody is forced to sign in again.

If the ciphertext was EXPOSED rather than merely aged, this is the wrong tool:
re-encrypting a token an attacker may already hold changes nothing. Use
`python -m app.scripts.reset_exposed_tokens` instead, and revoke the grant on
GitHub first.
"""
import sys

from app.core.logging import logger
from app.db.database import close_db, init_db
from app.db.models import User
from app.services.crypto_service import TokenDecryptionError, rotate_token


def main() -> int:
    init_db()
    rotated = failed = 0

    try:
        for user in User.select():
            try:
                user.access_token_encrypted = rotate_token(user.access_token_encrypted)
                user.save()
                rotated += 1
            except (TokenDecryptionError, Exception) as exc:  # noqa: B014
                failed += 1
                logger.error("Could not re-encrypt the token for user %s: %s", user.id, exc)
    finally:
        close_db()

    print(f"Re-encrypted {rotated} token(s); {failed} failed.")
    if failed:
        print("Users whose token failed must sign in again to restore access.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
