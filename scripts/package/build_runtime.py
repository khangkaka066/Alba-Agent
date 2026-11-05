#!/usr/bin/env python3
"""Assemble everything the desktop app needs so it runs with nothing installed (no Docker, no system Python, Postgres or Redis).

    python3 scripts/package/build_runtime.py mac-arm64

Output: apps/desktop/runtime/<platform>/ with
    python/    relocatable CPython with the API requirements (and the sandbox image's data libraries) installed
    postgres/  PostgreSQL server binaries
    redis/     redis-server
    qdrant/    qdrant
    node/      Node.js and npm for agent commands (the web server itself runs on Electron's Node, not this one)
    git/       git, relocatable (built with RUNTIME_PREFIX)
    tools/bin/ ffmpeg and ffprobe (built from source, LGPL) and the headless-browser wrapper
    backend/   the API and the packages, laid out as in the repository (the API's working directory)
    web/       the Next.js standalone server (started with Electron's own Node)
    manifest.json  versions that were assembled

Every download is checked against the SHA-256 pinned in runtime.json; a mismatch stops the build. Same pins as docker-compose.yml where a
version exists there (Redis 7.2.4, Qdrant 1.12.6); Postgres is the 16.x line.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import platform as host_platform
import re
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


def minimum_macos() -> str:
    """The lowest macOS the installer claims (build.mac.minimumSystemVersion). One place, so the claim, the wheels pip picks and the audit agree."""
    return json.loads((ROOT / "apps/desktop/package.json").read_text(encoding="utf-8"))["build"]["mac"]["minimumSystemVersion"]


# pip picks wheels by the macOS of the machine that runs it, so a builder on macOS 27 installed numpy, onnxruntime and orjson wheels that
# need macOS 14 and 15 and nothing said so. This makes pip answer as a Mac at exactly the claimed minimum, whatever the builder runs.
def pip_as_minimum_macos(binary: Path) -> list[str | Path]:
    code = (
        "import platform, runpy; real = platform.mac_ver; "
        f"platform.mac_ver = lambda *a, **k: ({minimum_macos()!r}, real()[1], real()[2]); "
        "runpy.run_module('pip', run_name='__main__')"
    )
    return [binary, "-c", code]


def target_machine(platform: str) -> str:
    return "x86_64" if platform.endswith("x64") else "arm64"


def compile_environment(platform: str) -> dict[str, str]:
    """One minimum macOS for everything compiled here, and a PATH of system folders only, so nothing is taken from Homebrew. The compiler is
    told the target CPU (`-arch`), so an Intel build on an Apple Silicon Mac needs no emulated `make` (that fails: Apple's clang/xcrun shims have
    no Intel slice) and its result still runs here through Rosetta for testing."""
    target = PINS["macos_deployment_target"]
    clang = f"clang -arch {target_machine(platform)} -mmacosx-version-min={target}"
    sdk = subprocess.run(["xcrun", "--show-sdk-path"], capture_output=True, text=True, check=True).stdout.strip()
    return {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": os.environ.get("HOME", "/tmp"), "MACOSX_DEPLOYMENT_TARGET": target, "CC": clang, "LD": clang, "SDKROOT": sdk}


RELOCATABLE_SHEBANG = b"""#!/bin/sh
'''exec' "$(dirname "$0")/python3" "$0" "$@"
' '''
"""


def relocate_scripts(python_root: Path) -> None:
    """pip writes `#!/abs/path/to/this/python3` into every console script (pytest, uvicorn, celery, alembic). That path is the builder's: on
    any other machine, or once the app sits in /Applications, the script fails with "bad interpreter". This sh/python polyglot finds the
    interpreter next to itself instead."""
    changed = 0
    for script in (python_root / "bin").iterdir():
        if script.is_symlink() or not script.is_file():
            continue
        with script.open("rb") as handle:
            first = handle.readline().decode("utf-8", "replace")
        if first.startswith("#!") and str(python_root) in first:
            script.write_bytes(RELOCATABLE_SHEBANG + script.read_bytes().split(b"\n", 1)[1])
            changed += 1
    log(f"made {changed} console scripts relocatable")


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
        # Wheels only: a package built from source here would be compiled by the builder's compiler against the builder's libraries.
        pip = [*pip_as_minimum_macos(binary), "install", "--no-cache-dir", "--disable-pip-version-check", "--only-binary=:all:"]
    requirements = ROOT / "apps/api/requirements.txt"
    run([*pip, "-r", requirements])
    # The libraries the Docker sandbox image offers to agent code, so a task that plots or reads a spreadsheet behaves the same.
    # Pillow is not pinned to the image's 11.0.0: the API already installs a newer one that pdfplumber needs, and one interpreter has one Pillow.
    run([*pip, *PINS["sandbox_libraries"]])
    if not target:
        relocate_scripts(out)
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
    # PL/Perl, PL/Python, PL/Tcl and xml2 are built against languages and libraries of the packager's machine (/Library/edb/languagepack...,
    # libxslt) that no user has. The app uses none of them, and a CREATE EXTENSION on one would fail at load time, so they are not shipped.
    unused = re.compile(r"^(?:.*_)?(?:plperlu?|plpython3u?|pltclu?)\b|^(?:pgxml|xml2)\b|^(?:bool|hstore|jsonb|ltree)_pl(?:perl|python3|tcl)")
    for folder in (out / "lib" / "postgresql", out / "share" / "postgresql" / "extension"):
        for file in folder.iterdir():
            if unused.match(file.name):
                file.unlink()


def build_redis(platform: str, out: Path) -> None:
    pin = PINS["redis"]
    archive = fetch(pin["file"], pin["url"], pin["sha256"])
    work = out.parent / ".redis-build"
    shutil.rmtree(work, ignore_errors=True)
    extract_tar(archive, work)
    source = next(work.iterdir())
    run(["make", "-j", str(os.cpu_count() or 4), "BUILD_TLS=no", "MALLOC=libc"], cwd=source, env=compile_environment(platform))
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


def build_node(platform: str, out: Path) -> None:
    pin = PINS["node"][platform]
    archive = fetch(pin["file"], pin["url"], pin["sha256"])
    work = out.parent / ".node-extract"
    shutil.rmtree(work, ignore_errors=True)
    extract_tar(archive, work)
    source = next(work.iterdir())
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    # Not include/ (C headers) or share/ (docs, man pages): agent commands run node and npm, nothing here is compiled against it.
    for name in ("bin", "lib"):
        shutil.copytree(source / name, out / name, symlinks=True)
    shutil.rmtree(work, ignore_errors=True)


def build_git(platform: str, out: Path) -> None:
    """git built to find its helper programs next to itself (RUNTIME_PREFIX), whichever folder the app is installed in. macOS's own libcurl
    and zlib are used, so nothing links to Homebrew. Perl, Python, Tcl and gettext support are left out: they only add `git send-email`,
    `git svn`, `gitk` and translated messages."""
    pin = PINS["git"]
    archive = fetch(pin["file"], pin["url"], pin["sha256"])
    work = out.parent / ".git-build"
    shutil.rmtree(work, ignore_errors=True)
    extract_tar(archive, work)
    source = next(work.iterdir())
    staging = work / "staging"
    flags = ["RUNTIME_PREFIX=1", "INSTALL_SYMLINKS=1", "NO_GETTEXT=1", "NO_TCLTK=1", "NO_PERL=1", "NO_PYTHON=1", "NO_EXPAT=1", "NO_DARWIN_PORTS=1", "NO_FINK=1", "NO_RUST=1", "prefix=/nexus-git"]  # NO_RUST: optional in this git, and the builder's Rust toolchain must not decide the result
    env = compile_environment(platform)
    flags.append(f"CC={env['CC']}")  # git's Makefile sets CC itself, which overrides the environment: without this an Intel build comes out arm64
    run(["make", "-j", str(os.cpu_count() or 4), *flags, "all"], cwd=source, env=env)
    run(["make", *flags, f"DESTDIR={staging}", "install"], cwd=source, env=env)
    shutil.rmtree(out, ignore_errors=True)
    shutil.move(str(staging / "nexus-git"), out)
    shutil.rmtree(work, ignore_errors=True)


def build_ffmpeg(platform: str, out: Path) -> None:
    """LGPL build: no GPL or non-free code, so no libx264; H.264 and AAC come from macOS's VideoToolbox and AudioToolbox. Nothing is
    auto-detected, so the machine that builds cannot decide what ends up linked."""
    pin = PINS["ffmpeg"]
    archive = fetch(pin["file"], pin["url"], pin["sha256"])
    work = out.parent / ".ffmpeg-build"
    shutil.rmtree(work, ignore_errors=True)
    extract_tar(archive, work)
    source = next(work.iterdir())
    machine = target_machine(platform)
    target = PINS["macos_deployment_target"]
    env = compile_environment(platform)
    options = [
        "--disable-gpl", "--disable-nonfree", "--disable-autodetect", "--disable-doc", "--disable-ffplay", "--disable-debug",
        "--enable-videotoolbox", "--enable-audiotoolbox", "--enable-zlib", "--enable-bzlib", "--enable-iconv", "--extra-libs=-liconv",
        f"--arch={machine}", f"--cc={env['CC']}", f"--extra-cflags=-mmacosx-version-min={target}", f"--extra-ldflags=-mmacosx-version-min={target}",
    ]
    if machine != host_platform.machine():
        options.append("--enable-cross-compile")  # code for another CPU than this Mac's: configure must not assume it can run what it compiles
    if machine == "x86_64":
        options.append("--disable-x86asm")  # needs nasm, which would be the builder's own; slower on Intel, same output
    run(["./configure", *options], cwd=source, env=env)
    run(["make", "-j", str(os.cpu_count() or 4)], cwd=source, env=env)
    (out / "bin").mkdir(parents=True, exist_ok=True)
    for name in ("ffmpeg", "ffprobe"):
        shutil.copy2(source / name, out / "bin" / name)
    shutil.rmtree(work, ignore_errors=True)


HEADLESS_BROWSER = """#!/bin/sh
# Headless screenshots and PDFs of local pages, like the Docker sandbox's `headless-browser`. No browser is bundled (Chromium alone is over
# 300 MB): this uses a Chromium-based browser that is already installed, and says so when there is none.
for app in "Google Chrome" "Chromium" "Microsoft Edge" "Brave Browser"; do
  binary="/Applications/$app.app/Contents/MacOS/$app"
  if [ -x "$binary" ]; then
    # The command already runs inside a sandbox, so the browser's own sandbox cannot start; its profile goes to the command's temp folder.
    exec "$binary" --headless=new --no-sandbox --disable-gpu --disable-crash-reporter --no-first-run \\
      --user-data-dir="${TMPDIR:-/tmp}/headless-browser-profile" "$@"
  fi
