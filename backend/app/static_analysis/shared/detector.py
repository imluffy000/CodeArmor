from pathlib import Path


IGNORED_DIRECTORIES = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "__pycache__",
    "bin",
    "build",
    "dist",
    "node_modules",
    "obj",
    "target",
    "venv",
}

FILE_LANGUAGE_MARKERS = {
    "requirements.txt": {"python"},
    "pyproject.toml": {"python"},
    "setup.py": {"python"},
    "package.json": {"javascript"},
    "pom.xml": {"java"},
    "build.gradle": {"java"},
}

SUFFIX_LANGUAGE_MARKERS = {
    ".py": {"python"},
    ".js": {"javascript"},
    ".jsx": {"javascript"},
    ".ts": {"typescript"},
    ".tsx": {"typescript"},
    ".java": {"java"},
    ".sln": {"csharp"},
    ".csproj": {"csharp"},
    ".cs": {"csharp"},
    ".sql": {"sql"},
}


def scan_repository_languages(target_dir: str) -> set[str]:
    repo_path = Path(target_dir)
    if not repo_path.exists():
        return set()

    languages: set[str] = set()
    for path in repo_path.rglob("*"):
        if _is_ignored(path):
            continue

        languages.update(FILE_LANGUAGE_MARKERS.get(path.name, set()))
        languages.update(SUFFIX_LANGUAGE_MARKERS.get(path.suffix.lower(), set()))

    return languages


def _is_ignored(path: Path) -> bool:
    return any(part in IGNORED_DIRECTORIES for part in path.parts)
