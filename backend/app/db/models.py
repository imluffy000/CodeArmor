"""Peewee models: users, connected repositories, sync jobs, stored reviews."""
import json

from peewee import (
    BooleanField,
    CharField,
    DateTimeField,
    FloatField,
    ForeignKeyField,
    IntegerField,
    Model,
    TextField,
)

from app.core.timeutil import utcnow
from app.db.database import db




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

    # --- observability ---------------------------------------------------
    # Correlates this review with its log lines, and makes a wrong answer
    # attributable to a specific agent, model and prompt version afterwards.
    trace_id = CharField(index=True, null=True)
    duration_ms = IntegerField(null=True)
    tokens_in = IntegerField(default=0)
    tokens_out = IntegerField(default=0)
    cost_usd = FloatField(default=0.0)
    model = CharField(null=True)
    prompt_version = CharField(null=True)
    # Full span list as JSON, for the trace view.
    trace = TextField(null=True)

    created_at = DateTimeField(default=utcnow, index=True)

    class Meta:
        indexes = ((("user", "repo_full_name", "pr_number", "head_sha"), False),)

    @property
    def data(self) -> dict:
        return json.loads(self.payload)


class AgentRun(BaseModel):
    """One agent's execution inside one review.

    A row per span rather than only the JSON blob on Review, so that questions
    like "which agent times out most" or "what does the security agent cost"
    are a query instead of a scan.
    """

    review = ForeignKeyField(Review, backref="agent_runs", on_delete="CASCADE")
    agent = CharField(index=True)
    status = CharField(default="ok")  # ok | error | timeout | skipped
    model = CharField(null=True)
    duration_ms = IntegerField(default=0)
    tokens_in = IntegerField(default=0)
    tokens_out = IntegerField(default=0)
    cost_usd = FloatField(default=0.0)
    findings = IntegerField(default=0)
    # Findings the model returned that failed validation. A rising number here
    # is the earliest signal that a prompt or model change went wrong.
    dropped = IntegerField(default=0)
    parse_status = CharField(null=True)
    error = TextField(null=True)
    created_at = DateTimeField(default=utcnow, index=True)
