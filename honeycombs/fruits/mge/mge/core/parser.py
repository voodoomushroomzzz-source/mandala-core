"""Parser: read Mandala structure, extract nodes and edges."""
import json
import os
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


def scan_filesystem_honeycombs(root: Path = None) -> list:
    """Scan honeycombs/ folder for all dirs with index.json. Returns list of names."""
    if root is None:
        root = find_repo_root()
    hc_dir = root / "honeycombs"
    if not hc_dir.exists():
        return []
    result = []
    for entry in sorted(hc_dir.iterdir()):
        if entry.is_dir() and (entry / "index.json").exists():
            result.append(entry.name)
    return result


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
            "source": "core_map",
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


def find_unregistered_honeycombs() -> dict:
    """Compare filesystem honeycombs vs core_map. Returns unregistered + missing."""
    root = find_repo_root()
    fs_honeycombs = set(scan_filesystem_honeycombs(root))

    core_map_data = read_json(root / "honeycombs" / "core_map" / "index.json")
    registered = set(core_map_data.get("honeycombs", {}).keys())

    unregistered = sorted(fs_honeycombs - registered)
    missing = sorted(registered - fs_honeycombs)

    unregistered_nodes = []
    unregistered_edges = []
    for name in unregistered:
        unregistered_nodes.append({
            "id": name,
            "type": "honeycomb_unregistered",
            "source": "filesystem",
            "path": "honeycombs/" + name + "/index.json",
            "description": "NOT REGISTERED in core_map"
        })
        unregistered_edges.append({
            "from": "core_map",
            "to": name,
            "type": "unregistered"
        })

    return {
        "unregistered": unregistered,
        "missing": missing,
        "nodes": unregistered_nodes,
        "edges": unregistered_edges
    }


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


def count_seeds() -> dict:
    """Count seeds in inbox and root folders (real filesystem count)."""
    root = find_repo_root()
    seeds_dir = root / "honeycombs" / "seeds"
    inbox_dir = seeds_dir / "inbox"

    inbox_count = 0
    if inbox_dir.exists():
        inbox_count = sum(1 for f in inbox_dir.iterdir()
                         if f.is_file() and f.name.endswith(".json") and f.name != "index.json")

    root_count = 0
    if seeds_dir.exists():
        root_count = sum(1 for f in seeds_dir.iterdir()
                        if f.is_file() and f.name.endswith(".json") and f.name != "index.json")

    return {
        "seeds_inbox_count": inbox_count,
        "seeds_root_count": root_count,
        "seeds_total": inbox_count + root_count
    }


def compute_degree(nodes: list, edges: list) -> dict:
    """Compute in+out degree for each node."""
    degree = {n["id"]: 0 for n in nodes}
    for e in edges:
        if e["from"] in degree:
            degree[e["from"]] += 1
        if e["to"] in degree:
            degree[e["to"]] += 1
    return degree


def find_top_hubs(nodes: list, edges: list, top: int = 5) -> list:
    """Return top N nodes by degree."""
    degree = compute_degree(nodes, edges)
    sorted_nodes = sorted(degree.items(), key=lambda x: -x[1])
    return [{"id": k, "degree": v} for k, v in sorted_nodes[:top]]


def find_broken_refs(nodes: list, edges: list) -> list:
    """Find edges pointing to non-existent nodes."""
    node_ids = {n["id"] for n in nodes}
    broken = []
    for e in edges:
        if e["to"] not in node_ids:
            broken.append({"from": e["from"], "to": e["to"], "type": e["type"]})
    return broken


def normalize_work_id(wid: str) -> str:
    """Strip __suffix from work IDs for comparison.
    W-T-20260511-ENGCHAT__engineer_chat -> W-T-20260511-ENGCHAT
    """
    if not isinstance(wid, str):
        return wid
    return wid.split("__")[0] if "__" in wid else wid


