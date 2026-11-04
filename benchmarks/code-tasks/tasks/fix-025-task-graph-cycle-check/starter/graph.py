"""A minimal directed graph that remembers insertion order."""


class DiGraph:
    def __init__(self):
        self._succ = {}

    def add_node(self, node):
        self._succ.setdefault(node, [])

    def add_edge(self, src, dst):
        """Add the edge ``src -> dst`` (duplicates are ignored); both nodes are created."""
        self.add_node(src)
        self.add_node(dst)
        if dst not in self._succ[src]:
            self._succ[src].append(dst)

    def nodes(self):
        """Nodes in the order they were first added."""
        return list(self._succ)

    def successors(self, node):
        """Targets of edges leaving ``node`` in the order the edges were added."""
        return list(self._succ[node])
