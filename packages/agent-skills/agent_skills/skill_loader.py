"""Progressive skill catalog and explicit task matching."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .spec import SkillSpec


class SkillLoader:
    def __init__(self, directories: Iterable[Path] = ()) -> None:
        root = Path(__file__).resolve().parents[1] / "catalog"
        self._directories = (root, *tuple(directories))
        self._skills: dict[str, SkillSpec] = {}
        self.reload()

    def reload(self) -> None:
        loaded: dict[str, SkillSpec] = {}
        for directory in self._directories:
            if directory.exists():
                for path in sorted(directory.glob("*.md")):
                    skill = SkillSpec.from_file(path)
                    # Later directories are workspace overrides of packaged defaults.
                    loaded[skill.slug] = skill
        self._skills = loaded

    def catalog(self) -> tuple[dict[str, str], ...]:
        """Return metadata only: no SOP body is included in default prompts."""
        return tuple(skill.summary() for skill in self._skills.values())

    def get(self, slug: str) -> SkillSpec:
        try:
            return self._skills[slug]
        except KeyError as error:
            raise LookupError(f"Skill is not available: {slug}") from error

    def match(self, task: str, *, limit: int = 3) -> tuple[SkillSpec, ...]:
        if limit < 1:
            return ()
        tokens = set(task.lower().replace("/", " ").replace("-", " ").split())
        ranked: list[tuple[int, SkillSpec]] = []
        for skill in self._skills.values():
            terms = set(skill.trigger_keywords) | {skill.slug.replace("-", " "), skill.name.lower()}
            score = sum(1 for term in terms if term.lower() in task.lower() or set(term.lower().split()) <= tokens)
            if score:
                ranked.append((score, skill))
        ranked.sort(key=lambda item: (-item[0], item[1].slug))
        return tuple(skill for _, skill in ranked[:limit])

    def instructions_for(self, slugs: Iterable[str] = (), *, task: str | None = None) -> str:
        chosen: dict[str, SkillSpec] = {slug: self.get(slug) for slug in slugs}
        if task:
            chosen.update({skill.slug: skill for skill in self.match(task)})
        return "\n\n".join(f"## Skill: {skill.name}\n\n{skill.body}" for skill in chosen.values())

    def inject(self, prompt: str, *, assigned: Iterable[str] = (), task: str | None = None) -> str:
        """Append only explicitly assigned or task-matched bodies to an agent prompt."""
        instructions = self.instructions_for(assigned, task=task)
        return prompt if not instructions else prompt.rstrip() + "\n\nAssigned skills:\n" + instructions

    def promote_capsule(self, slug: str, capsule: object, *, tis: float, minimum_tis: float = 0.15) -> SkillSpec:
        """Append verified, high-impact sanitized heuristics to a workspace skill file."""
        scope = str(getattr(capsule, "propagation_scope", ""))
        if scope not in {"WORKSPACE_VERIFIED", "PropagationScope.WORKSPACE_VERIFIED"}:
            raise PermissionError("Only workspace-verified capsules can be promoted")
        if tis < minimum_tis:
            raise ValueError("Capsule transfer impact is below the promotion threshold")
        skill = self.get(slug)
        heuristic = str(getattr(capsule, "distilled_heuristic", "")).strip()
        if not heuristic or len(heuristic) > 8000:
            raise ValueError("Capsule heuristic is empty or too large")
        directory = Path(self._directories[1]) if len(self._directories) > 1 else Path.cwd() / "custom-skills"
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{slug}.md"
        original = target.read_text(encoding="utf-8") if target.exists() else skill.to_markdown()
        section = "## Learned Best Practices & Edge Cases"
        addition = f"\n\n### Verified capsule (TIS {tis:.3f})\n\n{heuristic}"
        if section in original:
            updated = original.rstrip() + addition + "\n"
        else:
            updated = original.rstrip() + "\n\n" + section + addition + "\n"
        target.write_text(updated, encoding="utf-8")
        self.reload()
        return self.get(slug)
