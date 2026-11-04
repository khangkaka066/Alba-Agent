
## Benchmark harness (Phase 28)
- A tool that "fails" in under a minute with zero tokens is a harness bug until proven otherwise. Read the transcript/error of every
  surprising record before believing the verdict; do this on the pilot, before the full run.
- Never write an adapter against an API from memory: print one real response first (NexusAgent artifacts use `filename`, not `name`;
  `auto_run=false` does not persist the workflow, so it must be created with POST, not PUT).
- Anything that can only be our own mistake (HTTP 400/401/403/404/405) is `INFRA`, retried and excluded, never a FAIL for the tool.
- Run every tool with an empty HOME: dsh loaded the operator's personal skills from ~/.agents, which would have skewed the result.
- Measure cost from the provider's account counter over a whole system run; the counter is too coarse for single tiny calls.
- Do not wipe a dev database to make a stack start: run a separate compose project (`-p nexus-bench`) with fresh volumes.

## A silent `except ... continue` around an export hides lost work (Phase 29)
- Pattern: an export loop swallowed `FileNotFoundError`, so after a lifecycle change the run still reported "completed" with no deliverables.
- Rule: when a component reports an artifact exists, failing to read it must fail the run loudly. Treat "completed with nothing delivered" as a bug, and rerun the benchmark after any change to container or run lifecycle.

## Chấm điểm: lỗi của bộ chấm không được tính là lỗi của agent
- Lỗi: `bench/grade.py` ghi `FAIL 0/0` khi Docker nghẽn và test ẩn không chạy; một lời giải đúng (impl-021) bị tính là rớt và là "tuyên bố sai".
- Quy tắc: trước khi phân tích vì sao một tác vụ rớt, chạy lại test ẩn trên workspace đã lưu. Verdict mà không có dòng "Ran N tests" là `INFRA`, không phải `FAIL`.
