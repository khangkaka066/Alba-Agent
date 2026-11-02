"""Three-tier studio blueprints (game, video, software) and their graph builder."""

from .blueprint import StudioBlueprint, StudioDepartment, StudioGraph, StudioRole, build_studio_graph
from .catalog import STUDIO_BLUEPRINTS, STUDIO_BY_ID, detect_studio

__all__ = [
    "STUDIO_BLUEPRINTS", "STUDIO_BY_ID", "StudioBlueprint", "StudioDepartment", "StudioGraph", "StudioRole",
    "build_studio_graph", "detect_studio",
]
