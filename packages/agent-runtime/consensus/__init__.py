"""Provider-agnostic adversarial consensus orchestration and breadth-depth refinement."""

from .breadth_depth_refiner import (
    BreadthDepthRefiner,
    Corrector,
    Critic,
    Critique,
    DepthRecord,
    Generator,
    MissingCritiqueError,
    RefinementResult,
    RefinerConfig,
    plurality_vote,
    planned_model_calls,
)
from .diversity import CENTERED_TAU, ClusterStats, DirectionAnalysis, agglomerative_clusters, analyze_directions, center, cluster_stats, cosine, redundant_pairs, remove_direction
from .embedders import Embedder, EmbedderUnavailableError, LexicalEmbedder, MiniLMOnnxEmbedder, OnnxSentenceEmbedder
from .engine import ConsensusEngine, ConsensusResult, ModelDraft

__all__ = [
    "BreadthDepthRefiner", "CENTERED_TAU", "ClusterStats", "DirectionAnalysis", "ConsensusEngine", "ConsensusResult", "Corrector", "Critic", "Critique", "DepthRecord",
    "Embedder", "EmbedderUnavailableError", "Generator", "LexicalEmbedder", "MiniLMOnnxEmbedder", "MissingCritiqueError", "ModelDraft", "OnnxSentenceEmbedder",
    "RefinementResult", "RefinerConfig", "agglomerative_clusters", "analyze_directions", "center", "cluster_stats", "cosine", "planned_model_calls", "plurality_vote",
    "redundant_pairs", "remove_direction",
]
