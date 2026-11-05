#!/usr/bin/env python3
"""Assemble everything the desktop app needs so it runs with nothing installed (no Docker, no system Python, Postgres or Redis).

    python3 scripts/package/build_runtime.py mac-arm64

Output: apps/desktop/runtime/<platform>/ with
    python/    relocatable CPython with the API requirements (and the sandbox image's data libraries) installed
    postgres/  PostgreSQL server binaries
    redis/     redis-server
    qdrant/    qdrant
    backend/   the API and the packages, laid out as in the repository (the API's working directory)
    web/       the Next.js standalone server (started with Electron's own Node)
    manifest.json  versions that were assembled

Every download is checked against the SHA-256 pinned in runtime.json; a mismatch stops the build. Same pins as docker-compose.yml where a
version exists there (Redis 7.2.4, Qdrant 1.12.6); Postgres is the 16.x line.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PINS = json.loads((Path(__file__).parent / "runtime.json").read_text(encoding="utf-8"))
CACHE = ROOT / "apps/desktop/.cache/runtime-downloads"
API_PORT = PINS["ports"]["api"]


def log(message: str) -> None:
    print(f"[runtime] {message}", flush=True)


def fetch(name: str, url: str, sha256: str) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    target = CACHE / name
    if not target.exists():
        log(f"download {name}")
        request = urllib.request.Request(url, headers={"User-Agent": "nexus-runtime-build"})
        with urllib.request.urlopen(request) as response, target.open("wb") as handle:
            shutil.copyfileobj(response, handle)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    if sha256 != "pending" and digest != sha256:
        target.unlink()
        raise SystemExit(f"{name}: sha256 {digest} does not match the pinned {sha256}")
    if sha256 == "pending":
        print(f"[runtime] {name}: no published checksum; observed sha256 {digest} (pin it in runtime.json)")
    return target


def run(command: list[str | Path], cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    log(" ".join(str(part) for part in command)[:200])
    subprocess.run([str(part) for part in command], cwd=cwd, env=env, check=True)


def extract_tar(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as bundle:
        if hasattr(tarfile, "data_filter"):
            bundle.extractall(destination, filter="data")  # refuses absolute paths and links that leave the folder
        else:  # Python before the filter backports: check by hand
            root = destination.resolve()
            for member in bundle.getmembers():
                if not (destination / member.name).resolve().is_relative_to(root) if hasattr(Path, "is_relative_to") else ".." in Path(member.name).parts:
                    raise SystemExit(f"{archive.name}: unsafe path {member.name}")
            bundle.extractall(destination)


def build_python(platform: str, out: Path) -> None:
    pin = PINS["python"][platform]
    archive = fetch(pin["file"], pin["url"], pin["sha256"])
    work = out.parent / ".python-extract"
    shutil.rmtree(work, ignore_errors=True)
    extract_tar(archive, work)
    shutil.rmtree(out, ignore_errors=True)
    shutil.move(str(work / "python"), out)
    shutil.rmtree(work, ignore_errors=True)
    binary = out / ("python.exe" if platform.startswith("win") else "bin/python3")
    if not platform.startswith("win"):
        link = out / "bin" / "python"
        if not link.exists():
            link.symlink_to("python3")  # agent commands say `python`
    target = ["--platform", pin["wheel_platform"], "--python-version", "3.12", "--only-binary=:all:", "--implementation", "cp"] if pin.get("cross") else []
    if target:
        site = out / "Lib" / "site-packages"
        site.mkdir(parents=True, exist_ok=True)
        pip = [sys.executable, "-m", "pip", "install", "--no-cache-dir", "--target", site, *target]
    else:
        pip = [binary, "-m", "pip", "install", "--no-cache-dir", "--disable-pip-version-check"]
    requirements = ROOT / "apps/api/requirements.txt"
    run([*pip, "-r", requirements])
    # The libraries the Docker sandbox image offers to agent code, so a task that plots or reads a spreadsheet behaves the same.
    # Pillow is not pinned to the image's 11.0.0: the API already installs a newer one that pdfplumber needs, and one interpreter has one Pillow.
    run([*pip, *PINS["sandbox_libraries"]])
    if not target:
        # Best effort: a package that ships a file for another Python version fails to compile here and would fail to import anyway.
        subprocess.run([str(binary), "-m", "compileall", "-q", "-j", "0", str(out / "lib")], check=False, capture_output=True)


def build_postgres(platform: str, out: Path) -> None:
    pin = PINS["postgres"][platform]
    jar = fetch(pin["file"], pin["url"], pin["sha256"])
    work = out.parent / ".postgres-extract"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    with zipfile.ZipFile(jar) as bundle:
        archive = next(name for name in bundle.namelist() if name.endswith((".txz", ".tar.xz")))
        bundle.extract(archive, work)
    shutil.rmtree(out, ignore_errors=True)
    extract_tar(work / archive, out)
    shutil.rmtree(work, ignore_errors=True)


def build_redis(platform: str, out: Path) -> None:
    pin = PINS["redis"]
    archive = fetch(pin["file"], pin["url"], pin["sha256"])
    work = out.parent / ".redis-build"
    shutil.rmtree(work, ignore_errors=True)
    extract_tar(archive, work)
    source = next(work.iterdir())
    env = {**os.environ, "MACOSX_DEPLOYMENT_TARGET": "12.0"}
    run(["make", "-j", str(os.cpu_count() or 4), "BUILD_TLS=no", "MALLOC=libc"], cwd=source, env=env)
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    shutil.copy2(source / "src" / "redis-server", out / "redis-server")
    shutil.copy2(source / "src" / "redis-cli", out / "redis-cli")
    shutil.rmtree(work, ignore_errors=True)


def build_qdrant(platform: str, out: Path) -> None:
    pin = PINS["qdrant"][platform]
    archive = fetch(pin["file"], pin["url"], pin["sha256"])
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(out)
    else:
        extract_tar(archive, out)
    for candidate in out.rglob("qdrant"):
        candidate.chmod(0o755)


IGNORED = shutil.ignore_patterns("__pycache__", "*.pyc", "tests", "test", ".pytest_cache", ".mypy_cache", "node_modules")


def build_backend(out: Path) -> None:
    shutil.rmtree(out, ignore_errors=True)
    (out / "apps" / "api").mkdir(parents=True)
    for name in ("app", "migrations"):
        shutil.copytree(ROOT / "apps/api" / name, out / "apps/api" / name, ignore=IGNORED)
    shutil.copy2(ROOT / "apps/api/alembic.ini", out / "apps/api/alembic.ini")
    shutil.copytree(ROOT / "packages", out / "packages", ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "tests", "test", "node_modules", "typescript", "Dockerfile", "*.md"))
    shutil.copy2(Path(__file__).parent / "bootstrap_database.py", out / "bootstrap_database.py")
    (out / "VERSION").write_text(json.loads((ROOT / "apps/desktop/package.json").read_text(encoding="utf-8"))["version"], encoding="utf-8")


def build_web(out: Path) -> None:
    env = {**os.environ, "NEXT_PUBLIC_NEXUS_API_WS_URL": f"ws://127.0.0.1:{API_PORT}", "NEXT_TELEMETRY_DISABLED": "1"}
    run(["pnpm", "--filter", "@nexus/web", "build"], cwd=ROOT, env=env)
    standalone = ROOT / "apps/web/.next/standalone"
    shutil.rmtree(out, ignore_errors=True)
    # pnpm links packages with relative symlinks inside this folder; keep them as links (copying their targets would repeat every package).
    shutil.copytree(standalone, out, symlinks=True)
    shutil.copytree(ROOT / "apps/web/.next/static", out / "apps/web/.next/static", dirs_exist_ok=True)
    public = ROOT / "apps/web/public"
    if public.exists():
        shutil.copytree(public, out / "apps/web/public", dirs_exist_ok=True)


def main() -> None:
    platform = sys.argv[1] if len(sys.argv) > 1 else ""
    if platform not in PINS["python"]:
        raise SystemExit(f"usage: build_runtime.py <{'|'.join(PINS['python'])}>")
    out = ROOT / "apps/desktop/runtime" / platform
    out.mkdir(parents=True, exist_ok=True)
    only = set(sys.argv[2:])
    steps = {
        "python": lambda: build_python(platform, out / "python"),
        "postgres": lambda: build_postgres(platform, out / "postgres"),
        "redis": lambda: build_redis(platform, out / "redis"),
        "qdrant": lambda: build_qdrant(platform, out / "qdrant"),
        "backend": lambda: build_backend(out / "backend"),
        "web": lambda: build_web(out / "web"),
    }
    for name, step in steps.items():
        if not only or name in only:
            step()
    (out / "manifest.json").write_text(json.dumps({"platform": platform, "pins": PINS}, indent=2), encoding="utf-8")
    log(f"done: {out}")


if __name__ == "__main__":
    main()
