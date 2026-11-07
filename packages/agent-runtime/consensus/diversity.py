"""How different a set of reasoning rollouts really is: cosine similarity, average-linkage clusters, entropy.

Follows Appendix A.6 of arXiv:2608.05643 (Bilal et al., 2026): the rollouts' embeddings are grouped by agglomerative clustering with
average linkage and cosine distance, merging while the average distance is at most `1 - tau_sim` (the paper uses tau_sim = 0.85 with
the all-MiniLM-L6-v2 sentence encoder). With cluster masses p_j = |C_j| / N it reports the number of realised clusters R(N),
R(N) / N, the dominant-cluster share f_max(N) and the entropy H(N) = -sum_j p_j log2 p_j. A falling R(N) / N and a slowly growing
H(N) mean the extra samples only repeat directions that were already there ("diversity saturation").

tau_sim = 0.85 is the paper's setting, for full reasoning traces of math problems. On short rollouts of ONE problem it fails: the
shared topic makes every pair about equally similar, so no pair clears 0.85 and every rollout becomes its own cluster (H always
log2 N). `analyze_directions` therefore looks at the rollouts after removing what they share (see `center`), which on hand-labelled
solution approaches raised the adjusted Rand index from 0.00 to about 0.5-0.6 on problems it was not tuned on.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

Vector = Sequence[float]

PAPER_TAU_SIM = 0.85


def cosine(left: Vector, right: Vector) -> float:
    """Cosine similarity; 0.0 when either vector is all zeros (no direction to compare)."""
    if len(left) != len(right):
        raise ValueError("Vectors must have the same dimension")
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norm = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    return 0.0 if norm == 0 else max(-1.0, min(1.0, dot / norm))


@dataclass(frozen=True)
class Merge:
    """One step of average-linkage clustering: two groups joined at an average cosine distance."""

    left: tuple[int, ...]
    right: tuple[int, ...]
    distance: float


def dendrogram(vectors: Sequence[Vector]) -> list[Merge]:
    """The full average-linkage merge sequence (cosine distance), closest groups first; ties go to the lowest indices."""
    count = len(vectors)
    distance = [[1.0 - cosine(vectors[i], vectors[j]) for j in range(count)] for i in range(count)]
    clusters: list[list[int]] = [[index] for index in range(count)]
    merges: list[Merge] = []
    while len(clusters) > 1:
        best: tuple[float, int, int] | None = None
        for a in range(len(clusters)):
            for b in range(a + 1, len(clusters)):
                average = sum(distance[i][j] for i in clusters[a] for j in clusters[b]) / (len(clusters[a]) * len(clusters[b]))
                if best is None or average < best[0] - 1e-12:
                    best = (average, a, b)
        assert best is not None
        average, a, b = best
        merges.append(Merge(tuple(clusters[a]), tuple(clusters[b]), average))
        clusters[a] = sorted(clusters[a] + clusters[b])
        del clusters[b]
    return merges


def _apply(count: int, merges: Sequence[Merge]) -> list[list[int]]:
    groups: dict[int, list[int]] = {index: [index] for index in range(count)}
    owner = {index: index for index in range(count)}
    for merge in merges:
        keep, drop = owner[merge.left[0]], owner[merge.right[0]]
        groups[keep] = sorted(groups[keep] + groups[drop])
        for member in groups[drop]:
            owner[member] = keep
        del groups[drop]
    return sorted(groups.values(), key=lambda members: members[0])


def cut_at_similarity(count: int, merges: Sequence[Merge], tau_sim: float = PAPER_TAU_SIM) -> list[list[int]]:
    """Apply the merges while their average distance stays at most `1 - tau_sim`."""
    if not -1 <= tau_sim <= 1:
        raise ValueError("tau_sim must be a cosine value in [-1, 1]")
    limit = 1.0 - tau_sim + 1e-12
    applied: list[Merge] = []
    for merge in merges:
        if merge.distance > limit:
            break
        applied.append(merge)
    return _apply(count, applied)


def agglomerative_clusters(vectors: Sequence[Vector], tau_sim: float = PAPER_TAU_SIM) -> list[list[int]]:
    """Group vector indices; clusters merge while their average pairwise cosine distance is at most `1 - tau_sim`.

    Deterministic: ties go to the pair with the lowest indices. Clusters come back ordered by their first member, members ascending.
    """
    return cut_at_similarity(len(vectors), dendrogram(vectors), tau_sim)


def _unit(vector: Vector) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector] if norm > 1e-12 else [0.0] * len(vector)


def center(vectors: Sequence[Vector], strength: float = 1.0) -> list[list[float]]:
    """Subtract `strength` times the batch mean, then re-normalise.

    Rollouts of ONE problem share its topic, and that shared part dominates their cosine similarity; what tells two solution
    approaches apart is what is left after it is removed. Needs several rollouts: a batch of one has no shared part to find.
    """
    if not vectors:
        return []
    dims = len(vectors[0])
    mean = [sum(vector[d] for vector in vectors) / len(vectors) for d in range(dims)]
    return [_unit([value - strength * m for value, m in zip(vector, mean, strict=True)]) for vector in vectors]


def remove_direction(vectors: Sequence[Vector], direction: Vector, strength: float = 1.0) -> list[list[float]]:
    """Subtract `strength` times each vector's projection on `direction` (e.g. the embedded problem statement), then re-normalise."""
    unit = _unit(direction)
    out: list[list[float]] = []
    for vector in vectors:
        along = sum(a * b for a, b in zip(vector, unit, strict=True))
        out.append(_unit([a - strength * along * b for a, b in zip(vector, unit, strict=True)]))
    return out


