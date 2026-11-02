"""Files a team says it wrote: find the claims in its structured output, and the files a task is told to write."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

MAX_CLAIMS = 20
_FILE = re.compile(r"^(?:[A-Za-z0-9][\w.\-]*/){0,7}[A-Za-z0-9][\w.\-]*\.[A-Za-z0-9]{1,5}$")
_KEY = re.compile(r"(?:^|_)(?:files?|filenames?|filepaths?|file_names?|paths?|artifacts?|files_written)$", re.IGNORECASE)
_EXTENSIONS = "md|txt|csv|json|html|srt|pdf|docx|xlsx|png|jpg|jpeg|mp4|mp3|wav"
_WRITES = re.compile(r"\b(?:export|exports|exported|write|writes|save|saves|create|creates|generate|generates|produce|produces|store|stores|output)\b", re.IGNORECASE)
_NAMED = re.compile(r"\b(?:named|called|as|to|into)\s+(?:the\s+|an?\s+)?(?:\w+\s+){0,2}?[`'\"]?((?:[A-Za-z0-9][\w\-]*/){0,3}[A-Za-z0-9][\w\-]*\.(?:" + _EXTENSIONS + r"))\b", re.IGNORECASE)


def looks_like_file(value: object) -> bool:
    """A plain relative file path: no URL, no spaces, no parent or hidden folders."""
    if not isinstance(value, str) or not _FILE.match(value) or "://" in value or ".." in value:
        return False
    return not any(part.startswith(".") for part in value.split("/"))


def claimed_files(outputs: Iterable[Mapping[str, Any]]) -> list[str]:
    """File names a team reported in fields such as `exported_filename`, `report_path` or `files_written`."""
    found: list[str] = []
    for output in outputs:
        for key, value in output.items():
            if not _KEY.search(str(key)):
                continue
            for item in value if isinstance(value, (list, tuple)) else [value]:
                if looks_like_file(item) and item not in found:
                    found.append(str(item))
    return found[:MAX_CLAIMS]


def claim_material(task_outputs: Mapping[str, Mapping[str, Any]], output: Mapping[str, Any]) -> dict[str, Any]:
    """What a claimed document can be rebuilt from: everything the team wrote in words, minus the file names themselves."""
    material: dict[str, Any] = {}
    for source in (*task_outputs.values(), output):
        for key, value in source.items():
            if _KEY.search(str(key)) or key in {"task_outputs", "artifact_contract", "dynamic_team"}:
                continue
            if isinstance(value, str) and value.strip() and key not in material:
                material[str(key)] = value
    return material


def deliverables_in(description: str) -> list[str]:
    """Files a task description tells the agent to write ("export the summary to a file named summary.md").
    A file that is only mentioned as input ("parse squares.md") is not a deliverable."""
    found: list[str] = []
    for sentence in re.split(r"(?<=[.!?\n])\s+", description):
        if not _WRITES.search(sentence):
            continue
        for match in _NAMED.finditer(sentence):
            if looks_like_file(match.group(1)) and match.group(1) not in found:
                found.append(match.group(1))
    return found[:5]
