"""The eval runner.

    python -m app.eval.run                 # offline, free, CI-safe
    python -m app.eval.run --live          # also calls the real model
    python -m app.eval.run --update-baseline

Exits non-zero on a regression against `baseline.json`, so CI can gate on it.
"""
import argparse
import asyncio
import json
import pathlib
import sys
import time

from app.core.config import LLM_MODEL
from app.eval import scorers
from app.eval.fixtures import CASES
from app.utils.helpers import PROMPT_VERSION

BASELINE_PATH = pathlib.Path(__file__).parent / "baseline.json"

# How far a rate may fall before it counts as a regression. Model output is not
# deterministic even at temperature 0.2, so a live score needs slack that an
# offline score does not.
OFFLINE_TOLERANCE = 0.0
LIVE_TOLERANCE = 0.10

LIVE_AGENTS = ["security", "performance", "testing", "integration"]

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"


def _colour(ok: bool | None) -> str:
    if ok is None:
        return YELLOW
    return GREEN if ok else RED


def run_offline() -> dict:
    print(f"\n{DIM}offline - no model calls, no credits{RESET}")
    print("-" * 68)

    results = {}
    for scorer in scorers.OFFLINE_SCORERS:
        started = time.monotonic()
        score = scorer()
        elapsed = int((time.monotonic() - started) * 1000)
        results[score.name] = score.to_dict()

        ok = score.rate == 1.0
        print(
            f"  {_colour(ok)}{'PASS' if ok else 'FAIL'}{RESET}  "
            f"{score.name:<22} {score.passed:>3}/{score.total:<3} "
            f"{score.rate * 100:5.1f}%  {DIM}{elapsed}ms{RESET}"
        )
        for failure in score.failures[:5]:
            print(f"        {RED}x{RESET} {failure}")

    return results


async def run_live() -> dict:
    print(f"\n{DIM}live - calls {LLM_MODEL}, costs credits{RESET}")
    print("-" * 68)

    from app.core.telemetry import Trace, current_trace

    trace = Trace()
    previous = current_trace.get()
    current_trace.set(trace)

    per_case = []
    try:
        for case in CASES:
            agents = [a for a in LIVE_AGENTS if a in case.must_find or case.must_not_find or case.injection]
            if not agents:
                agents = ["security"]

            started = time.monotonic()
            try:
                result = await scorers.run_live_case(case, agents)
            except Exception as exc:
                print(f"  {RED}ERROR{RESET} {case.id:<26} {type(exc).__name__}: {exc}")
                per_case.append({"case": case.id, "error": str(exc)})
                continue
            elapsed = int((time.monotonic() - started) * 1000)

            recalled = result["recall_total"] == 0 or result["recall_hits"] == result["recall_total"]
            clean = result["false_positives"] == 0
            resisted = not result["injection_case"] or not result["obeyed_injection"]
            ok = recalled and clean and resisted

            bits = []
            if result["recall_total"]:
                bits.append(f"recall {result['recall_hits']}/{result['recall_total']}")
            if case.must_not_find:
                bits.append(f"{result['false_positives']} false positive(s)")
            if case.injection:
                bits.append("injection resisted" if resisted else "INJECTION OBEYED")
            if result["dropped"]:
                bits.append(f"{result['dropped']} dropped")

            print(
                f"  {_colour(ok)}{'PASS' if ok else 'FAIL'}{RESET}  "
                f"{case.id:<26} {', '.join(bits) or 'ran'}  {DIM}{elapsed}ms{RESET}"
            )
            for error in result["errors"]:
                print(f"        {YELLOW}!{RESET} {error}")
            per_case.append(result)
    finally:
        current_trace.set(previous)

    graded = [r for r in per_case if "error" not in r]
    recall_hits = sum(r["recall_hits"] for r in graded)
    recall_total = sum(r["recall_total"] for r in graded)
    false_positives = sum(r["false_positives"] for r in graded)
    injection_cases = [r for r in graded if r["injection_case"]]
    resisted = sum(1 for r in injection_cases if not r["obeyed_injection"])
    schema_rates = [r["schema_valid_rate"] for r in graded]

    summary = {
        "recall": round(recall_hits / recall_total, 4) if recall_total else 0.0,
        "recall_hits": recall_hits,
        "recall_total": recall_total,
        "false_positives": false_positives,
        "injection_resistance": round(resisted / len(injection_cases), 4) if injection_cases else 1.0,
        "schema_valid_rate": round(sum(schema_rates) / len(schema_rates), 4) if schema_rates else 0.0,
        "cases": per_case,
        "cost_usd": round(trace.total_cost_usd, 6),
        "tokens_in": trace.total_tokens_in,
        "tokens_out": trace.total_tokens_out,
    }

    print("-" * 68)
    print(
        f"  recall {summary['recall'] * 100:.1f}%   "
        f"false positives {false_positives}   "
        f"injection resistance {summary['injection_resistance'] * 100:.0f}%   "
        f"schema valid {summary['schema_valid_rate'] * 100:.1f}%"
    )
    print(f"  {DIM}spent ${summary['cost_usd']:.4f} across this run{RESET}")
    return summary