@dataclass(frozen=True)
class ClusterStats:
    """R(N), R(N) / N, f_max(N) and H(N) of a set of N rollouts (Appendix A.6)."""

    realised: int
    per_sample: float
    dominant_share: float
    entropy_bits: float
    sizes: tuple[int, ...]


def cluster_stats(clusters: Sequence[Sequence[int]]) -> ClusterStats:
    """Statistics of a clustering. An empty clustering has no diversity: every figure is zero."""
    sizes = tuple(len(members) for members in clusters if members)
    total = sum(sizes)
    if total == 0:
        return ClusterStats(0, 0.0, 0.0, 0.0, ())
    shares = [size / total for size in sizes]
    entropy = -sum(share * math.log2(share) for share in shares)
    return ClusterStats(len(sizes), len(sizes) / total, max(shares), entropy + 0.0, sizes)


def redundant_pairs(vectors: Sequence[Vector], clusters: Sequence[Sequence[int]], threshold: float) -> list[tuple[int, int, float]]:
    """Pairs (i, j), i < j, that share a cluster and whose cosine similarity is above `threshold`.

    This is an extension of ours, not part of the paper: a pair this close adds almost nothing as two independent samples.
    """
    pairs: list[tuple[int, int, float]] = []
    for members in clusters:
        for position, i in enumerate(members):
            for j in members[position + 1:]:
                similarity = cosine(vectors[i], vectors[j])
                if similarity > threshold:
                    pairs.append((min(i, j), max(i, j), similarity))
    return sorted(pairs)


CENTERED_TAU = -0.1
"""After the batch mean is removed, rollouts of one direction point the same way and different directions point away from each other
(cosine about -1/(k-1) for k balanced groups). -0.1 was the best cut for all six sentence encoders tried, picked on four problems and
confirmed on four others; the useful window is roughly -0.2 to 0.0."""


@dataclass(frozen=True)
class DirectionAnalysis:
    clusters: list[list[int]]
    stats: ClusterStats
    view: Literal["centered", "raw"]
    mean_similarity: float
    relative_similarity: float | None
    single_direction_likely: bool | None


def analyze_directions(
    vectors: Sequence[Vector],
    problem: Vector | None = None,
    *,
    view: Literal["centered", "raw"] = "centered",
    tau_centered: float = CENTERED_TAU,
    tau_raw: float = PAPER_TAU_SIM,
    flat_margin: float | None = None,
) -> DirectionAnalysis:
    """Group rollouts by solution direction and report R(N), f_max(N) and H(N).

    centered (default): remove the part the rollouts share (the embedded `problem` statement's direction when given, then the batch
    mean), re-normalise, and cluster at cosine `tau_centered`. raw: the paper's setting, cosine `tau_raw` on the vectors as they are.
    Fewer than three rollouts cannot be centered (two are always opposite after it), so they use the raw view.

    Centering keeps only RELATIVE differences: it says which rollouts resemble each other more than the rest, not whether the whole
    batch is one direction. `flat_margin` adds an optional check for that: when the mean pairwise similarity (minus the mean
    similarity to the problem, if given) is at least `flat_margin`, the batch is reported as a single direction. It is uncalibrated by
    default (None = no check) because the similarity level of one direction varies by problem: tuned for 10% false alarms on four
    problems it gave 5-30% on four others while catching 40-80% of single-direction batches.
    """
    count = len(vectors)
    if count == 0:
        return DirectionAnalysis([], cluster_stats([]), view, 0.0, None, None)
    pair_values = [cosine(vectors[i], vectors[j]) for i in range(count) for j in range(i + 1, count)]
    mean_similarity = sum(pair_values) / len(pair_values) if pair_values else 1.0
    relative = None if problem is None or not pair_values else mean_similarity - sum(cosine(vector, problem) for vector in vectors) / count
    effective: Literal["centered", "raw"] = "raw" if view == "raw" or count < 3 else "centered"
    if effective == "centered":
        working = remove_direction(vectors, problem) if problem is not None else [list(vector) for vector in vectors]
        clusters = cut_at_similarity(count, dendrogram(center(working)), tau_centered)
    else:
        clusters = cut_at_similarity(count, dendrogram(vectors), tau_raw)
    flat: bool | None = None
    if flat_margin is not None and pair_values:
        flat = (relative if relative is not None else mean_similarity) >= flat_margin
        if flat:
            clusters = [list(range(count))]
    return DirectionAnalysis(clusters, cluster_stats(clusters), effective, mean_similarity, relative, flat)
