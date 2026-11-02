"""`python -m nexus_plugins dump-config` prints the plugin list this process would boot."""

from __future__ import annotations

import sys
from pathlib import Path

from nexus_kernel import build_rows, dump_rows

from . import DEFAULT_PLUGINS


def main(arguments: list[str]) -> int:
    if not arguments or arguments[0] != "dump-config":
        print("usage: python -m nexus_plugins dump-config [--patch FILE ...]", file=sys.stderr)
        return 2
    patches = tuple(Path(arguments[index + 1]) for index, value in enumerate(arguments) if value == "--patch" and index + 1 < len(arguments))
    print(dump_rows(build_rows(DEFAULT_PLUGINS, patches)), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
