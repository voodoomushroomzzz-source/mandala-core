"""Mermaid reporter."""
from pathlib import Path


def write_mermaid(graph_dict: dict, output_path: str = "output/mandala_graph.mmd"):
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    lines = ["graph TD"]
    for e in graph_dict["edges"]:
        lines.append(f'  {e["from"]} --> {e["to"]}')
    with open(output_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))
        f.write("\n")
    return output_path
