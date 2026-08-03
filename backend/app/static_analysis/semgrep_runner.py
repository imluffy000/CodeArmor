import json
import subprocess
from pathlib import Path


def run_semgrep(target_dir: str) -> list[dict]:
    path = Path(target_dir)
    if not path.exists():
        return []

    try:
        result = subprocess.run(
            [
                "semgrep",
                "--config=auto",
                "--json",
                "--quiet",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []

    if result.returncode not in (0, 1) or not result.stdout.strip():
        return []

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []

    findings = []
    for item in payload.get("results", []):
        extra = item.get("extra", {})
        metadata = extra.get("metadata", {})
        findings.append(
            {
                "file": item.get("path", "unknown"),
                "severity": str(
                    metadata.get("impact", extra.get("severity", "MEDIUM"))
                ).upper(),
                "issue": extra.get("message", "Semgrep finding"),
                "suggestion": "Fix or suppress with documented rationale.",
            }
        )
    return findings
