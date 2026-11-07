#!/usr/bin/env python3
"""Does the runtime folder depend on the machine that built it? Run this before every installer is built.

    python3 scripts/package/verify_runtime.py mac-arm64          # static audit + smoke run from a relocated copy
    python3 scripts/package/verify_runtime.py mac-arm64 --audit  # static audit only
    python3 scripts/package/verify_runtime.py mac-arm64 --runtime /Applications/NexusAgent.app/Contents/Resources/runtime

Static audit, for every Mach-O file in apps/desktop/runtime/<platform>/:
  - it contains code for the platform's CPU;
  - every library it loads is one macOS ships (/usr/lib, /System/Library) or one inside the runtime (never Homebrew, /usr/local, a home folder);
  - the lowest macOS it needs (reported; the installer must not claim an older one than the highest).
Every executable script starts with an interpreter that exists on any Mac, not a path of the builder.

Smoke run: the runtime is cloned to a folder whose name has a space (as "Application Support" does), then the tools agent commands use are run
with a PATH of system folders plus the bundled folders only, so a tool that is only installed on the builder cannot be found by accident.

Exit status 1 when anything is wrong. Windows needs its own version of this (PE files, DLL imports); it is not written until there is a build.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CPU = {"arm64": 0x0100000C, "x86_64": 0x01000007}
SYSTEM_PREFIXES = ("/usr/lib/", "/System/Library/")
INTERPRETERS = {"/bin/sh", "/bin/bash", "/bin/zsh", "/usr/bin/env", "/usr/bin/perl"}  # all shipped with macOS
FORBIDDEN_IN_SCRIPTS = ("/opt/homebrew", "/usr/local", "/Users/")


def cpus_in(head: bytes) -> set[int] | None:
    """CPU types a file contains, or None when it is not a Mach-O file."""
    if len(head) < 8:
        return None
    if head[:4] == b"\xcf\xfa\xed\xfe":  # thin 64-bit, little endian
        return {struct.unpack("<I", head[4:8])[0]}
    if head[:4] == b"\xca\xfe\xba\xbe":  # fat; a Java class file starts the same way but its "count" is far larger
        count = struct.unpack(">I", head[4:8])[0]
        if 0 < count <= 8 and len(head) >= 8 + 20 * count:
            return {struct.unpack(">I", head[8 + 20 * i : 12 + 20 * i])[0] for i in range(count)}
    return None


def load_commands(path: Path) -> tuple[list[str], list[str], tuple[int, ...]]:
    """(libraries loaded, rpaths, lowest macOS version) from `otool -l`."""
    text = subprocess.run(["otool", "-l", str(path)], capture_output=True, text=True).stdout
    libraries = re.findall(r"cmd LC_(?:LOAD_DYLIB|LOAD_WEAK_DYLIB|REEXPORT_DYLIB|LOAD_UPWARD_DYLIB)\n(?:.*\n){1}\s+name (.+?) \(offset", text)
    rpaths = re.findall(r"cmd LC_RPATH\n(?:.*\n){1}\s+path (.+?) \(offset", text)
    versions = [tuple(int(part) for part in found.split(".")) for found in re.findall(r"minos (\d+(?:\.\d+)*)", text)]
    versions += [tuple(int(part) for part in found.split(".")) for found in re.findall(r"cmd LC_VERSION_MIN_MACOSX\n(?:.*\n){1}\s+version (\d+(?:\.\d+)*)", text)]
    return libraries, rpaths, max(versions, default=())


def claimed_minimum() -> tuple[int, ...]:
    """What the installer promises (build.mac.minimumSystemVersion). The audit proves the runtime does not need more."""
    package = json.loads((ROOT / "apps/desktop/package.json").read_text(encoding="utf-8"))
    return tuple(int(part) for part in package["build"]["mac"]["minimumSystemVersion"].split("."))


def audit(runtime: Path, machine: str) -> int:
    wanted = CPU[machine]
    problems: list[str] = []
    warnings: list[str] = []
    macho: list[Path] = []
    scripts: list[Path] = []
    names: set[str] = set()
    for directory, _folders, files in os.walk(runtime):
        for name in files:
            path = Path(directory) / name
            names.add(name)
            if path.is_symlink() or not path.is_file():
                continue
            try:
                with path.open("rb") as handle:
                    head = handle.read(8 + 20 * 8)
            except OSError:
                continue
            kinds = cpus_in(head)
            if kinds is not None:
                macho.append(path)
                if wanted not in kinds:
                    problems.append(f"{path.relative_to(runtime)}: no {machine} code")
            elif head[:2] == b"#!" and os.access(path, os.X_OK):
                scripts.append(path)
    print(f"[audit] {len(macho)} Mach-O files, {len(scripts)} executable scripts")

    def inspect(path: Path) -> tuple[Path, list[str], list[str], tuple[int, ...]]:
        libraries, rpaths, minimum = load_commands(path)
        return path, libraries, rpaths, minimum

    minimum_of: dict[Path, tuple[int, ...]] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        for path, libraries, rpaths, minimum in pool.map(inspect, macho):
            relative = path.relative_to(runtime)
            minimum_of[path] = minimum
            for rpath in rpaths:
                # A search folder in somebody's build tree. dyld skips folders that do not exist, and a library that is really needed is
                # checked below by name, so this is reported, not failed.
                if rpath.startswith("/") and not rpath.startswith(SYSTEM_PREFIXES) and not Path(rpath).is_relative_to(runtime):
                    warnings.append(f"{relative}: rpath {rpath}")
            for library in dict.fromkeys(libraries):
                if library.startswith(SYSTEM_PREFIXES):
                    continue
                if library.startswith(("@rpath/", "@loader_path/", "@executable_path/")):
                    if Path(library).name not in names:  # approximation: the file must exist somewhere inside the runtime
                        problems.append(f"{relative}: loads {library}, which is not in the runtime")
                    continue
                problems.append(f"{relative}: loads {library}")

    highest = max(minimum_of.items(), key=lambda item: item[1], default=(None, ()))
    by_version = Counter(".".join(map(str, version)) for version in minimum_of.values() if version)
    print("[audit] lowest macOS each file needs:", ", ".join(f"{version} x{count}" for version, count in sorted(by_version.items(), key=lambda item: tuple(map(int, item[0].split("."))))))
    if highest[0] is not None:
        print(f"[audit] the app needs macOS {'.'.join(map(str, highest[1]))} or later (set by {highest[0].relative_to(runtime)})")
    claim = claimed_minimum()
    if highest[0] is not None and highest[1] > claim:
        problems.append(f"the installer claims macOS {'.'.join(map(str, claim))} but {highest[0].relative_to(runtime)} needs {'.'.join(map(str, highest[1]))}")
    missing = [path.relative_to(runtime) for path, version in minimum_of.items() if not version]
    if missing:
        print(f"[audit] {len(missing)} files declare no minimum macOS (e.g. {missing[0]})")

    for script in scripts:
        with script.open("rb") as handle:
            first = handle.readline().decode("utf-8", "replace").strip()
        interpreter = first[2:].split()[0] if len(first) > 2 else ""
        if interpreter not in INTERPRETERS or any(bad in first for bad in FORBIDDEN_IN_SCRIPTS) or str(runtime) in first:
            problems.append(f"{script.relative_to(runtime)}: starts with {first!r}")

    for warning in sorted(set(warnings))[:10]:
        print(f"[audit] note    {warning}")
    for problem in problems[:60]:
        print(f"[audit] PROBLEM {problem}")
    if len(problems) > 60:
        print(f"[audit] ... and {len(problems) - 60} more")
    print(f"[audit] {'FAILED' if problems else 'passed'}: {len(problems)} problems")
    return len(problems)


def smoke(runtime: Path) -> int:
    holder = Path(tempfile.mkdtemp(prefix="nexus relocated "))
    try:
        target = holder / "Application Support" / "runtime"
        target.mkdir(parents=True)
        for name in ("python", "node", "git", "tools"):
            if (runtime / name).exists():
                # `cp -c` clones on APFS: instant and no extra space; the copy is still a different path.
                subprocess.run(["cp", "-cR", str(runtime / name), str(target / name)], check=True)
        folders = [target / "python" / "bin"] + [target / name / "bin" for name in ("node", "git", "tools") if (target / name / "bin").exists()]
        home = holder / "home"
        work = holder / "work"
        home.mkdir()
        work.mkdir()
        environment = {"PATH": os.pathsep.join([*map(str, folders), "/usr/bin", "/bin", "/usr/sbin", "/sbin"]), "HOME": str(home), "TMPDIR": str(holder), "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"}
        checks: list[tuple[str, str, str]] = [
            ("python and the libraries agent code imports", "python3 -c \"import sys,numpy,pandas,matplotlib,openpyxl,PIL,pytest; print(sys.prefix)\"", str(target / "python")),
            ("pytest as a command (relocatable script)", "pytest --version", "pytest"),
            ("uvicorn as a command", "uvicorn --version", "Running uvicorn"),
            ("alembic as a command", "alembic --version", "alembic"),
            ("node", "node -e \"console.log(6*7)\"", "42"),
            ("npm", "npm --version", "."),
            ("npx", "npx --version", "."),
            ("git exec path is inside the bundle", "git --exec-path", str(target / "git")),
            ("git can make a commit", "git init -q repo && cd repo && git -c user.name=t -c user.email=t@t commit -q --allow-empty -m first && git log --oneline", "first"),
            ("ffmpeg encodes H.264 (VideoToolbox) into mp4", "ffmpeg -v error -f lavfi -i testsrc=duration=1:size=128x128:rate=10 -c:v h264_videotoolbox -y out.mp4 && ffprobe -v error -show_entries stream=codec_name -of csv=p=0 out.mp4", "h264"),
            ("ffmpeg encodes AAC audio", "ffmpeg -v error -f lavfi -i sine=duration=1 -c:a aac -y out.m4a && ffprobe -v error -show_entries stream=codec_name -of csv=p=0 out.m4a", "aac"),
            ("no Homebrew tool is visible", "command -v brew || echo none", "none"),
        ]
        failures = 0
        for label, command, expect in checks:
            if "ffmpeg" in command and not (target / "tools" / "bin" / "ffmpeg").exists():
                print(f"[smoke] skip  {label} (this runtime has no ffmpeg)")
                continue
            if command.split()[0] in {"node", "npm", "npx"} and not (target / "node").exists():
                print(f"[smoke] skip  {label} (this runtime has no node)")
                continue
            if command.startswith("git") and not (target / "git").exists():
                print(f"[smoke] skip  {label} (this runtime has no git)")
                continue
            done = subprocess.run(["/bin/sh", "-c", command], cwd=work, env=environment, capture_output=True, text=True, timeout=180)
            output = (done.stdout + done.stderr).strip()
            ok = done.returncode == 0 and expect in output
            failures += not ok
            print(f"[smoke] {'ok   ' if ok else 'FAIL '} {label}" + ("" if ok else f"\n        exit {done.returncode}: {output[-300:]}"))
        if (target / "tools" / "bin" / "headless-browser").exists():
            # Informational only: no browser is bundled, so a machine without Chrome/Edge legitimately answers "not found". A slow first start
            # (Chrome translated by Rosetta) is reported, not fatal.
            try:
                browser = subprocess.run(["/bin/sh", "-c", "headless-browser --version"], cwd=work, env=environment, capture_output=True, text=True, timeout=180)
                print(f"[smoke] {'ok   ' if browser.returncode == 0 else 'note '} headless-browser: {(browser.stdout + browser.stderr).strip()[:120]}")
            except subprocess.TimeoutExpired:
                print("[smoke] note  headless-browser: no answer within 180 s (a browser translated by Rosetta can be slow on its first start)")
        print(f"[smoke] {'FAILED' if failures else 'passed'}: {failures} failures")
        return failures
    finally:
        shutil.rmtree(holder, ignore_errors=True)


def main() -> None:
    platform = sys.argv[1] if len(sys.argv) > 1 else ""
    if platform not in ("mac-arm64", "mac-x64"):
        raise SystemExit("usage: verify_runtime.py <mac-arm64|mac-x64> [--audit]")
    runtime = ROOT / "apps/desktop/runtime" / platform
    if "--runtime" in sys.argv:  # e.g. the runtime folder inside an installed copy of the app: proves the installer, not just the build folder
        runtime = Path(sys.argv[sys.argv.index("--runtime") + 1]).resolve()
    if not runtime.exists():
        raise SystemExit(f"{runtime} does not exist; run build_runtime.py first")
    machine = "x86_64" if platform.endswith("x64") else "arm64"
    bad = 0 if "--smoke-only" in sys.argv else audit(runtime, machine)
    if "--audit" not in sys.argv:
        if subprocess.run(["uname", "-m"], capture_output=True, text=True).stdout.strip() != machine:
            # An Intel runtime on an Apple Silicon Mac: run the smoke part through Rosetta, with the runtime's OWN Intel Python (the audit above
            # needed Apple's tools, which have no Intel slice, so it runs natively; the smoke test needs none of them).
            print("[smoke] Intel runtime on an Apple Silicon Mac: commands are run through Rosetta")
            again = subprocess.run(["arch", "-x86_64", str(runtime / "python/bin/python3"), "-I", __file__, platform, "--smoke-only", "--runtime", str(runtime)])
            raise SystemExit(1 if bad or again.returncode else 0)
        bad += smoke(runtime)
    raise SystemExit(1 if bad else 0)


if __name__ == "__main__":
    main()
