"""Validated SKILL.md documents with a deliberately small frontmatter contract."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, cast

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, field_validator


class SkillSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    category: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=1000)
    trigger_keywords: tuple[str, ...] = ()
    required_tools: tuple[str, ...] = ()
    required_builtin_tools: tuple[str, ...] = ()
    recommended_models: tuple[str, ...] = ()
    body: str = Field(min_length=1)

    @field_validator("body")
    @classmethod
    def meaningful_body(cls, value: str) -> str:
        if len(value.strip()) < 40:
            raise ValueError("Skill instructions must contain at least 40 characters")
        return value.strip()

    @classmethod
    def from_markdown(cls, source: str) -> "SkillSpec":
        match = re.match(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", source, re.S)
        if match is None:
            raise ValueError("SKILL.md must begin with YAML frontmatter delimited by ---")
        metadata: Any = yaml.safe_load(match.group(1))
        if not isinstance(metadata, dict):
            raise ValueError("Skill frontmatter must be a YAML mapping")
        return cls.model_validate({**metadata, "body": match.group(2)})

    @classmethod
    def from_file(cls, path: str | Path) -> "SkillSpec":
        return cls.from_markdown(Path(path).read_text(encoding="utf-8"))

    def to_markdown(self) -> str:
        header = self.model_dump(exclude={"body"}, mode="json")
        frontmatter = cast(str, yaml.safe_dump(header, sort_keys=False, allow_unicode=True))
        return "---\n" + frontmatter.rstrip() + "\n---\n\n" + self.body + "\n"

    def summary(self) -> dict[str, str]:
        return {"name": self.name, "slug": self.slug, "category": self.category, "description": self.description}
