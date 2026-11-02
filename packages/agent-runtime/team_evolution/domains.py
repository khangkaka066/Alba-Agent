"""Product-domain knowledge used to name the specialist a failing team is missing."""

from __future__ import annotations

import re
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from pathlib import PurePosixPath

from agent_skills import SkillLoader

CODE_SUFFIXES = frozenset({".py", ".js", ".mjs", ".ts", ".tsx", ".gd", ".cs", ".sql", ".sh", ".html", ".css", ".tscn", ".tres"})
MEDIA_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".mov", ".webm", ".mp3", ".wav", ".srt", ".vtt", ".zip"})
DOCUMENT_SUFFIXES = frozenset({".md", ".txt", ".json"})


@dataclass(frozen=True)
class Domain:
    key: str
    keywords: tuple[str, ...]
    role: str
    goal: str
    path: str
    tools: tuple[str, ...] = ("report_exporter",)


DOMAINS: tuple[Domain, ...] = (
    Domain("balance", ("balance", "balancing", "difficulty curve", "tuning"), "Level Balance Designer",
           "model difficulty, rewards and progression curves and fix the numbers that make the product unfair or dull",
           "design/balance_report.md", ("chart_generator", "report_exporter")),
    Domain("av_sync", ("subtitle", "audio sync", "ducking", "captions", "lip sync", "audio-subtitle", "timecode"),
           "Audio & Subtitle Sync Specialist", "align narration, music ducking and subtitle timing to the picture and report drift",
           "media/sync_report.md"),
    Domain("migration", ("migration", "migrations", "schema change", "alembic", "backfill"), "Database Migration Engineer",
           "plan and verify reversible schema migrations and data backfills", "design/migrations.md"),
    Domain("security", ("security", "vulnerab", "owasp", "secret leak", "injection"), "Security Reviewer",
           "review the deliverables for exploitable weaknesses and leaked secrets", "qa/security_review.md"),
    Domain("accessibility", ("accessib", "contrast", "screen reader", "keyboard navigation"), "Accessibility Specialist",
           "check contrast, input alternatives and readability against accessibility guidance", "qa/accessibility_review.md"),
    Domain("localization", ("locali", "translation", "string table", "language support"), "Localisation Specialist",
           "prepare string tables and translation notes for every supported language", "narrative/localisation.md"),
    Domain("performance", ("performance", "latency budget", "frame budget", "memory leak", "slow"), "Performance Analyst",
           "measure budgets, find hot spots and propose concrete fixes", "qa/performance_review.md"),
    Domain("diagram", ("diagram", "3d render", "architectural", "illustration", "infographic"), "Technical Diagram Artist",
           "produce precise diagrams and illustrations that explain the subject", "visual/diagrams.md", ("media_generation", "report_exporter")),
    Domain("research", ("citation", "source", "fact check", "fact-check", "unverified", "hallucinat"), "Fact-Checking Researcher",
           "verify claims against sources and attach citations to every factual statement", "story/fact_check.md", ("web_search", "report_exporter")),
    Domain("compliance", ("compliance", "licen", "copyright", "brand rule", "rights"), "Compliance Reviewer",
           "check licences, rights and brand rules for every asset", "qa/compliance_review.md"),
)

TOOL_KEYWORDS: dict[str, tuple[str, ...]] = {
    "web_search": ("web", "search", "research", "news", "source"),
    "web_scraper": ("scrape", "web page", "crawl"),
    "document_parser": ("document", "csv", "pdf", "excel", "parse"),
    "chart_generator": ("chart", "plot", "curve", "graph"),
    "safe_sql": ("sql", "database", "query"),
    "report_exporter": ("report", "document", "export", "write"),
    "media_generation": ("image", "video", "audio", "voice", "illustration", "render", "diagram", "draw"),
    "sandbox_shell": ("ffmpeg", "shell", "command"),
}

SECTION_DIRECTORIES: dict[str, tuple[str, ...]] = {
    "design": ("design",), "narrative": ("narrative", "story"), "art": ("art", "visual", "media"),
    "audio": ("audio", "media"), "qa": ("qa",), "release": ("release",),
}


def suffix_of(path: str) -> str:
    return PurePosixPath(path).suffix.lower()


def is_code_or_media(path: str) -> bool:
    return suffix_of(path) in CODE_SUFFIXES | MEDIA_SUFFIXES


def domain_matches(text: str) -> list[Domain]:
    lowered = text.lower()
    return [domain for domain in DOMAINS if any(keyword in lowered for keyword in domain.keywords)]


def covers(text: str, domain: Domain) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in domain.keywords) or domain.role.lower() in lowered


def uncovered_terms(complaint: str, team_text: str, domain: Domain) -> list[str]:
    """Words of the complaint that name this domain but appear nowhere in the team's roles, goals or tasks."""
    complaint_text, team = complaint.lower(), team_text.lower()
    return [keyword for keyword in domain.keywords if keyword in complaint_text and keyword not in team]


def role_from_path(path: str) -> tuple[str, tuple[str, ...]]:
    """Derive a specialist role and its vocabulary from an unowned artifact path."""
    stem = PurePosixPath(path).stem
    words = [word for word in re.split(r"[^A-Za-z0-9]+", stem) if word]
    title = " ".join(word.capitalize() for word in words) or "Deliverable"
    return f"{title} Specialist", tuple(word.lower() for word in words if len(word) > 2)


def discover_tools(text: str, available: Collection[str] | None, seed: Iterable[str] = ()) -> tuple[str, ...]:
    lowered = text.lower()
    chosen = list(dict.fromkeys(seed))
    chosen += [tool for tool, terms in TOOL_KEYWORDS.items() if any(term in lowered for term in terms)]
    unique = list(dict.fromkeys(chosen))
    return tuple(tool for tool in unique if available is None or tool in available)


def discover_skills(text: str, loader: SkillLoader | None = None, available: Collection[str] | None = None, limit: int = 3) -> tuple[str, ...]:
    """Match Phase 15 skills to the specialist's job description."""
    matches = (loader or SkillLoader()).match(text, limit=limit)
    return tuple(skill.slug for skill in matches if available is None or skill.slug in available)
