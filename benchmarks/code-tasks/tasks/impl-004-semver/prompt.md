Implement `compare_versions`, `sort_versions` and `bump_version` in `semver.py`.

Version syntax: `[v]MAJOR.MINOR.PATCH[-PRERELEASE][+BUILD]`
- An optional single leading lowercase `v` is allowed.
- MAJOR, MINOR, PATCH are non-negative decimal integers without leading zeros (`0` is fine, `01` is not).
- PRERELEASE is one or more dot-separated identifiers; each identifier is non-empty and made of `[0-9A-Za-z-]`. A purely numeric identifier must not have leading zeros.
- BUILD is one or more dot-separated non-empty identifiers of `[0-9A-Za-z-]` (leading zeros allowed).
- Anything else (missing parts like `1.2`, extra parts, spaces, empty identifiers like `1.0.0-`, `1.0.0-a..b`) raises `ValueError`.

`compare_versions(a: str, b: str) -> int` returns `-1`, `0` or `1` using semantic-versioning precedence:
1. Compare MAJOR, then MINOR, then PATCH numerically.
2. If those are equal, a version with a PRERELEASE is lower than one without: `1.0.0-rc.1 < 1.0.0`.
3. If both have a PRERELEASE, compare identifiers left to right: numeric identifiers compare numerically; alphanumeric identifiers compare by plain ASCII string order; a numeric identifier is always lower than an alphanumeric one; if all shared identifiers are equal, the version with fewer identifiers is lower (`1.0.0-alpha < 1.0.0-alpha.1`).
4. BUILD metadata and the optional `v` prefix are ignored: `1.0.0+x` and `v1.0.0` compare equal to `1.0.0` (result `0`).
Either argument being invalid raises `ValueError`.

`sort_versions(versions: list[str]) -> list[str]` returns a new list in ascending precedence order, containing the original strings unchanged (including any `v` prefix or build metadata). The sort is stable: versions that compare equal keep their input order. Raises `ValueError` if any entry is invalid. Does not modify the input list.

`bump_version(version: str, part: str) -> str` returns the next version as a string, without a `v` prefix, without PRERELEASE and without BUILD:
- `part == "major"`: MAJOR + 1, MINOR = 0, PATCH = 0
- `part == "minor"`: MINOR + 1, PATCH = 0
- `part == "patch"`: PATCH + 1
The chosen number is always incremented, even if the input had a PRERELEASE (`"1.2.3-rc.1"`, `"patch"` -> `"1.2.4"`). Raises `ValueError` for an invalid version or any other `part`.
