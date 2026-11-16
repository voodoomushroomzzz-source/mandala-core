"""Graph model."""
from collections import defaultdict


def find_orphans(node_ids, edges) -> list:
    """Return nodes with no incoming or outgoing edges."""
    connected = {edge[end] for edge in edges for end in ("from", "to")}
    return [node_id for node_id in node_ids if node_id not in connected]


class Graph:
    def __init__(self):
        self.nodes = {}
        self.edges = []

    def add_node(self, node_id: str, **attrs):
        if node_id not in self.nodes:
            self.nodes[node_id] = {"id": node_id, **attrs}

    def add_edge(self, from_id: str, to_id: str, edge_type: str):
        self.edges.append({"from": from_id, "to": to_id, "type": edge_type})

    def in_degree(self) -> dict:
        deg = defaultdict(int)
        for e in self.edges:
            deg[e["to"]] += 1
        return dict(deg)

    def orphans(self) -> list:
        return find_orphans(self.nodes, self.edges)

    def to_dict(self) -> dict:
        return {"nodes": list(self.nodes.values()), "edges": self.edges, "analysis": {"total_nodes": len(self.nodes), "total_edges": len(self.edges), "orphans": self.orphans()}}
