import json
import subprocess
from pathlib import Path


def run_bandit(target_dir: str) -> list[dict]:
    path = Path(target_dir)
    if not path.exists():
        return []

    try:
        result = subprocess.run(
            [
                "bandit",
                "-r",
                str(path),
                "-f",
                "json",
                "-q",
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

    findings = []
    for item in payload.get("results", []):
        findings.append(
            {
                "file": item.get("filename", "unknown"),
                "severity": _bandit_severity(item.get("issue_severity")),
                "issue": item.get("issue_text", "Bandit finding"),
                "suggestion": "Remediate insecure pattern or document exception.",
            }
        )
    return findings


def _bandit_severity(severity: str | None) -> str:
    if not severity:
        return "MEDIUM"
    normalized = severity.upper()
    if normalized in {"LOW", "MEDIUM", "HIGH"}:
        return normalized
    return "MEDIUM"
