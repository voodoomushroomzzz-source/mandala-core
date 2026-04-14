"""
Task service for personal task management.
Handles CRUD operations, auto-priority calculation, and archiving.
"""

import json
import os
from datetime import datetime
from typing import List, Dict, Optional, Any

GARDENER_ID = "001"
TASKS_FILE = f"honeycombs/personal_gardeners/gardener_{GARDENER_ID}/tasks.json"
ARCHIVE_FILE = f"honeycombs/personal_gardeners/gardener_{GARDENER_ID}/tasks_archive.json"


def read_tasks() -> Dict:
    """Read tasks.json and return dict with tasks array."""
    if not os.path.exists(TASKS_FILE):
        return {"tasks": [], "updated": datetime.now().isoformat()}
    with open(TASKS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def write_tasks(data: Dict) -> None:
    """Write tasks data to tasks.json."""
    data["updated"] = datetime.now().isoformat()
    os.makedirs(os.path.dirname(TASKS_FILE), exist_ok=True)
    with open(TASKS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def read_archive() -> Dict:
    """Read archive file."""
    if not os.path.exists(ARCHIVE_FILE):
        return {"tasks": [], "updated": datetime.now().isoformat()}
    with open(ARCHIVE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def write_archive(data: Dict) -> None:
    """Write archive data."""
    data["updated"] = datetime.now().isoformat()
    os.makedirs(os.path.dirname(ARCHIVE_FILE), exist_ok=True)
    with open(ARCHIVE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def generate_task_id() -> str:
    """Generate unique task_id: task_YYYYMMDD_NNN"""
    today = datetime.now().strftime("%Y%m%d")
    data = read_tasks()
    tasks = data.get("tasks", [])
    today_tasks = [t for t in tasks if t.get("task_id", "").startswith(f"task_{today}")]
    counter = len(today_tasks) + 1
    return f"task_{today}_{counter:03d}"


def calculate_priority(
    resonance_match: int,
    life_area_gap: float,
    deadline: Optional[str] = None
) -> int:
    """
    Auto-calculate priority (1-10).
    Formula: base_priority = (resonance_match * 0.6) + (life_area_gap * 0.4)
    Deadline modifier: +1 if within 3 days, +2 if overdue.
    """
    base = (resonance_match * 0.6) + (life_area_gap * 0.4)
    priority = int(round(base))
    
    if deadline:
        try:
            dl = datetime.fromisoformat(deadline)
            days_left = (dl - datetime.now()).days
            if days_left < 0:
                priority += 2
            elif days_left <= 3:
                priority += 1
        except (ValueError, TypeError):
            pass
    
    return max(1, min(10, priority))


def create_task(
    title: str,
    group_id: str,
    life_area: str,
    resonance_match: int = 5,
    life_area_gap: float = 5.0,
    deadline: Optional[str] = None,
    estimated_hours: Optional[int] = None,
    notes: str = "",
    source: str = "manual",
    tags: List[str] = None,
    linked_achievement: Optional[str] = None
) -> Dict:
    """Create new task. Returns created task."""
    data = read_tasks()
    tasks = data.get("tasks", [])
    
    priority = calculate_priority(resonance_match, life_area_gap, deadline)
    
    new_task = {
        "task_id": generate_task_id(),
        "title": title,
        "status": "todo",
        "priority": priority,
        "life_area": life_area,
        "group_id": group_id,
        "source": source,
        "tags": tags or [],
        "deadline": deadline,
        "estimated_hours": estimated_hours,
        "linked_achievement": linked_achievement,
        "created": datetime.now().isoformat(),
        "updated": datetime.now().isoformat(),
        "completed": None,
        "notes": notes
    }
    tasks.append(new_task)
    data["tasks"] = tasks
    write_tasks(data)
    return new_task


def get_task(task_id: str) -> Optional[Dict]:
    """Get task by id."""
    data = read_tasks()
    for t in data.get("tasks", []):
        if t.get("task_id") == task_id:
            return t
    return None


def update_task(task_id: str, updates: Dict) -> Optional[Dict]:
    """Update task fields. Returns updated task or None."""
    data = read_tasks()
    tasks = data.get("tasks", [])
    for t in tasks:
        if t.get("task_id") == task_id:
            for key, value in updates.items():
                if key in t:
                    t[key] = value
            t["updated"] = datetime.now().isoformat()
            
            # Recalculate priority if relevant fields changed
            if any(k in updates for k in ["resonance_match", "life_area_gap", "deadline"]):
                t["priority"] = calculate_priority(
                    updates.get("resonance_match", 5),
                    updates.get("life_area_gap", 5.0),
                    t.get("deadline")
                )
            
            write_tasks(data)
            return t
    return None


def delete_task(task_id: str) -> bool:
    """Delete task by id. Returns True if deleted."""
    data = read_tasks()
    tasks = data.get("tasks", [])
    initial_len = len(tasks)
    data["tasks"] = [t for t in tasks if t.get("task_id") != task_id]
    if len(data["tasks"]) < initial_len:
        write_tasks(data)
        return True
    return False


def complete_task(task_id: str) -> Optional[Dict]:
    """Mark task as completed."""
    return update_task(task_id, {"status": "completed", "completed": datetime.now().isoformat()})


def archive_completed() -> int:
    """Move all completed tasks to archive. Returns count of archived tasks."""
    data = read_tasks()
    tasks = data.get("tasks", [])
    completed = [t for t in tasks if t.get("status") == "completed"]
    active = [t for t in tasks if t.get("status") != "completed"]
    
    if completed:
        archive_data = read_archive()
        archive_tasks = archive_data.get("tasks", [])
        archive_tasks.extend(completed)
        archive_data["tasks"] = archive_tasks
        write_archive(archive_data)
        
        data["tasks"] = active
        write_tasks(data)
    
    return len(completed)


def list_tasks(status: Optional[str] = None, group_id: Optional[str] = None) -> List[Dict]:
    """List tasks with optional filters."""
    data = read_tasks()
    tasks = data.get("tasks", [])
    
    if status:
        tasks = [t for t in tasks if t.get("status") == status]
    if group_id:
        tasks = [t for t in tasks if t.get("group_id") == group_id]
    
    return sorted(tasks, key=lambda x: (-x.get("priority", 0), x.get("created", "")))


def get_task_counts() -> Dict:
    """Return task counts by status."""
    tasks = read_tasks().get("tasks", [])
    return {
        "todo": len([t for t in tasks if t.get("status") == "todo"]),
        "in_progress": len([t for t in tasks if t.get("status") == "in_progress"]),
        "completed": len([t for t in tasks if t.get("status") == "completed"]),
        "total": len(tasks)
    }
