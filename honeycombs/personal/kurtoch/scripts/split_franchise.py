#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Разбивка franchise.json на модули: taskboard.json, team.json, knowledge_base.json.
Пересобирает kurtoch/index.json -> v2.0.0.
franchise.json НЕ трогает, НЕ удаляет, НЕ коммитит."""
import io, json, os

HERE = os.path.dirname(os.path.abspath(__file__))
KURTOCH = os.path.dirname(HERE)
FRANCHISE = os.path.join(KURTOCH, "franchise.json")
INDEX = os.path.join(KURTOCH, "index.json")
TODAY = "2026-09-23"

def load(p):
    with io.open(p, encoding="utf-8") as f:
        return json.load(f)

def save(p, data):
    with io.open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    size = os.path.getsize(p)
    print(f"  записан: {os.path.relpath(p, KURTOCH)} ({size} байт)")

f = load(FRANCHISE)
old_index = load(INDEX)
print("Читаю franchise.json и index.json...")

# =========================================================
# 1. taskboard.json
# =========================================================
taskboard_module = {
    "identity": {
        "module_id": "KURTOCH-TASKBOARD-001",
        "name": "Kurtoch — Taskboard",
        "version": f["taskboard"]["version"],
        "created": f["taskboard"]["created"],
        "updated": TODAY,
        "layer": 2,
        "type": "taskboard_module",
        "description": "База задач Куртош + крупные вехи. Синхронизируется с Notion Taskboard по API.",
        "status": "active",
        "priority": "critical",
        "parent": "index.json",
        "resonance": "100%"
    },
    "taskboard": f["taskboard"],
    "milestones": f["milestones"],
    "navigation": {
        "parent": "honeycombs/personal/kurtoch/index.json",
        "siblings": ["team.json", "knowledge_base.json"],
        "external": ["Notion Taskboard: https://app.notion.com/p/Taskboard-aaa1aec62ffe49ab8c393edd4132c1d1"]
    },
    "notion_sync": f["taskboard"]["notion_sync"],
    "sync_rule": "Mandala (taskboard.json) — эталон. Notion Taskboard — визуальное зеркало."
}
save(os.path.join(KURTOCH, "taskboard.json"), taskboard_module)

# =========================================================
# 2. team.json
# =========================================================
team_module = {
    "identity": {
        "module_id": "KURTOCH-TEAM-001",
        "name": "Kurtoch — Team Roster",
        "version": "v1.0.0",
        "created": TODAY,
        "updated": TODAY,
        "layer": 2,
        "type": "team_module",
        "description": "Картотека сотрудников Куртош. 16 человек. Синхронизируется с Notion Team (в будущем).",
        "status": "active",
        "priority": "high",
        "parent": "index.json",
        "resonance": "100%"
    },
    "team_roster": f["team_roster"],
    "navigation": {
        "parent": "honeycombs/personal/kurtoch/index.json",
        "siblings": ["taskboard.json", "knowledge_base.json"]
    },
    "sync_rule": "Mandala (team.json) — эталон. Notion Team — визуальное зеркало (когда создадим базу)."
}
save(os.path.join(KURTOCH, "team.json"), team_module)

# =========================================================
# 3. knowledge_base.json
# =========================================================
kb_sections = f.get("workspace_mirror", {}).get("sections", {}).get("knowledge_base", {}).get("sections", {})
kb_module = {
    "identity": {
        "module_id": "KURTOCH-KB-001",
        "name": "Kurtoch — Knowledge Base",
        "version": "v1.0.0",
        "created": TODAY,
        "updated": TODAY,
        "layer": 2,
        "type": "knowledge_base_module",
        "description": "База знаний Куртош: чек-листы, регламенты, техкарты, обучение, ЦУ. Пока структура, наполнение — впереди.",
        "status": "active",
        "priority": "critical",
        "parent": "index.json",
        "resonance": "100%"
    },
    "knowledge_base_plan": f.get("knowledge_base_plan", {}),
    "sections": kb_sections,
    "content": {},
    "navigation": {
        "parent": "honeycombs/personal/kurtoch/index.json",
        "siblings": ["taskboard.json", "team.json"]
    },
    "status_note": "Структура готова. Содержимое добавляется постепенно, по мере сбора у команды."
}
save(os.path.join(KURTOCH, "knowledge_base.json"), kb_module)

# =========================================================
# 4. index.json -> v2.0.0
# =========================================================
new_index = dict(old_index)

# identity
new_index["identity"]["version"] = "v2.0.0"
new_index["identity"]["updated"] = TODAY
new_index["identity"]["description"] = (
    "Хаб проекта 'Куртош' — кризис-менеджмент, операционная система, франшиза. "
    "Входная точка: контекст, инструкции, ссылки на модули. "
    "Данные разбиты: taskboard.json, team.json, knowledge_base.json."
)

# содержимое: модули вместо franchise
new_index["contents"] = {
    "taskboard.json": {
        "description": "База задач Куртош + крупные вехи.",
        "purpose": "Задачи, milestones, синхронизация с Notion.",
        "version": f["taskboard"]["version"],
        "tasks_count": f["taskboard"]["counters"]["total"]
    },
    "team.json": {
        "description": "Картотека сотрудников.",
        "purpose": "Все 16 сотрудников: контакты, навыки, статусы.",
        "version": "v1.0.0",
        "total_employees": f["team_roster"]["total_employees"]
    },
    "knowledge_base.json": {
        "description": "База знаний: чек-листы, регламенты, техкарты, обучение, ЦУ.",
        "purpose": "Структура готова, наполнение — по мере сбора.",
        "version": "v1.0.0",
        "sections_count": len(kb_sections)
    }
}

# контекстные блоки из franchise — в index
new_index["work_context"] = {
    "work_id": f.get("work_id"),
    "status": f.get("status"),
    "priority": f.get("priority"),
    "horizon": f.get("horizon"),
    "owner": f.get("owner"),
    "role": f.get("role"),
    "key_contacts": f.get("key_contacts"),
    "directive_used": f.get("directive_used")
}
new_index["offer"] = f.get("offer")
new_index["success_criteria_3_months"] = f.get("success_criteria_3_months")
new_index["hot_zones"] = f.get("hot_zones")
new_index["context"] = f.get("context")
new_index["plan"] = f.get("plan")
new_index["success_metrics"] = f.get("success_metrics")
new_index["current_status"] = f.get("current_status")
new_index["risks"] = f.get("risks")
new_index["history"] = f.get("history")
new_index["workspace_mirror"] = f.get("workspace_mirror")
new_index["compensation_system"] = f.get("compensation_system")

# навигация
new_index["navigation"]["children"] = [
    "index.json",
    "taskboard.json",
    "team.json",
    "knowledge_base.json",
    "scripts/",
    "_logs/",
    "_snapshots/"
]

# health
new_index["health"] = {
    "status": "healthy",
    "last_check": TODAY,
    "notes": "v2.0.0: разбит franchise.json на 3 модуля: taskboard, team, knowledge_base. Контекст перенесён в index. franchise.json пока на месте (удалим после подтверждения)."
}

save(INDEX, new_index)

print("\nOK — разбивка завершена.")
print("franchise.json НЕ тронут (удалим отдельным шагом).")
print("\nСледующий шаг: проверь глазами taskboard.json, team.json, knowledge_base.json, index.json.")
