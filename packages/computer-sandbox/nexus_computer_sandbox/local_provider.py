"""Run a computer's commands on the host without Docker, inside a macOS Seatbelt sandbox.

What the sandbox enforces, whatever the command says:
- writes only inside the computer's own directory (and its private temp folder);
- no reads of credential files (``.env``, ``~/.ssh``, cloud and keychain folders) and no reads of other computers' directories;
- no network, unless the person approved a command that needs it, and then only for that one command. Seatbelt cannot filter by
  host: the network is open or closed.

What it does not do: it works on macOS only (``sandbox-exec`` is deprecated by Apple but still shipped), it caps the size of one file but not
memory or process count (macOS enforces neither reliably, unlike the Docker provider), and a command still sees the rest of the host filesystem read-only.
"""

from __future__ import annotations

import asyncio
import os
import resource
import shutil
import signal
import sys
from pathlib import Path
from time import monotonic

from .docker_supervisor import OutputSink, SandboxExecution
from .execution_policy import Decision, ExecutionPolicy, Verdict, approved_commands
from .supervisor import ComputerHandle, DockerSandboxProvider
from .shell_state import CAPTURE, command_script, read_shell_state

SANDBOX_EXEC = "/usr/bin/sandbox-exec"
MAX_FILE_BYTES = 1 << 30  # one file cannot grow past 1 GiB; macOS does not enforce a memory or process-count cap that holds
EXIT_BLOCKED = 126  # the shell's own code for "found but not allowed to run"

# Under the person's home: credentials and history that no agent command needs.
HOME_SECRETS = (
    ".ssh", ".aws", ".gnupg", ".kube", ".docker", ".config/gcloud", ".config/gh", ".azure",
    "Library/Keychains", "Library/Cookies", "Library/Application Support/Google/Chrome",
)
HOME_SECRET_FILES = (".netrc", ".npmrc", ".pypirc", ".zsh_history", ".bash_history", ".git-credentials")


def seatbelt_available() -> bool:
    # A function, not an inline `sys.platform` test: mypy would treat everything after a failed inline test as unreachable on Linux.
    return sys.platform == "darwin" and Path(SANDBOX_EXEC).exists()


def _quoted(path: Path | str) -> str:
    text = str(path)
    if '"' in text or "\\" in text or "\n" in text:
        raise ValueError(f"Path cannot be used in a sandbox profile: {text!r}")
    return f'"{text}"'


def seatbelt_profile(run_directory: Path, scratch_directory: Path, computers_root: Path, home: Path, network: bool) -> str:
    """Seatbelt rules. Every read rule names the same operation, file-read-data: Seatbelt lets a rule for a narrower operation beat an
    earlier broad one, so mixing ``file-read*`` with ``file-read-data`` made an allow silently override a deny. Within one operation, later
    rules win, so each allow that re-opens something comes after the deny it narrows."""
    lines = [
        "(version 1)", "(allow default)",
        "(deny file-write*)",
        '(deny mach-lookup (global-name "com.apple.SecurityServer") (global-name "com.apple.securityd.xpc"))',
        f"(allow file-write* (subpath {_quoted(run_directory)}))",
        '(allow file-write* (literal "/dev/null") (literal "/dev/tty") (literal "/dev/dtracehelper"))',
        # Other computers' contents and listings are off limits, this one's own are not. Only the data is denied, not the metadata: a
        # shell walks the parent directories when it changes directory, and a deny of everything makes `cd` fail.
        f"(deny file-read-data (subpath {_quoted(computers_root)}))",
        f"(allow file-read-data (subpath {_quoted(run_directory)}))",
        # Scratch space (temp files, HOME) lives beside the run directory, never inside it: a tool that copies the working directory into
        # a temp folder would otherwise copy that folder into itself without end.
        f"(allow file-read-data (subpath {_quoted(scratch_directory)}))",
        f"(allow file-write* (subpath {_quoted(scratch_directory)}))",
        r'(deny file-read-data (regex #"/\.env(\.[^/]*)?$"))',
        r'(allow file-read-data (regex #"/\.env\.(example|sample|template)$"))',
    ]
    lines += [f"(deny file-read-data (subpath {_quoted(home / name)}))" for name in HOME_SECRETS]
    lines += [f"(deny file-read-data (literal {_quoted(home / name)}))" for name in HOME_SECRET_FILES]
    if not network:
        lines += ["(deny network*)", '(allow network-bind (local ip "localhost:*"))', '(allow network-inbound (local ip "localhost:*"))']
    return "\n".join(lines) + "\n"


