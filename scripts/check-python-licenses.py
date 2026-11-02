"""Reject restrictive copyleft and proprietary-restricted Python dependencies.

Undeclared and non-copyleft licenses are surfaced for the consolidated notice
inventory, but only explicit copyleft/proprietary-restricted identifiers or
known restricted product terms block the image, per the repository license
policy.
"""

from __future__ import annotations

import re
import sys
from importlib.metadata import distributions

ALLOWED = {
    "MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "0BSD", "ISC",
    "Zlib", "Unlicense", "CC0-1.0", "CC-BY-3.0", "CC-BY-4.0",
    "BlueOak-1.0.0", "Python-2.0", "Artistic-2.0", "MPL-2.0",
}
DENIED = re.compile(r"^(?:AGPL|GPL|SSPL|BUSL)(?:-|$)", re.IGNORECASE)
RESTRICTIVE_NAME = re.compile(
    r"(?:^|[\s:/])(?:dify|langgenius)(?:$|[\s:/])|"
    r"business source license|proprietary license",
    re.IGNORECASE,
)
CLASSIFIER_MAP = {
    "mit license": "MIT",
    "apache software license": "Apache-2.0",
    "bsd license": "BSD-3-Clause",
    "python software foundation license": "Python-2.0",
    "python software foundation license version 2": "Python-2.0",
    "isc license (iscl)": "ISC",
    "zlib/libpng license": "Zlib",
    "mozilla public license 2.0 (mpl 2.0)": "MPL-2.0",
}


def license_ids(distribution: object) -> tuple[str, ...]:
    metadata = distribution.metadata  # type: ignore[attr-defined]
    expression = metadata.get("License-Expression")
    if not expression:
        raw_license = metadata.get("License") or ""
        expression = raw_license if len(raw_license) <= 200 else ""
    if expression and expression.strip().casefold() not in ("unknown", "none"):
        values = re.findall(r"[A-Za-z0-9.+-]+", expression)
        identifiers = tuple(value for value in values if value not in {"AND", "OR", "WITH"})
        if identifiers:
            return identifiers

    classifiers = metadata.get_all("Classifier") or []
    for classifier in classifiers:
        if classifier.startswith("License :: OSI Approved :: "):
            label = classifier.rsplit(" :: ", 1)[-1].strip().casefold()
            mapped = CLASSIFIER_MAP.get(label)
            if mapped:
                return (mapped,)
            if "gnu general public license" in label:
                return ("GPL-classifier",)
            if "gnu affero general public license" in label:
                return ("AGPL-classifier",)
            if "mozilla public license 2.0" in label:
                return ("MPL-2.0",)
            if "bsd license" in label:
                return ("BSD-3-Clause",)
    return ()


def main() -> int:
    failures: list[str] = []
    found = 0
    for distribution in distributions():
        name = distribution.metadata.get("Name")
        version = distribution.version
        if not name or not version:
            continue
        found += 1
        declared = license_ids(distribution)
        expression = distribution.metadata.get("License-Expression") or ""
        raw = expression or distribution.metadata.get("License") or ""
        explicit_denial = any(DENIED.match(identifier) for identifier in declared)
        explicit_restricted = bool(RESTRICTIVE_NAME.search(f"{name} {raw[:512]}"))
        if explicit_denial or explicit_restricted:
            failures.append(f"{name}=={version}: {raw or ', '.join(declared)}")
    if failures:
        print(f"Python license check failed for {len(failures)} of {found} distributions:", file=sys.stderr)
        for failure in sorted(failures):
            print(f"- {failure}", file=sys.stderr)
        return 1
    print(f"Python license check passed for {found} installed distributions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
