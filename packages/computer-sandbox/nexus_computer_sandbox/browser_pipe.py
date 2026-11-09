"""Runs inside the isolated computer: JSON-line transport to Chromium's private CDP pipe."""
from __future__ import annotations

import fcntl
import os
import select
import subprocess
import sys


def main() -> None:
    executable, profile = sys.argv[1:3]
    first = os.pipe()
    second = os.pipe()
    cr, cw, rr, rw = (fcntl.fcntl(fd, fcntl.F_DUPFD_CLOEXEC, 20) for fd in (*first, *second))
    for fd in (*first, *second):
        os.close(fd)
    # Keep 3 and 4 in pass_fds so CPython preserves the descriptors after preexec_fn.
    reserved = [os.open(os.devnull, os.O_RDONLY), os.open(os.devnull, os.O_RDONLY)]
    def descriptors() -> None:
        os.dup2(cr, 3)
        os.dup2(rw, 4)
    process = subprocess.Popen([executable, "--no-proxy-server", "--headless=new", "--no-sandbox", "--disable-dev-shm-usage",
        "--no-first-run", "--use-mock-keychain", "--disable-breakpad", "--disable-crash-reporter", f"--crash-dumps-dir={profile}/crashes", "--disable-background-networking", "--disable-component-update", "--disable-sync", "--metrics-recording-only",
        "--disable-features=MediaRouter,OptimizationHints,AutofillServerCommunication", "--remote-debugging-pipe",
        f"--user-data-dir={profile}", "about:blank"], pass_fds=(3, 4, cr, rw), preexec_fn=descriptors,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=sys.stderr)
    for fd in (cr, rw, *reserved):
        os.close(fd)
    pending = b""
    incoming = b""
    try:
        while process.poll() is None:
            readable, _, _ = select.select([0, rr], [], [], 1)
            if 0 in readable:
                data = os.read(0, 65536)
                if not data:
                    break
                incoming += data
                while b"\n" in incoming:
                    line, incoming = incoming.split(b"\n", 1)
                    os.write(cw, line + b"\0")
            if rr in readable:
                data = os.read(rr, 65536)
                if not data:
                    break
                pending += data
                while b"\0" in pending:
                    line, pending = pending.split(b"\0", 1)
                    sys.stdout.buffer.write(line + b"\n")
                    sys.stdout.buffer.flush()
    finally:
        os.close(cw)
        os.close(rr)
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    main()
