import json
import subprocess
from pathlib import Path


def run_pylint(target_dir: str) -> list[dict]:
    path = Path(target_dir)
    if not path.exists():
        return []

    try:
        result = subprocess.run(
            [
                "pylint",
                str(path),
                "--output-format=json",
                "--disable=all",
                "--enable=E,F",
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []

    if not result.stdout.strip():
        return []

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []

    if not isinstance(payload, list):
        return []

    findings = []
    for item in payload:
        findings.append(
            {
                "file": item.get("path", "unknown"),
                "severity": "MEDIUM" if item.get("type") == "error" else "LOW",
                "issue": item.get("message", "Pylint finding"),
                "suggestion": "Resolve lint error or refactor code.",
            }
        )
    return findings
