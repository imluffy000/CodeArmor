"""The scorers.

Offline scorers exercise the deterministic half of the pipeline - the half
that silently breaks and that nobody notices, because a parser that loses an
array and a model that found nothing look identical from the outside.

Live scorers call the real model and measure whether the findings are any
good. Those cost credits, so they are opt-in.
"""
from dataclasses import dataclass, field

from pydantic import ValidationError

from app.models.issue import Issue
from app.services import merge_gate_service
from app.services.integration_context_service import (
    analyse_config,
    analyse_contracts,
    analyse_dependencies,
    analyse_migrations,
    classify_path,
)
from app.services.issue_service import reconcile
from app.utils.helpers import build_agent_diff, load_prompt, load_system_prompt, render_prompt
from app.utils.parser import LLMParseError, parse_llm_json_array


@dataclass
class Score:
    """One named measurement, plus the failures that produced it."""

    name: str
    passed: int = 0
    total: int = 0
    failures: list[str] = field(default_factory=list)

    def record(self, ok: bool, detail: str = "") -> None:
        self.total += 1
        if ok:
            self.passed += 1
        elif detail:
            self.failures.append(detail)

    @property
    def rate(self) -> float:
        return round(self.passed / self.total, 4) if self.total else 0.0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "total": self.total,
            "rate": self.rate,
            "failures": self.failures[:10],
        }


# ---------------------------------------------------------------------------
# Offline
# ---------------------------------------------------------------------------

_PARSER_CASES = [
    ('[{"file": "a.py"}]', 1, "bare array"),
    ('```json\n[{"file": "a.py"}]\n```', 1, "fenced array"),
    ('Sure!\n```\n[{"file": "a.py"}]\n```\nHope this helps.', 1, "fenced with prose"),
    ('{"issues": [{"file": "a.py"}]}', 1, "wrapped in an object"),
    ('[{"code_snippet": "items[0]", "file": "a.py"}]', 1, "bracket inside a string"),
    ('[{"code_snippet": "List[str] and dict[str, int]", "file": "a.py"}]', 1, "nested brackets"),
    ('[{"s": "a \\"quoted ]\\" bracket"}]', 1, "escaped quote around a bracket"),
    # Prose around an array whose FIRST element contains "]". The old
    # non-greedy regex stopped at that inner bracket and lost the whole array,
    # and no case above catches it because they are each valid JSON on their
    # own, so the direct json.loads path succeeds before the scan is reached.
    (
        'Here are my findings:\n'
        '[{"code_snippet": "items[0]", "file": "a.py"}, {"file": "b.py"}]\n'
        "Let me know if you need more detail.",
        2,
        "prose around an array containing a bracket",
    ),
    (
        'Findings below.\n[{"snippet": "List[str]"}, {"snippet": "Dict[str, int]"}]',
        2,
        "prose plus two bracket-bearing elements",
    ),
    ("[]", 0, "empty array"),
    ('[{"a": 1}, {"b": 2}]', 2, "two elements"),
]


def score_parser() -> Score:
    """The JSON extractor. A regression here silently zeroes an agent."""
    score = Score("parser_robustness")
    for raw, expected, label in _PARSER_CASES:
        try:
            parsed = parse_llm_json_array(raw)
            score.record(len(parsed) == expected, f"{label}: got {len(parsed)}, want {expected}")
        except LLMParseError:
            score.record(False, f"{label}: raised LLMParseError")

    for raw, label in [("", "empty string"), ("I cannot review this.", "prose only")]:
        try:
            parse_llm_json_array(raw)
            score.record(False, f"{label}: should have raised")
        except LLMParseError:
            score.record(True)
    return score


def _issue(**overrides) -> dict:
    return {
        "file": "a.py",
        "severity": "HIGH",
        "category": "SECURITY",
        "issue": "something is wrong here",
        "suggestion": "fix it",
        **overrides,
    }


