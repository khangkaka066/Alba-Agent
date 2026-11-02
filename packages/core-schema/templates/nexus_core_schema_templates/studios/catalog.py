"""Seed studio blueprints and prompt-based studio detection."""

from __future__ import annotations

import re

from .blueprint import StudioBlueprint
from .film import FILM_STUDIO
from .analytics import ANALYTICS_STUDIO
from .game import GAME_STUDIO
from .marketing import MARKETING_STUDIO
from .software import SOFTWARE_FACTORY
from .video import VIDEO_STUDIO

STUDIO_BLUEPRINTS: tuple[StudioBlueprint, ...] = (GAME_STUDIO, VIDEO_STUDIO, FILM_STUDIO, MARKETING_STUDIO, ANALYTICS_STUDIO, SOFTWARE_FACTORY)
STUDIO_BY_ID = {blueprint.id: blueprint for blueprint in STUDIO_BLUEPRINTS}

# Each domain scores weighted pattern matches. A bare "film" or "phim" is ambiguous (a campaign video or a feature), so it only
# counts once; words that name a feature production count twice and outweigh video vocabulary such as "trailer".
_PATTERNS: tuple[tuple[str, tuple[tuple[str, int], ...]], ...] = (
    (GAME_STUDIO.id, ((r"\b(game|gameplay|platformer|rpg|roguelike|puzzle|phaser|godot|unity|trò chơi)\b", 1),)),
    (VIDEO_STUDIO.id, ((r"\b(video|documentary|campaign|trailer|storyboard|cinematic|clip|quảng cáo)\b", 1),)),
    (FILM_STUDIO.id, (
        (r"\b(film|phim)\b", 1),
        (r"\b(movie|feature film|short film|tv series|web series|screenplay|film studio|phim điện ảnh|phim truyện|phim ngắn|xưởng phim|điện ảnh|bộ phim|kịch bản phim)\b", 2),
    )),
    (SOFTWARE_FACTORY.id, ((r"\b(app|saas|website|web app|platform|api|backend|frontend|software|dashboard|ứng dụng|phần mềm)\b", 1),)),
    (MARKETING_STUDIO.id, ((r"\b(marketing|advertis\w*|promot\w*|social media|go-to-market|quảng bá|truyền thông|chiến dịch)\b", 2),)),
    (ANALYTICS_STUDIO.id, ((r"\b(analytics|kpis?|a/b tests?|conversion rates?|funnel analysis|performance report|báo cáo hiệu suất|phân tích hiệu quả|tối ưu hóa)\b", 2),)),
)
_BUILD = r"\b(build|create|develop|make|produce|ship|tạo|xây dựng|làm|sản xuất)\b"


def detect_studio(prompt: str) -> StudioBlueprint | None:
    """Return the studio whose domain the prompt asks to build, or None for small or ambiguous requests."""
    if not re.search(_BUILD, prompt, re.IGNORECASE):
        return None
    best_id, best_score = "", 0
    for blueprint_id, weighted in _PATTERNS:  # a tie keeps the earlier domain, so "documentary film" stays a video
        score = sum(weight * len(re.findall(pattern, prompt, re.IGNORECASE)) for pattern, weight in weighted)
        if score > best_score:
            best_id, best_score = blueprint_id, score
    return STUDIO_BY_ID[best_id] if best_score else None
