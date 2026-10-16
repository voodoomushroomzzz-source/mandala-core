"""Parser: read Mandala structure, extract nodes and edges."""
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
    """Parse core_map: honeycombs + navigation edges."""
    if core_map_path is None:
        root = find_repo_root()
        core_map_path = root / "honeycombs" / "core_map" / "index.json"
    data = read_json(core_map_path)

    nodes = []
    edges_raw = []

    for name, info in data.get("honeycombs", {}).items():
        nodes.append({
            "id": name,
            "type": "honeycomb",
            "path": info.get("path", ""),
            "description": info.get("description", "")
        })

    nav = data.get("navigation", {})
    for ref in nav.get("references", []):
        target = ref.replace("honeycombs/", "").replace("/index.json", "").split("/")[0]
        edges_raw.append({"from": "core_map", "to": target, "type": "references"})
    for child in nav.get("children", []):
        target = child.replace("honeycombs/", "").replace("/index.json", "").split("/")[0]
        edges_raw.append({"from": "core_map", "to": target, "type": "children"})

    seen = {}
    for e in edges_raw:
        key = (e["from"], e["to"])
        if key not in seen or e["type"] == "children":
            seen[key] = e
    edges = list(seen.values())

    return {"nodes": nodes, "edges": edges}


def parse_works(works_path=None) -> dict:
    """Parse works/index.json: works nodes + related edges."""
    if works_path is None:
        root = find_repo_root()
        works_path = root / "honeycombs" / "works" / "index.json"
    data = read_json(works_path)

    nodes = []
    edges = []
    manifest = data.get("manifest", {})

    for work_id in manifest.get("works_list", []):
        nodes.append({
            "id": work_id,
            "type": "work",
            "path": "honeycombs/works/" + work_id + ".json",
            "description": "",
            "deadline": manifest.get("deadlines", {}).get(work_id),
            "progress": manifest.get("progress", {}).get(work_id, 0)
        })
        edges.append({"from": "works", "to": work_id, "type": "contains"})

    related = manifest.get("related_works", {})
    for src, targets in related.items():
        if isinstance(targets, list):
            for tgt in targets:
                tgt_clean = tgt.split("__")[0] if "__" in tgt else tgt
                edges.append({"from": src, "to": tgt_clean, "type": "related_works"})

    return {"nodes": nodes, "edges": edges}


def parse_fruits(fruits_path=None) -> dict:
    """Parse fruits/index.json: fruit nodes."""
    if fruits_path is None:
        root = find_repo_root()
        fruits_path = root / "honeycombs" / "fruits" / "index.json"
    data = read_json(fruits_path)

    nodes = []
    edges = []

    for fruit in data.get("fruits", []):
        fid = fruit.get("id", "")
        if not fid:
            continue
        nodes.append({
            "id": fid,
            "type": "fruit",
            "path": fruit.get("path") or "",
            "description": fruit.get("short_description", ""),
            "status": fruit.get("status", ""),
            "version": fruit.get("version", "")
        })
        edges.append({"from": "fruits", "to": fid, "type": "contains"})

    return {"nodes": nodes, "edges": edges}


def parse_knowledge(knowledge_path=None) -> dict:
    """Parse knowledge/index.json: knowledge resource nodes."""
    if knowledge_path is None:
        root = find_repo_root()
        knowledge_path = root / "honeycombs" / "knowledge" / "index.json"
    data = read_json(knowledge_path)

    nodes = []
    edges = []

    for item in data.get("contents", []):
        kid = item.get("id", "")
        if not kid:
            continue
        nodes.append({
            "id": "K-" + kid,
            "type": "knowledge",
            "path": "honeycombs/knowledge/" + (item.get("file") or ""),
            "description": item.get("description", "")
        })
        edges.append({"from": "knowledge", "to": "K-" + kid, "type": "contains"})

    return {"nodes": nodes, "edges": edges}


def parse_seeds_count(seeds_path=None) -> dict:
    """Count seeds for analysis (not as graph nodes)."""
    if seeds_path is None:
        root = find_repo_root()
        seeds_path = root / "honeycombs" / "seeds" / "index.json"
    data = read_json(seeds_path)
    meta = data.get("meta", {})
    total = meta.get("total_seeds", 0)
    return {"seeds_total": total}


def parse_all() -> dict:
    """Parse everything and return combined graph."""
    parts = [
        parse_core_map(),
        parse_works(),
        parse_fruits(),
        parse_knowledge(),
    ]

    all_nodes = []
    all_edges = []
    seen_nodes = set()

    for p in parts:
        for n in p.get("nodes", []):
            if n["id"] not in seen_nodes:
                all_nodes.append(n)
                seen_nodes.add(n["id"])
        all_edges.extend(p.get("edges", []))

    seen_edges = {}
    for e in all_edges:
        key = (e["from"], e["to"], e["type"])
        if key not in seen_edges:
            seen_edges[key] = e
    edges = list(seen_edges.values())

    seeds_info = parse_seeds_count()

    return {
        "nodes": all_nodes,
        "edges": edges,
        "seeds_total": seeds_info.get("seeds_total", 0)
    }