def find_missing_nodes(nodes: list, edges: list) -> dict:
    """Find edges pointing to non-existent nodes.
    Uses normalized IDs: __suffix is stripped for comparison.
    Returns: phantom nodes for truly missing, format_mismatches separately.
    """
    node_ids_normalized = {normalize_work_id(n["id"]) for n in nodes}
    original_ids = {n["id"] for n in nodes}

    missing_targets = {}
    format_mismatches = set()
    broken_edges = []

    for e in edges:
        target = e["to"]
        if target in original_ids:
            continue
        target_norm = normalize_work_id(target)
        if target_norm in node_ids_normalized:
            format_mismatches.add(target)
            continue
        missing_targets[target] = missing_targets.get(target, 0) + 1
        broken_edges.append({
            "from": e["from"],
            "to": target,
            "type": "broken_link",
            "original_type": e["type"]
        })

    phantom_nodes = []
    for mid, count in missing_targets.items():
        phantom_nodes.append({
            "id": mid,
            "type": "missing",
            "path": "",
            "description": "Referenced by " + str(count) + " node(s) but does not exist",
            "referenced_count": count
        })

    return {
        "nodes": phantom_nodes,
        "edges": broken_edges,
        "missing_ids": sorted(missing_targets.keys()),
        "format_mismatches": sorted(format_mismatches)
    }


def find_islands(nodes: list, edges: list, root: str = "core_map") -> list:
    """Find nodes not reachable from root (BFS)."""
    node_ids = {n["id"] for n in nodes}
    if root not in node_ids:
        return sorted(node_ids)

    adj = {nid: set() for nid in node_ids}
    for e in edges:
        if e["from"] in adj and e["to"] in adj:
            adj[e["from"]].add(e["to"])
            adj[e["to"]].add(e["from"])

    visited = set()
    queue = [root]
    while queue:
        cur = queue.pop()
        if cur in visited:
            continue
        visited.add(cur)
        for nb in adj.get(cur, []):
            if nb not in visited:
                queue.append(nb)

    return sorted(node_ids - visited)


def parse_all() -> dict:
    """Parse everything and return combined graph."""
    unregistered_info = find_unregistered_honeycombs()
    seeds_info = count_seeds()

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

    for n in unregistered_info["nodes"]:
        if n["id"] not in seen_nodes:
            all_nodes.append(n)
            seen_nodes.add(n["id"])
    all_edges.extend(unregistered_info["edges"])

    seen_edges = {}
    for e in all_edges:
        key = (e["from"], e["to"], e["type"])
        if key not in seen_edges:
            seen_edges[key] = e
    edges = list(seen_edges.values())

    incoming = {}
    for e in edges:
        incoming[e["to"]] = incoming.get(e["to"], 0) + 1
    orphans = [n["id"] for n in all_nodes if incoming.get(n["id"], 0) == 0]

    by_type = {}
    for n in all_nodes:
        t = n.get("type", "unknown")
        by_type[t] = by_type.get(t, 0) + 1

    islands = find_islands(all_nodes, edges, root="core_map")
    broken_refs = find_broken_refs(all_nodes, edges)
    top_hubs = find_top_hubs(all_nodes, edges, top=5)

    missing_info = find_missing_nodes(all_nodes, edges)
    for phantom in missing_info["nodes"]:
        if phantom["id"] not in seen_nodes:
            all_nodes.append(phantom)
            seen_nodes.add(phantom["id"])
    for broken_edge in missing_info["edges"]:
        edges.append(broken_edge)

    # Remove broken refs from normal edges (they pointed to missing nodes)
    node_ids_final = {n["id"] for n in all_nodes}
    edges = [e for e in edges if e["to"] in node_ids_final]

    reachable_count = len(all_nodes) - len(islands)

    by_type = {}
    for n in all_nodes:
        t = n.get("type", "unknown")
        by_type[t] = by_type.get(t, 0) + 1

    return {
        "nodes": all_nodes,
        "edges": edges,
        "analysis": {
            "total_nodes": len(all_nodes),
            "total_edges": len(edges),
            "by_type": by_type,
            "orphans": orphans,
            "unregistered_honeycombs": unregistered_info["unregistered"],
            "missing_honeycombs": unregistered_info["missing"],
            "seeds_inbox_count": seeds_info["seeds_inbox_count"],
            "seeds_root_count": seeds_info["seeds_root_count"],
            "seeds_total": seeds_info["seeds_total"],
            "islands": islands,
            "broken_refs": broken_refs,
            "missing_node_ids": missing_info["missing_ids"],
            "id_format_mismatches": missing_info["format_mismatches"],
            "reachable_from_core": reachable_count,
            "unreachable": islands,
            "top_hubs": top_hubs
        }
    }
