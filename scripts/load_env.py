"""Print `export KEY=value` lines for a dotenv file, quoted for a POSIX shell. A .env value may contain spaces, which `source` cannot read."""

from __future__ import annotations

import shlex
import sys
from pathlib import Path


def main(paths: list[str]) -> None:
    for name in paths:
        for line in Path(name).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]
            print(f"export {key.strip()}={shlex.quote(value)}")


if __name__ == "__main__":
    main(sys.argv[1:] or [".env"])
