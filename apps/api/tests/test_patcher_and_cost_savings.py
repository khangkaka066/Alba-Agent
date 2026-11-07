"""Tests for diff/patch editing, log compaction, and cost-reduction capabilities.

Covers:
- Patch block parsing (line-by-line FSM)
- Exact, normalised, and whitespace-tolerant matching
- CRLF preservation in library AND on disk via compiled sandbox script
- Dotfile path cleaning (.gitignore must survive)
- Path traversal rejection (..) and absolute path rejection (/etc/hosts, /tmp/...)
- False-positive patch detection (marker strings in code)
- ``=======`` inside file content (ambiguity)
- compact_log hard ceiling (<= max_chars, <= 16KB) and O(N) deduplication on 100,000-line logs
- Real NexusGenSandboxRunner execution tests:
  * Scenario S10: attempt 1 SyntaxError still stages initial source files on attempt 2
  * Scenario S11: attempt 1 PatchError still stages initial source files on attempt 2
  * Scenario S3: cumulative patches survive across real attempts (test-only re-stage)
  * Scenario S4: SEARCH on patched content works across real attempts
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from autogen_core import FunctionCall
from autogen_core.models import CreateResult, ModelInfo, RequestUsage
from autogen_ext.models.replay import ReplayChatCompletionClient

from callbacks.event_bus import RuntimeEventEmitter
from nexus_computer_sandbox import SandboxExecution
from nexus_core_schema.models import NexusGenSandboxNodeSpec
from nexusgen_bridge.patcher import (
    PatchBlock,
    _clean_path,
    apply_patch_block,
    compile_patch_script,
    is_patch_text,
    parse_patch_blocks,
)
from nexusgen_bridge.sandbox_team import (
    _TEST_NAME_RE,
    NexusGenSandboxRunner,
    compact_log,
    extract_failure_summary,
)


# ---------------------------------------------------------------------------
# Test Helpers for Real NexusGenSandboxRunner Execution
# ---------------------------------------------------------------------------

class DummyRedis:
    """Mock Redis client for event emitter in unit tests."""

    async def publish(self, *args: Any, **kwargs: Any) -> int:
        return 0


class LocalTestSupervisor:
    """Lightweight test supervisor running python scripts in a local temp directory without Docker."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.calls: list[dict[str, Any]] = []

    async def run_python(
        self,
        tenant_id: UUID,
        workspace_id: UUID,
        run_id: UUID,
        source: str,
        verification_command: str,
        attempt: int,
        timeout_seconds: int,
        output_sink: Any = None,
        input_files: dict[str, bytes] | None = None,
        script_label: str = "run",
    ) -> SandboxExecution:
        staged_names = set(input_files.keys()) if input_files else set()
        self.calls.append({
            "attempt": attempt,
            "staged_files": staged_names,
        })
        if input_files:
            for name, data in input_files.items():
                target = self.root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)

        script_path = self.root / f"{script_label}_attempt_{attempt}.py"
        script_path.write_text(source, encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(self.root),
            capture_output=True,
            text=True,
        )
        artifacts = tuple(p.name for p in self.root.iterdir() if p.is_file())
        return SandboxExecution(
            stdout=proc.stdout,
            stderr=proc.stderr,
            exit_code=proc.returncode,
            artifacts=artifacts,
            elapsed_seconds=0.01,
        )


# ---------------------------------------------------------------------------
# is_patch_text
# ---------------------------------------------------------------------------

class TestIsPatchText:
    def test_detects_valid_block(self) -> None:
        patch = (
            "<<<<<<< SEARCH: test.py\n"
            "def old():\n"
            "    pass\n"
            "=======\n"
            "def new():\n"
            "    return 42\n"
            ">>>>>>> REPLACE\n"
        )
        assert is_patch_text(patch) is True

    def test_rejects_plain_code(self) -> None:
        assert is_patch_text("print('hello world')") is False

    def test_rejects_partial_markers(self) -> None:
        assert is_patch_text("<<<<<<< SEARCH\nfoo") is False

    def test_false_positive_marker_strings_in_docstring(self) -> None:
        """Code that *mentions* the three marker strings must NOT be detected."""
        code = (
            "# This module explains the patch format:\n"
            '# Use <<<<<<< SEARCH to start, ======= as separator, >>>>>>> REPLACE to close.\n'
            "def explain():\n"
            '    return "<<<<<<< SEARCH ... ======= ... >>>>>>> REPLACE"\n'
        )
        assert is_patch_text(code) is False


