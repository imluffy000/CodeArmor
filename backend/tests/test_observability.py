"""Tracing, cost accounting and the eval harness itself."""
import json
import logging

import pytest
from fastapi.testclient import TestClient

from app.core import logging as log_module
from app.core.telemetry import (
    CostCeilingExceeded,
    Span,
    Trace,
    agent_span,
    check_cost_ceiling,
    current_trace,
    estimate_cost,
)
from app.db.models import AgentRun, Review
from app.main import app
from app.services.auth_service import CSRF_COOKIE, SESSION_COOKIE, create_session_token


class FakeResponse:
    def __init__(self, usage=None, metadata=None):
        self.content = "[]"
        self.usage_metadata = usage
        self.response_metadata = metadata or {}


class TestCostAccounting:
    def test_reads_token_counts_from_a_response(self):
        span = Span("security")
        span.record_usage(
            FakeResponse(usage={"input_tokens": 1200, "output_tokens": 300}),
            "deepseek/deepseek-chat-v3-0324",
        )
        assert span.tokens_in == 1200
        assert span.tokens_out == 300
        assert span.cost_usd > 0

    def test_falls_back_to_the_legacy_usage_shape(self):
        span = Span("security")
        span.record_usage(
            FakeResponse(metadata={"token_usage": {"prompt_tokens": 50, "completion_tokens": 10}}),
            "openai/gpt-4o-mini",
        )
        assert span.tokens_in == 50 and span.tokens_out == 10

    def test_a_provider_reported_cost_beats_the_estimate(self):
        span = Span("security")
        span.record_usage(
            FakeResponse(usage={"input_tokens": 1000, "output_tokens": 1000}, metadata={"cost": 0.0042}),
            "deepseek/deepseek-chat-v3-0324",
        )
        assert span.cost_usd == 0.0042
        assert span.cost_is_estimate is False

    def test_an_unknown_model_still_costs_something(self):
        # Reporting zero would read as "this review was free", which is worse
        # than an imprecise estimate.
        assert estimate_cost("some/unlisted-model", 1_000_000, 1_000_000) > 0

    def test_a_malformed_response_does_not_raise(self):
        span = Span("security")
        span.record_usage(object(), "whatever")  # no usage attributes at all
        assert span.tokens_in == 0

    def test_a_trace_rolls_up_its_spans(self):
        trace = Trace()
        for tokens in (100, 200):
            with trace.span("agent") as span:
                span.record_usage(
                    FakeResponse(usage={"input_tokens": tokens, "output_tokens": tokens}),
                    "deepseek/deepseek-chat-v3-0324",
                )
        assert trace.total_tokens_in == 300
        assert trace.total_cost_usd > 0
        assert len(trace.to_dict()["spans"]) == 2


class TestSpans:
    def test_an_exception_marks_the_span_and_propagates(self):
        trace = Trace()
        with pytest.raises(ValueError):
            with trace.span("security"):
                raise ValueError("boom")
        assert trace.spans[0].status == "error"
        assert trace.failed_spans

    def test_agent_span_works_without_a_trace(self):
        # Tests and the eval harness run untraced; an agent must not care.
        assert current_trace.get() is None
        with agent_span("security") as span:
            span.findings = 3
        assert span.findings == 3

    def test_agent_span_attaches_to_the_current_trace(self):
        trace = Trace()
        token = current_trace.set(trace)
        try:
            with agent_span("security"):
                pass
        finally:
            current_trace.reset(token)
        assert [s.name for s in trace.spans] == ["security"]

    @pytest.mark.asyncio
    async def test_parallel_tasks_share_one_trace(self):
        import asyncio

        trace = Trace()
        token = current_trace.set(trace)

        async def work(name):
            with agent_span(name):
                await asyncio.sleep(0)

        try:
            # asyncio.create_task copies the context, which is what lets six
            # parallel graph branches record into one trace.
            await asyncio.gather(*[work(n) for n in ("a", "b", "c")])
        finally:
            current_trace.reset(token)

        assert sorted(s.name for s in trace.spans) == ["a", "b", "c"]


class TestCostCeiling:
    def test_it_stops_a_runaway_review(self):
        trace = Trace()
        with trace.span("expensive") as span:
            span.cost_usd = 5.0
        with pytest.raises(CostCeilingExceeded, match="cost ceiling"):
            check_cost_ceiling(trace, 0.50)

    def test_a_normal_review_passes(self):
        trace = Trace()
        with trace.span("cheap") as span:
            span.cost_usd = 0.002
        check_cost_ceiling(trace, 0.50)

    def test_a_zero_ceiling_disables_the_check(self):
        trace = Trace()
        with trace.span("anything") as span:
            span.cost_usd = 999.0
        check_cost_ceiling(trace, 0)


