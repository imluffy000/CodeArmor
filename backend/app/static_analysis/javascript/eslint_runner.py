import json
import subprocess
from pathlib import Path


def run_eslint(target_dir: str) -> list[dict]:
    path = Path(target_dir)
    if not path.exists():
        return []

    try:
        result = subprocess.run(
            [
                "eslint",
                str(path),
                "--format",
                "json",
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
    for file_result in payload:
        file_path = file_result.get("filePath", "unknown")
        for message in file_result.get("messages", []):
            findings.append(
                {
                    "file": file_path,
                    "severity": "MEDIUM" if message.get("severity") == 2 else "LOW",
                    "issue": message.get("message", "ESLint finding"),
                    "suggestion": "Resolve lint finding or update project ESLint configuration.",
                }
            )
    return findings
