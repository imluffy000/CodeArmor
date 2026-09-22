"""Finding validation, deduplication, scoring and the folder tree."""
import pytest
from pydantic import ValidationError

from app.models.issue import Issue
from app.services.issue_service import (
    compute_score,
    deduplicate_issues,
    merge_issues,
    reconcile,
    sort_issues,
)
from app.utils.parser import LLMParseError, parse_llm_json_array
from app.visualizer.folder_tree import build_folder_tree
from app.visualizer.review_output import build_folder_view, build_stats


def make_issue(**overrides) -> Issue:
    base = {
        "file": "app/main.py",
        "severity": "HIGH",
        "category": "SECURITY",
        "issue": "Something is wrong",
        "suggestion": "Fix it",
    }
    return Issue(**{**base, **overrides})


class TestIssueValidation:
    def test_normalises_severity_aliases(self):
        assert make_issue(severity="warning").severity == "MEDIUM"
        assert make_issue(severity="info").severity == "LOW"
        assert make_issue(severity="blocker").severity == "CRITICAL"

    def test_accepts_semgrep_error_severity(self):
        # semgrep uses ERROR for its real security rules; rejecting it dropped
        # exactly the findings that matter most.
        assert make_issue(severity="ERROR").severity == "HIGH"

    def test_rejects_unknown_severity(self):
        # An unrecognised severity falls out of every histogram and score, so a
        # PR with ten "SEVERE" findings would display as clean.
        with pytest.raises(ValidationError):
            make_issue(severity="very bad")

    def test_normalises_category_aliases(self):
        assert make_issue(category="efficiency").category == "PERFORMANCE"
        assert make_issue(category="dependency").category == "INTEGRATION"

    def test_coerces_snippet_given_as_a_list(self):
        issue = make_issue(code_snippet=["line one", "line two"])
        assert issue.code_snippet == "line one\nline two"

    def test_rejects_null_required_text(self):
        with pytest.raises(ValidationError):
            make_issue(suggestion=None)


class TestParser:
    def test_parses_a_bare_array(self):
        assert parse_llm_json_array('[{"a": 1}]') == [{"a": 1}]

    def test_survives_a_bracket_inside_a_snippet(self):
        # A non-greedy regex stopped at the inner "]" and lost the whole array.
        raw = '[{"code_snippet": "items[0] = List[str]", "file": "a.py"}]'
        assert parse_llm_json_array(raw)[0]["file"] == "a.py"

    def test_extracts_from_a_fenced_block_with_prose(self):
        raw = 'Sure, here you go:\n```json\n[{"file": "a.py"}]\n```\nHope that helps.'
        assert parse_llm_json_array(raw) == [{"file": "a.py"}]

    def test_unwraps_a_keyed_object(self):
        assert parse_llm_json_array('{"issues": [{"file": "a.py"}]}') == [{"file": "a.py"}]

    def test_raises_on_unusable_output(self):
        with pytest.raises(LLMParseError):
            parse_llm_json_array("I could not review this pull request.")


class TestDeduplication:
    def test_collapses_the_same_problem_from_two_agents(self):
        issues = [
            make_issue(category="SECURITY", issue="user input reaches the SQL query unescaped"),
            make_issue(category="QUALITY", issue="the SQL query uses unescaped user input"),
        ]
        deduped = deduplicate_issues(issues)
        assert len(deduped) == 1
        assert deduped[0].agreement == 2
        assert "QUALITY" in deduped[0].also_reported_as

    def test_keeps_distinct_problems_in_the_same_file(self):
        issues = [
            make_issue(issue="the password is written to the log file"),
            make_issue(issue="the request timeout is never configured anywhere"),
        ]
        assert len(deduplicate_issues(issues)) == 2

    def test_keeps_the_same_text_in_different_files(self):
        issues = [
            make_issue(file="a.py", issue="missing input validation here"),
            make_issue(file="b.py", issue="missing input validation here"),
        ]
        assert len(deduplicate_issues(issues)) == 2

    def test_survivor_keeps_the_worst_severity(self):
        issues = [
            make_issue(severity="LOW", issue="the auth check is missing on this route"),
            make_issue(severity="CRITICAL", issue="this route is missing its auth check"),
        ]
        assert deduplicate_issues(issues)[0].severity == "CRITICAL"

    def test_merge_issues_takes_any_number_of_lists(self):
        assert len(merge_issues([make_issue()], [], [make_issue()], None or [])) == 2


class TestOrdering:
    def test_sorts_worst_first(self):
        issues = [
            make_issue(severity="LOW", file="a.py"),
            make_issue(severity="CRITICAL", file="b.py"),
            make_issue(severity="MEDIUM", file="c.py"),
        ]
        assert [i.severity for i in sort_issues(issues)] == ["CRITICAL", "MEDIUM", "LOW"]

    def test_reconcile_orders_integration_findings_above_style_notes(self):
        # The summary agent only reads the first N findings, so an unsorted list
        # could hide a blocking integration problem behind a run of LOW notes.
        low_notes = [
            make_issue(severity="LOW", category="QUALITY", file=f"f{n}.py", issue=f"unused import {n}")
            for n in range(30)
        ]
        blocker = make_issue(
            severity="CRITICAL", category="INTEGRATION", file="migrations/001.sql",
            issue="this migration drops a populated column",
        )
        assert reconcile(low_notes, [blocker])[0].category == "INTEGRATION"


class TestFolderTree:
    def test_handles_a_path_that_is_both_a_file_and_a_directory(self):
        # Previously crashed: one ordering raised KeyError('severity') at render
        # time, the other TypeError while building the tree.
        for files in (["src/app/main.py", "src/app"], ["src/app", "src/app/main.py"]):
            tree = build_folder_tree([make_issue(file=path) for path in files])
            rendered = build_folder_view(tree)
            assert "main.py" in rendered
            assert "app" in rendered

    def test_drops_absolute_path_noise(self):
        tree = build_folder_tree([make_issue(file="/app/app/services/llm.py")])
        assert "" not in tree["dirs"]

    def test_groups_several_findings_per_file(self):
        tree = build_folder_tree([make_issue(file="a.py"), make_issue(file="a.py")])
        assert len(tree["files"]["a.py"]) == 2


class TestStats:
    def test_every_severity_bucket_is_present_and_worst_first(self):
        stats = build_stats([make_issue(severity="HIGH")])
        assert list(stats["by_severity"]) == ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
        assert stats["by_severity"]["CRITICAL"] == 0
        assert stats["blocking_issues"] == 1

    def test_integration_category_is_reported(self):
        stats = build_stats([make_issue(category="INTEGRATION")])
        assert stats["by_category"]["INTEGRATION"] == 1

    def test_score_is_100_for_a_clean_review(self):
        assert compute_score([]) == 100

    def test_score_does_not_floor_at_zero_for_a_large_review(self):
        # A linear penalty hit 0 after seven high findings and then stopped
        # discriminating between a bad PR and a catastrophic one.
        many = [make_issue(severity="HIGH") for _ in range(20)]
        more = [make_issue(severity="CRITICAL") for _ in range(20)]
        assert 0 < compute_score(many)
        assert compute_score(more) < compute_score(many)

    def test_partial_coverage_caps_the_score(self):
        assert compute_score([], coverage_percent=20) <= 60
