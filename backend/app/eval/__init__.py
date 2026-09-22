"""The evaluation harness.

Without this, every prompt edit is an unmeasured change to product behaviour:
you cannot tell whether a rewrite found more real problems or just more
problems. That is the difference between a tool you can tune and one you
change on vibes.

Two tiers, because they have very different costs:

**Offline** (`python -m app.eval.run`) needs no model call and no credits, so
it runs in CI on every push. It scores the deterministic half of the pipeline,
which is most of what breaks: JSON parsing, finding validation, severity
normalisation, cross-agent deduplication, the integration fact extractors, the
merge gate, and whether a partial or failed review can ever be reported as
clean.

**Live** (`python -m app.eval.run --live`) calls the real model against frozen
diffs and scores agent precision and recall, schema-validity rate, and
resistance to prompt injection. It costs credits, so it is opt-in and run by
hand when a prompt or model changes.

Both write a scorecard and compare it against `baseline.json`. A regression
fails the run.
"""
