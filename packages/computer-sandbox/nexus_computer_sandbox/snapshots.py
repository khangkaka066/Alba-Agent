"""Content-addressed workspace snapshots; metadata stays outside the untrusted computer."""
from __future__ import annotations

import hashlib
import fcntl
from contextlib import contextmanager
from collections.abc import Iterator
import json
import os
import shutil
import stat
import tempfile
from pathlib import Path
from time import time, monotonic
from typing import Any
import builtins
from uuid import uuid4

MAX_FILE_BYTES = 500 * 1024 * 1024
MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024 * 1024
EXCLUDED = frozenset({".git", "node_modules", ".venv", "__pycache__", ".nexus-home", ".nexus-packages", ".screen"})


class WorkspaceSnapshots:
    def __init__(self, workspace: Path, store: Path) -> None:
        self.workspace = workspace.resolve()
        self.store = store
        (store / "objects").mkdir(parents=True, exist_ok=True)

    def _files(self) -> list[Path]:
        found: list[Path] = []
        for directory, dirs, files in os.walk(self.workspace, followlinks=False):
            parent = Path(directory)
            dirs[:] = [name for name in dirs if name not in EXCLUDED and not (parent / name).is_symlink()]
            for name in files:
                path = parent / name
                if path.is_symlink():
                    raise ValueError("Snapshots refuse symbolic links; no external files are followed")
                if not path.is_file():
                    raise ValueError("Snapshots support regular workspace files only")
                found.append(path)
                if len(found) > 20_000:
                    raise ValueError("Workspace exceeds the 20,000-file snapshot budget")
        return found

    def _open(self, path: Path) -> int:
        relative = path.relative_to(self.workspace)
        directory = os.open(self.workspace, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for part in relative.parts[:-1]:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
                os.close(directory)
                directory = child
            return os.open(relative.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
        finally:
            os.close(directory)

    @contextmanager
    def _locked(self) -> Iterator[None]:
        with (self.store / "snapshot.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield

    def create(self, command_hash: str = "") -> dict[str, Any]:
        with self._locked():
            return self._create(command_hash)

    def _create(self, command_hash: str) -> dict[str, Any]:
        started = monotonic()
        entries: dict[str, dict[str, Any]] = {}
        total = 0
        for path in self._files():
            descriptor = self._open(path)
            with os.fdopen(descriptor, "rb") as source:
                info = os.fstat(source.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE_BYTES:
                    raise ValueError("Workspace file exceeds the 500 MiB snapshot limit")
                total += info.st_size
                if total > MAX_SNAPSHOT_BYTES:
                    raise ValueError("Workspace exceeds the 2 GiB snapshot budget")
                digest = hashlib.sha256()
                with tempfile.NamedTemporaryFile(dir=self.store, delete=False) as target:
                    temporary = Path(target.name)
                    try:
                        copied = 0
                        while block := source.read(1024 * 1024):
                            copied += len(block)
                            if copied > info.st_size:
                                raise ValueError("Workspace changed during snapshot; retry when writers are idle")
                            digest.update(block)
                            target.write(block)
                        changed = os.fstat(source.fileno())
                        if changed.st_size != info.st_size or changed.st_mtime_ns != info.st_mtime_ns:
                            raise ValueError("Workspace changed during snapshot; retry when writers are idle")
                        target.flush()
                        key = digest.hexdigest()
                        destination = self.store / "objects" / key
                        if not destination.exists():
                            os.replace(temporary, destination)
                    finally:
                        temporary.unlink(missing_ok=True)
                entries[path.relative_to(self.workspace).as_posix()] = {"object": key, "mode": stat.S_IMODE(info.st_mode), "size": info.st_size}
        identifier = uuid4().hex
        document = {"id": identifier, "created_at": time(), "command_sha256": command_hash, "files": entries, "size_bytes": total, "duration_ms": round((monotonic() - started) * 1000, 3)}
        (self.store / f"{identifier}.json").write_text(json.dumps(document), encoding="utf-8")
        self._prune()
        return {key: value for key, value in document.items() if key != "files"}

    def _prune(self) -> None:
        manifests = sorted(self.store.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
        retained: set[str] = set()
        kept = size = 0
        for path in manifests:
            entries = json.loads(path.read_text())["files"].values()
            objects = {str(entry["object"]) for entry in entries}
            additional = sum((self.store / "objects" / key).stat().st_size for key in objects - retained)
            if kept >= 50 or (kept and size + additional > MAX_SNAPSHOT_BYTES):
                path.unlink()
                continue
            kept += 1
            size += additional
            retained.update(objects)
        for path in (self.store / "objects").iterdir():
            if path.name not in retained:
                path.unlink()

    def list(self) -> list[dict[str, Any]]:
        with self._locked():
            return self._list()

    def _list(self) -> builtins.list[dict[str, Any]]:
        rows = []
        for path in self.store.glob("*.json"):
            document = json.loads(path.read_text(encoding="utf-8"))
            rows.append({key: value for key, value in document.items() if key != "files"})
        return sorted(rows, key=lambda row: row["created_at"], reverse=True)

    def restore(self, identifier: str) -> None:
        with self._locked():
            self._restore(identifier)

    def _parent(self, path: Path, create: bool = False) -> int:
        directory = os.open(self.workspace, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for part in path.relative_to(self.workspace).parts[:-1]:
                if create:
                    try:
                        os.mkdir(part, dir_fd=directory)
                    except FileExistsError:
                        pass
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
                os.close(directory)
                directory = child
            return directory
        except BaseException:
            os.close(directory)
            raise

    def _restore(self, identifier: str) -> None:
        if len(identifier) != 32 or any(char not in "0123456789abcdef" for char in identifier):
            raise ValueError("Invalid filesystem checkpoint")
        manifest = self.store / f"{identifier}.json"
        if not manifest.exists():
            raise FileNotFoundError("Filesystem checkpoint is unavailable")
        entries = json.loads(manifest.read_text(encoding="utf-8"))["files"]
        # Validate the complete current tree before making any mutation.
        current = self._files()
        for name, entry in entries.items():
            destination = self.workspace / name
            if not destination.resolve().is_relative_to(self.workspace) or not (self.store / "objects" / entry["object"]).is_file():
                raise ValueError("Snapshot manifest is invalid")
        for path in current:
            if path.relative_to(self.workspace).as_posix() not in entries:
                directory = self._parent(path)
                try:
                    os.unlink(path.name, dir_fd=directory)
                finally:
                    os.close(directory)
        for name, entry in entries.items():
            destination = self.workspace / name
            directory = self._parent(destination, create=True)
            temporary = f".nexus-restore-{uuid4().hex}"
            try:
                descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
                with os.fdopen(descriptor, "wb") as target, (self.store / "objects" / entry["object"]).open("rb") as source:
                    shutil.copyfileobj(source, target, 1024 * 1024)
                    os.fchmod(target.fileno(), entry["mode"])
                    target.flush()
                    os.fsync(target.fileno())
                os.replace(temporary, destination.name, src_dir_fd=directory, dst_dir_fd=directory)
            finally:
                try:
                    os.unlink(temporary, dir_fd=directory)
                except FileNotFoundError:
                    pass
                os.close(directory)
