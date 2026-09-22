"""Deterministic integration facts about a pull request.

Integration questions are relational: "is this change compatible with code the
diff does not contain?" An LLM looking at a diff alone cannot answer that, so
this module computes the facts first - from the diff itself and from GitHub -
and the integration agent reasons over the facts rather than guessing.

Everything here is deterministic and cheap. No LLM calls.
"""
import re
from typing import Any

from app.core.logging import logger
from app.github import client as gh

# --------------------------------------------------------------------------
# File classification
# --------------------------------------------------------------------------

DEPENDENCY_MANIFESTS = {
    "requirements.txt",
    "requirements-dev.txt",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "Pipfile",
    "package.json",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "Cargo.toml",
    "Gemfile",
    "composer.json",
}

LOCKFILES = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "Pipfile.lock",
    "go.sum",
    "Cargo.lock",
    "Gemfile.lock",
    "composer.lock",
}

SCHEMA_FILES = re.compile(
    r"(openapi|swagger)\.(ya?ml|json)$|\.proto$|\.graphql$|schema\.(graphql|json)$",
    re.IGNORECASE,
)

MIGRATION_PATH = re.compile(
    r"(^|/)(migrations?|alembic/versions|db/migrate|prisma/migrations)(/|$)",
    re.IGNORECASE,
)

CI_CONFIG = re.compile(
    r"(^|/)(\.github/workflows/|\.gitlab-ci\.yml|Jenkinsfile|\.circleci/|azure-pipelines\.yml)",
    re.IGNORECASE,
)

CONFIG_SAMPLE = re.compile(r"\.env\.(example|sample|template)$|config\.(example|sample)\.", re.IGNORECASE)

# Destructive or blocking SQL, in rough order of how much it hurts.
RISKY_SQL = [
    (re.compile(r"\bDROP\s+TABLE\b", re.IGNORECASE), "drops a table"),
    (re.compile(r"\bDROP\s+COLUMN\b", re.IGNORECASE), "drops a column"),
    (re.compile(r"\bDROP\s+(CONSTRAINT|INDEX)\b", re.IGNORECASE), "drops a constraint or index"),
    (re.compile(r"\bRENAME\s+(TO|COLUMN)\b", re.IGNORECASE), "renames a table or column"),
    (re.compile(r"\bSET\s+NOT\s+NULL\b", re.IGNORECASE), "adds a NOT NULL constraint"),
    (re.compile(r"\bALTER\s+COLUMN\b.*\bTYPE\b", re.IGNORECASE), "changes a column type"),
    (re.compile(r"\bTRUNCATE\b", re.IGNORECASE), "truncates a table"),
]

# Route declarations across the frameworks this is most likely to meet.
ROUTE_DECL = re.compile(
    r"""(?x)
    @(?:\w+\.)?(?:router|app|blueprint)\.(get|post|put|patch|delete)\s*\(\s*["']([^"']+)["']
    | \b(?:app|router)\.(get|post|put|patch|delete)\s*\(\s*["']([^"']+)["']
    | \b(?:Route|HttpGet|HttpPost|RequestMapping|GetMapping|PostMapping)\s*\(\s*["']([^"']+)["']
    """
)

PUBLIC_DEF = re.compile(r"^\s*(?:async\s+)?(?:def|class)\s+([A-Za-z]\w*)\s*\(?", re.MULTILINE)
EXPORT_DECL = re.compile(
    r"^\s*export\s+(?:default\s+)?(?:async\s+)?(?:function|class|const|let|var)\s+(\w+)",
    re.MULTILINE,
)
ENV_LOOKUP = re.compile(r"""(?:os\.getenv|os\.environ\.get|process\.env)[\s(\[]*["']?(\w+)""")

PY_REQUIREMENT = re.compile(r"^\s*([A-Za-z0-9._-]+)\s*(==|>=|<=|~=|>|<)?\s*([0-9][\w.\-+]*)?")


