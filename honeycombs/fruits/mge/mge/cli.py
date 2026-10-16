"""MGE CLI."""
import sys
from mge.core.parser import parse_all
from mge.core.graph import Graph
from mge.reporters.json_reporter import write_json
from mge.reporters.mermaid_reporter import write_mermaid
from mge.reporters.html_reporter import write_html


def cmd_scan():
    print("Scanning Mandala...")
    parsed = parse_all()

    g = Graph()
    for node in parsed["nodes"]:
        g.add_node(node["id"], **{k: v for k, v in node.items() if k != "id"})
    for edge in parsed["edges"]:
        g.add_edge(edge["from"], edge["to"], edge["type"])

    graph_dict = g.to_dict()
    graph_dict["analysis"] = parsed["analysis"]

    json_path = write_json(graph_dict)
    mmd_path = write_mermaid(graph_dict)
    html_path = write_html(graph_dict)

    a = graph_dict["analysis"]
    print(f"OK nodes: {a['total_nodes']}")
    print(f"OK edges: {a['total_edges']}")
    print(f"OK orphans: {a['orphans']}")
    if a.get("unregistered_honeycombs"):
        print(f"WARN unregistered: {a['unregistered_honeycombs']}")
    if a.get("missing_honeycombs"):
        print(f"WARN missing: {a['missing_honeycombs']}")
    print(f"OK seeds: total={a.get('seeds_total', 0)} (inbox={a.get('seeds_inbox_count', 0)}, root={a.get('seeds_root_count', 0)})")
    print(f"OK JSON: {json_path}")
    print(f"OK Mermaid: {mmd_path}")
    print(f"OK HTML: {html_path}")


def main():
    if len(sys.argv) < 2 or sys.argv[1] != "scan":
        print("Usage: python -m mge scan")
        sys.exit(1)
    cmd_scan()


if __name__ == "__main__":
    main()
