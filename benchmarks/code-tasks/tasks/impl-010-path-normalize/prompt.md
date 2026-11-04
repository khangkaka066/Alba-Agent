Implement `normalize_path` and `join_paths` in `paths.py`. They work on POSIX-style strings only (separator `/`) and never touch the filesystem.

`normalize_path(path: str) -> str`
- Collapse runs of `/` into one, drop `.` segments, and resolve `..` segments lexically (a `..` removes the previous real segment).
- An absolute path (starts with `/`) stays absolute. A `..` that would go above the root is dropped: `"/../a"` -> `"/a"`. A path made only of root is `"/"` (also for `"//"`, `"/."`, `"/a/.."`).
- A relative path stays relative. Leading `..` segments that cannot be resolved are kept: `"../../a"` -> `"../../a"`, `"a/../../b"` -> `"../b"`. A relative path that reduces to nothing is `"."` (also for the empty string).
- No trailing slash in the result, except the root `"/"`.
- Segments are otherwise opaque: `"..."` and `".config"` are ordinary names, and the result is case-preserved.

`join_paths(base: str, *parts: str) -> str`
- Joins `base` and each part in order with `/` and returns the normalized result. If a part is absolute (starts with `/`), everything before it is discarded and joining restarts from that part. Empty parts are ignored. `join_paths("")` is `"."`.
- Examples: `join_paths("/a/b", "../c", "d.txt")` -> `"/a/c/d.txt"`, `join_paths("a", "/x", "y")` -> `"/x/y"`.
