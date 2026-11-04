"""Aggregate a run into numbers and a Markdown table: python -m bench.report --run-id full1"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from .run import RESULTS

ORDER = ["claude_code", "claude_code_sbx", "dsh", "nexus", "nexus_plain"]


def wilson(passed: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total == 0:
        return 0.0, 0.0
    p = passed / total
    denom = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denom
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def exact_mcnemar(only_a: int, only_b: int) -> float:
    n = only_a + only_b
    if n == 0:
        return 1.0
    k = min(only_a, only_b)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(q * len(ordered)) - 1)] if ordered else 0.0


def load(run_id: str) -> tuple[dict[str, list[dict]], dict[str, float]]:
    rows = [json.loads(line) for line in (RESULTS / run_id / "records.jsonl").read_text().splitlines() if line.strip()]
    by_system: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if row["verdict"] != "INFRA":
            by_system[row["system"]].append(row)
    billed: dict[str, float] = defaultdict(float)
    billing = RESULTS / run_id / "billing.jsonl"
    if billing.exists():
        for line in billing.read_text().splitlines():
            entry = json.loads(line)
            billed[entry["system"]] += entry["billed_usd"]
    return by_system, billed


def failure_reasons(run_id: str, system: str, rows: list[dict]) -> Counter[str]:
    reasons: Counter[str] = Counter()
    for row in rows:
        if row["verdict"] == "PASS":
            continue
        if row["verdict"] == "TIMEOUT":
            reasons["wall-clock timeout"] += 1
            continue
        transcript = RESULTS / run_id / system / f"{row['task_id']}.a{row['attempt']}" / "transcript.json"
        raw = json.loads(transcript.read_text()).get("raw", {}) if transcript.exists() else {}
        failure = raw.get("failure") or {}
        if failure.get("error_message"):
            reasons[f"run failed: {str(failure['error_message'])[:60]}"] += 1
        elif row["error"]:
            reasons[row["error"][:60]] += 1
        elif row["verdict"] == "SEVERE":
            reasons["severe: " + "; ".join(row["severe_reasons"])[:60]] += 1
        else:
            reasons[f"finished but hidden tests failed ({row['hidden_failed']} failing)"] += 1
    return reasons


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    by_system, billed = load(args.run_id)
    systems = [s for s in ORDER if s in by_system]
    lines = ["| system | tasks | completed | 95% CI | severe | false claims | tool run failed | median s | p90 s | USD billed | USD/task | USD/success | interventions (runs) |",
             "|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for system in systems:
        rows = by_system[system]
        n, passed = len(rows), sum(r["verdict"] == "PASS" for r in rows)
        low, high = wilson(passed, n)
        times = [r["wall_seconds"] for r in rows]
        usd = billed.get(system, 0.0)
        runs_with = sum(r["interventions"] > 0 for r in rows)
        lines.append(
            f"| {system} | {n} | {passed} ({100 * passed / n:.0f}%) | {100 * low:.0f}-{100 * high:.0f}% | "
            f"{sum(r['verdict'] == 'SEVERE' for r in rows)} | {sum(r['false_claim'] for r in rows)} | "
            f"{sum(r['run_status'] == 'failed' for r in rows)} | {statistics.median(times):.0f} | {percentile(times, 0.9):.0f} | "
            f"{usd:.2f} | {usd / n:.3f} | {usd / passed if passed else float('nan'):.3f} | "
            f"{sum(r['interventions'] for r in rows)} ({runs_with}) |")
    print("\n".join(lines))
    print("\nBy category (completed / tasks):")
    for system in systems:
        cells = []
        for category in ("implement", "fix"):
            rows = [r for r in by_system[system] if r["category"] == category]
            cells.append(f"{category} {sum(r['verdict'] == 'PASS' for r in rows)}/{len(rows)}")
        for difficulty in (1, 2, 3):
            rows = [r for r in by_system[system] if r["difficulty"] == difficulty]
            cells.append(f"d{difficulty} {sum(r['verdict'] == 'PASS' for r in rows)}/{len(rows)}")
        print(f"  {system:16} " + " | ".join(cells))
    print("\nPaired by task (only-A-passes / only-B-passes, exact McNemar p):")
    for i, a in enumerate(systems):
        for b in systems[i + 1:]:
            ra = {r["task_id"]: r["verdict"] == "PASS" for r in by_system[a]}
            rb = {r["task_id"]: r["verdict"] == "PASS" for r in by_system[b]}
            common = ra.keys() & rb.keys()
            only_a = sum(ra[t] and not rb[t] for t in common)
            only_b = sum(rb[t] and not ra[t] for t in common)
            print(f"  {a:16} vs {b:16} n={len(common)} {only_a:2}/{only_b:2} p={exact_mcnemar(only_a, only_b):.3f}")
    print("\nWhy runs did not complete:")
    for system in systems:
        reasons = failure_reasons(args.run_id, system, by_system[system])
        if reasons:
            print(f"  {system}:")
            for reason, count in reasons.most_common():
                print(f"    {count:2} x {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
