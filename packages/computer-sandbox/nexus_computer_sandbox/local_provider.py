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
        lines.append("(deny network*)")
    return "\n".join(lines) + "\n"


def _limit_file_size() -> None:
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_FILE_BYTES, MAX_FILE_BYTES))


def _environment(scratch_directory: Path, interpreter_directory: Path) -> dict[str, str]:
    """Only what a command needs. The host environment holds API keys and tokens, so none of it is passed on."""
    scratch_directory.mkdir(parents=True, exist_ok=True)
    return {
        "PATH": f"{interpreter_directory}:/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME": str(scratch_directory), "TMPDIR": str(scratch_directory),
        "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
    }


class LocalSandboxProvider(DockerSandboxProvider):
    """File handling is shared with the Docker provider (same directory layout, same symlink-safe opens); only execution differs."""

    name = "local"

    def __init__(
        self, host_root: Path, policy: ExecutionPolicy | None = None,
        interpreter: Path | None = None, home: Path | None = None,
    ) -> None:
        if not seatbelt_available():
            raise RuntimeError("The local sandbox needs macOS sandbox-exec; use the docker provider on this machine")
        super().__init__(host_root)
        self._policy = policy or ExecutionPolicy()
        self._interpreter_directory = (interpreter or Path(sys.executable)).resolve().parent
        self._home = (home or Path.home()).resolve()

    def _scratch(self, handle: ComputerHandle) -> Path:
        # Under the computers root but outside every run directory, like the Docker provider's /tmp tmpfs.
        return self._root / ".scratch" / str(handle.access.tenant_id) / str(handle.access.workspace_id) / str(handle.id)

    async def create(self, handle: ComputerHandle) -> str:
        self._directory(handle).mkdir(parents=True, exist_ok=True)
        self._scratch(handle).mkdir(parents=True, exist_ok=True)
        return f"local-{handle.id.hex}"

    async def destroy(self, handle: ComputerHandle) -> None:
        # Nothing runs between commands; the run directory is removed by the run's retirement, as for Docker. Scratch goes with the computer.
        shutil.rmtree(self._scratch(handle), ignore_errors=True)

    def evaluate_command(self, command: str) -> Verdict:
        """What the supervisor asks before running a command, so an Ask can go through the existing approval boundary first."""
        return self._policy.evaluate(command)

    async def _blocked(self, command: str, reason: str, started: float, handle: ComputerHandle) -> SandboxExecution:
        return SandboxExecution(EXIT_BLOCKED, "", f"Blocked by the execution policy: {reason}\n", await self.files(handle), monotonic() - started)

    async def shell(self, handle: ComputerHandle, command: str, timeout_seconds: int, sink: OutputSink) -> SandboxExecution:
        if handle.external_id is None or not command.strip() or not 1 <= timeout_seconds <= 3600:
            raise ValueError("Computer, command, and timeout must be valid")
        started = monotonic()
        verdict = self.evaluate_command(command)
        if verdict.decision is Decision.DENY:
            return await self._blocked(command, verdict.reason, started, handle)
        if verdict.decision is Decision.ASK and command not in approved_commands.get():
            # Nobody approved it (a benchmark, a service key, a caller without a guard): a refusal, never a wait.
            return await self._blocked(command, f"{verdict.reason} (needs approval)", started, handle)
        run_directory = self._directory(handle).resolve()
        scratch = self._scratch(handle).resolve()
        profile = seatbelt_profile(run_directory, scratch, self._root, self._home, network=verdict.needs_network and verdict.decision is Decision.ASK)
        process = await asyncio.create_subprocess_exec(
            SANDBOX_EXEC, "-p", profile, "/bin/sh", "-c", command,
            cwd=run_directory, env=_environment(scratch, self._interpreter_directory),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, start_new_session=True, preexec_fn=_limit_file_size,
        )
        chunks: dict[str, list[str]] = {"stdout": [], "stderr": []}

        async def forward(reader: asyncio.StreamReader | None, stream: str) -> None:
            if reader is None:
                raise RuntimeError("Computer output stream is unavailable")
            while data := await reader.read(4096):
                decoded = data.decode(errors="replace")
                chunks[stream].append(decoded)
                await sink(stream, decoded)

        def kill_tree() -> None:
            try:
                os.killpg(process.pid, signal.SIGKILL)  # the session leader's group: the shell and everything it started
            except ProcessLookupError:
                pass

        tasks = [asyncio.create_task(forward(process.stdout, "stdout")), asyncio.create_task(forward(process.stderr, "stderr"))]
        timed_out = False
        try:
            await asyncio.wait_for(process.wait(), timeout_seconds)
        except asyncio.TimeoutError:
            timed_out = True
            kill_tree()
            await process.wait()
        except BaseException:
            kill_tree()
            await process.wait()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
        await asyncio.gather(*tasks)
        # A shell killed on timeout reports 137, as `timeout --signal=KILL` does in the Docker provider.
        return SandboxExecution(137 if timed_out else process.returncode or 0, "".join(chunks["stdout"]), "".join(chunks["stderr"]), await self.files(handle), monotonic() - started)
