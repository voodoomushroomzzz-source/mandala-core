"""Parser: read JSON files, extract nodes and edges."""
import json
from pathlib import Path


def find_repo_root(start: Path = None) -> Path:
    """Walk up from start until we find honeycombs/core_map/index.json."""
    if start is None:
        start = Path.cwd()
    current = start.resolve()
    for _ in range(10):
        candidate = current / "honeycombs" / "core_map" / "index.json"
        if candidate.exists():
            return current
        if current.parent == current:
            break
        current = current.parent
    raise FileNotFoundError("honeycombs/core_map/index.json not found in any parent directory")


def read_json(path) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        return {"_error": str(e)}


def parse_core_map(core_map_path=None) -> dict:
    if core_map_path is None:
        root = find_repo_root()
        core_map_path = root / "honeycombs" / "core_map" / "index.json"
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
