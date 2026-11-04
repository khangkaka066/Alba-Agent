"""Depth-first ordering with cycle detection."""


class CycleError(Exception):
    """The graph has a cycle. ``cycle`` lists it as ``[n0, n1, ..., n0]`` following edges."""

    def __init__(self, cycle):
        super().__init__("cycle: " + " -> ".join(map(str, cycle)))
        self.cycle = cycle


def postorder(graph):
    """Return every node of ``graph`` in DFS post-order: a node comes after all nodes
    reachable from it through its edges.

    Start nodes are tried in ``graph.nodes()`` order and successors in edge order. A node
    that is reached again through a different path (a "diamond") is fine; only an edge
    back to a node that is still being explored is a cycle, and that raises CycleError
    (a self-loop counts as a cycle).
    """
    done = set()
    in_progress = set()
    order = []
    path = []

    def visit(node):
        if node in in_progress:
            start = path.index(node)
            raise CycleError(path[start:] + [node])
        if node in done:
            return
        in_progress.add(node)
        path.append(node)
        for nxt in graph.successors(node):
            visit(nxt)
        path.pop()
        in_progress.discard(node)
        done.add(node)
        order.append(node)

    for node in graph.nodes():
        visit(node)
    return order