def _limit_file_size() -> None:
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_FILE_BYTES, MAX_FILE_BYTES))


SYSTEM_PATH = ("/usr/bin", "/bin", "/usr/sbin", "/sbin")
TOOLS_PATH_VARIABLE = "NEXUS_SANDBOX_TOOLS_PATH"


def tool_directories_from_environment() -> tuple[Path, ...]:
    """Folders of tools that ship with the app (Node, git, ffmpeg...), set by the app that starts the API. Relative entries are ignored: a
    command's PATH must not depend on where the API happens to be running."""
    entries = (entry for entry in os.environ.get(TOOLS_PATH_VARIABLE, "").split(os.pathsep) if entry)
    return tuple(path for path in map(Path, entries) if path.is_absolute())


def _environment(scratch_directory: Path, interpreter_directory: Path, tool_directories: tuple[Path, ...] = ()) -> dict[str, str]:
    """Only what a command needs. The host environment holds API keys and tokens, so none of it is passed on."""
    scratch_directory.mkdir(parents=True, exist_ok=True)
    return {
        "PATH": os.pathsep.join([str(interpreter_directory), *map(str, tool_directories), *SYSTEM_PATH]),
        "HOME": str(scratch_directory), "TMPDIR": str(scratch_directory),
        "TERM": "dumb", "PAGER": "cat", "GIT_PAGER": "cat", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
    }


