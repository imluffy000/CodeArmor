"""Test fixtures: an isolated database per test module, never the real one."""
import os
import tempfile

# Must be set before app.core.config is imported anywhere.
_TMP_DB = os.path.join(tempfile.mkdtemp(prefix="codearmor-test-"), "test.db")
os.environ.setdefault("DATABASE_PATH", _TMP_DB)
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("SESSION_SECRET", "test-secret-value-long-enough-for-tests")
os.environ.pop("DATABASE_URL", None)

import pytest  # noqa: E402

from app.db.database import db, init_db  # noqa: E402
from app.db.models import Repository, Review, SyncJob, User  # noqa: E402
from app.services.crypto_service import encrypt_token  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def database():
    init_db()
    yield db
    if not db.is_closed():
        db.close()


@pytest.fixture(autouse=True)
def clean_tables(database):
    for model in (Review, SyncJob, Repository, User):
        model.delete().execute()
    yield


@pytest.fixture
def user():
    return User.create(
        github_id=4242,
        login="tester",
        name="Tester",
        access_token_encrypted=encrypt_token("gho_testtoken"),
    )


@pytest.fixture
def repo(user):
    return Repository.create(
        user=user,
        full_name="tester/demo",
        owner="tester",
        name="demo",
        private=False,
        html_url="https://github.com/tester/demo",
        sync_status="synced",
    )
