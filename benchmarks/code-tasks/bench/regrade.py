"""Re-grade every stored workspace of a run with the current hidden tests (used after fixing a task).

python -m bench.regrade --run-id full1 [--task ID ...]
Rewrites the matching records in place; prints every verdict that changed.
"""

from __future__ import annotations

import argparse
import json

from .grade import grade
from .run import RESULTS
from .task import load_tasks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--task", nargs="*")
    args = parser.parse_args()
    tasks = {t.id: t for t in load_tasks(set(args.task) if args.task else None)}
    path = RESULTS / args.run_id / "records.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    for row in rows:
        task = tasks.get(row["task_id"])
        workspace = RESULTS / args.run_id / row["system"] / f"{row['task_id']}.a{row['attempt']}" / "workspace"
        if task is None or row["verdict"] in {"INFRA", "TIMEOUT"} or not workspace.exists():
            continue
        result = grade(task, workspace)
        verdict = "SEVERE" if row["severe_reasons"] and result.verdict in {"PASS", "FAIL"} else result.verdict
        if verdict != row["verdict"]:
            print(f"{row['system']:12} {row['task_id']:34} {row['verdict']} -> {verdict}")
            row["verdict"], row["hidden_passed"], row["hidden_failed"] = verdict, result.passed, result.failed
            row["false_claim"] = row["claimed_done"] and verdict in {"FAIL", "SEVERE"}
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
