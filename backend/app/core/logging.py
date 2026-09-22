"""Logging setup, log redaction, and the audit trail for credential-using actions.

Three rules hold everywhere in this codebase:

* Never log a token, a diff, or a raw upstream response body. A GitHub error
  body can name a private repository; a diff is the user's source code.
* Every log record passes through a redaction filter anyway, because the rule
  above is only as good as the next person to add a handler.
* Security-relevant actions get an `audit()` line with a stable event name, so
  that after an incident you can reconstruct who did what.
"""
import logging
import os
import re
import sys
import uuid
from contextvars import ContextVar

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Set per request so every line from one request can be correlated, and so an
# error response can hand the user an id to quote back at you.
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


def new_request_id() -> str:
    return uuid.uuid4().hex[:12]


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = request_id_var.get()
        return True


# Defence in depth. Nothing here logs a token today, but a future
# `rich.traceback.install(show_locals=True)` would start dumping Authorization
# headers, and uvicorn's access logger records full query strings.
_REDACTIONS = [
    (re.compile(r"gh[opusr]_[A-Za-z0-9]{16,}"), "gh?_[REDACTED]"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{16,}"), "github_pat_[REDACTED]"),
    (re.compile(r"gAAAAA[A-Za-z0-9_=-]{16,}"), "[REDACTED_CIPHERTEXT]"),
    (re.compile(r"sk-[A-Za-z0-9_-]{16,}"), "sk-[REDACTED]"),
    (
        re.compile(
            r"(?i)(authorization|bearer|api[_-]?key|client_secret|access_token)"
            r"([\"']?\s*[:=]\s*[\"']?)\S+"
        ),
        r"\1\2[REDACTED]",
    ),
]


class RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            return True
        redacted = message
        for pattern, replacement in _REDACTIONS:
            redacted = pattern.sub(replacement, redacted)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


def _configure(name: str, level: str, label: str) -> logging.Logger:
    log = logging.getLogger(name)
    log.setLevel(level)
    if not log.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | " + label + " | %(request_id)s | %(message)s"
            )
        )
        handler.addFilter(RequestIdFilter())
        handler.addFilter(RedactFilter())
        log.addHandler(handler)
    log.propagate = False
    return log


logger = _configure("codearmor", LOG_LEVEL, "%(levelname)-7s")
audit_logger = _configure("codearmor.audit", "INFO", "AUDIT  ")


def install_log_redaction() -> None:
    """Attach the filters to uvicorn's loggers too.

    uvicorn.access logs the request line, which is where a private repository
    name would otherwise appear in the log store.
    """
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        target = logging.getLogger(name)
        for scope in [target, *target.handlers]:
            if not any(isinstance(f, RedactFilter) for f in scope.filters):
                scope.addFilter(RedactFilter())
            if not any(isinstance(f, RequestIdFilter) for f in scope.filters):
                scope.addFilter(RequestIdFilter())


def audit(event: str, **fields: object) -> None:
    """Record a security-relevant action.

    Callers pass identifiers, never secrets. Values are rendered as key=value
    so the stream stays greppable without a log pipeline in front of it.
    """
    rendered = " ".join(f"{key}={value!r}" for key, value in sorted(fields.items()))
    audit_logger.info("%s %s", event, rendered)


install_log_redaction()