def classify_path(path: str) -> list[str]:
    """Tag a changed path with every role it plays."""
    name = path.rsplit("/", 1)[-1]
    tags: list[str] = []

    if name in DEPENDENCY_MANIFESTS:
        tags.append("dependency_manifest")
    if name in LOCKFILES:
        tags.append("lockfile")
    if SCHEMA_FILES.search(path):
        tags.append("api_schema")
    if MIGRATION_PATH.search(path) or (path.endswith(".sql") and "migrat" in path.lower()):
        tags.append("migration")
    elif path.endswith(".sql"):
        tags.append("sql")
    if CI_CONFIG.search(path):
        tags.append("ci_config")
    if CONFIG_SAMPLE.search(path):
        tags.append("config_sample")
    if re.search(r"(^|/)(models?|entities|schema)\.py$|(^|/)models/", path, re.IGNORECASE):
        tags.append("orm_model")
    if re.search(r"(^|/)(routes?|controllers?|api|endpoints?|views?)(/|\.)", path, re.IGNORECASE):
        tags.append("route")
    if re.search(r"(^|/)tests?/|(^|/)test_|_test\.|\.spec\.|\.test\.", path, re.IGNORECASE):
        tags.append("test")
    if name in ("Dockerfile", "docker-compose.yml", "render.yaml", "vercel.json", "Procfile"):
        tags.append("deploy_config")

    return tags or ["source"]


# --------------------------------------------------------------------------
# Patch helpers
# --------------------------------------------------------------------------

def _added_lines(patch: str) -> list[str]:
    return [line[1:] for line in patch.splitlines() if line.startswith("+") and not line.startswith("+++")]


def _removed_lines(patch: str) -> list[str]:
    return [line[1:] for line in patch.splitlines() if line.startswith("-") and not line.startswith("---")]


def _parse_python_requirements(lines: list[str]) -> dict[str, str | None]:
    parsed: dict[str, str | None] = {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "-", "git+")):
            continue
        match = PY_REQUIREMENT.match(stripped)
        if match:
            parsed[match.group(1).lower()] = match.group(3)
    return parsed


def _parse_json_deps(lines: list[str]) -> dict[str, str | None]:
    """Pull "name": "version" pairs out of a package.json hunk.

    Only the changed lines are available, so this is a line scan rather than a
    JSON parse - which is fine, because we only care about what moved.
    """
    parsed: dict[str, str | None] = {}
    pattern = re.compile(r'"([@\w][\w./@-]*)"\s*:\s*"([^"]+)"')
    for line in lines:
        match = pattern.search(line)
        if match and not match.group(1) in ("name", "version", "description", "main", "license"):
            parsed[match.group(1).lower()] = match.group(2)
    return parsed


def _major(version: str | None) -> str | None:
    if not version:
        return None
    match = re.search(r"(\d+)", version)
    return match.group(1) if match else None


# --------------------------------------------------------------------------
# Individual fact collectors
# --------------------------------------------------------------------------

def analyse_dependencies(files: list[dict]) -> dict:
    """Added, removed and bumped dependencies, plus manifest/lockfile skew."""
    added: dict[str, str | None] = {}
    removed: dict[str, str | None] = {}
    bumped: list[dict] = []

    manifests_changed: list[str] = []
    lockfiles_changed: list[str] = []

    for entry in files:
        path = entry.get("filename", "")
        name = path.rsplit("/", 1)[-1]
        tags = classify_path(path)

        if "lockfile" in tags:
            lockfiles_changed.append(path)
            continue
        if "dependency_manifest" not in tags:
            continue

        manifests_changed.append(path)
        patch = entry.get("patch") or ""
        if not patch:
            continue

        if name == "package.json" or name.endswith(".json"):
            after = _parse_json_deps(_added_lines(patch))
            before = _parse_json_deps(_removed_lines(patch))
        else:
            after = _parse_python_requirements(_added_lines(patch))
            before = _parse_python_requirements(_removed_lines(patch))

        for package, version in after.items():
            if package in before:
                old = before[package]
                if old != version:
                    bumped.append(
                        {
                            "package": package,
                            "from": old,
                            "to": version,
                            "major_change": _major(old) != _major(version),
                            "file": path,
                        }
                    )
            else:
                added[package] = version

        for package, version in before.items():
            if package not in after:
                removed[package] = version

    return {
        "added": [{"package": k, "version": v} for k, v in sorted(added.items())],
        "removed": [{"package": k, "version": v} for k, v in sorted(removed.items())],
        "bumped": bumped,
        "manifests_changed": manifests_changed,
        "lockfiles_changed": lockfiles_changed,
        "manifest_without_lockfile": bool(manifests_changed and not lockfiles_changed),
        "lockfile_without_manifest": bool(lockfiles_changed and not manifests_changed),
        "unpinned_additions": [k for k, v in added.items() if v in (None, "", "*", "latest")],
    }


