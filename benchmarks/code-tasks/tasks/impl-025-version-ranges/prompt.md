Our plugin loader must decide whether an installed plugin version fits the range a manifest asks for. Implement the functions in `vranges.py`. Versions are plain `MAJOR.MINOR.PATCH` strings; there are no pre-release or build suffixes.

**`parse_version(text) -> tuple[int, int, int]`**: exactly three dot-separated parts, each one or more ASCII digits (leading zeros are allowed and ignored, so `"1.02.3"` is `(1, 2, 3)`). Anything else (`"1.2"`, `"1.2.3.4"`, `"v1.2.3"`, `"1.2.x"`, `"1.2.3-beta"`, spaces, an empty string) raises `ValueError`. Versions compare numerically as tuples, so `1.10.0` is greater than `1.9.0`.

**Range syntax** (`spec`): one or more alternatives separated by `||`; a version satisfies the spec if it satisfies **any** alternative. An alternative is one or more clauses separated by `,`; a version satisfies the alternative if it satisfies **all** its clauses. Whitespace around clauses, around `||` and between an operator and its version is ignored. A clause is one of:
- `*`: matches every version.
- `>=V`, `<=V`, `>V`, `<V`, `==V`, `=V`, `!=V`: the usual comparisons (`==` and `=` mean equality).
- `V` with no operator: equality.
- `~V`: at least `V` and below the next minor, i.e. `~1.2.3` means `>=1.2.3,<1.3.0`.
- `^V` with `V = X.Y.Z`: at least `V` and below the next "breaking" version: `^1.2.3` means `>=1.2.3,<2.0.0`; if `X` is 0 it means `>=0.Y.Z,<0.(Y+1).0` (so `^0.2.3` is `>=0.2.3,<0.3.0`); if `X` and `Y` are both 0 it means `>=0.0.Z,<0.0.(Z+1)` (so `^0.0.3` matches only `0.0.3`).

An empty spec, an empty alternative or clause (`">=1.0.0,"`, `"||"`), an unknown operator or a malformed version inside a clause raises `ValueError`. The **whole** spec is validated before anything is evaluated, so an invalid spec raises even if an earlier alternative would already match.

**`satisfies(version, spec) -> bool`**: parses `version` (malformed -> `ValueError`) and applies the rules above.

**`max_satisfying(versions, spec) -> str | None`**: the highest version among the strings in `versions` that satisfies `spec`, returned exactly as written in the input; `None` if none satisfies. If two entries are numerically equal (e.g. `"1.2.3"` and `"1.02.3"`) the one appearing first wins. A malformed entry in `versions` raises `ValueError`, and so does an invalid `spec` (even when `versions` is empty).
