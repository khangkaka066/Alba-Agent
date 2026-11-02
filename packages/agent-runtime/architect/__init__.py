"""Natural-language workflow and teammate generation."""

from .team_generator import (
    ArchitectWorkspaceContext,
    MetaArchitectService,
    ToolDescriptor,
    KnowledgeBaseDescriptor,
    VerifiedCapsuleDescriptor,
)

__all__ = [
    "ArchitectWorkspaceContext", "MetaArchitectService", "ToolDescriptor",
    "KnowledgeBaseDescriptor", "VerifiedCapsuleDescriptor",
]
