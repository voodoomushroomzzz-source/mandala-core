"""MGE CLI."""
import sys
from mge.core.parser import parse_core_map
from mge.core.graph import Graph
from mge.reporters.json_reporter import write_json
from mge.reporters.mermaid_reporter import write_mermaid


def cmd_scan():
    print("Scanning Mandala...")
    parsed = parse_core_map()
    g = Graph()
    for node in parsed["nodes"]:
        g.add_node(node["id"], type=node["type"], path=node["path"], description=node["description"])
    for edge in parsed["edges"]:
        g.add_edge(edge["from"], edge["to"], edge["type"])
    graph_dict = g.to_dict()
    json_path = write_json(graph_dict)
    mmd_path = write_mermaid(graph_dict)
    print(f"OK nodes: {graph_dict['analysis']['total_nodes']}")
    print(f"OK edges: {graph_dict['analysis']['total_edges']}")
    print(f"OK orphans: {graph_dict['analysis']['orphans']}")
    print(f"OK JSON: {json_path}")
    print(f"OK Mermaid: {mmd_path}")


def main():
    if len(sys.argv) < 2 or sys.argv[1] != "scan":
        print("Usage: python -m mge scan")
        sys.exit(1)
    cmd_scan()


if __name__ == "__main__":
    main()
