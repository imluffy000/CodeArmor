"""Prompt composition and diff budgeting.

Two deliberate choices here.

**Prompts are assembled with token replacement, not `str.format`.** The prompt
fragments contain literal JSON braces (the worked example in the output
contract), and `str.format` would raise `KeyError` on the first one. That
failure is especially nasty because the natural "fix" - moving `.format` inside
the existing try/except - makes every agent silently return zero findings, so a
broken pipeline reports a clean pull request.

**The diff is budgeted per file, not truncated at a character count.** A flat
cut means a 300 KB pull request is reviewed on its first 4%, with no signal to
the user; if that slice happens to be clean, the product reports a clean PR. So
files are ranked by how much they matter to a reviewer, each gets a share of the
budget, and every changed file is at least named even when its hunks do not fit.
"""
import hashlib
from pathlib import Path

from app.core.config import AGENT_DIFF_CHARS, MAX_DIFF_CHARS
from app.core.constants import ISSUE_BUCKETS

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
SHARED_DIR = PROMPTS_DIR / "_shared"

def _compute_prompt_version() -> str:
    """A short hash over every prompt file.

    Stored on each review so a change in findings can be attributed to a prompt
    edit rather than to the model drifting, and so a cached review is
    invalidated when the prompts change under it.
    """
    digest = hashlib.sha256()
    for path in sorted(PROMPTS_DIR.rglob('*.txt')):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


PROMPT_VERSION = _compute_prompt_version()


# Files a reviewer should see first if the budget is tight. Lower sorts earlier.
_PRIORITY_TAGS = {
    "migration": 0,
    "api_schema": 0,
    "route": 1,
    "orm_model": 1,
    "dependency_manifest": 2,
    "source": 3,
    "test": 4,
    "config_sample": 5,
    "ci_config": 5,
    "deploy_config": 5,
    "sql": 3,
    "lockfile": 9,
}

# Generated or vendored content burns budget without informing a review.
_LOW_VALUE = (
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "Pipfile.lock",
    "go.sum",
    "Cargo.lock",
    "composer.lock",
    ".min.js",
    ".min.css",
    ".map",
    ".snap",
)


def load_prompt(name: str) -> str:
    """Read a prompt file from app/prompts, with shared fragments inlined."""
    path = PROMPTS_DIR / f"{name}_prompt.txt"
    if not path.exists():
        raise FileNotFoundError(f"Prompt not found: {path}")

    text = path.read_text(encoding="utf-8").strip()

    for fragment in ("output_contract", "severity_rubric"):
        placeholder = "{{" + fragment.upper() + "}}"
        if placeholder in text:
            fragment_path = SHARED_DIR / f"{fragment}.txt"
            text = text.replace(
                placeholder, fragment_path.read_text(encoding="utf-8").strip()
            )

    return text


def load_system_prompt() -> str:
    return (SHARED_DIR / "system.txt").read_text(encoding="utf-8").strip()


def render_prompt(template: str, **fields: str) -> str:
    """Substitute {{NAME}} placeholders. Never `str.format`; see module docstring."""
    rendered = template
    for key, value in fields.items():
        rendered = rendered.replace("{{" + key.upper() + "}}", value if value is not None else "")
    return rendered


# --------------------------------------------------------------------------
# Diff budgeting
# --------------------------------------------------------------------------

def _file_sort_key(entry: dict) -> tuple:
    path = entry.get("path", "")
    tags = entry.get("tags") or ["source"]
    priority = min((_PRIORITY_TAGS.get(tag, 3) for tag in tags), default=3)
    if any(path.endswith(marker) or path.rsplit("/", 1)[-1] == marker for marker in _LOW_VALUE):
        priority = 9
    # Within a priority band, smaller files first so the budget covers more of them.
    size = entry.get("additions", 0) + entry.get("deletions", 0)
    return (priority, size, path)


