"""Development entrypoint.

Production does not use this file — it runs uvicorn directly (see render.yaml) —
but the defaults here are env-aware so the two cannot silently disagree. A
hardcoded 127.0.0.1 bind is invisible on a PaaS: the platform port-scans the
container, sees nothing on 0.0.0.0, and fails the deploy with "no open ports".
"""
import os
import sys

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BACKEND_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import uvicorn  # noqa: E402  (path setup must come first)


def _flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    reload = _flag("RELOAD", os.getenv("ENVIRONMENT", "development") != "production")

    print(f"CodeArmor API on http://{host}:{port}")
    print(f"  health: http://{host}:{port}/health")
    print(f"  docs:   http://{host}:{port}/docs")

    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=reload,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