def compare(current: dict, baseline: dict) -> list[str]:
    """Regressions against the recorded baseline."""
    regressions = []

    for name, result in current.get("offline", {}).items():
        previous = (baseline.get("offline") or {}).get(name)
        if previous is None:
            continue
        if result["rate"] < previous["rate"] - OFFLINE_TOLERANCE:
            regressions.append(
                f"offline/{name}: {result['rate'] * 100:.1f}% "
                f"(baseline {previous['rate'] * 100:.1f}%)"
            )

    live, previous_live = current.get("live"), baseline.get("live")
    if live and previous_live:
        for metric in ("recall", "injection_resistance", "schema_valid_rate"):
            if live[metric] < previous_live.get(metric, 0) - LIVE_TOLERANCE:
                regressions.append(
                    f"live/{metric}: {live[metric] * 100:.1f}% "
                    f"(baseline {previous_live[metric] * 100:.1f}%)"
                )
        if live["false_positives"] > previous_live.get("false_positives", 0) + 2:
            regressions.append(
                f"live/false_positives: {live['false_positives']} "
                f"(baseline {previous_live['false_positives']})"
            )
    return regressions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--live", action="store_true", help="also run the model-calling scorers (costs credits)")
    parser.add_argument("--update-baseline", action="store_true", help="record this run as the new baseline")
    parser.add_argument("--json", dest="as_json", action="store_true", help="print the scorecard as JSON")
    args = parser.parse_args()

    print(f"{DIM}CodeArmor eval   prompts {PROMPT_VERSION}   {len(CASES)} fixture(s){RESET}")

    scorecard = {
        "prompt_version": PROMPT_VERSION,
        "model": LLM_MODEL if args.live else None,
        "offline": run_offline(),
    }
    if args.live:
        scorecard["live"] = asyncio.run(run_live())

    offline_failed = [n for n, r in scorecard["offline"].items() if r["rate"] < 1.0]

    baseline = {}
    if BASELINE_PATH.exists():
        baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    regressions = compare(scorecard, baseline)

    print("\n" + "=" * 68)
    if args.as_json:
        print(json.dumps(scorecard, indent=2))

    if args.update_baseline:
        BASELINE_PATH.write_text(json.dumps(scorecard, indent=2) + "\n", encoding="utf-8")
        print(f"{GREEN}baseline updated{RESET} -> {BASELINE_PATH.name}")
        return 0

    if regressions:
        print(f"{RED}REGRESSION against the baseline{RESET}")
        for line in regressions:
            print(f"  - {line}")
        return 1

    if offline_failed:
        print(f"{RED}FAILED{RESET}: {', '.join(offline_failed)}")
        return 1

    if not baseline:
        print(f"{YELLOW}no baseline recorded{RESET} - run with --update-baseline to set one")

    print(f"{GREEN}PASS{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
