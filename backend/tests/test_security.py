"""The security properties this app must not regress on.

Each test here corresponds to a hole that was live in the previous version.
"""
import pytest
from fastapi.testclient import TestClient

from app.core import config
from app.db.models import Repository, Review, User
from app.main import app
from app.services import rate_limit_service
from app.services.auth_service import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    create_session_token,
    revoke_all_sessions,
)
from app.services.crypto_service import encrypt_token


@pytest.fixture
def client():
    rate_limit_service.reset()
    return TestClient(app)


def sign_in(client: TestClient, user: User) -> str:
    """Attach a valid session and CSRF cookie pair. Returns the CSRF token."""
    client.cookies.set(SESSION_COOKIE, create_session_token(user))
    client.cookies.set(CSRF_COOKIE, "csrf-test-token")
    return "csrf-test-token"


class TestNoAnonymousAccess:
    """A confused deputy: anonymous callers used to borrow the server's token."""

    @pytest.mark.parametrize(
        "method,path",
        [
            ("post", "/reviews"),
            ("get", "/reviews/stream?repo_id=1&pr_number=1"),
            ("get", "/reviews"),
            ("get", "/reviews/1"),
            ("post", "/reviews/chat"),
            ("post", "/reviews/1/publish"),
            ("get", "/repos"),
            ("get", "/repos/available"),
            ("post", "/repos/connect"),
            ("get", "/repos/1/pulls"),
            ("delete", "/repos/1"),
            ("get", "/auth/me"),
        ],
    )
    def test_every_data_endpoint_rejects_an_anonymous_caller(self, client, method, path):
        kwargs = {"json": {}} if method in ("post", "put", "patch") else {}
        response = getattr(client, method)(path, **kwargs)
        assert response.status_code == 401, f"{method.upper()} {path} allowed an anonymous caller"

    def test_no_server_wide_github_token_exists(self):
        # The fallback `token or GITHUB_TOKEN` is what made the deputy possible.
        assert not hasattr(config, "GITHUB_TOKEN")

    def test_health_stays_public(self, client):
        assert client.get("/health").status_code == 200


class TestSessionHandling:
    def test_a_forged_token_signed_with_the_old_default_is_rejected(self, client, user):
        import jwt

        forged = jwt.encode(
            {"sub": str(user.id), "sv": 1, "iss": "codearmor-api", "aud": "codearmor-web",
             "iat": 0, "exp": 9999999999},
            "dev-insecure-secret-change-me",
            algorithm="HS256",
        )
        client.cookies.set(SESSION_COOKIE, forged)
        assert client.get("/auth/me").status_code == 401

    def test_signing_out_invalidates_an_already_issued_cookie(self, client, user):
        token = create_session_token(user)
        client.cookies.set(SESSION_COOKIE, token)
        assert client.get("/auth/me").status_code == 200

        # A copied cookie used to keep working for the full 7-day TTL.
        revoke_all_sessions(user)
        client.cookies.set(SESSION_COOKIE, token)
        assert client.get("/auth/me").status_code == 401

    def test_a_token_without_required_claims_is_rejected_not_crashed(self, client, user):
        import jwt

        partial = jwt.encode({"sub": str(user.id)}, config.SESSION_SECRET, algorithm="HS256")
        client.cookies.set(SESSION_COOKIE, partial)
        assert client.get("/auth/me").status_code == 401

    def test_a_non_numeric_subject_is_a_401_not_a_500(self, client):
        import datetime
        import jwt

        now = datetime.datetime.now(datetime.timezone.utc)
        bad = jwt.encode(
            {"sub": "not-a-number", "sv": 1, "iss": "codearmor-api",
             "aud": "codearmor-web", "iat": now,
             "exp": now + datetime.timedelta(hours=1)},
            config.SESSION_SECRET,
            algorithm="HS256",
        )
        client.cookies.set(SESSION_COOKIE, bad)
        assert client.get("/auth/me").status_code == 401


class TestCsrf:
    """SameSite=None is required cross-site, so SameSite no longer blocks CSRF."""

    def test_a_state_changing_request_without_the_header_is_refused(self, client, user, repo):
        client.cookies.set(SESSION_COOKIE, create_session_token(user))
        client.cookies.set(CSRF_COOKIE, "csrf-test-token")
        response = client.post(
            "/reviews", json={"repo_id": repo.id, "pr_number": 1}
        )
        assert response.status_code == 403

    def test_a_mismatched_token_is_refused(self, client, user, repo):
        sign_in(client, user)
        response = client.post(
            "/reviews",
            json={"repo_id": repo.id, "pr_number": 1},
            headers={"X-CSRF-Token": "a-different-value"},
        )
        assert response.status_code == 403

    def test_a_disallowed_origin_is_refused(self, client, user, repo):
        csrf = sign_in(client, user)
        response = client.delete(
            f"/repos/{repo.id}",
            headers={"X-CSRF-Token": csrf, "Origin": "https://evil.example"},
        )
        assert response.status_code == 403

    def test_reads_do_not_require_a_csrf_token(self, client, user):
        client.cookies.set(SESSION_COOKIE, create_session_token(user))
        assert client.get("/repos").status_code == 200