def build_agent_diff(
    files: list[dict],
    raw_diff: str = "",
    budget: int = AGENT_DIFF_CHARS,
) -> dict:
    """Assemble the diff text an agent sees, with an honest coverage report.

    `files` are GitHub's per-file entries (filename/patch/additions/...) enriched
    with a `tags` list. Returns the text plus coverage numbers that the API
    response surfaces, so "partial review" is visible instead of implied.
    """
    if not files:
        # No per-file data (e.g. a repo the files endpoint would not serve).
        # Fall back to the raw diff so the review still runs.
        text = raw_diff[:budget]
        return {
            "text": text,
            "files_included": [],
            "files_omitted": [],
            "truncated": len(raw_diff) > budget,
            "coverage_percent": 100 if not raw_diff else round(100 * len(text) / len(raw_diff)),
        }

    entries = [
        {
            "path": entry.get("filename") or entry.get("path", ""),
            "status": entry.get("status", "modified"),
            "additions": entry.get("additions", 0),
            "deletions": entry.get("deletions", 0),
            "patch": entry.get("patch") or "",
            "tags": entry.get("tags") or ["source"],
        }
        for entry in files
    ]

    total_patch_chars = sum(len(e["patch"]) for e in entries)
    remaining = budget
    included: list[str] = []
    omitted: list[str] = []
    blocks: list[str] = []

    for entry in sorted(entries, key=_file_sort_key):
        header = (
            f"--- {entry['path']} ({entry['status']}, "
            f"+{entry['additions']}/-{entry['deletions']}) ---\n"
        )
        block = header + entry["patch"] + "\n"

        if not entry["patch"]:
            omitted.append(entry["path"])
            continue
        if len(block) <= remaining:
            blocks.append(block)
            included.append(entry["path"])
            remaining -= len(block)
        else:
            omitted.append(entry["path"])

    # Every changed file is named even when its hunks did not fit, so an agent
    # can tell "no test was added" from "the test file did not fit".
    manifest_lines = [
        f"  {e['path']} ({e['status']}, +{e['additions']}/-{e['deletions']})"
        for e in sorted(entries, key=lambda x: x["path"])
    ]
    manifest = "ALL FILES CHANGED IN THIS PULL REQUEST:\n" + "\n".join(manifest_lines)

    if omitted:
        manifest += (
            "\n\nNOTE: the hunks for these files are NOT included below and you "
            "cannot review their contents: " + ", ".join(omitted)
        )

    included_chars = sum(len(e["patch"]) for e in entries if e["path"] in set(included))
    coverage = 100 if not total_patch_chars else round(100 * included_chars / total_patch_chars)

    return {
        "text": manifest + "\n\n" + "".join(blocks),
        "files_included": included,
        "files_omitted": omitted,
        "truncated": bool(omitted),
        "coverage_percent": coverage,
    }


def truncate_diff(diff: str, max_length: int = MAX_DIFF_CHARS) -> str:
    """Hard cap for the raw diff we keep in memory and persist."""
    if len(diff) <= max_length:
        return diff
    return diff[:max_length] + "\n\n... [diff truncated]"


def default_pr_state(
    pr_url: str,
    diff: str,
    parsed_files: list,
    *,
    agent_diff: str = "",
    review_context: str = "",
    integration_context: dict | None = None,
    coverage: dict | None = None,
) -> dict:
    """The initial graph state, with every bucket pre-seeded.

    Pre-seeding matters: summary_agent reads the buckets directly, so a missing
    key is a KeyError at the end of a review that already cost six LLM calls.
    """
    state = {
        "pr_url": pr_url,
        "diff": diff,
        "agent_diff": agent_diff or diff,
        "review_context": review_context,
        "integration_context": integration_context or {},
        "coverage": coverage or {},
        "parsed_files": parsed_files,
        "all_issues": [],
        "folder_tree": {},
        "final_summary": "",
        "agent_errors": [],
        "dropped_findings": 0,
        "merge_readiness": {},
    }
    for bucket in ISSUE_BUCKETS:
        state[bucket] = []
    return state
