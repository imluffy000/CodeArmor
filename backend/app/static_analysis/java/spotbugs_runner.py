import subprocess
from pathlib import Path
from xml.etree import ElementTree


def run_spotbugs(target_dir: str) -> list[dict]:
    path = Path(target_dir)
    if not path.exists():
        return []

    try:
        result = subprocess.run(
            [
                "spotbugs",
                "-textui",
                "-xml",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []

    if not result.stdout.strip():
        return []

    try:
        payload = ElementTree.fromstring(result.stdout)
    except ElementTree.ParseError:
        return []

    findings = []
    for bug in payload.findall(".//BugInstance"):
        source_line = bug.find("SourceLine")
        file_path = source_line.get("sourcepath", "unknown") if source_line is not None else "unknown"
        findings.append(
            {
                "file": file_path,
                "severity": _spotbugs_severity(bug.get("priority")),
                "issue": bug.get("type", "SpotBugs finding"),
                "suggestion": "Fix the defect reported by SpotBugs or document why it is acceptable.",
            }
        )
    return findings


def _spotbugs_severity(priority: str | None) -> str:
    if priority == "1":
        return "HIGH"
    if priority == "2":
        return "MEDIUM"
    return "LOW"
