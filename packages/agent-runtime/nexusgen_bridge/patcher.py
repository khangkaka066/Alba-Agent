"""Search-and-replace block parsing, whitespace-tolerant patching, and sandbox script compilation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Sequence


@dataclass(frozen=True)
class PatchBlock:
    filepath: str
    search: str
    replace: str


# ---------------------------------------------------------------------------
# Line-by-line state-machine parser
# ---------------------------------------------------------------------------
# Instead of a single regex (which breaks on content lines identical to
# the ``=======`` separator), we parse line-by-line with an explicit FSM.
#
# Recognised header forms:
#   <<<<<<< SEARCH: filepath          (inline filepath)
#   FILE: filepath                    (preceding-line filepath)
#   # filepath  /  --- filepath       (git-diff-like preceding filepath)
#
# The separator between search-text and replace-text is exactly a line
# consisting of ``=======`` (optionally followed by whitespace).
# The closing marker is a line starting with ``>>>>>>> REPLACE``.

_HEADER_INLINE_RE = re.compile(
    r"^<{7}\s+SEARCH(?::\s*(.+?))?\s*$",
)
_PRECEDING_FILE_RE = re.compile(
    r"^(?:FILE:\s*|#\s*|---\s*|file:\s*)(.+?)\s*$",
)
_SEPARATOR_RE = re.compile(r"^={7}\s*$")
_FOOTER_RE = re.compile(r"^>{7}\s+REPLACE\s*$")


def is_patch_text(text: str) -> bool:
    """Check if *text* contains at least one SEARCH/REPLACE block structure.

    Requires an opening SEARCH header line, a subsequent ======= separator line,
    and a >>>>>>> REPLACE footer line.
    """
    state = 0  # 0: looking for SEARCH, 1: looking for =======, 2: looking for REPLACE
    for line in text.splitlines():
        line_stripped = line.rstrip("\r\n")
        if state == 0:
            if _HEADER_INLINE_RE.match(line_stripped):
                state = 1
        elif state == 1:
            if _SEPARATOR_RE.match(line_stripped):
                state = 2
            elif _HEADER_INLINE_RE.match(line_stripped):
                state = 1
        elif state == 2:
            if _FOOTER_RE.match(line_stripped):
                return True
            elif _HEADER_INLINE_RE.match(line_stripped):
                state = 1
    return False


def _clean_path(raw: str) -> str:
    """Normalise a filepath extracted from a patch header.

    * Strips surrounding quotes, backticks, and whitespace.
    * Rejects absolute paths (leading /) and backslashes.
    * Removes ``a/`` or ``b/`` prefixes from git diffs.
    * Removes a leading ``./`` prefix (proper prefix, not per-character).
    * Rejects paths containing ``..`` components (directory traversal).
    """
    path = raw.strip("`'\" \t\r\n")
    if not path:
        raise ValueError("Patch filepath cannot be empty")
    if path.startswith("/") or PurePosixPath(path).is_absolute():
        raise ValueError(f"Absolute paths are not allowed in patch filepaths: {raw!r}")
    if "\\" in path:
        raise ValueError(f"Backslashes are not allowed in patch filepaths: {raw!r}")
    # Strip git diff a/ b/ prefixes
    if path.startswith("a/") or path.startswith("b/"):
        path = path[2:]
    # Strip leading ./ — removeprefix instead of lstrip to avoid eating
    # leading dots in filenames like ``.gitignore``.
    path = path.removeprefix("./")
    # Defence-in-depth: reject directory traversal
    if ".." in PurePosixPath(path).parts:
        raise ValueError(
            f"Path traversal is not allowed in patch filepaths: {raw!r}"
        )
    return path


def parse_patch_blocks(text: str) -> list[PatchBlock]:
    """Parse all SEARCH/REPLACE blocks from *text*.

    Raises ``ValueError`` if blocks are found but missing target filepaths,
    or if the text contains no valid blocks at all.
    """
    blocks: list[PatchBlock] = []
    lines = text.splitlines(keepends=True)
    idx = 0
    preceding_filepath: str | None = None

    while idx < len(lines):
        line_stripped = lines[idx].rstrip("\r\n")

        # Try to match a preceding-line filepath (e.g. ``FILE: foo.py``)
        m_pre = _PRECEDING_FILE_RE.match(line_stripped)
        if m_pre:
            preceding_filepath = m_pre.group(1)
            idx += 1
            continue

        # Try to match the opening ``<<<<<<< SEARCH`` header
        m_header = _HEADER_INLINE_RE.match(line_stripped)
        if not m_header:
            # Not a patch-related line — reset the preceding filepath
            preceding_filepath = None
            idx += 1
            continue

        inline_filepath = m_header.group(1)
        file_candidate = inline_filepath or preceding_filepath or ""
        filepath = _clean_path(file_candidate) if file_candidate else ""
        if not filepath:
            raise ValueError(
                "SEARCH block is missing a target filepath. "
                "Specify it as `<<<<<<< SEARCH: path/to/file.py` or preceding `FILE: path/to/file.py`."
            )
        idx += 1

        # Collect search lines until the ``=======`` separator
        search_lines: list[str] = []
        found_sep = False
        while idx < len(lines):
            if _SEPARATOR_RE.match(lines[idx].rstrip("\r\n")):
                found_sep = True
                idx += 1
                break
            search_lines.append(lines[idx])
            idx += 1
        if not found_sep:
            raise ValueError(
                f"SEARCH block for {filepath!r} is missing the ======= separator."
            )

        # Collect replace lines until the ``>>>>>>> REPLACE`` footer
        replace_lines: list[str] = []
        found_footer = False
        while idx < len(lines):
            if _FOOTER_RE.match(lines[idx].rstrip("\r\n")):
                found_footer = True
                idx += 1
                break
            replace_lines.append(lines[idx])
            idx += 1
        if not found_footer:
            raise ValueError(
                f"SEARCH block for {filepath!r} is missing the >>>>>>> REPLACE footer."
            )

        blocks.append(PatchBlock(
            filepath=filepath,
            search="".join(search_lines),
            replace="".join(replace_lines),
        ))
        preceding_filepath = None

    if not blocks:
        raise ValueError(
            "No valid <<<<<<< SEARCH ... ======= ... >>>>>>> REPLACE blocks found"
        )
    return blocks


def apply_patch_block(content: str, patch: PatchBlock) -> str:
    """Apply a single patch block to file content.

    Supports:
    1. Exact match.
    2. Normalised line endings (CRLF → LF) with **CRLF preservation**.
    3. Trailing-whitespace-tolerant line matching with CRLF preservation.

    Raises ``ValueError`` if the search block is not found or is ambiguous.
    """
    search = patch.search
    replace = patch.replace

    # Case 0: Empty search block on empty/new content → full replace
    if not search and not content:
        return replace

    # Detect whether the original file uses CRLF line endings
    has_crlf = "\r\n" in content

    # Case 1: Exact match
    count = content.count(search)
    if count == 1:
        rep = replace
        if has_crlf and "\r\n" not in rep:
            rep = rep.replace("\n", "\r\n")
        return content.replace(search, rep, 1)
    if count > 1:
        raise ValueError(
            f"SEARCH block found {count} times in {patch.filepath}. "
            "Please include more surrounding context lines to make the match unique."
        )

    # Case 2: Line endings normalisation (CRLF ↔ LF)
    norm_content = content.replace("\r\n", "\n")
    norm_search = search.replace("\r\n", "\n")
    norm_replace = replace.replace("\r\n", "\n")

    count = norm_content.count(norm_search)
    if count == 1:
        result = norm_content.replace(norm_search, norm_replace, 1)
        if has_crlf:
            result = result.replace("\n", "\r\n")
        return result
    if count > 1:
        raise ValueError(
            f"SEARCH block found {count} times in {patch.filepath} after normalizing newlines. "
            "Please include more surrounding context lines to make the match unique."
        )

    # Case 3: Trailing whitespace tolerance on lines
    content_lines = norm_content.splitlines(keepends=True)
    search_lines = norm_search.splitlines(keepends=True)

    if not search_lines:
        raise ValueError(f"Empty SEARCH block cannot be matched in non-empty file {patch.filepath}")

    search_stripped = [line.rstrip() for line in search_lines]
    search_len = len(search_lines)

    matched_indices: list[int] = []
    for i in range(len(content_lines) - search_len + 1):
        window = [line.rstrip() for line in content_lines[i : i + search_len]]
        if window == search_stripped:
            matched_indices.append(i)

    if len(matched_indices) == 1:
        idx = matched_indices[0]
        new_lines = content_lines[:idx] + [norm_replace] + content_lines[idx + search_len :]
        result = "".join(new_lines)
        if has_crlf:
            result = result.replace("\n", "\r\n")
        return result
    elif len(matched_indices) > 1:
        raise ValueError(
            f"SEARCH block found {len(matched_indices)} times in {patch.filepath} (ignoring trailing whitespace). "
            "Please include more surrounding context lines to make the match unique."
        )

    raise ValueError(
        f"SEARCH block not found in {patch.filepath}. "
        "Make sure the search block matches the current file contents and indentation."
    )


def compile_patch_script(patches: Sequence[PatchBlock]) -> str:
    """Compile patch blocks into a self-contained Python script to run inside the sandbox container.

    Preserves exact newline format (CRLF / LF) on disk using `open(..., newline='')`.
    """
    import json
    data = [
        {"filepath": p.filepath, "search": p.search, "replace": p.replace}
        for p in patches
    ]
    serialized = json.dumps(data)

    return f'''# Auto-generated by NexusAgent Diff Engine
import json
import sys
from pathlib import Path

PATCHES = {serialized}

def apply_patch(content: str, filepath: str, search: str, replace: str) -> str:
    if not search and not content:
        return replace

    has_crlf = "\\r\\n" in content

    # Case 1: Exact match
    count = content.count(search)
    if count == 1:
        rep = replace
        if has_crlf and "\\r\\n" not in rep:
            rep = rep.replace("\\n", "\\r\\n")
        return content.replace(search, rep, 1)
    if count > 1:
        raise ValueError(f"SEARCH block found {{count}} times in {{filepath}}. Add more context.")

    # Case 2: Line endings normalisation (CRLF <-> LF)
    norm_c = content.replace("\\r\\n", "\\n")
    norm_s = search.replace("\\r\\n", "\\n")
    norm_r = replace.replace("\\r\\n", "\\n")
    count = norm_c.count(norm_s)
    if count == 1:
        result = norm_c.replace(norm_s, norm_r, 1)
        if has_crlf:
            result = result.replace("\\n", "\\r\\n")
        return result
    if count > 1:
        raise ValueError(f"SEARCH block found {{count}} times in {{filepath}} after normalizing newlines. Add more context.")

    # Case 3: Whitespace tolerance
    c_lines = norm_c.splitlines(keepends=True)
    s_lines = norm_s.splitlines(keepends=True)
    s_stripped = [l.rstrip() for l in s_lines]
    s_len = len(s_lines)

    matches = [i for i in range(len(c_lines) - s_len + 1) if [l.rstrip() for l in c_lines[i:i+s_len]] == s_stripped]
    if len(matches) == 1:
        idx = matches[0]
        result = "".join(c_lines[:idx] + [norm_r] + c_lines[idx+s_len:])
        if has_crlf:
            result = result.replace("\\n", "\\r\\n")
        return result
    if len(matches) > 1:
        raise ValueError(f"SEARCH block found {{len(matches)}} times in {{filepath}} (whitespace-tolerant). Add more context.")

    raise ValueError(f"SEARCH block not found in {{filepath}}. Check indentation and existing code.")

applied_files = []
for p in PATCHES:
    target = Path(p["filepath"])
    if not target.exists():
        if not p["search"]:
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "w", encoding="utf-8", newline="") as f:
                f.write(p["replace"])
            applied_files.append(p["filepath"])
            continue
        raise FileNotFoundError(f"Cannot patch missing file: {{p['filepath']}}")
    with open(target, "r", encoding="utf-8", newline="") as f:
        old_content = f.read()
    new_content = apply_patch(old_content, p["filepath"], p["search"], p["replace"])
    with open(target, "w", encoding="utf-8", newline="") as f:
        f.write(new_content)
    applied_files.append(p["filepath"])

print(f"Successfully applied patches to: {{', '.join(applied_files)}}")
'''