def analyse_migrations(files: list[dict]) -> dict:
    """Schema changes and whether they can deploy without breaking running code."""
    migration_files: list[str] = []
    orm_model_files: list[str] = []
    risky: list[dict] = []

    for entry in files:
        path = entry.get("filename", "")
        tags = classify_path(path)
        patch = entry.get("patch") or ""

        if "migration" in tags:
            migration_files.append(path)
        if "orm_model" in tags:
            orm_model_files.append(path)

        if "migration" in tags or "sql" in tags or "orm_model" in tags:
            for line in _added_lines(patch):
                for pattern, description in RISKY_SQL:
                    if pattern.search(line):
                        risky.append(
                            {
                                "file": path,
                                "operation": description,
                                "statement": line.strip()[:300],
                            }
                        )
                        break

    return {
        "migration_files": migration_files,
        "orm_model_files": orm_model_files,
        "risky_operations": risky,
        # Either half without the other is a deploy-ordering hazard.
        "model_changed_without_migration": bool(orm_model_files and not migration_files),
        "migration_without_model_change": bool(migration_files and not orm_model_files),
    }


def analyse_contracts(files: list[dict]) -> dict:
    """Removed routes, removed public symbols, and API schema edits."""
    removed_routes: list[dict] = []
    added_routes: list[dict] = []
    removed_symbols: list[dict] = []
    schema_files: list[str] = []

    def routes_in(lines: list[str]) -> set[tuple[str, str]]:
        found: set[tuple[str, str]] = set()
        for line in lines:
            for match in ROUTE_DECL.finditer(line):
                groups = [g for g in match.groups() if g]
                if len(groups) >= 2:
                    found.add((groups[0].upper(), groups[1]))
                elif groups:
                    found.add(("ANY", groups[0]))
        return found

    def symbols_in(lines: list[str]) -> set[str]:
        text = "\n".join(lines)
        return {
            name
            for name in PUBLIC_DEF.findall(text) + EXPORT_DECL.findall(text)
            if not name.startswith("_")
        }

    for entry in files:
        path = entry.get("filename", "")
        patch = entry.get("patch") or ""
        tags = classify_path(path)
        status = entry.get("status", "modified")

        if "api_schema" in tags:
            schema_files.append(path)

        if not patch:
            continue

        before_routes = routes_in(_removed_lines(patch))
        after_routes = routes_in(_added_lines(patch))
        for method, route in sorted(before_routes - after_routes):
            removed_routes.append({"file": path, "method": method, "path": route})
        for method, route in sorted(after_routes - before_routes):
            added_routes.append({"file": path, "method": method, "path": route})

        if status == "removed":
            continue

        for symbol in sorted(symbols_in(_removed_lines(patch)) - symbols_in(_added_lines(patch))):
            removed_symbols.append({"file": path, "symbol": symbol})

    return {
        "removed_routes": removed_routes,
        "added_routes": added_routes,
        "removed_public_symbols": removed_symbols,
        "api_schema_files_changed": schema_files,
        "deleted_files": [
            entry.get("filename", "")
            for entry in files
            if entry.get("status") == "removed"
        ],
        "renamed_files": [
            {"from": entry.get("previous_filename"), "to": entry.get("filename")}
            for entry in files
            if entry.get("status") == "renamed"
        ],
    }


def analyse_config(files: list[dict]) -> dict:
    """New environment lookups that nothing documents."""
    new_keys: set[str] = set()
    documented: set[str] = set()
    sample_changed = False

    for entry in files:
        path = entry.get("filename", "")
        patch = entry.get("patch") or ""
        tags = classify_path(path)

        if "config_sample" in tags:
            sample_changed = True
            for line in _added_lines(patch):
                if "=" in line and not line.strip().startswith("#"):
                    documented.add(line.split("=", 1)[0].strip())
            continue

        for line in _added_lines(patch):
            for match in ENV_LOOKUP.finditer(line):
                key = match.group(1)
                # A lookup with a default is not a deploy blocker.
                if re.search(r"(getenv|environ\.get)\([^)]*,", line) or "||" in line:
                    continue
                new_keys.add(key)

    return {
        "new_required_env_keys": sorted(new_keys - documented),
        "config_sample_updated": sample_changed,
    }