class TestStructuredLogging:
    def test_json_mode_emits_one_object_per_line(self, monkeypatch, capsys):
        monkeypatch.setattr(log_module, "LOG_FORMAT", "json")
        record = logging.LogRecord("codearmor", logging.INFO, __file__, 1, "hello", None, None)
        record.request_id = "abc123"
        rendered = log_module.JsonFormatter("app").format(record)
        payload = json.loads(rendered)
        assert payload["message"] == "hello"
        assert payload["request_id"] == "abc123"
        assert payload["stream"] == "app"

    def test_extra_fields_become_top_level_keys(self):
        record = logging.LogRecord("codearmor.audit", logging.INFO, __file__, 1, "e", None, None)
        record.fields = {"review_id": 7, "cost_usd": 0.01}
        payload = json.loads(log_module.JsonFormatter("audit").format(record))
        assert payload["review_id"] == 7 and payload["cost_usd"] == 0.01

    def test_redaction_still_applies_in_json_mode(self):
        record = logging.LogRecord(
            "codearmor", logging.INFO, __file__, 1,
            "using ghp_abcdefghijklmnopqrstuvwxyz012345", None, None,
        )
        log_module.RedactFilter().filter(record)
        payload = json.loads(log_module.JsonFormatter("app").format(record))
        assert "ghp_abcdefghijklmnopqrstuvwxyz012345" not in payload["message"]


class TestOpsEndpoints:
    @pytest.fixture
    def client(self, user):
        client = TestClient(app)
        client.cookies.set(SESSION_COOKIE, create_session_token(user))
        client.cookies.set(CSRF_COOKIE, "csrf-test-token")
        return client

    def _review(self, user, repo, **overrides):
        review = Review.create(
            user=user, repository=repo, repo_full_name=repo.full_name,
            pr_number=1, head_sha="abc", payload=json.dumps({"stats": {"score": 80}}),
            trace_id="trace123", duration_ms=4200, tokens_in=1000, tokens_out=400,
            cost_usd=0.0031, model="deepseek/deepseek-chat-v3-0324",
            prompt_version="abc123", trace=json.dumps({"trace_id": "trace123", "spans": []}),
            **overrides,
        )
        AgentRun.create(
            review=review, agent="security", status="ok", model="m",
            duration_ms=1800, tokens_in=600, tokens_out=200, cost_usd=0.002,
            findings=3, dropped=1, parse_status="ok",
        )
        AgentRun.create(
            review=review, agent="testing", status="timeout",
            duration_ms=120000, error="timed out",
        )
        return review

    def test_the_trace_is_retrievable(self, client, user, repo):
        review = self._review(user, repo)
        body = client.get(f"/ops/reviews/{review.id}/trace").json()
        assert body["trace_id"] == "trace123"
        assert body["cost_usd"] == 0.0031
        # A findings change must be attributable to a prompt edit.
        assert body["prompt_version"] == "abc123"
        assert {a["agent"] for a in body["agents"]} == {"security", "testing"}

    def test_a_trace_is_scoped_to_its_owner(self, client, user, repo):
        from app.db.models import User
        from app.services.crypto_service import encrypt_token

        review = self._review(user, repo)
        other = User.create(
            github_id=5150, login="other", access_token_encrypted=encrypt_token("t")
        )
        client.cookies.set(SESSION_COOKIE, create_session_token(other))
        assert client.get(f"/ops/reviews/{review.id}/trace").status_code == 404

    def test_usage_rolls_up_cost_and_failure_rates(self, client, user, repo):
        self._review(user, repo)
        body = client.get("/ops/usage").json()
        assert body["reviews"] == 1
        assert body["cost_usd"] == 0.0031
        assert body["cost_per_review_usd"] == 0.0031

        agents = {a["agent"]: a for a in body["agents"]}
        # A rising drop rate is the earliest signal that output quality slipped.
        assert agents["security"]["drop_rate"] == 0.25
        assert agents["testing"]["failure_rate"] == 1.0

    def test_usage_requires_a_session(self):
        assert TestClient(app).get("/ops/usage").status_code == 401