# ---------------------------------------------------------------------------
# _clean_path
# ---------------------------------------------------------------------------

class TestCleanPath:
    def test_strips_git_diff_prefix(self) -> None:
        assert _clean_path("a/src/main.py") == "src/main.py"
        assert _clean_path("b/src/main.py") == "src/main.py"

    def test_strips_dot_slash_prefix(self) -> None:
        assert _clean_path("./module.py") == "module.py"

    def test_preserves_dotfiles(self) -> None:
        """Bug #2: lstrip('./') ate leading dots; .gitignore → gitignore."""
        assert _clean_path(".gitignore") == ".gitignore"
        assert _clean_path(".github/ci.yml") == ".github/ci.yml"
        assert _clean_path("./.gitignore") == ".gitignore"
        assert _clean_path(".env") == ".env"

    def test_rejects_path_traversal(self) -> None:
        """Bug #4: sub/../../escape.py must be rejected."""
        with pytest.raises(ValueError, match="Path traversal"):
            _clean_path("sub/../../escape.py")
        with pytest.raises(ValueError, match="Path traversal"):
            _clean_path("../secret.py")

    def test_rejects_absolute_paths(self) -> None:
        """Issue #3: absolute paths like /etc/hosts or /tmp/... must be rejected."""
        with pytest.raises(ValueError, match="Absolute paths"):
            _clean_path("/etc/hosts")
        with pytest.raises(ValueError, match="Absolute paths"):
            _clean_path("/tmp/money.py")
        with pytest.raises(ValueError, match="Absolute paths"):
            _clean_path("//var/log")

    def test_rejects_backslashes(self) -> None:
        with pytest.raises(ValueError, match="Backslashes"):
            _clean_path("sub\\file.py")

    def test_rejects_empty_path(self) -> None:
        with pytest.raises(ValueError, match="cannot be empty"):
            _clean_path("   ")

    def test_strips_quotes_and_backticks(self) -> None:
        assert _clean_path("`main.py`") == "main.py"
        assert _clean_path("'main.py'") == "main.py"
        assert _clean_path('"main.py"') == "main.py"


# ---------------------------------------------------------------------------
# parse_patch_blocks
# ---------------------------------------------------------------------------

