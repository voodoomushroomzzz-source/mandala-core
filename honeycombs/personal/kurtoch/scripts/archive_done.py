#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Переносит done + cancelled из taskboard.json в taskboard_archive.json.
Идемпотентно. Без интерактива."""
import io, json, os
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
KURTOCH = os.path.dirname(HERE)
TB = os.path.join(KURTOCH, "taskboard.json")
ARCHIVE = os.path.join(KURTOCH, "taskboard_archive.json")
TODAY = datetime.now().strftime("%Y-%m-%d")

def load(p):
    with io.open(p, encoding="utf-8") as f:
        return json.load(f)

def save(p, d):
    with io.open(p, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
        f.write("\n")

d = load(TB)
tasks = d["taskboard"]["tasks"]
ARCHIVE_STATUSES = {"done", "cancelled"}

to_archive = [t for t in tasks if t["status"] in ARCHIVE_STATUSES]
to_keep = [t for t in tasks if t["status"] not in ARCHIVE_STATUSES]

if not to_archive:
    print("Нет задач для архивации.")
    raise SystemExit(0)

# читаем/создаём архив
if os.path.exists(ARCHIVE):
    arch = load(ARCHIVE)
    existing_ids = {t["id"] for t in arch["archive"]["tasks"]}
else:
    arch = {
        "identity": {
            "module_id": "KURTOCH-TASKBOARD-ARCHIVE-001",
            "name": "Kurtoch — Taskboard Archive",
            "version": "v1.0.0",
            "created": TODAY, "updated": TODAY,
            "type": "taskboard_archive",
            "parent": "taskboard.json",
            "description": "Архив завершённых задач (done + cancelled).",
            "status": "active", "priority": "medium"
        },
        "archive": {"description": "Завершённые задачи.", "tasks": []},
        "navigation": {"parent": "honeycombs/personal/kurtoch/index.json", "sibling": "taskboard.json"}
    }
    existing_ids = set()

added = 0
for t in to_archive:
    if t["id"] in existing_ids:
        continue
    t_arch = dict(t)
    t_arch["archived_at"] = TODAY
    arch["archive"]["tasks"].append(t_arch)
    added += 1
    print(f"  -> архив: {t['id']} {t['title'][:60]}")

arch["identity"]["updated"] = TODAY
arch["archive"]["total"] = len(arch["archive"]["tasks"])
arch["archive"]["by_status"] = {
    "done": sum(1 for t in arch["archive"]["tasks"] if t["status"] == "done"),
    "cancelled": sum(1 for t in arch["archive"]["tasks"] if t["status"] == "cancelled")
}
save(ARCHIVE, arch)

# обновляем taskboard.json
d["taskboard"]["tasks"] = to_keep
by_status, by_priority, by_column = {}, {}, {}
for t in to_keep:
    by_status[t["status"]] = by_status.get(t["status"], 0) + 1
    by_priority[t["priority"]] = by_priority.get(t["priority"], 0) + 1
    col = t.get("metadata", {}).get("column", "—")
    by_column[col] = by_column.get(col, 0) + 1

d["taskboard"]["counters"] = {
    "total": len(to_keep),
    "by_status": by_status,
    "by_priority": by_priority,
    "by_column": by_column,
    "by_phase": {"phase_0": len(to_keep)}
}
d["taskboard"]["updated"] = TODAY
save(TB, d)

print(f"\nOK — архивировано: {added}")
print(f"  Активных: {len(to_keep)}")
print(f"  В архиве: {arch['archive']['total']}")