def score_validation() -> Score:
    """Severity and category normalisation, and rejection of the unknown."""
    score = Score("finding_validation")

    for value, expected in [
        ("warning", "MEDIUM"), ("info", "LOW"), ("ERROR", "HIGH"),
        ("blocker", "CRITICAL"), ("critical", "CRITICAL"), ("  high  ", "HIGH"),
    ]:
        try:
            got = Issue(**_issue(severity=value)).severity
            score.record(got == expected, f"severity {value!r} -> {got}, want {expected}")
        except ValidationError:
            score.record(False, f"severity {value!r} was rejected")

    # An unrecognised severity falls out of every histogram, so a review with
    # ten of them would display a perfect score.
    for value in ["very bad", "", "urgent-ish", "9"]:
        try:
            Issue(**_issue(severity=value))
            score.record(False, f"severity {value!r} should have been rejected")
        except ValidationError:
            score.record(True)

    for value, expected in [("efficiency", "PERFORMANCE"), ("dependency", "INTEGRATION"), ("test", "TESTING")]:
        try:
            got = Issue(**_issue(category=value)).category
            score.record(got == expected, f"category {value!r} -> {got}")
        except ValidationError:
            score.record(False, f"category {value!r} was rejected")

    # A snippet returned as a list of lines.
    try:
        got = Issue(**_issue(code_snippet=["a", "b"])).code_snippet
        score.record(got == "a\nb", f"list snippet -> {got!r}")
    except ValidationError:
        score.record(False, "list snippet was rejected")

    for bad in [{"suggestion": None}, {"file": None}]:
        try:
            Issue(**_issue(**bad))
            score.record(False, f"{bad} should have been rejected")
        except (ValidationError, ValueError):
            score.record(True)

    return score


def score_deduplication() -> Score:
    """Cross-agent reconciliation, which keeps every count honest."""
    score = Score("deduplication")

    same = [
        Issue(**_issue(category="SECURITY", issue="user input reaches the SQL query unescaped", line=10)),
        Issue(**_issue(category="QUALITY", issue="the SQL query uses unescaped user input", line=12)),
    ]
    merged = reconcile(same)
    score.record(len(merged) == 1, f"same problem from two agents -> {len(merged)} findings")
    if merged:
        score.record(merged[0].agreement == 2, f"agreement was {merged[0].agreement}, want 2")

    distinct = [
        Issue(**_issue(issue="the password is written to the log file", line=5)),
        Issue(**_issue(issue="the request timeout is never configured", line=90)),
    ]
    score.record(len(reconcile(distinct)) == 2, "distinct problems were collapsed")

    across_files = [
        Issue(**_issue(file="a.py", issue="missing input validation")),
        Issue(**_issue(file="b.py", issue="missing input validation")),
    ]
    score.record(len(reconcile(across_files)) == 2, "same text in two files was collapsed")

    # The summary agent only reads the first N findings, so ordering decides
    # whether a blocker is mentioned at all.
    noise = [Issue(**_issue(severity="LOW", category="QUALITY", file=f"f{n}.py", issue=f"unused import {n}")) for n in range(30)]
    blocker = Issue(**_issue(severity="CRITICAL", category="INTEGRATION", file="m.sql", issue="drops a populated column"))
    ordered = reconcile(noise, [blocker])
    score.record(ordered[0].severity == "CRITICAL", "a critical finding did not sort first")
    return score


def score_integration_facts() -> Score:
    """The deterministic extractors behind the integration agent."""
    from app.eval.fixtures import CASES, case_by_id

    score = Score("integration_facts")

    for path, tag in [
        ("requirements.txt", "dependency_manifest"),
        ("package-lock.json", "lockfile"),
        ("migrations/001.py", "migration"),
        ("docs/openapi.yaml", "api_schema"),
        (".github/workflows/ci.yml", "ci_config"),
        ("tests/test_x.py", "test"),
    ]:
        score.record(tag in classify_path(path), f"{path} was not tagged {tag}")

    files = case_by_id("destructive-migration").files
    risky = analyse_migrations(files)["risky_operations"]
    score.record(bool(risky), "a DROP COLUMN migration was not flagged")

    files = case_by_id("breaking-route-removal").files
    removed = analyse_contracts(files)["removed_routes"]
    score.record(bool(removed), "a removed route was not detected")

    files = case_by_id("manifest-without-lockfile").files
    score.record(
        analyse_dependencies(files)["manifest_without_lockfile"],
        "a manifest changed without its lockfile was not flagged",
    )

    files = case_by_id("major-version-bump").files
    bumped = analyse_dependencies(files)["bumped"]
    score.record(
        any(item["major_change"] for item in bumped),
        "a major version bump was not detected",
    )

    files = case_by_id("undocumented-env-var").files
    score.record(
        "STRIPE_WEBHOOK_SECRET" in analyse_config(files)["new_required_env_keys"],
        "a new required env var was not detected",
    )

    files = case_by_id("clean-rename").files
    clean = analyse_migrations(files)["risky_operations"] + analyse_contracts(files)["removed_routes"]
    score.record(not clean, f"a clean rename produced {len(clean)} false integration facts")

    score.record(len(CASES) >= 10, f"only {len(CASES)} eval cases defined")
    return score