def summarise_ci(check_runs: dict, combined_status: dict) -> dict:
    """Roll CI up into something a gate can read."""
    runs = check_runs.get("check_runs") or []
    failing = [
        r.get("name", "unnamed")
        for r in runs
        if r.get("conclusion") in ("failure", "timed_out", "cancelled", "action_required")
    ]
    pending = [
        r.get("name", "unnamed")
        for r in runs
        if r.get("status") in ("queued", "in_progress")
    ]
    succeeded = [r.get("name", "unnamed") for r in runs if r.get("conclusion") == "success"]

    legacy_state = combined_status.get("state", "unknown")
    if legacy_state == "failure":
        failing.extend(
            s.get("context", "status")
            for s in combined_status.get("statuses", [])
            if s.get("state") == "failure"
        )
    elif legacy_state == "pending":
        pending.extend(
            s.get("context", "status")
            for s in combined_status.get("statuses", [])
            if s.get("state") == "pending"
        )

    if failing:
        state = "failing"
    elif pending:
        state = "pending"
    elif succeeded or legacy_state == "success":
        state = "passing"
    else:
        state = "none"

    return {
        "state": state,
        "failing": sorted(set(failing)),
        "pending": sorted(set(pending)),
        "passed_count": len(succeeded),
        "total_count": len(runs),
    }


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

async def build_integration_context(
    token: str, full_name: str, pr_number: int
) -> dict[str, Any]:
    """Gather every deterministic integration fact for one pull request.

    Degrades rather than failing: if GitHub will not answer a secondary
    question (check runs on a repo without Actions, a compare the token cannot
    read), that part of the context is marked unknown and the review continues.
    """
    pr = await gh.fetch_mergeability(token, full_name, pr_number)
    files = await gh.fetch_pr_files(token, full_name, pr_number)

    head_sha = (pr.get("head") or {}).get("sha") or ""
    base_ref = (pr.get("base") or {}).get("ref") or "main"
    head_ref = (pr.get("head") or {}).get("ref") or ""

    check_runs: dict = {"check_runs": []}
    combined_status: dict = {"state": "unknown", "statuses": []}
    comparison: dict = {}

    if head_sha:
        check_runs = await gh.fetch_check_runs(token, full_name, head_sha)
        combined_status = await gh.fetch_combined_status(token, full_name, head_sha)
        comparison = await gh.compare_refs(token, full_name, base_ref, head_sha)

    # Enrich once: the same entries feed the facts below, the merge gate, and
    # the per-file diff budget in helpers.build_agent_diff.
    enriched = [
        {**entry, "tags": classify_path(entry.get("filename", ""))} for entry in files
    ]

    changed_files = [
        {
            "path": entry.get("filename", ""),
            "status": entry.get("status", "modified"),
            "additions": entry.get("additions", 0),
            "deletions": entry.get("deletions", 0),
            "tags": entry["tags"],
        }
        for entry in enriched
    ]

    behind_by = comparison.get("behind_by")
    drifted_paths = {f.get("filename") for f in comparison.get("files", []) or []}
    changed_paths = {f["path"] for f in changed_files}
    overlapping_drift = sorted(drifted_paths & changed_paths)

    context = {
        "pull_request": {
            "number": pr_number,
            "title": pr.get("title"),
            "body": (pr.get("body") or "")[:2000],
            "author": (pr.get("user") or {}).get("login"),
            "draft": pr.get("draft", False),
            "state": pr.get("state"),
            "base_ref": base_ref,
            "head_ref": head_ref,
            "head_sha": head_sha,
            "changed_file_count": pr.get("changed_files", len(changed_files)),
            "additions": pr.get("additions", 0),
            "deletions": pr.get("deletions", 0),
        },
        "merge_state": {
            "mergeable": pr.get("mergeable"),
            "mergeable_state": pr.get("mergeable_state"),
            "rebaseable": pr.get("rebaseable"),
            "has_conflicts": pr.get("mergeable") is False
            or pr.get("mergeable_state") == "dirty",
        },
        "base_drift": {
            "behind_by": behind_by,
            # Commits on base that touch the same files merge cleanly and still
            # break - that is a semantic conflict, worth flagging separately.
            "overlapping_files": overlapping_drift,
        },
        "ci": summarise_ci(check_runs, combined_status),
        "changed_files": changed_files,
        "dependencies": analyse_dependencies(files),
        "migrations": analyse_migrations(files),
        "contracts": analyse_contracts(files),
        "config": analyse_config(files),
    }

    # Patches are large and are not part of the persisted facts, so they travel
    # under a private key that the orchestrator pops before storing anything.
    context["_files_with_patches"] = enriched

    logger.info(
        "Integration context for %s#%s: %s files, ci=%s, mergeable=%s",
        full_name,
        pr_number,
        len(changed_files),
        context["ci"]["state"],
        context["merge_state"]["mergeable"],
    )
    return context


