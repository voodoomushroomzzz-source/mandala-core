#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Выносит done + cancelled из taskboard.json в taskboard_archive.json.
Режимы:
  --dry-run  (по умолчанию) — показать, что будет вынесено
  --apply                    — применить
"""
import io, json, os, sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
KURTOCH = os.path.dirname(HERE)
TB = os.path.join(KURTOCH, "taskboard.json")
ARCHIVE = os.path.join(KURTOCH, "taskboard_archive.json")
TODAY = "2026-09-23"
MODE = sys.argv[1] if len(sys.argv) > 1 else "--dry-run"

with io.open(TB, encoding="utf-8") as f:
    d = json.load(f)

tasks = d["taskboard"]["tasks"]
ARCHIVE_STATUSES = {"done", "cancelled"}

to_archive = [t for t in tasks if t["status"] in ARCHIVE_STATUSES]
to_keep = [t for t in tasks if t["status"] not in ARCHIVE_STATUSES]

print(f"Режим: {MODE}")
print(f"  Активных (останутся): {len(to_keep)}")
print(f"  В архив: {len(to_archive)}")
print(f"    done: {sum(1 for t in to_archive if t['status'] == 'done')}")
print(f"    cancelled: {sum(1 for t in to_archive if t['status'] == 'cancelled')}")
print(f"\nСписок задач в архив:")
for t in to_archive:
    print(f"  [{t['status']}] {t['id']}: {t['title'][:60]}")

if MODE != "--apply":
    print(f"\nDRY-RUN — файлы не изменены. Для применения: python3 split_archive.py --apply")
    sys.exit(0)

# ===== APPLY =====
# 1. Читаем существующий архив, если есть
if os.path.exists(ARCHIVE):
    with io.open(ARCHIVE, encoding="utf-8") as f:
        arch = json.load(f)
    existing_ids = {t["id"] for t in arch["archive"]["tasks"]}
else:
    arch = {
        "identity": {
            "module_id": "KURTOCH-TASKBOARD-ARCHIVE-001",
            "name": "Kurtoch — Taskboard Archive",
            "version": "v1.0.0",
            "created": TODAY,
            "updated": TODAY,
            "type": "taskboard_archive",
            "parent": "taskboard.json",
            "description": "Архив завершённых задач (done + cancelled).",
            "status": "active",
            "priority": "medium"
        },
        "archive": {
            "description": "Завершённые задачи. Синхронизируются с Notion тем же скриптом.",
            "tasks": []
        },
        "navigation": {
            "parent": "honeycombs/personal/kurtoch/index.json",
            "sibling": "taskboard.json"
        }
    }
    existing_ids = set()

# 2. Переносим новые задачи в архив
added = 0
for t in to_archive:
    t_arch = dict(t)
    t_arch["archived_at"] = TODAY
    if t["id"] not in existing_ids:
        arch["archive"]["tasks"].append(t_arch)
        added += 1

# 3. Обновляем архив
arch["identity"]["updated"] = TODAY
arch["archive"]["total"] = len(arch["archive"]["tasks"])
arch["archive"]["by_status"] = {
    "done": sum(1 for t in arch["archive"]["tasks"] if t["status"] == "done"),
    "cancelled": sum(1 for t in arch["archive"]["tasks"] if t["status"] == "cancelled")
}

# 4. Записываем архив
with io.open(ARCHIVE, "w", encoding="utf-8") as f:
    json.dump(arch, f, ensure_ascii=False, indent=2)
    f.write("\n")
print(f"\n  записан: taskboard_archive.json ({os.path.getsize(ARCHIVE)} байт, добавлено {added})")

# 5. Обновляем taskboard.json — оставляем только активные
d["taskboard"]["tasks"] = to_keep

# пересчёт counters
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
d["taskboard"]["archive_ref"] = "taskboard_archive.json"
d["taskboard"]["updated"] = TODAY

with io.open(TB, "w", encoding="utf-8") as f:
    json.dump(d, f, ensure_ascii=False, indent=2)
    f.write("\n")
print(f"  записан: taskboard.json ({os.path.getsize(TB)} байт, активных {len(to_keep)})")

print(f"\nOK — архив применён")
