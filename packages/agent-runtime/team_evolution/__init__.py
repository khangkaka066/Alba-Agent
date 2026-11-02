"""Autonomous team topology evolution: diagnose, mutate, adapt mid-run, score and roll back."""

from .bottleneck_analyzer import BottleneckAnalyzer
from .dynamic_spawner import TOOL_ID as DYNAMIC_TEAM_TOOL_ID
from .dynamic_spawner import DynamicSpawner, DynamicSpawnRequest, DynamicTeamMutatorTool, SpawnRecord
from .fitness_tracker import (
    FitnessTracker,
    GenerationStats,
    RollbackDecision,
    RunMetrics,
    aggregate,
    extract_run_metrics,
    product_fitness,
)
from .models import (
    BottleneckKind,
    BottleneckReport,
    Diagnosis,
    HumanFeedback,
    InjectQuality,
    MutationOp,
    OpKind,
    PruneOrMerge,
    RewireParallel,
    RunObservation,
    SpawnSpecialist,
    SplitOverloaded,
    TopologyDiff,
)
from .planner import EvolutionPlan, plan_operations
from .topology_mutator import MutationError, MutationResult, TeamTopologyMutator, diff_specs

__all__ = [
    "BottleneckAnalyzer", "BottleneckKind", "BottleneckReport", "DYNAMIC_TEAM_TOOL_ID", "Diagnosis", "DynamicSpawner",
    "DynamicSpawnRequest", "DynamicTeamMutatorTool", "EvolutionPlan", "FitnessTracker", "GenerationStats", "HumanFeedback",
    "InjectQuality", "MutationError", "MutationOp", "MutationResult", "OpKind", "PruneOrMerge", "RewireParallel",
    "RollbackDecision", "RunMetrics", "RunObservation", "SpawnRecord", "SpawnSpecialist", "SplitOverloaded",
    "TeamTopologyMutator", "TopologyDiff", "aggregate", "diff_specs", "extract_run_metrics", "plan_operations", "product_fitness",
]
