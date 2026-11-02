"""Layered (dagre-style) coordinates for evolved workflow graphs."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from statistics import median
from typing import Any

LAYER_WIDTH = 340.0
ROW_HEIGHT = 380.0
ORIGIN_X = 60.0


def layered_layout(
    node_ids: Sequence[str], edges: Sequence[Mapping[str, Any]], previous: Mapping[str, Mapping[str, float]] | None = None,
) -> dict[str, dict[str, float]]:
    """Longest-path layering over forward edges; rows inside a layer keep their previous vertical order."""
    forward = [(str(edge["source"]), str(edge["target"])) for edge in edges if not edge.get("loop_back")]
    known = set(node_ids)
    incoming: dict[str, list[str]] = defaultdict(list)
    for source, target in forward:
        if source in known and target in known:
            incoming[target].append(source)
    layer: dict[str, int] = {}

    def depth(node_id: str, trail: frozenset[str]) -> int:
        if node_id in layer:
            return layer[node_id]
        if node_id in trail:
            raise ValueError("Layout requires an acyclic forward graph")
        parents = incoming.get(node_id, [])
        layer[node_id] = 0 if not parents else 1 + max(depth(parent, trail | {node_id}) for parent in parents)
        return layer[node_id]

    for node_id in node_ids:
        depth(node_id, frozenset())
    columns: dict[int, list[str]] = defaultdict(list)
    for node_id in node_ids:
        columns[layer[node_id]].append(node_id)
    prior = previous or {}
    center = median([position["y"] for position in prior.values()]) if prior else 560.0
    order = {node_id: index for index, node_id in enumerate(node_ids)}
    result: dict[str, dict[str, float]] = {}
    for column, members in sorted(columns.items()):
        members.sort(key=lambda node_id: (prior[node_id]["y"] if node_id in prior else center, order[node_id]))
        top = center - (len(members) - 1) * ROW_HEIGHT / 2
        for row, node_id in enumerate(members):
            result[node_id] = {"x": ORIGIN_X + column * LAYER_WIDTH, "y": top + row * ROW_HEIGHT}
    return result
