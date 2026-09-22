"""Central configuration, loaded from environment (see .env.example).

Every setting has a development-friendly default, but anything that would be
unsafe in production raises at import time when ENVIRONMENT=production.
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=BACKEND_DIR / ".env")


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name)
    if not raw:
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


# --- Environment ---
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").strip().lower()
IS_PRODUCTION = ENVIRONMENT == "production"

# One JSON object per line, so a log aggregator can filter on trace_id,
# agent or cost instead of regexing a formatted string.
LOG_FORMAT = os.getenv("LOG_FORMAT", "json" if IS_PRODUCTION else "text").strip().lower()

# LangChain turns on LangSmith tracing from environment variables alone, and
# it uploads full prompt and completion payloads - which here means users'
# private source code, mirrored to a second third party with no code change.
# Pin it off unless an operator deliberately opts in.
for _tracing_var in ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2", "LANGCHAIN_TRACING"):
    os.environ.setdefault(_tracing_var, "false")

# --- LLM provider ---
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or OPENROUTER_API_KEY

if OPENAI_API_KEY and os.getenv("OPENAI_API_KEY") is None:
    os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY

LLM_MODEL = os.getenv("LLM_MODEL", "deepseek/deepseek-chat-v3-0324")
LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "120"))

# --- GitHub OAuth ---
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")

# --- Sessions & cookies ---
DEV_SESSION_SECRET = "dev-insecure-secret-change-me"
SESSION_SECRET = os.getenv("SESSION_SECRET", DEV_SESSION_SECRET)
SESSION_TTL_HOURS = int(os.getenv("SESSION_TTL_HOURS", str(24 * 7)))

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://127.0.0.1:5173").rstrip("/")
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")

# Browsers only send a cookie on a cross-site request when it is
# SameSite=None AND Secure. A Vercel frontend calling a Render backend is
# cross-site, so production must use None+Secure; local same-host dev over
# plain HTTP cannot use Secure, so it uses Lax.
COOKIE_SECURE = _env_bool("COOKIE_SECURE", IS_PRODUCTION)
COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "none" if IS_PRODUCTION else "lax").strip().lower()

# --- CORS ---
ALLOWED_ORIGINS = _env_list(
    "ALLOWED_ORIGINS",
    ["http://localhost:5173", "http://127.0.0.1:5173"],
)
if FRONTEND_URL and FRONTEND_URL not in ALLOWED_ORIGINS:
    ALLOWED_ORIGINS.append(FRONTEND_URL)

# --- Token encryption at rest ---
# Stored GitHub tokens are encrypted with this key. Keep it separate from
# SESSION_SECRET so rotating one does not lock you out of the other.
# Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
TOKEN_ENCRYPTION_KEY = os.getenv("TOKEN_ENCRYPTION_KEY")
TOKEN_ENCRYPTION_KEY_OLD = os.getenv("TOKEN_ENCRYPTION_KEY_OLD")

# --- Database ---
# DATABASE_URL wins when set (e.g. Render Postgres). SQLite is the local
# default; note that a container filesystem is ephemeral, so SQLite must not
# be used for a deployment whose data has to survive a restart.
DATABASE_URL = os.getenv("DATABASE_URL")
DATABASE_PATH = os.getenv("DATABASE_PATH", str(BACKEND_DIR / "app_data.db"))

# --- Review pipeline ---
MAX_DIFF_CHARS = int(os.getenv("MAX_DIFF_CHARS", "60000"))
AGENT_DIFF_CHARS = int(os.getenv("AGENT_DIFF_CHARS", "24000"))
REVIEW_RATE_LIMIT_PER_HOUR = int(os.getenv("REVIEW_RATE_LIMIT_PER_HOUR", "20"))
# Hard stop on one review's spend. A 500-file pull request otherwise costs
# whatever it costs, and nobody finds out until the invoice.
REVIEW_COST_CEILING_USD = float(os.getenv("REVIEW_COST_CEILING_USD", "0.50"))
CHAT_RATE_LIMIT_PER_HOUR = int(os.getenv("CHAT_RATE_LIMIT_PER_HOUR", "60"))

# Posting a review back to GitHub writes to the user's repository, so it is
# opt-in per request and never submits an APPROVE verdict on the user's behalf.
ALLOW_GITHUB_POSTING = _env_bool("ALLOW_GITHUB_POSTING", True)


class ConfigError(RuntimeError):
    """Raised when the process is started with an unsafe configuration."""


def _fatal(message: str) -> None:
    raise ConfigError(message)


def validate_config() -> list[str]:
    """Fail fast on unsafe production config; return warnings for dev."""
    warnings: list[str] = []

    if not OPENROUTER_API_KEY and not os.getenv("OPENAI_API_KEY"):
        warnings.append("No OPENROUTER_API_KEY/OPENAI_API_KEY set - reviews will fail.")

    if not (GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET):
        warnings.append(
            "GITHUB_CLIENT_ID/GITHUB_CLIENT_SECRET are unset - GitHub sign-in is disabled."
        )

    if not TOKEN_ENCRYPTION_KEY:
        warnings.append(
            "TOKEN_ENCRYPTION_KEY is unset - falling back to a key derived from "
            "SESSION_SECRET. Set a dedicated key before storing real tokens."
        )

    if COOKIE_SAMESITE not in ("lax", "strict", "none"):
        _fatal(f"COOKIE_SAMESITE must be lax, strict or none (got {COOKIE_SAMESITE!r}).")

    if COOKIE_SAMESITE == "none" and not COOKIE_SECURE:
        _fatal("COOKIE_SAMESITE=none requires COOKIE_SECURE=true; browsers drop the cookie otherwise.")

    if not IS_PRODUCTION:
        return warnings

    # --- production-only hard requirements ---
    if SESSION_SECRET == DEV_SESSION_SECRET:
        _fatal("SESSION_SECRET is still the development default. Set a strong random value.")
    if len(SESSION_SECRET) < 32:
        _fatal("SESSION_SECRET must be at least 32 characters in production.")
    if not TOKEN_ENCRYPTION_KEY:
        _fatal(
            "TOKEN_ENCRYPTION_KEY is required in production. Generate one with: "
            'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )
    if not COOKIE_SECURE:
        _fatal("COOKIE_SECURE must be true in production.")
    if not FRONTEND_URL.startswith("https://") or not BACKEND_URL.startswith("https://"):
        _fatal("FRONTEND_URL and BACKEND_URL must be https:// URLs in production.")
    if any(o.startswith("http://") for o in ALLOWED_ORIGINS):
        _fatal(f"ALLOWED_ORIGINS contains a plaintext origin: {ALLOWED_ORIGINS}")
    if "*" in ALLOWED_ORIGINS:
        _fatal("ALLOWED_ORIGINS cannot be '*' when credentials are allowed.")
    if not DATABASE_URL:
        print(
            "WARNING: running in production on SQLite. Container filesystems are "
            "ephemeral - set DATABASE_URL to a managed database to keep data.",
            file=sys.stderr,
        )

    return warnings
