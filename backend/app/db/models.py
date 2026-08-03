"""Peewee ORM models for users, connected repositories, and sync jobs."""
import datetime

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


def utcnow():
    return datetime.datetime.utcnow()


class BaseModel(Model):
    class Meta:
        database = db


class User(BaseModel):
    github_id = IntegerField(unique=True, index=True)
    login = CharField()
    name = CharField(null=True)
    avatar_url = CharField(null=True)
    # GitHub OAuth access token, encrypted with Fernet (see crypto_service)
    access_token_encrypted = TextField()
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
            # A user can connect a given repo only once
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
