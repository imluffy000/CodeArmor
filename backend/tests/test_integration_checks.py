"""The integration layer: deterministic facts and the merge gate.

These are the "check integration issues before merging" checks. They are
deliberately testable without an LLM, because a gate a model can talk its way
past is not a gate.
"""
from app.models.issue import Issue
from app.services import merge_gate_service
from app.services.integration_context_service import (
    analyse_config,
    analyse_contracts,
    analyse_dependencies,
    analyse_migrations,
    classify_path,
    summarise_ci,
)
from app.utils.helpers import build_agent_diff


def gh_file(filename, patch="", status="modified", additions=1, deletions=0):
    return {
        "filename": filename,
        "patch": patch,
        "status": status,
        "additions": additions,
        "deletions": deletions,
    }


class TestPathClassification:
    def test_recognises_the_roles_that_matter(self):
        assert "dependency_manifest" in classify_path("requirements.txt")
        assert "lockfile" in classify_path("frontend/package-lock.json")
        assert "migration" in classify_path("alembic/versions/001_add.py")
        assert "api_schema" in classify_path("docs/openapi.yaml")
        assert "route" in classify_path("backend/app/api/routes/review_routes.py")
        assert "test" in classify_path("backend/tests/test_thing.py")
        assert "ci_config" in classify_path(".github/workflows/ci.yml")
        assert "deploy_config" in classify_path("render.yaml")

    def test_falls_back_to_source(self):
        assert classify_path("src/lib/thing.go") == ["source"]


class TestDependencyAnalysis:
    def test_detects_a_major_bump(self):
        patch = "-requests==2.31.0\n+requests==3.0.0\n"
        result = analyse_dependencies([gh_file("requirements.txt", patch)])
        assert result["bumped"][0]["package"] == "requests"
        assert result["bumped"][0]["major_change"] is True

    def test_minor_bump_is_not_flagged_as_major(self):
        patch = "-requests==2.31.0\n+requests==2.32.1\n"
        result = analyse_dependencies([gh_file("requirements.txt", patch)])
        assert result["bumped"][0]["major_change"] is False

    def test_detects_a_manifest_changed_without_its_lockfile(self):
        result = analyse_dependencies([gh_file("package.json", '+    "left-pad": "^1.3.0"\n')])
        assert result["manifest_without_lockfile"] is True

    def test_lockfile_alongside_manifest_is_fine(self):
        result = analyse_dependencies(
            [
                gh_file("package.json", '+    "left-pad": "^1.3.0"\n'),
                gh_file("package-lock.json", '+    "left-pad": "1.3.0"\n'),
            ]
        )
        assert result["manifest_without_lockfile"] is False

    def test_detects_a_removed_dependency(self):
        result = analyse_dependencies([gh_file("requirements.txt", "-oldlib==1.0.0\n")])
        assert result["removed"][0]["package"] == "oldlib"


class TestMigrationAnalysis:
    def test_flags_a_dropped_column(self):
        patch = "+ALTER TABLE users DROP COLUMN email;\n"
        result = analyse_migrations([gh_file("migrations/003_drop.sql", patch)])
        assert any("drops a column" in item["operation"] for item in result["risky_operations"])

    def test_flags_not_null_without_default(self):
        patch = "+ALTER TABLE users ALTER COLUMN name SET NOT NULL;\n"
        result = analyse_migrations([gh_file("migrations/004.sql", patch)])
        assert result["risky_operations"]

    def test_additive_migration_is_not_risky(self):
        patch = "+ALTER TABLE users ADD COLUMN nickname text;\n"
        result = analyse_migrations([gh_file("migrations/005.sql", patch)])
        assert result["risky_operations"] == []

    def test_flags_a_model_change_with_no_migration(self):
        result = analyse_migrations([gh_file("app/db/models.py", "+    new_field = CharField()\n")])
        assert result["model_changed_without_migration"] is True


