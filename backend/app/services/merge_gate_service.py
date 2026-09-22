"""The merge gate: turn findings plus GitHub facts into a readiness verdict.

This is the "before merging" half of the product. It is deliberately
deterministic - a gate that an LLM can talk its way past is not a gate - and it
never returns "approved". The best verdict available is "nothing blocking found",
which is a different claim.
"""
from app.core.constants import SEVERITY_ORDER
from app.models.issue import Issue

# Verdicts, worst first.
BLOCKED = "blocked"
CAUTION = "caution"
CLEAR = "clear"


def _gate(status: str, detail: str) -> dict:
    return {"status": status, "detail": detail}


def evaluate(
    issues: list[Issue],
    integration_context: dict | None,
    coverage: dict | None = None,
    agent_errors: list[dict] | None = None,
) -> dict:
    """Return a structured readiness verdict.

    Each gate reports pass / fail / unknown independently, so the UI can show
    *why* something is blocked rather than one opaque colour.
    """
    context = integration_context or {}
    coverage = coverage or {}
    agent_errors = agent_errors or []

    merge_state = context.get("merge_state", {})
    drift = context.get("base_drift", {})
    ci = context.get("ci", {})
    migrations = context.get("migrations", {})
    contracts = context.get("contracts", {})
    dependencies = context.get("dependencies", {})
    config = context.get("config", {})

    gates: dict[str, dict] = {}
    blockers: list[str] = []
    warnings: list[str] = []

    # --- merge conflicts ---
    # Derived here rather than trusting a precomputed flag, so the gate is
    # correct for any caller that hands it raw GitHub fields.
    has_conflicts = (
        merge_state.get("has_conflicts")
        or merge_state.get("mergeable") is False
        or merge_state.get("mergeable_state") == "dirty"
    )
    if has_conflicts:
        gates["conflicts"] = _gate("fail", "This branch has conflicts with its base.")
        blockers.append("Merge conflicts with the base branch must be resolved.")
    elif merge_state.get("mergeable") is None:
        gates["conflicts"] = _gate("unknown", "GitHub had not finished computing mergeability.")
    else:
        gates["conflicts"] = _gate("pass", "No conflicts with the base branch.")

    # --- CI ---
    ci_state = ci.get("state", "none")
    if ci_state == "failing":
        names = ", ".join(ci.get("failing", [])[:5]) or "one or more checks"
        gates["ci"] = _gate("fail", f"Failing checks: {names}.")
        blockers.append(f"CI is failing ({names}).")
    elif ci_state == "pending":
        names = ", ".join(ci.get("pending", [])[:5]) or "checks"
        gates["ci"] = _gate("unknown", f"Still running: {names}.")
        warnings.append("CI has not finished yet.")
    elif ci_state == "passing":
        gates["ci"] = _gate("pass", f"{ci.get('passed_count', 0)} check(s) passed.")
    else:
        gates["ci"] = _gate("unknown", "No CI checks were reported for this commit.")

    # --- base drift ---
    behind = drift.get("behind_by")
    overlapping = drift.get("overlapping_files") or []
    if behind is None:
        gates["base_drift"] = _gate("unknown", "Could not compare against the base branch.")
    elif behind == 0:
        gates["base_drift"] = _gate("pass", "Up to date with the base branch.")
    elif overlapping:
        gates["base_drift"] = _gate(
            "fail",
            f"{behind} commit(s) behind, and the base also changed "
            f"{len(overlapping)} file(s) this PR touches.",
        )
        blockers.append(
            "The base branch changed files this PR also changes - it can merge "
            "cleanly and still break. Rebase and re-run the checks."
        )
    else:
        gates["base_drift"] = _gate("warn", f"{behind} commit(s) behind the base branch.")
        warnings.append(f"Branch is {behind} commit(s) behind its base.")

    # --- schema safety ---
    risky = migrations.get("risky_operations") or []
    if risky:
        operations = ", ".join(sorted({item["operation"] for item in risky}))
        gates["schema"] = _gate("fail", f"Destructive schema operations: {operations}.")
        blockers.append(
            f"This change {operations}. Confirm the expand-and-contract sequence "
            "and the deploy order before merging."
        )
    elif migrations.get("model_changed_without_migration"):
        gates["schema"] = _gate("warn", "A data model changed with no migration alongside it.")
        warnings.append("A data model changed but no migration was added.")
    elif migrations.get("migration_files"):
        gates["schema"] = _gate("pass", "Migrations present with no destructive operations.")
    else:
        gates["schema"] = _gate("pass", "No schema changes.")

    # --- API contracts ---
    removed_routes = contracts.get("removed_routes") or []
    removed_symbols = contracts.get("removed_public_symbols") or []
    if removed_routes:
        listing = ", ".join(f"{r['method']} {r['path']}" for r in removed_routes[:5])
        gates["contracts"] = _gate("fail", f"Routes removed or renamed: {listing}.")
        blockers.append(f"Removed or renamed routes ({listing}) may break live clients.")
    elif removed_symbols:
        listing = ", ".join(item["symbol"] for item in removed_symbols[:5])
        gates["contracts"] = _gate("warn", f"Public symbols removed: {listing}.")
        warnings.append(f"Public symbols were removed or renamed ({listing}).")
    elif contracts.get("api_schema_files_changed"):
        gates["contracts"] = _gate("warn", "An API schema file changed - check it is additive.")
        warnings.append("An API schema file changed; confirm the change is backward compatible.")
    else:
        gates["contracts"] = _gate("pass", "No public contract removals detected.")

    # --- dependencies ---
    major = [item for item in (dependencies.get("bumped") or []) if item.get("major_change")]
    if dependencies.get("manifest_without_lockfile"):
        gates["dependencies"] = _gate(
            "fail", "A dependency manifest changed without its lockfile."
        )
        blockers.append(
            "A dependency manifest changed without its lockfile, so CI and "
            "production will install different versions."
        )
    elif major:
        listing = ", ".join(f"{item['package']} {item['from']}->{item['to']}" for item in major[:5])
        gates["dependencies"] = _gate("warn", f"Major version bumps: {listing}.")
        warnings.append(f"Major dependency bumps ({listing}) are breaking until proven otherwise.")
    elif dependencies.get("unpinned_additions"):
        listing = ", ".join(dependencies["unpinned_additions"][:5])
        gates["dependencies"] = _gate("warn", f"Unpinned additions: {listing}.")
        warnings.append(f"Unpinned dependencies added ({listing}).")
    else:
        gates["dependencies"] = _gate("pass", "No risky dependency changes.")

    # --- configuration ---
    new_keys = config.get("new_required_env_keys") or []
    if new_keys:
        listing = ", ".join(new_keys[:5])
        gates["config"] = _gate("warn", f"New required environment variables: {listing}.")
        warnings.append(
            f"New required environment variables ({listing}) must be set before this deploys."
        )
    else:
        gates["config"] = _gate("pass", "No new required configuration.")

    # --- review findings ---
    critical = [i for i in issues if i.severity == "CRITICAL"]
    high = [i for i in issues if i.severity == "HIGH"]
    if critical:
        gates["findings"] = _gate("fail", f"{len(critical)} critical finding(s).")
        blockers.append(
            f"{len(critical)} critical finding(s) - see "
            + ", ".join(sorted({i.file for i in critical})[:3])
            + "."
        )
    elif high:
        gates["findings"] = _gate("warn", f"{len(high)} high-severity finding(s).")
        warnings.append(f"{len(high)} high-severity finding(s) to review.")
    elif issues:
        gates["findings"] = _gate("pass", f"{len(issues)} finding(s), none high or critical.")
    else:
        gates["findings"] = _gate("pass", "No findings.")

    # --- coverage and pipeline health ---
    coverage_percent = coverage.get("coverage_percent", 100)
    if coverage.get("truncated"):
        gates["coverage"] = _gate(
            "warn",
            f"Only about {coverage_percent}% of the diff was reviewed; "
            f"{len(coverage.get('files_omitted') or [])} file(s) were not read.",
        )
        warnings.append(
            f"This review covered about {coverage_percent}% of the diff - treat it as partial."
        )
    else:
        gates["coverage"] = _gate("pass", "The whole diff was reviewed.")

    if agent_errors:
        failed = ", ".join(sorted({e.get("agent", "unknown") for e in agent_errors}))
        gates["pipeline"] = _gate("warn", f"These reviewers did not complete: {failed}.")
        warnings.append(
            f"The {failed} reviewer(s) did not complete, so those findings are missing."
        )
    else:
        gates["pipeline"] = _gate("pass", "All reviewers completed.")

    if blockers:
        verdict = BLOCKED
        headline = f"Not ready to merge: {len(blockers)} blocking issue(s)."
    elif warnings:
        verdict = CAUTION
        headline = f"Merge with care: {len(warnings)} thing(s) to check first."
    else:
        verdict = CLEAR
        headline = "Nothing blocking was found. A human review is still required."

    return {
        "verdict": verdict,
        "headline": headline,
        "blockers": blockers,
        "warnings": warnings,
        "gates": gates,
        "highest_severity": max(
            (i.severity for i in issues), key=lambda s: SEVERITY_ORDER.get(s, 0), default=None
        ),
    }


def summarise_for_prompt(readiness: dict) -> str:
    """Render the verdict for the summary agent's prompt."""
    lines = [readiness.get("headline", "")]
    for blocker in readiness.get("blockers", []):
        lines.append(f"  BLOCKING: {blocker}")
    for warning in readiness.get("warnings", []):
        lines.append(f"  CHECK: {warning}")
    return "\n".join(line for line in lines if line)