class LocalSandboxProvider(DockerSandboxProvider):
    """File handling is shared with the Docker provider (same directory layout, same symlink-safe opens); only execution differs."""

    name = "local"

    def __init__(
        self, host_root: Path, policy: ExecutionPolicy | None = None,
        interpreter: Path | None = None, home: Path | None = None, tools: tuple[Path, ...] | None = None,
    ) -> None:
        if not seatbelt_available():
            raise RuntimeError("The local sandbox needs macOS sandbox-exec; use the docker provider on this machine")
        super().__init__(host_root)
        self._policy = policy or ExecutionPolicy()
        self._interpreter_directory = (interpreter or Path(sys.executable)).resolve().parent
        self._tool_directories = tool_directories_from_environment() if tools is None else tools
        self._home = (home or Path.home()).resolve()

    def _scratch(self, handle: ComputerHandle) -> Path:
        # Under the computers root but outside every run directory, like the Docker provider's /tmp tmpfs.
        return self._root / ".scratch" / str(handle.access.tenant_id) / str(handle.access.workspace_id) / str(handle.id)

    async def create(self, handle: ComputerHandle) -> str:
        self._directory(handle).mkdir(parents=True, exist_ok=True)
        self._scratch(handle).mkdir(parents=True, exist_ok=True)
        return f"local-{handle.id.hex}"

    async def destroy(self, handle: ComputerHandle) -> None:
        if handle.id in self._managers:
            await self._manager(handle).call("dispose")
        shutil.rmtree(self._scratch(handle), ignore_errors=True)

    def evaluate_command(self, command: str) -> Verdict:
        """What the supervisor asks before running a command, so an Ask can go through the existing approval boundary first."""
        return self._policy.evaluate(command)

    async def _blocked(self, command: str, reason: str, started: float, handle: ComputerHandle) -> SandboxExecution:
        from .error_digest import digest_error
        message = f"Blocked by the execution policy: {reason}\n"
        digest = digest_error(message, EXIT_BLOCKED)
        return SandboxExecution(EXIT_BLOCKED, "", message, await self.files(handle), monotonic() - started, error_digest=digest.as_dict() if digest else None)

    def _control(self, handle: ComputerHandle) -> Path:
        directory = self._scratch(handle) / "terminal"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    async def _spawn(self, handle: ComputerHandle, command: str, slave: int, identifier: str) -> asyncio.subprocess.Process:
        verdict = self.evaluate_command(command)
        if verdict.decision is Decision.DENY or (verdict.decision is Decision.ASK and command not in approved_commands.get()):
            raise PermissionError("Command requires approval or is blocked by policy")
        run_directory = self._directory(handle).resolve()
        scratch = self._scratch(handle).resolve()
        profile = seatbelt_profile(run_directory, scratch, self._root, self._home, network=verdict.needs_network and verdict.decision is Decision.ASK)
        control = self._control(handle)
        defaults = _environment(scratch, self._interpreter_directory, self._tool_directories)
        defaults.update({"PIP_TARGET": str(scratch / "python-packages"), "PYTHONPATH": str(scratch / "python-packages"), "NPM_CONFIG_PREFIX": str(scratch / "npm")})
        cwd, env = read_shell_state(control / "state.json", str(run_directory), defaults)
        if not Path(cwd).resolve().is_relative_to(run_directory):
            raise ValueError("Shell working directory escaped the computer")
        # Loader hooks may not run before sandbox-exec has installed the OS policy.
        env = {key: value for key, value in env.items() if not key.startswith(("DYLD_", "LD_")) and key not in {"ENV", "BASH_ENV"}}
        (control / "capture.py").write_text(CAPTURE)
        python = str(self._interpreter_directory / "python3")
        state = control / (f"{identifier}.state.json" if command.startswith("# NEXUS_BACKGROUND") else "state.json")
        script = command_script(command, python, str(control / "capture.py"), str(state), str(run_directory), str(control / f"{identifier}.pid"))
        script_file = control / f"{identifier}.sh"
        script_file.write_text(script)
        return await asyncio.create_subprocess_exec(SANDBOX_EXEC, "-p", profile, "/bin/sh", str(script_file), cwd=cwd, env=env,
            stdin=slave, stdout=slave, stderr=asyncio.subprocess.PIPE, start_new_session=True, preexec_fn=_limit_file_size)

    async def launch_browser(self, handle: ComputerHandle) -> asyncio.subprocess.Process:
        candidates = [os.environ.get("NEXUS_CHROMIUM_PATH", ""), "/Applications/Chromium.app/Contents/MacOS/Chromium", "/usr/bin/chromium", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
        binary = next((path for path in candidates if path and Path(path).is_file()), None)
        if binary is None:
            raise RuntimeError("Chromium is unavailable; configure NEXUS_CHROMIUM_PATH")
        control = self._control(handle)
        (control / "browser_pipe.py").write_bytes(Path(__file__).with_name("browser_pipe.py").read_bytes())
        scratch = self._scratch(handle).resolve()
        short = Path("/tmp") / f"nx-browser-{handle.id.hex}"
        if short.is_symlink() and short.resolve() != scratch:
            raise ValueError("Browser temporary directory belongs to another computer")
        if not short.exists():
            short.symlink_to(scratch, target_is_directory=True)
        environment = _environment(scratch, self._interpreter_directory, self._tool_directories)
        environment["TMPDIR"] = str(short)
        environment["MAC_CHROMIUM_TMPDIR"] = str(short)
        profile = seatbelt_profile(self._directory(handle).resolve(), scratch, self._root, self._home, network=False)
        profile += '(deny process-exec (literal "/bin/launchctl") (regex #"GoogleUpdater|Keystone"))\n'
        profile += f"(allow network* (local unix-socket (subpath {_quoted(scratch)})))\n"
        profile += f"(allow network* (remote unix-socket (subpath {_quoted(scratch)})))\n"
        return await asyncio.create_subprocess_exec(SANDBOX_EXEC, "-p", profile, str(self._interpreter_directory / "python3"), "-I", str(control / "browser_pipe.py"), binary, str(self._scratch(handle) / "browser"),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=environment, limit=8 * 1024 * 1024, start_new_session=True)

    async def terminal(self, handle: ComputerHandle, command: str, timeout_seconds: int, sink: OutputSink, background: bool = False) -> SandboxExecution:
        if handle.external_id is None or not command.strip() or not 1 <= timeout_seconds <= 3600:
            raise ValueError("Computer, command, and timeout must be valid")
        started = monotonic()
        verdict = self.evaluate_command(command)
        if verdict.decision is Decision.DENY:
            return await self._blocked(command, verdict.reason, started, handle)
        if verdict.decision is Decision.ASK and command not in approved_commands.get():
            return await self._blocked(command, f"{verdict.reason} (needs approval)", started, handle)
        return await super().terminal(handle, command, timeout_seconds, sink, background)

    async def shell(self, handle: ComputerHandle, command: str, timeout_seconds: int, sink: OutputSink) -> SandboxExecution:
        return await self.terminal(handle, command, timeout_seconds, sink)