class TestContractAnalysis:
    def test_detects_a_removed_route(self):
        patch = '-@router.get("/legacy")\n+@router.get("/current")\n'
        result = analyse_contracts([gh_file("app/api/routes/things.py", patch)])
        assert {"method": "GET", "path": "/legacy", "file": "app/api/routes/things.py"} in result[
            "removed_routes"
        ]
        assert any(r["path"] == "/current" for r in result["added_routes"])

    def test_detects_a_removed_public_function(self):
        patch = "-def compute_total(items):\n+def compute_sum(items):\n"
        result = analyse_contracts([gh_file("app/lib/math.py", patch)])
        symbols = {item["symbol"] for item in result["removed_public_symbols"]}
        assert "compute_total" in symbols

    def test_private_helpers_are_not_contract_changes(self):
        patch = "-def _internal(x):\n"
        result = analyse_contracts([gh_file("app/lib/math.py", patch)])
        assert result["removed_public_symbols"] == []

    def test_records_deletions_and_renames(self):
        files = [
            gh_file("old.py", status="removed"),
            {**gh_file("new.py", status="renamed"), "previous_filename": "older.py"},
        ]
        result = analyse_contracts(files)
        assert "old.py" in result["deleted_files"]
        assert result["renamed_files"][0]["from"] == "older.py"


class TestConfigAnalysis:
    def test_flags_a_new_required_env_var(self):
        patch = '+API_KEY = os.getenv("NEW_REQUIRED_KEY")\n'
        result = analyse_config([gh_file("app/core/config.py", patch)])
        assert "NEW_REQUIRED_KEY" in result["new_required_env_keys"]

    def test_a_getenv_with_a_default_is_not_required(self):
        patch = '+LEVEL = os.getenv("LOG_LEVEL", "INFO")\n'
        result = analyse_config([gh_file("app/core/config.py", patch)])
        assert "LOG_LEVEL" not in result["new_required_env_keys"]

    def test_documenting_the_key_clears_the_flag(self):
        files = [
            gh_file("app/core/config.py", '+X = os.getenv("DOCUMENTED_KEY")\n'),
            gh_file(".env.example", "+DOCUMENTED_KEY=\n"),
        ]
        result = analyse_config(files)
        assert "DOCUMENTED_KEY" not in result["new_required_env_keys"]


class TestCiSummary:
    def test_failing_checks_win_over_passing_ones(self):
        runs = {
            "check_runs": [
                {"name": "tests", "conclusion": "failure", "status": "completed"},
                {"name": "lint", "conclusion": "success", "status": "completed"},
            ]
        }
        result = summarise_ci(runs, {"state": "unknown", "statuses": []})
        assert result["state"] == "failing"
        assert result["failing"] == ["tests"]

    def test_pending_is_reported_distinctly_from_none(self):
        runs = {"check_runs": [{"name": "tests", "status": "in_progress"}]}
        assert summarise_ci(runs, {})["state"] == "pending"
        assert summarise_ci({"check_runs": []}, {})["state"] == "none"

    def test_reads_the_legacy_status_api(self):
        legacy = {"state": "failure", "statuses": [{"context": "ci/old", "state": "failure"}]}
        result = summarise_ci({"check_runs": []}, legacy)
        assert result["state"] == "failing"
        assert "ci/old" in result["failing"]


