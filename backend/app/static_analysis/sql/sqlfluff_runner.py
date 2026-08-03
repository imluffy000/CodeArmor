import json
import subprocess
from pathlib import Path


def run_sqlfluff(target_dir: str) -> list[dict]:
    path = Path(target_dir)
    if not path.exists():
        return []

    try:
        result = subprocess.run(
            [
                "sqlfluff",
                "lint",
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
        file_path = file_result.get("filepath", "unknown")
        for violation in file_result.get("violations", []):
            findings.append(
                {
                    "file": file_path,
                    "severity": "LOW",
                    "issue": violation.get("description", "SQLFluff finding"),
                    "suggestion": "Fix the SQL style or correctness violation.",
                }
            )
    return findings
