
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

## Bộ đo: kiểm tra đầu vào trước khi kết luận về năng lực
- Lỗi: bốn tác vụ nhiều file cho NexusAgent 0/4 qua ba lượt đo. Nguyên nhân là adapter chỉ gửi file ở thư mục gốc và backend cấm đường dẫn, nên agent nhận sandbox thiếu package; "completed" nhưng số test đạt y hệt starter.
- Quy tắc: khi một run báo hoàn thành mà workspace không đổi (số test đạt bằng starter), coi là lỗi bộ đo hoặc đầu vào trước, không phải lỗi agent. Kiểm tra mỗi hệ thống nhận đúng cùng đầu vào.
- Test ẩn phải suy ra được từ đề. Nếu một cách đọc hợp lệ của đề làm rớt test, sửa test, ghi lại, và chấm lại tất cả hệ thống theo cùng một test.

## Bộ đo: không sửa mã trong lúc đang đo
- Lỗi: đang chạy A/B (18 run) thì mình thêm một trường vào schema. Mã được bind-mount vào container, nên API (đã nạp bản mới) và worker (bản cũ) lệch nhau; 16/18 run chết sau 5 giây với `extra_forbidden`, số liệu A/B vô giá trị.
- Quy tắc: trước khi bắt đầu một phép đo, chốt mã và dựng lại stack; trong lúc đo chỉ viết mã ở nơi không được mount hoặc chờ đo xong. Khi trung vị thời gian của một nhóm run chỉ vài giây, đọc lỗi từ log worker trước khi diễn giải kết quả.


## Compare against a control from the same day when the model is the noisy part
A drop (mdlite 8/10 to 3/10) after a change is not caused by the change until a control run with the OLD setting, same day, same model, shows otherwise. Here the Docker control gave 3/10 too: the earlier 8/10 was another day. Before looking for a bug in the new code, run the control.

## A blocking test must check WHY it failed
`assert exit_code != 0` passes when the sandbox profile itself is broken (a bad regex made every command fail, so every "blocked" test passed for the wrong reason). Assert the kernel's refusal text, and run a positive case in the same environment first.

## A temp folder inside the working directory makes copy-the-workspace tools recurse
The Docker provider hid this with a separate /tmp tmpfs. Anything that replaces a container's separate temp space on the host needs the scratch directory OUTSIDE the directory that is copied, exported or listed.

## Packaging a multi-process app (Phase 36)
- Identify a process you started by pid AND start time, never by command line: Next.js renames its process (`next-server`), so a command-line check silently skipped it and it held the port after a crash. Test crash recovery by killing the parent with SIGKILL, not only by quitting.
- After killing stale processes, wait for their sockets to close before checking ports; the check raced the kernel.
- A quit that arrives while services are still starting must stop the start, otherwise processes spawned afterwards are orphans. Test "quit during first start".
- Do not count readiness from a port that an orphan may still be serving: compare the pid of the listener with the one before.
- When a test loop mixes `&&` and `||`, `A && B || break` breaks when A is false; write the wait condition as a function and test it once by hand.
- A one-off slow batch (280 s against 35 s) right after configuring a provider was not reproduced in 12 later runs; record it as unexplained instead of calling it noise or a regression.


## "Runs on any machine" is a property you test, not assume (Phase 37)
- Never state what a base image contains from memory; read its Dockerfile. I said the sandbox image had Node; it has no Node and no git. A wrong parity claim sends the packaging work in the wrong direction.
- pip picks wheels by the BUILDER's OS version: building on macOS 27 produced a bundle that needed macOS 15 without saying so. Pin the target OS in one declared place (installer's minimum version), make the build answer as that OS, and have an audit compare the highest version actually needed against the claim.
- Console scripts written by pip carry the builder's absolute interpreter path. Rewrite them to find the interpreter next to the script, and prove it by running from a copy in a folder whose name has a space.
- Test the package with a stripped PATH (system folders + bundled folders). A tool that works only because Homebrew is on PATH is not packaged.
- A transient provider test failure (ERROR with 0 models) right after startup passed on retry; retry once before debugging, but record it.
- A non-Python task through the Python-oriented verifier (needs >= 3 self-written Python tests) never reaches "verified" and the coder/reviewer loop runs until the wall-clock limit. Prove a bundled tool by reading what the agent produced in its computer directory, not by waiting for the run to finish.
- macOS has no `timeout` command and BSD `sed -i` needs an empty suffix argument (`sed -i ''`).
