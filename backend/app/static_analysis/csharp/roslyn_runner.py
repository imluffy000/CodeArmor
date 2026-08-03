import subprocess
from pathlib import Path


def run_roslyn(target_dir: str) -> list[dict]:
    path = Path(target_dir)
    if not path.exists():
        return []

    try:
        result = subprocess.run(
            [
                "dotnet",
                "build",
                str(path),
                "--no-restore",
                "/property:GenerateFullPaths=true",
                "/consoleloggerparameters:NoSummary",
            ],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []

    findings = []
    for line in result.stdout.splitlines() + result.stderr.splitlines():
        severity = _roslyn_severity(line)
        if severity:
            findings.append(
                {
                    "file": line.split(":", 1)[0] if ":" in line else "unknown",
                    "severity": severity,
                    "issue": line.strip(),
                    "suggestion": "Resolve the Roslyn analyzer diagnostic.",
                }
            )
    return findings


def _roslyn_severity(line: str) -> str | None:
    lowered = line.lower()
    if ": error " in lowered:
        return "HIGH"
    if ": warning " in lowered:
        return "MEDIUM"
    return None
