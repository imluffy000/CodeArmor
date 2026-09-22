"""Delete every stored GitHub token after an exposure, forcing re-authorization.

Use this when ciphertext has leaked (for example: a database file was committed
to a public repository). Re-encrypting is not a remedy there - the attacker may
already hold the plaintext, and rotating your key does not reach into their copy.

Order of operations, and the first step is the one that matters:

    1. Revoke the OAuth grant on GitHub:
       Settings > Applications > Authorized OAuth Apps > CodeArmor > Revoke.
       This is what actually invalidates the leaked tokens.
    2. Rotate GITHUB_CLIENT_SECRET, SESSION_SECRET and TOKEN_ENCRYPTION_KEY.
    3. python -m app.scripts.reset_exposed_tokens
    4. Purge the file from git history and force-push.

This clears the stored token and invalidates every session. Connected
repositories and stored reviews are kept, and come back when the user signs in
again. Pass --purge-users to delete the user rows outright instead.
"""
import argparse
import sys

from app.db.database import close_db, init_db
from app.db.models import User


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--purge-users",
        action="store_true",
        help="Delete user rows entirely, cascading repositories and reviews.",
    )
    parser.add_argument(
        "--yes", action="store_true", help="Skip the confirmation prompt."
    )
    args = parser.parse_args()

    init_db()
    try:
        # pylint: disable=no-value-for-parameter  # peewee binds the database
        total = User.select().count()
        if total == 0:
            print("No users stored; nothing to do.")
            return 0

        action = "DELETE" if args.purge_users else "invalidate the tokens of"
        if not args.yes:
            print(f"About to {action} {total} user(s). Everyone must sign in again.")
            if input("Type 'yes' to continue: ").strip().lower() != "yes":
                print("Aborted.")
                return 1

        if args.purge_users:
            for user in User.select():
                user.delete_instance(recursive=True)
            print(f"Deleted {total} user(s) and everything belonging to them.")
        else:
            for user in User.select():
                # Not a valid Fernet token, so any use raises
                # TokenDecryptionError and the API answers 401 with
                # "sign in again" rather than a 500.
                user.access_token_encrypted = "revoked"
                user.session_version = (user.session_version or 1) + 1
                user.save()
            print(f"Invalidated the stored token and all sessions for {total} user(s).")

        print("\nDid you revoke the OAuth grant on GitHub? That is the step that")
        print("actually stops a leaked token from working.")
        return 0
    finally:
        close_db()


if __name__ == "__main__":
    sys.exit(main())
