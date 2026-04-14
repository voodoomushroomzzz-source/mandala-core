"""
Group service for gardener groups.
Handles reading, creating, and deleting groups from groups.json.
"""

import json
import os
from datetime import datetime
from typing import List, Dict, Optional

GARDENER_ID = "001"
GROUPS_FILE = f"honeycombs/personal_gardeners/gardener_{GARDENER_ID}/groups.json"


def read_groups() -> Dict:
    """Read groups.json and return dict with groups array."""
    if not os.path.exists(GROUPS_FILE):
        return {"groups": [], "updated": datetime.now().isoformat()}
    with open(GROUPS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def write_groups(data: Dict) -> None:
    """Write groups data to groups.json."""
    data["updated"] = datetime.now().isoformat()
    os.makedirs(os.path.dirname(GROUPS_FILE), exist_ok=True)
    with open(GROUPS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def list_groups() -> List[Dict]:
    """Return list of all groups."""
    data = read_groups()
    return data.get("groups", [])


def get_group_by_id(group_id: str) -> Optional[Dict]:
    """Return group by id or None."""
    groups = list_groups()
    for g in groups:
        if g.get("id") == group_id:
            return g
    return None


def create_group(name: str, color: str = "#808080") -> Dict:
    """Create new group. Returns created group."""
    data = read_groups()
    groups = data.get("groups", [])
    
    # Generate id: lowercase name + random suffix if duplicate
    base_id = "".join(c for c in name.lower() if c.isalnum() or c == "_")
    if not base_id:
        base_id = "group"
    group_id = base_id
    counter = 1
    while any(g.get("id") == group_id for g in groups):
        group_id = f"{base_id}_{counter}"
        counter += 1
    
    new_group = {
        "id": group_id,
        "name": name,
        "color": color,
        "created": datetime.now().isoformat()
    }
    groups.append(new_group)
    data["groups"] = groups
    write_groups(data)
    return new_group


def delete_group(group_id: str) -> bool:
    """Delete group by id. Returns True if deleted, False if not found."""
    data = read_groups()
    groups = data.get("groups", [])
    initial_len = len(groups)
    data["groups"] = [g for g in groups if g.get("id") != group_id]
    if len(data["groups"]) < initial_len:
        write_groups(data)
        return True
    return False


def group_exists(group_id: str) -> bool:
    """Check if group exists."""
    return get_group_by_id(group_id) is not None


def get_group_names() -> List[str]:
    """Return list of group names for display."""
    return [g.get("name", "?") for g in list_groups()]


def get_group_ids() -> List[str]:
    """Return list of group ids."""
    return [g.get("id", "") for g in list_groups()]