class TestMergeGate:
    def _issue(self, severity="LOW"):
        return Issue(
            file="a.py", severity=severity, category="QUALITY",
            issue="something", suggestion="fix it",
        )

    def test_a_clean_review_is_clear_but_never_approved(self):
        result = merge_gate_service.evaluate([], {}, coverage={"coverage_percent": 100})
        assert result["verdict"] == merge_gate_service.CLEAR
        # The strongest available claim is "nothing blocking", not "approved".
        assert "approv" not in result["headline"].lower()
        assert "human review" in result["headline"].lower()

    def test_merge_conflicts_block(self):
        context = {"merge_state": {"mergeable": False, "mergeable_state": "dirty"}}
        result = merge_gate_service.evaluate([], context)
        assert result["verdict"] == merge_gate_service.BLOCKED
        assert result["gates"]["conflicts"]["status"] == "fail"

    def test_failing_ci_blocks_and_names_the_check(self):
        context = {"ci": {"state": "failing", "failing": ["unit-tests"], "passed_count": 0, "total_count": 1}}
        result = merge_gate_service.evaluate([], context)
        assert result["verdict"] == merge_gate_service.BLOCKED
        assert any("unit-tests" in blocker for blocker in result["blockers"])

    def test_a_critical_finding_blocks(self):
        result = merge_gate_service.evaluate([self._issue("CRITICAL")], {})
        assert result["verdict"] == merge_gate_service.BLOCKED

    def test_a_high_finding_cautions_rather_than_blocks(self):
        result = merge_gate_service.evaluate([self._issue("HIGH")], {})
        assert result["verdict"] == merge_gate_service.CAUTION

    def test_a_low_finding_alone_does_not_block(self):
        # One unused import used to put the PR into a blocking REQUEST_CHANGES.
        result = merge_gate_service.evaluate([self._issue("LOW")], {})
        assert result["verdict"] != merge_gate_service.BLOCKED

    def test_overlapping_base_drift_blocks(self):
        context = {"base_drift": {"behind_by": 4, "overlapping_files": ["app/main.py"]}}
        result = merge_gate_service.evaluate([], context)
        assert result["verdict"] == merge_gate_service.BLOCKED
        assert any("merge cleanly and still break" in b for b in result["blockers"])

    def test_plain_base_drift_only_warns(self):
        context = {"base_drift": {"behind_by": 4, "overlapping_files": []}}
        result = merge_gate_service.evaluate([], context)
        assert result["verdict"] == merge_gate_service.CAUTION

    def test_a_destructive_migration_blocks(self):
        context = {
            "migrations": {
                "risky_operations": [
                    {"file": "m.sql", "operation": "drops a column", "statement": "DROP COLUMN x"}
                ]
            }
        }
        result = merge_gate_service.evaluate([], context)
        assert result["verdict"] == merge_gate_service.BLOCKED
        assert result["gates"]["schema"]["status"] == "fail"

    def test_a_removed_route_blocks(self):
        context = {"contracts": {"removed_routes": [{"method": "GET", "path": "/v1/things", "file": "r.py"}]}}
        result = merge_gate_service.evaluate([], context)
        assert result["verdict"] == merge_gate_service.BLOCKED

    def test_a_partial_review_is_never_reported_as_clear(self):
        coverage = {"truncated": True, "coverage_percent": 30, "files_omitted": ["a.py", "b.py"]}
        result = merge_gate_service.evaluate([], {}, coverage=coverage)
        assert result["verdict"] == merge_gate_service.CAUTION
        assert any("partial" in w for w in result["warnings"])

    def test_a_failed_reviewer_is_surfaced_not_swallowed(self):
        # A review whose security agent timed out must not read as clean.
        errors = [{"agent": "security", "error": "timed out"}]
        result = merge_gate_service.evaluate([], {}, agent_errors=errors)
        assert result["verdict"] == merge_gate_service.CAUTION
        assert any("security" in w for w in result["warnings"])
        assert result["gates"]["pipeline"]["status"] == "warn"

    def test_every_gate_is_reported(self):
        result = merge_gate_service.evaluate([], {})
        for gate in ("conflicts", "ci", "base_drift", "schema", "contracts",
                     "dependencies", "config", "findings", "coverage", "pipeline"):
            assert gate in result["gates"]


class TestDiffBudgeting:
    def test_names_every_file_even_when_hunks_do_not_fit(self):
        files = [
            {**gh_file("important.py", "+" + "x" * 500), "tags": ["source"]},
            {**gh_file("huge.py", "+" + "y" * 5000), "tags": ["source"]},
        ]
        result = build_agent_diff(files, budget=1000)
        # The agent must be able to tell "not reviewed" from "unchanged".
        assert "huge.py" in result["text"]
        assert "huge.py" in result["files_omitted"]
        assert result["truncated"] is True

    def test_prioritises_migrations_over_lockfiles(self):
        files = [
            {**gh_file("package-lock.json", "+" + "l" * 900), "tags": ["lockfile"]},
            {**gh_file("migrations/001.sql", "+ALTER TABLE t ADD c int;"), "tags": ["migration"]},
        ]
        result = build_agent_diff(files, budget=1000)
        assert "migrations/001.sql" in result["files_included"]

    def test_reports_full_coverage_when_everything_fits(self):
        files = [{**gh_file("a.py", "+one line"), "tags": ["source"]}]
        result = build_agent_diff(files, budget=10000)
        assert result["truncated"] is False
        assert result["coverage_percent"] == 100

    def test_falls_back_to_the_raw_diff_without_file_data(self):
        result = build_agent_diff([], raw_diff="diff --git a/a.py b/a.py\n+x\n", budget=10000)
        assert "a.py" in result["text"]