done
echo "headless-browser: no Chromium-based browser found (looked for Google Chrome, Chromium, Microsoft Edge, Brave Browser in /Applications)." >&2
exit 127
"""


def build_tools(platform: str, out: Path) -> None:
    """ffmpeg, ffprobe and the headless-browser wrapper share one folder, which goes on the agent's PATH."""
    shutil.rmtree(out, ignore_errors=True)
    build_ffmpeg(platform, out)
    wrapper = out / "bin" / "headless-browser"
    wrapper.write_text(HEADLESS_BROWSER, encoding="utf-8")
    wrapper.chmod(0o755)


def copy_licenses(platform: str, out: Path) -> None:
    """The license text of each program sits next to it. Git (GPL) and FFmpeg (LGPL) require it to travel with the binaries."""
    wanted = {
        "node": (PINS["node"][platform], "LICENSE", "LICENSE"),
        "git": (PINS["git"], "COPYING", "LICENSE-GPL-2.0.txt"),
        "tools": (PINS["ffmpeg"], "COPYING.LGPLv2.1", "LICENSE-LGPL-2.1.txt"),
    }
    for folder, (pin, member, name) in wanted.items():
        if not (out / folder).exists():
            continue
        archive = fetch(pin["file"], pin["url"], pin["sha256"])
        with tarfile.open(archive) as bundle:
            found = next(item for item in bundle.getmembers() if item.isfile() and item.name.split("/", 1)[-1] == member)
            data = bundle.extractfile(found)
            assert data is not None
            (out / folder / name).write_bytes(data.read())
    log("license texts copied")


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


