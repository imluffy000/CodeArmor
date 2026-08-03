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
        severity = "HIGH" if float(item.get("issue_confidence", 0)) >= 0.7 else "MEDIUM"
        findings.append(
            {
                "file": item.get("filename", "unknown"),
                "severity": severity,
                "issue": item.get("issue_text", "Bandit finding"),
                "suggestion": "Remediate insecure pattern or document exception.",
            }
        )
    return findings
