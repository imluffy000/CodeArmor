"""UTC timestamps that survive a round trip through the database.

Peewee's SQLite `DateTimeField.formats` are:

    ['%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d']

None of them parse an offset, so a timezone-aware datetime is written as
`2026-09-22 22:24:45+00:00` and **read back as a plain string**. Every
`.isoformat()` call on a fetched row then raises AttributeError - a 500 on
every endpoint that returns a timestamp.

So: store naive UTC, which is also what Postgres `timestamp without time zone`
wants, and attach the `Z` at the API boundary. Without that suffix a browser
parses the string as local time and every timestamp silently shifts by the
viewer's offset.
"""
import datetime


def utcnow() -> datetime.datetime:
    """Naive UTC. Every stored timestamp in this app is UTC by convention."""
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def iso_utc(value: datetime.datetime | str | None) -> str | None:
    """Serialise a stored timestamp as an unambiguous UTC ISO-8601 string.

    Tolerates a string, because rows written before this fix exist and a
    legacy value should render rather than crash the endpoint.
    """
    if value is None:
        return None

    if isinstance(value, str):
        text = value.strip().replace(" ", "T")
        if text.endswith("+00:00"):
            return text[:-6] + "Z"
        return text if text.endswith("Z") else text + "Z"

    if value.tzinfo is not None:
        value = value.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return value.isoformat() + "Z"