def summarise_for_prompt(context: dict) -> str:
    """Render the facts compactly for the integration agent's prompt."""
    pr = context.get("pull_request", {})
    merge = context.get("merge_state", {})
    drift = context.get("base_drift", {})
    ci = context.get("ci", {})
    deps = context.get("dependencies", {})
    migrations = context.get("migrations", {})
    contracts = context.get("contracts", {})
    config = context.get("config", {})

    lines: list[str] = []
    add = lines.append

    add(f"Base branch: {pr.get('base_ref')}   Head: {pr.get('head_ref')}")
    add(
        "Merge state: mergeable={mergeable} ({state}); conflicts={conflicts}".format(
            mergeable=merge.get("mergeable"),
            state=merge.get("mergeable_state"),
            conflicts=merge.get("has_conflicts"),
        )
    )
    behind = drift.get("behind_by")
    add(
        f"Base drift: {behind if behind is not None else 'unknown'} commit(s) behind base"
        + (
            f"; base also changed these PR files: {', '.join(drift['overlapping_files'][:10])}"
            if drift.get("overlapping_files")
            else ""
        )
    )
    add(
        "CI: {state} ({passed}/{total} passed)".format(
            state=ci.get("state"), passed=ci.get("passed_count"), total=ci.get("total_count")
        )
        + (f"; failing: {', '.join(ci['failing'][:10])}" if ci.get("failing") else "")
        + (f"; pending: {', '.join(ci['pending'][:10])}" if ci.get("pending") else "")
    )

    add("")
    add("Dependency delta:")
    add(f"  added:   {deps.get('added') or 'none'}")
    add(f"  removed: {deps.get('removed') or 'none'}")
    add(f"  bumped:  {deps.get('bumped') or 'none'}")
    add(f"  manifest changed without lockfile: {deps.get('manifest_without_lockfile')}")
    add(f"  lockfile changed without manifest: {deps.get('lockfile_without_manifest')}")
    add(f"  unpinned additions: {deps.get('unpinned_additions') or 'none'}")

    add("")
    add("Schema / migrations:")
    add(f"  migration files: {migrations.get('migration_files') or 'none'}")
    add(f"  ORM model files: {migrations.get('orm_model_files') or 'none'}")
    add(f"  model changed without a migration: {migrations.get('model_changed_without_migration')}")
    add(f"  migration with no model change:    {migrations.get('migration_without_model_change')}")
    add(f"  risky operations: {migrations.get('risky_operations') or 'none'}")

    add("")
    add("Contracts:")
    add(f"  removed routes:         {contracts.get('removed_routes') or 'none'}")
    add(f"  added routes:           {contracts.get('added_routes') or 'none'}")
    add(f"  removed public symbols: {contracts.get('removed_public_symbols') or 'none'}")
    add(f"  API schema files changed: {contracts.get('api_schema_files_changed') or 'none'}")
    add(f"  deleted files: {contracts.get('deleted_files') or 'none'}")
    add(f"  renamed files: {contracts.get('renamed_files') or 'none'}")

    add("")
    add("Configuration:")
    add(f"  new required env keys: {config.get('new_required_env_keys') or 'none'}")
    add(f"  config sample updated: {config.get('config_sample_updated')}")

    add("")
    add("Changed files:")
    for entry in context.get("changed_files", [])[:80]:
        add(
            "  {path} ({status}, +{add_}/-{del_}) [{tags}]".format(
                path=entry["path"],
                status=entry["status"],
                add_=entry["additions"],
                del_=entry["deletions"],
                tags=",".join(entry["tags"]),
            )
        )

    return "\n".join(lines)