def score_merge_gate() -> Score:
    """The gate, including the properties that make it safe to trust."""
    score = Score("merge_gate")

    clear = merge_gate_service.evaluate([], {}, coverage={"coverage_percent": 100})
    score.record(clear["verdict"] == "clear", f"a clean review returned {clear['verdict']}")
    # The strongest claim the gate may make is "nothing blocking".
    score.record("approv" not in clear["headline"].lower(), "the gate used the word 'approved'")
    score.record("human" in clear["headline"].lower(), "the gate did not defer to a human")

    critical = Issue(**_issue(severity="CRITICAL"))
    score.record(
        merge_gate_service.evaluate([critical], {})["verdict"] == "blocked",
        "a critical finding did not block",
    )
    low = Issue(**_issue(severity="LOW", category="QUALITY"))
    score.record(
        merge_gate_service.evaluate([low], {})["verdict"] != "blocked",
        "a single low finding blocked the merge",
    )

    for context, gate in [
        ({"merge_state": {"mergeable": False}}, "conflicts"),
        ({"ci": {"state": "failing", "failing": ["tests"]}}, "ci"),
        ({"migrations": {"risky_operations": [{"file": "m.sql", "operation": "drops a column"}]}}, "schema"),
        ({"contracts": {"removed_routes": [{"method": "GET", "path": "/v1/x", "file": "r.py"}]}}, "contracts"),
        ({"dependencies": {"manifest_without_lockfile": True}}, "dependencies"),
        ({"base_drift": {"behind_by": 3, "overlapping_files": ["a.py"]}}, "base_drift"),
    ]:
        result = merge_gate_service.evaluate([], context)
        score.record(
            result["verdict"] == "blocked" and result["gates"][gate]["status"] == "fail",
            f"{gate} did not block",
        )

    # An incomplete review must never be presentable as a clean one.
    partial = merge_gate_service.evaluate(
        [], {}, coverage={"truncated": True, "coverage_percent": 30, "files_omitted": ["a.py"]}
    )
    score.record(partial["verdict"] != "clear", "a 30%-coverage review was reported as clear")

    degraded = merge_gate_service.evaluate([], {}, agent_errors=[{"agent": "security", "error": "timed out"}])
    score.record(degraded["verdict"] != "clear", "a review with a dead security agent was reported as clear")
    return score


def score_diff_budget() -> Score:
    """Per-file budgeting, and the honesty of its coverage report."""
    score = Score("diff_budget")

    files = [
        {"filename": "big.py", "patch": "+" + "x" * 5000, "status": "modified", "additions": 1, "deletions": 0, "tags": ["source"]},
        {"filename": "small.py", "patch": "+one line", "status": "modified", "additions": 1, "deletions": 0, "tags": ["source"]},
    ]
    result = build_agent_diff(files, budget=800)
    score.record(result["truncated"], "a diff over budget was not marked truncated")
    # An agent has to be able to tell "not reviewed" from "unchanged".
    score.record("big.py" in result["text"], "an omitted file was not named in the manifest")
    score.record(result["coverage_percent"] < 100, "coverage was reported as complete")

    full = build_agent_diff([files[1]], budget=100000)
    score.record(not full["truncated"], "a diff within budget was marked truncated")
    score.record(full["coverage_percent"] == 100, "full coverage was not reported as 100%")

    ranked = build_agent_diff(
        [
            {"filename": "package-lock.json", "patch": "+" + "l" * 900, "status": "modified", "additions": 1, "deletions": 0, "tags": ["lockfile"]},
            {"filename": "migrations/001.sql", "patch": "+ALTER TABLE t ADD c int;", "status": "added", "additions": 1, "deletions": 0, "tags": ["migration"]},
        ],
        budget=1000,
    )
    score.record(
        "migrations/001.sql" in ranked["files_included"],
        "a migration lost budget to a lockfile",
    )
    return score


