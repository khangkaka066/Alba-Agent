"""Small, deterministic failure evidence for the next repair turn."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ErrorDigest:
    error_category: str
    root_cause_line: str
    suggested_fix_command: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def digest_error(output: str, exit_code: int) -> ErrorDigest | None:
    if exit_code == 0:
        return None
    lines = [line.strip() for line in output[-32_000:].splitlines() if line.strip()]
    root = next((line for line in reversed(lines) if re.search(r"Error:|Error\b|not found|denied|in use|timed out", line, re.I)), lines[-1] if lines else f"Process exited with code {exit_code}")
    location = next((line for line in reversed(lines) if re.search(r'File ".+", line \d+|[^\s]+:\d+(?::\d+)?', line)), "")
    cause = " · ".join(dict.fromkeys(part for part in (location, root) if part))[:1200]
    missing = re.search(r"No module named ['\"]([A-Za-z0-9_.-]+)['\"]", root)
    if missing:
        package = missing.group(1).split(".")[0]
        return ErrorDigest("MISSING_PYTHON_PACKAGE", cause, f"python -m pip install {package}")
    if exit_code in (124, 137) or re.search(r"timed? out|timeout", root, re.I):
        return ErrorDigest("TIMEOUT", cause, "Inspect the running process; use background=true for a server or watcher.")
    if re.search(r"address already in use|EADDRINUSE", root, re.I):
        return ErrorDigest("PORT_IN_USE", cause, "List sandbox processes, then stop the owner or choose another port.")
    if re.search(r"SyntaxError|IndentationError|unexpected token|syntax error", output, re.I):
        return ErrorDigest("SYNTAX_ERROR", cause, "Use view_file_numbered and surgical_file_edit at the reported location.")
    if re.search(r"PermissionError|Permission denied|Operation not permitted|Blocked by|needs approval", output, re.I):
        return ErrorDigest("PERMISSION_OR_POLICY_BLOCKED", cause, "Request the required approval; keep writes inside the workspace.")
    if re.search(r"FileNotFoundError|No such file or directory|ENOENT", root, re.I):
        return ErrorDigest("FILE_NOT_FOUND", cause, "Inspect the current directory and verify the file path.")
    if re.search(r"command not found|: not found|executable.*not found", root, re.I) or exit_code == 127:
        return ErrorDigest("MISSING_SYSTEM_BINARY", cause, "Inspect the sandbox PATH and install the missing tool through an approved command.")
    return ErrorDigest("COMMAND_FAILED", cause, "Inspect the reported cause and verify the smallest correction.")