class TestParsePatchBlocks:
    def test_single_and_multi_file(self) -> None:
        text = (
            "Here is the fix:\n"
            "<<<<<<< SEARCH: math_utils.py\n"
            "def add(a, b):\n"
            "    return a - b\n"
            "=======\n"
            "def add(a, b):\n"
            "    return a + b\n"
            ">>>>>>> REPLACE\n"
            "\n"
            "And for the other file:\n"
            "FILE: test_math.py\n"
            "<<<<<<< SEARCH\n"
            "assert add(1, 2) == -1\n"
            "=======\n"
            "assert add(1, 2) == 3\n"
            ">>>>>>> REPLACE\n"
        )
        blocks = parse_patch_blocks(text)
        assert len(blocks) == 2
        assert blocks[0].filepath == "math_utils.py"
        assert "return a - b" in blocks[0].search
        assert "return a + b" in blocks[0].replace
        assert blocks[1].filepath == "test_math.py"
        assert "-1" in blocks[1].search
        assert "3" in blocks[1].replace

    def test_missing_filepath_raises(self) -> None:
        text = (
            "<<<<<<< SEARCH\n"
            "def foo():\n"
            "    pass\n"
            "=======\n"
            "def foo():\n"
            "    return 1\n"
            ">>>>>>> REPLACE\n"
        )
        with pytest.raises(ValueError, match="missing a target filepath"):
            parse_patch_blocks(text)

    def test_content_with_separator_in_body(self) -> None:
        """Bug #7: a line consisting of ``=======`` inside file content."""
        text = (
            "<<<<<<< SEARCH: conflict.py\n"
            "line_one\n"
            "=======\n"
            "line_one_fixed\n"
            ">>>>>>> REPLACE\n"
        )
        blocks = parse_patch_blocks(text)
        assert len(blocks) == 1
        assert blocks[0].search == "line_one\n"
        assert blocks[0].replace == "line_one_fixed\n"

    def test_dotfile_filepath_preserved(self) -> None:
        """Bug #2 regression: .gitignore must not become gitignore."""
        text = (
            "<<<<<<< SEARCH: .gitignore\n"
            "*.pyc\n"
            "=======\n"
            "*.pyc\n"
            "__pycache__/\n"
            ">>>>>>> REPLACE\n"
        )
        blocks = parse_patch_blocks(text)
        assert blocks[0].filepath == ".gitignore"

    def test_path_traversal_rejected(self) -> None:
        text = (
            "<<<<<<< SEARCH: sub/../../escape.py\n"
            "x = 1\n"
            "=======\n"
            "x = 2\n"
            ">>>>>>> REPLACE\n"
        )
        with pytest.raises(ValueError, match="Path traversal"):
            parse_patch_blocks(text)

    def test_absolute_path_rejected(self) -> None:
        text = (
            "<<<<<<< SEARCH: /etc/shadow\n"
            "root:*\n"
            "=======\n"
            "root:hacked\n"
            ">>>>>>> REPLACE\n"
        )
        with pytest.raises(ValueError, match="Absolute paths"):
            parse_patch_blocks(text)


# ---------------------------------------------------------------------------
# apply_patch_block
# ---------------------------------------------------------------------------

class TestApplyPatchBlock:
    def test_exact_match(self) -> None:
        original = "def round_cents(x):\n    return int(x * 100)\n"
        patch = PatchBlock(
            filepath="money.py",
            search="    return int(x * 100)\n",
            replace="    return int(round(x * 100))\n",
        )
        patched = apply_patch_block(original, patch)
        assert patched == "def round_cents(x):\n    return int(round(x * 100))\n"

    def test_whitespace_tolerance(self) -> None:
        original = "def calc():   \n    a = 1   \n    return a\n"
        patch = PatchBlock(
            filepath="calc.py",
            search="def calc():\n    a = 1\n",
            replace="def calc():\n    a = 2\n",
        )
        patched = apply_patch_block(original, patch)
        assert "a = 2" in patched
        assert "return a" in patched

    def test_ambiguous_raises(self) -> None:
        original = "item = 1\nitem = 1\n"
        patch = PatchBlock(filepath="test.py", search="item = 1\n", replace="item = 2\n")
        with pytest.raises(ValueError, match="found 2 times"):
            apply_patch_block(original, patch)

    def test_not_found_raises(self) -> None:
        original = "def foo(): return 1\n"
        patch = PatchBlock(filepath="test.py", search="def bar(): return 2\n", replace="def bar(): return 3\n")
        with pytest.raises(ValueError, match="SEARCH block not found"):
            apply_patch_block(original, patch)

    def test_crlf_preservation_in_library(self) -> None:
        """Bug #6: patching a CRLF file must keep CRLF endings."""
        original = "line_one\r\nline_two\r\nline_three\r\n"
        patch = PatchBlock(
            filepath="dos.txt",
            search="line_two\n",
            replace="LINE_TWO_FIXED\n",
        )
        result = apply_patch_block(original, patch)
        assert "LINE_TWO_FIXED" in result
        assert "\r\n" in result
        assert result.count("\n") == result.count("\r\n")

    def test_empty_search_creates_new_file(self) -> None:
        result = apply_patch_block("", PatchBlock(filepath="new.py", search="", replace="x = 1\n"))
        assert result == "x = 1\n"