class TestCrossUserIsolation:
    def test_a_user_cannot_reach_another_users_repository(self, client, user, repo):
        other = User.create(
            github_id=9999, login="intruder",
            access_token_encrypted=encrypt_token("gho_other"),
        )
        client.cookies.set(SESSION_COOKIE, create_session_token(other))
        csrf = "csrf-test-token"
        client.cookies.set(CSRF_COOKIE, csrf)

        assert client.get(f"/repos/{repo.id}/sync").status_code == 404
        assert client.get(f"/repos/{repo.id}/pulls").status_code == 404
        assert client.delete(
            f"/repos/{repo.id}", headers={"X-CSRF-Token": csrf}
        ).status_code == 404

    def test_a_user_cannot_read_another_users_review(self, client, user, repo):
        review = Review.create(
            user=user, repository=repo, repo_full_name=repo.full_name,
            pr_number=7, head_sha="abc123", payload="{}",
        )
        other = User.create(
            github_id=8888, login="intruder2",
            access_token_encrypted=encrypt_token("gho_other2"),
        )
        client.cookies.set(SESSION_COOKIE, create_session_token(other))
        assert client.get(f"/reviews/{review.id}").status_code == 404

    def test_a_review_must_target_a_connected_repository(self, client, user):
        csrf = sign_in(client, user)
        unconnected = Repository.create(
            user=User.create(
                github_id=7777, login="somebody",
                access_token_encrypted=encrypt_token("gho_x"),
            ),
            full_name="somebody/private", owner="somebody", name="private",
            private=True, html_url="https://github.com/somebody/private",
        )
        response = client.post(
            "/reviews",
            json={"repo_id": unconnected.id, "pr_number": 1},
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 404


class TestTokenAtRest:
    def test_encryption_round_trips(self):
        from app.services.crypto_service import decrypt_token

        assert decrypt_token(encrypt_token("gho_secret")) == "gho_secret"

    def test_ciphertext_does_not_contain_the_token(self):
        assert "gho_secret" not in encrypt_token("gho_secret")

    def test_undecryptable_ciphertext_raises_a_typed_error(self):
        from app.services.crypto_service import TokenDecryptionError, decrypt_token

        with pytest.raises(TokenDecryptionError):
            decrypt_token("gAAAAABnotarealfernettokenatall")

    def test_an_undecryptable_token_gives_401_not_500(self, client, user):
        user.access_token_encrypted = "gAAAAABnotarealfernettokenatall"
        user.save()
        client.cookies.set(SESSION_COOKIE, create_session_token(user))
        assert client.get("/repos/available").status_code == 401


class TestConfigGuards:
    def test_production_refuses_the_default_session_secret(self, monkeypatch):
        monkeypatch.setattr(config, "IS_PRODUCTION", True)
        monkeypatch.setattr(config, "SESSION_SECRET", config.DEV_SESSION_SECRET)
        with pytest.raises(config.ConfigError, match="SESSION_SECRET"):
            config.validate_config()

    def test_production_refuses_a_plaintext_allowed_origin(self, monkeypatch):
        monkeypatch.setattr(config, "IS_PRODUCTION", True)
        monkeypatch.setattr(config, "SESSION_SECRET", "x" * 40)
        monkeypatch.setattr(config, "TOKEN_ENCRYPTION_KEY", "k" * 44)
        monkeypatch.setattr(config, "COOKIE_SECURE", True)
        monkeypatch.setattr(config, "FRONTEND_URL", "https://app.example")
        monkeypatch.setattr(config, "BACKEND_URL", "https://api.example")
        monkeypatch.setattr(config, "ALLOWED_ORIGINS", ["http://app.example"])
        with pytest.raises(config.ConfigError, match="plaintext origin"):
            config.validate_config()

    def test_samesite_none_without_secure_is_refused(self, monkeypatch):
        monkeypatch.setattr(config, "COOKIE_SAMESITE", "none")
        monkeypatch.setattr(config, "COOKIE_SECURE", False)
        with pytest.raises(config.ConfigError, match="COOKIE_SECURE"):
            config.validate_config()


class TestRateLimiting:
    def test_the_review_limit_is_enforced_per_user(self, monkeypatch):
        rate_limit_service.reset()
        monkeypatch.setitem(rate_limit_service._LIMITS, "review", 2)
        from fastapi import HTTPException

        rate_limit_service.check_rate_limit("review", 1)
        rate_limit_service.check_rate_limit("review", 1)
        with pytest.raises(HTTPException) as caught:
            rate_limit_service.check_rate_limit("review", 1)
        assert caught.value.status_code == 429
        # A different user is unaffected.
        rate_limit_service.check_rate_limit("review", 2)


class TestLogRedaction:
    def test_a_token_in_a_log_line_is_redacted(self):
        import logging

        from app.core.logging import RedactFilter

        record = logging.LogRecord(
            "t", logging.INFO, __file__, 1,
            "calling with Authorization: Bearer ghp_abcdefghijklmnopqrstuvwxyz012345",
            None, None,
        )
        RedactFilter().filter(record)
        assert "ghp_abcdefghijklmnopqrstuvwxyz012345" not in record.getMessage()

    def test_fernet_ciphertext_is_redacted(self):
        import logging

        from app.core.logging import RedactFilter

        ciphertext = encrypt_token("gho_secret")
        record = logging.LogRecord(
            "t", logging.INFO, __file__, 1, "stored %s", (ciphertext,), None
        )
        RedactFilter().filter(record)
        assert ciphertext not in record.getMessage()
