"""Generate a self-contained neural map from the real graph, without a CDN."""
import json
from pathlib import Path


ASSETS = Path(__file__).parent
HTML_TEMPLATE = (ASSETS / "neural_map.html").read_text(encoding="utf-8")


def write_html(graph_dict: dict, output_path: str = "output/mandala_graph.html"):
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    graph_json = json.dumps(graph_dict, ensure_ascii=True).replace("</", "<\\/")
    script = (ASSETS / "neural_map.js").read_text(encoding="utf-8")
    # Insert data last: data containing template tokens must remain literal data.
    html = HTML_TEMPLATE.replace("__NEURAL_JS__", script).replace("__GRAPH_JSON__", graph_json)
    Path(output_path).write_text(html, encoding="utf-8", newline="\n")
    return output_path