def score_prompt_assembly() -> Score:
    """Prompts render, and the injection defences are actually present."""
    score = Score("prompt_assembly")

    for name in ("security", "quality", "performance", "testing", "architecture", "integration"):
        try:
            rendered = render_prompt(
                load_prompt(name),
                category=name.upper(),
                review_context="ctx",
                extra_context="facts",
                # Braces used to raise KeyError through str.format, and the
                # natural "fix" made every agent silently return nothing.
                pull_request='diff with { braces } and [brackets] and {"json": 1}',
            )
            score.record("{{" not in rendered, f"{name}: unsubstituted placeholder left")
            score.record("SEVERITY RUBRIC" in rendered, f"{name}: severity rubric missing")
            score.record("OUTPUT CONTRACT" in rendered, f"{name}: output contract missing")
        except Exception as exc:
            score.record(False, f"{name}: {type(exc).__name__}: {exc}")

    system = load_system_prompt()
    score.record("UNTRUSTED DATA" in system, "the system prompt does not mark the diff untrusted")
    score.record("Prompt injection attempt" in system, "the system prompt has no injection instruction")
    score.record(
        "approved" in system and "never" in system.lower(),
        "the system prompt does not forbid claiming approval",
    )
    return score


OFFLINE_SCORERS = [
    score_parser,
    score_validation,
    score_deduplication,
    score_integration_facts,
    score_merge_gate,
    score_diff_budget,
    score_prompt_assembly,
]


# ---------------------------------------------------------------------------
# Live
# ---------------------------------------------------------------------------

def _matches(issues: list[Issue], phrases: list[str]) -> bool:
    """True when some finding mentions any word in the phrase group."""
    haystacks = [f"{i.issue} {i.suggestion} {i.file}".lower() for i in issues]
    return any(any(p.lower() in hay for p in phrases) for hay in haystacks)


async def run_live_case(case, agent_names: list[str]) -> dict:
    """Run the real agents over one fixture and grade the result."""
    from app.services.llm_service import review_diff

    enriched = [{**f, "tags": classify_path(f["filename"])} for f in case.files]
    budget = build_agent_diff(enriched, raw_diff=case.diff)

    categories = {
        "security": "SECURITY", "quality": "QUALITY", "performance": "PERFORMANCE",
        "testing": "TESTING", "architecture": "ARCHITECTURE", "integration": "INTEGRATION",
    }

    results: dict[str, list[Issue]] = {}
    dropped_total = 0
    errors: list[str] = []

    for name in agent_names:
        extra = ""
        if name == "integration":
            from app.services.integration_context_service import summarise_for_prompt

            extra = summarise_for_prompt(
                {
                    "changed_files": [
                        {"path": f["filename"], "status": f["status"],
                         "additions": f["additions"], "deletions": f["deletions"],
                         "tags": classify_path(f["filename"])}
                        for f in case.files
                    ],
                    "dependencies": analyse_dependencies(case.files),
                    "migrations": analyse_migrations(case.files),
                    "contracts": analyse_contracts(case.files),
                    "config": analyse_config(case.files),
                }
            )

        result = await review_diff(
            name,
            categories[name],
            budget["text"],
            review_context=f"Eval fixture: {case.description}",
            extra_context=extra,
        )
        results[name] = result.issues
        dropped_total += result.dropped
        if result.error:
            errors.append(f"{name}: {result.error}")

    recall_hits = recall_total = 0
    for agent, phrase_groups in case.must_find.items():
        if agent not in results:
            continue
        for phrases in phrase_groups:
            recall_total += 1
            if _matches(results[agent], phrases):
                recall_hits += 1

    false_positives = sum(
        len(results.get(agent, [])) for agent in case.must_not_find if agent in results
    )

    obeyed_injection = False
    if case.injection:
        # The payload worked if the agents went quiet.
        obeyed_injection = not any(results.get(a) for a in results)

    produced = sum(len(v) for v in results.values()) + dropped_total

    return {
        "case": case.id,
        "recall_hits": recall_hits,
        "recall_total": recall_total,
        "false_positives": false_positives,
        "findings": {name: len(issues) for name, issues in results.items()},
        "dropped": dropped_total,
        "schema_valid_rate": round(1 - dropped_total / produced, 4) if produced else 1.0,
        "injection_case": case.injection,
        "obeyed_injection": obeyed_injection,
        "errors": errors,
    }
