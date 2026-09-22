"""Database wiring.

Uses a DatabaseProxy so models can be declared before we know whether the
process is talking to SQLite (local default) or a managed Postgres instance
(DATABASE_URL, e.g. on Render, where the container filesystem is ephemeral
and SQLite would lose every row on each deploy).
"""
import re

from peewee import DatabaseProxy, IntegerField, SqliteDatabase

from app.core.config import DATABASE_PATH, DATABASE_URL
from app.core.logging import logger

db = DatabaseProxy()


def _build_database():
    if DATABASE_URL:
        from playhouse.db_url import connect

        return connect(DATABASE_URL)

    return SqliteDatabase(
        DATABASE_PATH,
        pragmas={
            "journal_mode": "wal",
            "foreign_keys": 1,
            "busy_timeout": 5000,
        },
    )


def init_db() -> None:
    """Bind the proxy, create missing tables, and clean up orphaned jobs."""
    from app.db.models import Repository, Review, SyncJob, User

    database = _build_database()
    db.initialize(database)

    db.connect(reuse_if_open=True)
    db.create_tables([User, Repository, SyncJob, Review], safe=True)

    _apply_column_migrations()
    _reconcile_interrupted_jobs()

    backend = "postgres" if DATABASE_URL else f"sqlite ({DATABASE_PATH})"
    logger.info("Database ready: %s", backend)


def _reconcile_interrupted_jobs() -> None:
    """Sync jobs run as in-process asyncio tasks, so a restart abandons them.

    Without this, a repo connected right before a deploy is stuck showing
    "Syncing..." in the UI forever.
    """
    import datetime

    from app.db.models import Repository, SyncJob

    stranded = (
        SyncJob.update(
            status="failed",
            progress="Interrupted by a server restart",
            error="Server restarted before the sync finished. Reconnect the repository to retry.",
            finished_at=datetime.datetime.now(datetime.timezone.utc),
        )
        .where(SyncJob.status.in_(["queued", "running"]))
        .execute()
    )
    if stranded:
        Repository.update(sync_status="failed").where(
            Repository.sync_status.in_(["pending", "syncing"])
        ).execute()
        logger.warning("Marked %s interrupted sync job(s) as failed on startup", stranded)


# Columns added after the first release, as (table, column, field factory).
# create_tables(safe=True) creates missing tables but never ALTERs an existing
# one, so without this an upgraded deployment reads a database whose `user`
# table has no `session_version` and every authenticated request fails with
# "no such column".
_ADDED_COLUMNS = [
    ("user", "session_version", lambda: IntegerField(default=1)),
]


_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _is_safe_identifier(name: str) -> bool:
    """A plain SQL identifier: letters, digits and underscores only."""
    return bool(_IDENTIFIER_RE.match(name))


def _apply_column_migrations() -> None:
    from playhouse.migrate import PostgresqlMigrator, SqliteMigrator, migrate

    database = db.obj
    migrator = (
        PostgresqlMigrator(database) if DATABASE_URL else SqliteMigrator(database)
    )

    for table, column, field_factory in _ADDED_COLUMNS:
        existing = {info.name for info in database.get_columns(table)}
        if column in existing:
            continue
        logger.info("Migrating: adding %s.%s", table, column)
        field = field_factory()
        field.null = True  # an ALTER cannot backfill a NOT NULL column in place
        migrate(migrator.add_column(table, column, field))

        # Identifiers cannot be bound as query parameters, so they are
        # interpolated - and therefore validated against the allowlist above
        # first, so this stays true even if _ADDED_COLUMNS is edited later.
        if not (_is_safe_identifier(table) and _is_safe_identifier(column)):
            raise ValueError(
                f"Refusing to migrate unsafe identifier: {table}.{column}"
            )
        database.execute_sql(
            f"UPDATE {table} SET {column} = 1 WHERE {column} IS NULL"  # nosec B608
        )


def close_db() -> None:
    if not db.is_closed():
        db.close()
