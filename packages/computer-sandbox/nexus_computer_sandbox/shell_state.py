"""Trusted shell-state serialization, without sourcing agent-writable shell scripts."""
from __future__ import annotations

import json
import os
import shlex
from pathlib import Path

# This helper runs with Python's isolated mode in the computer, after the command's shell exits.
CAPTURE = '''import json,os,sys
from pathlib import Path
path=Path(sys.argv[1]); root=Path(sys.argv[2]).resolve(); cwd=Path.cwd().resolve()
if cwd.is_relative_to(root):
    env={k:v for k,v in os.environ.items() if k not in {"_","SHLVL","PWD","OLDPWD"} and len(k)<256 and len(v)<16384}
    encoded=json.dumps({"cwd":str(cwd),"env":env})
    if len(encoded)<65536:
        temporary=path.with_suffix(".tmp"); temporary.write_text(encoded); os.replace(temporary,path)
'''


def read_shell_state(path: Path, root: str, defaults: dict[str, str]) -> tuple[str, dict[str, str]]:
    try:
        if path.stat().st_size > 65536 or path.is_symlink():
            raise ValueError("Shell state is invalid")
        data = json.loads(path.read_text())
    except FileNotFoundError:
        return root, defaults
    cwd = data.get("cwd", root)
    env = data.get("env", {})
    if not isinstance(cwd, str) or (not Path(cwd).is_absolute() or ".." in Path(cwd).parts or not Path(cwd).is_relative_to(Path(root))) or not isinstance(env, dict) or any(not isinstance(key, str) or not isinstance(value, str) or "\x00" in key + value or "=" in key for key, value in env.items()):
        raise ValueError("Shell state escapes the computer or contains invalid environment entries")
    return cwd, {**defaults, **env, "OTEL_SDK_DISABLED": "true", "CREWAI_DISABLE_TELEMETRY": "true", "NEXT_TELEMETRY_DISABLED": "1"}


def command_script(command: str, python: str, capture: str, state: str, workspace: str, pid: str) -> str:
    capture_command = " ".join(shlex.quote(part) for part in (python, "-I", capture, state, workspace))
    return f'printf \'%s\' "$$" > {shlex.quote(pid)}\ntrap {shlex.quote(capture_command)} EXIT\n{command}\n'
