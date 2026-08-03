"""SQLite database setup using peewee."""
from peewee import SqliteDatabase

from app.core.config import DATABASE_PATH

db = SqliteDatabase(
    DATABASE_PATH,
    pragmas={
        "journal_mode": "wal",
        "foreign_keys": 1,
    },
)


def init_db():
    """Create tables if they don't exist. Called on app startup."""
    from app.db.models import User, Repository, SyncJob

    db.connect(reuse_if_open=True)
    db.create_tables([User, Repository, SyncJob], safe=True)
