"""Peewee models: users, connected repositories, sync jobs, stored reviews."""
import datetime
import json

from peewee import (
    BooleanField,
    CharField,
    DateTimeField,
    ForeignKeyField,
    IntegerField,
    Model,
    TextField,
)

from app.db.database import db


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class BaseModel(Model):
    class Meta:
        database = db


class User(BaseModel):
    github_id = IntegerField(unique=True, index=True)
    login = CharField()
    name = CharField(null=True)
    avatar_url = CharField(null=True)
    # GitHub OAuth access token, encrypted at rest (see crypto_service).
    access_token_encrypted = TextField()
    # Bumped on sign-out and on account switch. Session JWTs carry the value
    # they were minted with, so bumping it invalidates every issued cookie -
    # that is what makes "sign out" actually revoke a stolen session.
    session_version = IntegerField(default=1)
    created_at = DateTimeField(default=utcnow)
    updated_at = DateTimeField(default=utcnow)


class Repository(BaseModel):
    user = ForeignKeyField(User, backref="repositories", on_delete="CASCADE")
    full_name = CharField(index=True)  # "owner/repo"
    owner = CharField()
    name = CharField()
    private = BooleanField(default=False)
    default_branch = CharField(default="main")
    html_url = CharField()
    description = TextField(null=True)
    language = CharField(null=True)
    stars = IntegerField(default=0)
    open_prs = IntegerField(default=0)
    # pending | syncing | synced | failed
    sync_status = CharField(default="pending")
    synced_at = DateTimeField(null=True)
    created_at = DateTimeField(default=utcnow)

    class Meta:
        indexes = (
            # A user can connect a given repo only once.
            (("user", "full_name"), True),
        )


class SyncJob(BaseModel):
    repository = ForeignKeyField(Repository, backref="sync_jobs", on_delete="CASCADE")
    # queued | running | completed | failed
    status = CharField(default="queued")
    progress = CharField(default="Queued")
    error = TextField(null=True)
    started_at = DateTimeField(null=True)
    finished_at = DateTimeField(null=True)
    created_at = DateTimeField(default=utcnow)


class Review(BaseModel):
    """A completed review, stored so results survive a page refresh and so a
    re-review of an unchanged PR head can be served from cache instead of
    re-spending tokens."""

    user = ForeignKeyField(User, backref="reviews", on_delete="CASCADE")
    repository = ForeignKeyField(
        Repository, backref="reviews", on_delete="CASCADE", null=True
    )
    repo_full_name = CharField(index=True)
    pr_number = IntegerField()
    pr_title = CharField(null=True)
    # The PR head commit the review was produced from. A new push changes this,
    # which is what invalidates the cache.
    head_sha = CharField(index=True, null=True)
    total_issues = IntegerField(default=0)
    critical_issues = IntegerField(default=0)
    posted_to_github = BooleanField(default=False)
    # Full structured ReviewResponse payload as JSON.
    payload = TextField()
    created_at = DateTimeField(default=utcnow, index=True)

    class Meta:
        indexes = ((("user", "repo_full_name", "pr_number", "head_sha"), False),)

    @property
    def data(self) -> dict:
        return json.loads(self.payload)
