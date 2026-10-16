"""Parser: read JSON files, extract nodes and edges."""
import json


def read_json(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        return {"_error": str(e)}


def parse_core_map(core_map_path: str = "honeycombs/core_map/index.json") -> dict:
    data = read_json(core_map_path)
    nodes = []
    edges = []
    for name, info in data.get("honeycombs", {}).items():
        nodes.append({"id": name, "type": "honeycomb", "path": info.get("path", ""), "description": info.get("description", "")})
    nav = data.get("navigation", {})
    for ref in nav.get("references", []):
        target = ref.replace("honeycombs/", "").replace("/index.json", "").split("/")[0]
        edges.append({"from": "core_map", "to": target, "type": "references"})
    for child in nav.get("children", []):
        target = child.replace("honeycombs/", "").replace("/index.json", "").split("/")[0]
        edges.append({"from": "core_map", "to": target, "type": "children"})
    return {"nodes": nodes, "edges": edges}
