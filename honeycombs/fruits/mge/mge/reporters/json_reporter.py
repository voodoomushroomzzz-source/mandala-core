"""JSON reporter."""
import json
from pathlib import Path


def write_json(graph_dict: dict, output_path: str = "output/mandala_graph.json"):
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(graph_dict, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return output_path
