"""Graph model."""
from collections import defaultdict


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
        incoming = self.in_degree()
        return [nid for nid in self.nodes if incoming.get(nid, 0) == 0]

    def to_dict(self) -> dict:
        return {"nodes": list(self.nodes.values()), "edges": self.edges, "analysis": {"total_nodes": len(self.nodes), "total_edges": len(self.edges), "orphans": self.orphans()}}