def retarget_sharp(web: Path, platform: str) -> None:
    """`next build` on this Mac installs the image library `sharp` for this Mac's CPU only. For the other CPU, swap in the matching
    prebuilt packages from the npm registry (same versions, checked against the registry's own sha512), so the Intel app does not ship
    arm64-only code and the audit passes. Layout (pnpm): sharp/node_modules/@img/sharp-darwin-<cpu> -> the CPU package, whose own
    node_modules/@img/sharp-libvips-darwin-<cpu> -> the libvips package."""
    want = "x64" if platform.endswith("x64") else "arm64"
    have = "arm64" if want == "x64" else "x64"
    store = web / "node_modules/.pnpm"
    versions: dict[str, str] = {}
    for package in ("sharp-darwin", "sharp-libvips-darwin"):
        for old in store.glob(f"@img+{package}-{have}@*"):
            version = old.name.rsplit("@", 1)[1]
            versions[package] = version
            name = f"{package}-{want}"
            with urllib.request.urlopen(urllib.request.Request(f"https://registry.npmjs.org/@img%2f{name}/{version}", headers={"User-Agent": "nexus-runtime-build"})) as response:
                dist = json.load(response)["dist"]
            tarball = CACHE / f"{name}-{version}.tgz"
            if not tarball.exists():
                log(f"download {tarball.name}")
                CACHE.mkdir(parents=True, exist_ok=True)
                with urllib.request.urlopen(urllib.request.Request(dist["tarball"], headers={"User-Agent": "nexus-runtime-build"})) as response, tarball.open("wb") as handle:
                    shutil.copyfileobj(response, handle)
            algorithm, _, expected = dist["integrity"].partition("-")
            if algorithm != "sha512" or base64.b64encode(hashlib.sha512(tarball.read_bytes()).digest()).decode() != expected:
                tarball.unlink()
                raise SystemExit(f"{tarball.name}: does not match the registry's {dist['integrity'][:30]}...")
            unpacked = store / f".unpack-{name}"
            shutil.rmtree(unpacked, ignore_errors=True)
            extract_tar(tarball, unpacked)
            target = store / f"@img+{name}@{version}/node_modules/@img" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(unpacked / "package"), target)
            shutil.rmtree(unpacked)
            shutil.rmtree(old)
    if not versions:
        return
    for sharp in store.glob("sharp@*/node_modules/@img"):
        (sharp / f"sharp-darwin-{have}").unlink(missing_ok=True)
        (sharp / f"sharp-darwin-{want}").symlink_to(f"../../../@img+sharp-darwin-{want}@{versions['sharp-darwin']}/node_modules/@img/sharp-darwin-{want}")
    cpu_links = store / f"@img+sharp-darwin-{want}@{versions['sharp-darwin']}/node_modules/@img"
    (cpu_links / f"sharp-libvips-darwin-{want}").symlink_to(f"../../../@img+sharp-libvips-darwin-{want}@{versions['sharp-libvips-darwin']}/node_modules/@img/sharp-libvips-darwin-{want}")


def build_web(platform: str, out: Path) -> None:
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
    retarget_sharp(out, platform)


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
        "node": lambda: build_node(platform, out / "node"),
        "git": lambda: build_git(platform, out / "git"),
        "tools": lambda: build_tools(platform, out / "tools"),
        "backend": lambda: build_backend(out / "backend"),
        "web": lambda: build_web(platform, out / "web"),
        "licenses": lambda: copy_licenses(platform, out),
    }
    for name, step in steps.items():
        if not only or name in only:
            step()
    (out / "manifest.json").write_text(json.dumps({"platform": platform, "pins": PINS}, indent=2), encoding="utf-8")
    log(f"done: {out}")


if __name__ == "__main__":
    main()