# ---------------------------------------------------------------------------
# compile_patch_script (actual sandbox script execution on disk)
# ---------------------------------------------------------------------------

class TestCompilePatchScript:
    def test_execution(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            file1 = root / "module_a.py"
            file1.write_text("x = 10\n", encoding="utf-8")

            file2 = root / "sub" / "module_b.py"
            file2.parent.mkdir(parents=True)
            file2.write_text("y = 20\n", encoding="utf-8")

            patches = [
                PatchBlock("module_a.py", "x = 10\n", "x = 15\n"),
                PatchBlock("sub/module_b.py", "y = 20\n", "y = 25\n"),
            ]
            script_content = compile_patch_script(patches)
            script_file = root / "attempt_patch.py"
            script_file.write_text(script_content, encoding="utf-8")

            proc = subprocess.run(
                [sys.executable, str(script_file)], cwd=str(root), capture_output=True, text=True,
            )
            assert proc.returncode == 0
            assert "Successfully applied patches" in proc.stdout
            assert file1.read_text(encoding="utf-8") == "x = 15\n"
            assert file2.read_text(encoding="utf-8") == "y = 25\n"

    def test_crlf_preservation_on_disk_via_script(self) -> None:
        """Issue #4: compiled script running in sandbox must preserve CRLF on disk bytes."""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            target = root / "windows_file.py"
            target.write_bytes(b"def greet():\r\n    return 'hello'\r\n")

            patches = [
                PatchBlock("windows_file.py", "    return 'hello'\n", "    return 'hi'\n"),
            ]
            script_content = compile_patch_script(patches)
            script_file = root / "patch_crlf.py"
            script_file.write_text(script_content, encoding="utf-8")

            proc = subprocess.run(
                [sys.executable, str(script_file)], cwd=str(root), capture_output=True, text=True,
            )
            assert proc.returncode == 0
            raw_bytes = target.read_bytes()
            assert b"\r\n" in raw_bytes
            assert b"return 'hi'\r\n" in raw_bytes
            assert raw_bytes.count(b"\n") == raw_bytes.count(b"\r\n")


# ---------------------------------------------------------------------------
# compact_log
# ---------------------------------------------------------------------------

class TestCompactLog:
    def test_short_log_unchanged(self) -> None:
        short_log = "Ran 5 tests in 0.01s\nOK\n"
        assert compact_log(short_log) == short_log.strip()

    def test_large_log_truncated(self) -> None:
        long_log = "START\n" + ("line output\n" * 500) + "Traceback (most recent call last):\nAssertionError: 42 != 43\nFAILED"
        compacted = compact_log(long_log, max_chars=1500)
        assert len(compacted) <= 1500
        assert "truncated" in compacted

    def test_preserves_all_14_failures(self) -> None:
        """Bug #3 regression: 14 FAIL lines must all survive compaction."""
        failures = [f"FAIL: test_case_{i} (module.TestSuite)" for i in range(14)]
        body_lines = ["ok line"] * 300
        for i, f in enumerate(failures):
            body_lines.insert(i * 20, f)
        full_log = "\n".join(body_lines)
        compacted = compact_log(full_log, max_chars=2500)
        for f in failures:
            assert f in compacted, f"Missing failure line: {f}"

    def test_preserves_assertion_errors(self) -> None:
        lines = ["pass"] * 400
        lines[50] = "AssertionError: expected 1 got 2"
        lines[250] = "AssertionError: list index mismatch"
        full_log = "\n".join(lines)
        compacted = compact_log(full_log, max_chars=1200)
        assert "expected 1 got 2" in compacted
        assert "list index mismatch" in compacted

    def test_hard_ceiling_and_fast_dedupe_on_massive_log(self) -> None:
        """Issue #2: 100,000 failure lines (1.79 MB) must not explode token cost.

        Must finish in < 0.5s (O(N) dedupe), never exceed max_chars (2500) or
        the 16 KB hard ceiling, and summarize the overflow cleanly.
        """
        lines = [f"FAILED test_case_{i}" for i in range(100_000)]
        massive_log = "\n".join(lines)
        assert len(massive_log) > 1_500_000

        t0 = time.monotonic()
        compacted = compact_log(massive_log, max_chars=2500)
        elapsed = time.monotonic() - t0

        assert elapsed < 1.0, f"Dedupe took too long: {elapsed:.2f}s (should be O(N))"
        assert len(compacted) <= 2500, f"Compacted log exceeded max_chars: {len(compacted)}"
        assert "unique failure line(s)" in compacted
        assert "[... " in compacted

    def test_hard_ceiling_caps_at_16kb_even_with_large_param(self) -> None:
        lines = [f"FAIL: test_{i}" for i in range(50_000)]
        massive_log = "\n".join(lines)
        compacted = compact_log(massive_log, max_chars=100_000)
        assert len(compacted) <= 16_384


# ---------------------------------------------------------------------------
# extract_failure_summary
# ---------------------------------------------------------------------------

class TestExtractFailureSummary:
    def test_extracts_assertion(self) -> None:
        summary = extract_failure_summary("", "Traceback...\nAssertionError: expected True but got False\n")
        assert "AssertionError: expected True but got False" in summary


# ---------------------------------------------------------------------------
# REAL NexusGenSandboxRunner Execution Tests (S10, S11, S3, S4)
# ---------------------------------------------------------------------------

class TestRealNexusGenSandboxRunnerExecution:
    """End-to-end integration tests running real NexusGenSandboxRunner with scripted models."""

    @pytest.mark.anyio
    async def test_real_runner_s10_syntax_error_then_valid_patch(self) -> None:
        """Scenario S10: Attempt 1 has SyntaxError (never reaches supervisor).

        Attempt 2 is a valid patch on money.py.
        Verifies:
        1. execute_python does not raise UnboundLocalError on initial_files_staged.
        2. Supervisor was NOT called on attempt 1.
        3. Supervisor received full input_files (including money.py) on attempt 2.
        4. money.py is successfully patched on disk.
        """
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            sup = LocalTestSupervisor(root)
            model_info = ModelInfo(
                vision=False, function_calling=True, json_output=False, family="test", structured_output=False
            )

            patch = (
                "<<<<<<< SEARCH: money.py\n"
                "    return 0\n"
                "=======\n"
                "    return 42\n"
                ">>>>>>> REPLACE\n"
            )

            coder_turns = [
                # Attempt 1: SyntaxError
                CreateResult(
                    finish_reason="function_calls",
                    content=[FunctionCall(id="c1", name="execute_python", arguments=json.dumps({"code": "def broken_syntax("}))],
                    usage=RequestUsage(prompt_tokens=1, completion_tokens=1), cached=False,
                ),
                # Attempt 2: Valid patch
                CreateResult(
                    finish_reason="function_calls",
                    content=[FunctionCall(id="c2", name="execute_python", arguments=json.dumps({"code": patch}))],
                    usage=RequestUsage(prompt_tokens=1, completion_tokens=1), cached=False,
                ),
            ]
            reviewer_turns = [
                CreateResult(finish_reason="stop", content="Fix syntax", usage=RequestUsage(prompt_tokens=1, completion_tokens=1), cached=False),
                CreateResult(finish_reason="stop", content="APPROVED", usage=RequestUsage(prompt_tokens=1, completion_tokens=1), cached=False),
            ]

            def client_factory(model_name: str) -> Any:
                if "coder" in model_name:
                    return ReplayChatCompletionClient(coder_turns, model_info=model_info)
                return ReplayChatCompletionClient(reviewer_turns, model_info=model_info)

            runner = NexusGenSandboxRunner(cast(Any, sup), client_factory)
            spec = NexusGenSandboxNodeSpec(
                id="s10_node", label="S10 Test", coder_model="coder", reviewer_model="reviewer",
                verification_command="python -c \"import money; assert money.calc() == 42\"",
                max_rounds=3, timeout_seconds=5,
            )
            emitter = RuntimeEventEmitter(DummyRedis(), uuid4(), uuid4(), uuid4())  # type: ignore[arg-type]

            input_files = {
                "money.py": b"def calc():\n    return 0\n",
                "test_money.py": b"import money\nassert money.calc() == 42\n",
            }
            res = await runner.run("Fix money.py", spec, emitter, input_files=input_files)

            # Verification of supervisor call behavior
            coder_supervisor_calls = [c for c in sup.calls if c["attempt"] <= 10]
            assert len(coder_supervisor_calls) == 1, "Attempt 1 had SyntaxError so supervisor must only be called on attempt 2"
            assert coder_supervisor_calls[0]["attempt"] == 2
            assert "money.py" in coder_supervisor_calls[0]["staged_files"]
            assert (root / "money.py").read_text(encoding="utf-8") == "def calc():\n    return 42\n"

    @pytest.mark.anyio
    async def test_real_runner_s11_patch_error_then_valid_patch(self) -> None:
        """Scenario S11: Attempt 1 is rejected at patch parse time (no filepath).

        Attempt 2 is a valid patch.
        Verifies:
        1. Supervisor was NOT called on attempt 1.
        2. Supervisor received full input_files on attempt 2.
        3. money.py is successfully patched.
        """
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            sup = LocalTestSupervisor(root)
            model_info = ModelInfo(
                vision=False, function_calling=True, json_output=False, family="test", structured_output=False
            )

            malformed_patch = "<<<<<<< SEARCH\nfoo\n=======\nbar\n>>>>>>> REPLACE\n"
            valid_patch = (
                "<<<<<<< SEARCH: money.py\n"
                "    return 0\n"
                "=======\n"
                "    return 100\n"
                ">>>>>>> REPLACE\n"
            )

            coder_turns = [
                CreateResult(
                    finish_reason="function_calls",
                    content=[FunctionCall(id="c1", name="execute_python", arguments=json.dumps({"code": malformed_patch}))],
                    usage=RequestUsage(prompt_tokens=1, completion_tokens=1), cached=False,
                ),
                CreateResult(
                    finish_reason="function_calls",
                    content=[FunctionCall(id="c2", name="execute_python", arguments=json.dumps({"code": valid_patch}))],
                    usage=RequestUsage(prompt_tokens=1, completion_tokens=1), cached=False,
                ),
            ]
            reviewer_turns = [
                CreateResult(finish_reason="stop", content="Specify filepath", usage=RequestUsage(prompt_tokens=1, completion_tokens=1), cached=False),
                CreateResult(finish_reason="stop", content="APPROVED", usage=RequestUsage(prompt_tokens=1, completion_tokens=1), cached=False),
            ]

            def client_factory(model_name: str) -> Any:
                if "coder" in model_name:
                    return ReplayChatCompletionClient(coder_turns, model_info=model_info)
                return ReplayChatCompletionClient(reviewer_turns, model_info=model_info)

            runner = NexusGenSandboxRunner(cast(Any, sup), client_factory)
            spec = NexusGenSandboxNodeSpec(
                id="s11_node", label="S11 Test", coder_model="coder", reviewer_model="reviewer",
                verification_command="python -c \"import money; assert money.calc() == 100\"",
                max_rounds=3, timeout_seconds=5,
            )
            emitter = RuntimeEventEmitter(DummyRedis(), uuid4(), uuid4(), uuid4())  # type: ignore[arg-type]

            input_files = {
                "money.py": b"def calc():\n    return 0\n",
                "test_money.py": b"import money\nassert money.calc() == 100\n",
            }
            res = await runner.run("Fix money.py", spec, emitter, input_files=input_files)

            coder_supervisor_calls = [c for c in sup.calls if c["attempt"] <= 10]
            assert len(coder_supervisor_calls) == 1
            assert coder_supervisor_calls[0]["attempt"] == 2
            assert "money.py" in coder_supervisor_calls[0]["staged_files"]
            assert (root / "money.py").read_text(encoding="utf-8") == "def calc():\n    return 100\n"

    @pytest.mark.anyio
    async def test_real_runner_s3_cumulative_patches_across_two_attempts(self) -> None:
        """Scenario S3: Two sequential patches in two attempts fixing bugs A and B.

        Attempt 1 patches bug A -> supervisor runs with full input_files.
        Attempt 2 patches bug B -> supervisor runs with ONLY protected tests (test_app.py).
        Verifies:
        1. app.py is NOT re-staged on attempt 2.
        2. Fix A from attempt 1 survives.
        3. Fix B from attempt 2 applies on top of Fix A.
        """
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            sup = LocalTestSupervisor(root)
            model_info = ModelInfo(
                vision=False, function_calling=True, json_output=False, family="test", structured_output=False
            )

            patch_a = (
                "<<<<<<< SEARCH: app.py\n"
                "def func_a(): return 0\n"
                "=======\n"
                "def func_a(): return 1\n"
                ">>>>>>> REPLACE\n"
            )
            patch_b = (
                "<<<<<<< SEARCH: app.py\n"
                "def func_b(): return 0\n"
                "=======\n"
                "def func_b(): return 2\n"
                ">>>>>>> REPLACE\n"
            )

            coder_turns = [
                CreateResult(
                    finish_reason="function_calls",
                    content=[FunctionCall(id="c1", name="execute_python", arguments=json.dumps({"code": patch_a}))],
                    usage=RequestUsage(prompt_tokens=1, completion_tokens=1), cached=False,
                ),
                CreateResult(
                    finish_reason="function_calls",
                    content=[FunctionCall(id="c2", name="execute_python", arguments=json.dumps({"code": patch_b}))],
                    usage=RequestUsage(prompt_tokens=1, completion_tokens=1), cached=False,
                ),
            ]
            reviewer_turns = [
                CreateResult(finish_reason="stop", content="Now fix func_b", usage=RequestUsage(prompt_tokens=1, completion_tokens=1), cached=False),
                CreateResult(finish_reason="stop", content="APPROVED", usage=RequestUsage(prompt_tokens=1, completion_tokens=1), cached=False),
            ]

            def client_factory(model_name: str) -> Any:
                if "coder" in model_name:
                    return ReplayChatCompletionClient(coder_turns, model_info=model_info)
                return ReplayChatCompletionClient(reviewer_turns, model_info=model_info)

            runner = NexusGenSandboxRunner(cast(Any, sup), client_factory)
            spec = NexusGenSandboxNodeSpec(
                id="s3_node", label="S3 Test", coder_model="coder", reviewer_model="reviewer",
                verification_command="python -c \"import app; assert app.func_a() == 1 and app.func_b() == 2\"",
                max_rounds=3, timeout_seconds=5,
            )
            emitter = RuntimeEventEmitter(DummyRedis(), uuid4(), uuid4(), uuid4())  # type: ignore[arg-type]

            input_files = {
                "app.py": b"def func_a(): return 0\ndef func_b(): return 0\n",
                "test_app.py": b"import app\nassert app.func_a() == 1\nassert app.func_b() == 2\n",
            }
            res = await runner.run("Fix app.py", spec, emitter, input_files=input_files)

            coder_calls = [c for c in sup.calls if c["attempt"] <= 10]
            assert len(coder_calls) == 2
            # Attempt 1: full input files
            assert "app.py" in coder_calls[0]["staged_files"]
            assert "test_app.py" in coder_calls[0]["staged_files"]
            # Attempt 2: ONLY test files re-staged! app.py is NOT in staged_files!
            assert "app.py" not in coder_calls[1]["staged_files"]
            assert "test_app.py" in coder_calls[1]["staged_files"]

            # File on disk must have BOTH fixes!
            final_content = (root / "app.py").read_text(encoding="utf-8")
            assert "def func_a(): return 1" in final_content
            assert "def func_b(): return 2" in final_content