class TestEvalHarness:
    """The harness has to be trustworthy before its verdict means anything."""

    def test_every_offline_scorer_is_clean(self):
        from app.eval.scorers import OFFLINE_SCORERS

        for scorer in OFFLINE_SCORERS:
            score = scorer()
            assert score.total > 0, f"{score.name} asserted nothing"
            assert score.rate == 1.0, f"{score.name} failed: {score.failures}"

    def test_the_fixtures_cover_the_cases_that_matter(self):
        from app.eval.fixtures import CASES

        ids = {c.id for c in CASES}
        assert len(CASES) >= 12
        # A clean diff and an injection payload are the two cases a review bot
        # most needs to get right and most often does not.
        assert any(c.must_not_find for c in CASES), "no negative case"
        assert any(c.injection for c in CASES), "no prompt-injection case"
        assert {"destructive-migration", "breaking-route-removal"} <= ids

    def test_every_fixture_builds_a_parseable_diff(self):
        from app.eval.fixtures import CASES
        from app.services.diff_parser_service import parse_diff_files

        for case in CASES:
            parsed = parse_diff_files(case.diff)
            assert parsed, f"{case.id} produced an unparseable diff"
            assert len(parsed) == len(case.files)

    def test_a_regression_is_detected(self):
        from app.eval.run import compare

        baseline = {"offline": {"parser_robustness": {"rate": 1.0, "passed": 13, "total": 13}}}
        current = {"offline": {"parser_robustness": {"rate": 0.84, "passed": 11, "total": 13}}}
        assert compare(current, baseline)

    def test_an_unchanged_run_is_not_a_regression(self):
        from app.eval.run import compare

        baseline = {"offline": {"parser_robustness": {"rate": 1.0, "passed": 13, "total": 13}}}
        assert compare(dict(baseline), baseline) == []

    def test_live_scores_tolerate_model_nondeterminism(self):
        from app.eval.run import compare

        baseline = {"live": {"recall": 0.90, "injection_resistance": 1.0,
                             "schema_valid_rate": 1.0, "false_positives": 0}}
        # A small dip is noise, not a regression.
        noise = {"live": {"recall": 0.85, "injection_resistance": 1.0,
                          "schema_valid_rate": 1.0, "false_positives": 1}}
        assert compare(noise, baseline) == []

        real = {"live": {"recall": 0.40, "injection_resistance": 0.5,
                         "schema_valid_rate": 1.0, "false_positives": 9}}
        assert len(compare(real, baseline)) >= 2

    def test_the_committed_baseline_is_current(self):
        """Guards against a baseline recorded from a failing run."""
        import pathlib

        from app.eval.run import BASELINE_PATH

        assert BASELINE_PATH.exists(), "no baseline committed"
        baseline = json.loads(pathlib.Path(BASELINE_PATH).read_text(encoding="utf-8"))
        for name, result in baseline["offline"].items():
            assert result["rate"] == 1.0, f"baseline recorded {name} at {result['rate']}"


class TestTimestamps:
    """Peewee's SQLite DateTimeField cannot parse an offset, so a tz-aware
    datetime writes fine and reads back as a *string* - which made every
    endpoint returning a timestamp raise AttributeError on .isoformat()."""

    def test_a_stored_timestamp_reads_back_as_a_datetime(self, user, repo):
        import datetime

        review = Review.create(
            user=user, repository=repo, repo_full_name=repo.full_name,
            pr_number=1, payload="{}",
        )
        fetched = Review.get_by_id(review.id)
        assert isinstance(fetched.created_at, datetime.datetime)

    def test_serialisation_is_explicitly_utc(self, user, repo):
        from app.core.timeutil import iso_utc

        review = Review.create(
            user=user, repository=repo, repo_full_name=repo.full_name,
            pr_number=1, payload="{}",
        )
        rendered = iso_utc(Review.get_by_id(review.id).created_at)
        # Without the Z a browser parses the string as local time and every
        # timestamp shifts by the viewer's offset.
        assert rendered.endswith("Z")

    def test_a_legacy_offset_string_still_renders(self):
        from app.core.timeutil import iso_utc

        assert iso_utc("2026-09-22 22:24:45.110310+00:00") == "2026-09-22T22:24:45.110310Z"
        assert iso_utc(None) is None

    def test_an_aware_datetime_is_normalised(self):
        import datetime

        from app.core.timeutil import iso_utc

        aware = datetime.datetime(2026, 1, 1, 12, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=5)))
        assert iso_utc(aware) == "2026-01-01T07:00:00Z"

    def test_stored_time_is_naive_utc(self):
        from app.core.timeutil import utcnow

        now = utcnow()
        assert now.tzinfo is None

    def test_every_timestamp_field_survives_the_api(self, user, repo):
        """The endpoints that return timestamps must not 500."""
        from fastapi.testclient import TestClient

        from app.services.auth_service import CSRF_COOKIE, SESSION_COOKIE, create_session_token

        Review.create(
            user=user, repository=repo, repo_full_name=repo.full_name,
            pr_number=1, payload=json.dumps({"stats": {"score": 90}}),
        )
        client = TestClient(app)
        client.cookies.set(SESSION_COOKIE, create_session_token(user))
        client.cookies.set(CSRF_COOKIE, "csrf-test-token")

        for path in ("/repos", f"/repos/{repo.id}/sync", "/reviews", "/ops/usage"):
            response = client.get(path)
            assert response.status_code == 200, f"{path} -> {response.status_code}"
