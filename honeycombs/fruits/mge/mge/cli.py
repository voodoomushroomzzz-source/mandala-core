"""MGE CLI."""
from pathlib import Path
from mge.core.parser import find_repo_root, parse_all
from mge.core.graph import Graph
from mge.reporters.json_reporter import write_json
from mge.reporters.mermaid_reporter import write_mermaid
from mge.reporters.html_reporter import write_html


def cmd_scan(output=Path("output")):
    print("Scanning Mandala...")
    parsed = parse_all()
    from mge.knowledge import load_knowledge, write_knowledge_index
    knowledge_root = find_repo_root() / "honeycombs/knowledge"
    write_knowledge_index(knowledge_root, load_knowledge(knowledge_root))

    g = Graph()
    for node in parsed["nodes"]:
        g.add_node(node["id"], **{k: v for k, v in node.items() if k != "id"})
    for edge in parsed["edges"]:
        g.add_edge(edge["from"], edge["to"], edge["type"])

    graph_dict = g.to_dict()
    graph_dict["analysis"] = parsed["analysis"]

    json_path = write_json(graph_dict, output / "mandala_graph.json")
    mmd_path = write_mermaid(graph_dict, output / "mandala_graph.mmd")
    html_path = write_html(graph_dict, output / "mandala_graph.html")

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
    return graph_dict


def main():
    import argparse

    cli = argparse.ArgumentParser(description="Build Mandala graph and dashboards")
    commands = cli.add_subparsers(dest="command", required=True)
    commands.add_parser("scan", help="Build graph only into ./output")
    dashboard = commands.add_parser("dashboard", help="Build the entire static dashboard")
    dashboard.add_argument("--output", type=Path, help="Output site root (defaults to the repository)")
    args = cli.parse_args()

    if args.command == "scan":
        cmd_scan()
    else:
        from mge.dashboard import build_catalogs

        root = find_repo_root()
        site = args.output.resolve() if args.output else root
        output = site / "honeycombs/fruits/mge/output"
        graph = cmd_scan(output)
        build_catalogs(root, site, output, graph)


if __name__ == "__main__":
    main()
