#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Notion Sync — один скрипт для всех команд.

Использование:
    python3 notion_sync.py list
    python3 notion_sync.py pull_taskboard

Токен читается из scripts/notion_token.txt (в .gitignore, в репу не попадает).
"""
import io, json, os, sys, time, urllib.request, urllib.error
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
KURTOCH = os.path.dirname(HERE)
TOKEN_FILE = os.path.join(HERE, "notion_token.txt")
SNAPSHOTS = os.path.join(KURTOCH, "_snapshots")
LOGS = os.path.join(KURTOCH, "_logs")

# Базы Notion
DATABASES = {
    "taskboard": "f6ffa784e7594df9add4fd1c697d4ada",
}

# Максимум снапшотов на одну базу
MAX_SNAPSHOTS = 10

def load_token():
    if not os.path.isfile(TOKEN_FILE):
        fail(f"Токен не найден: {TOKEN_FILE}")
    with io.open(TOKEN_FILE, "r", encoding="utf-8") as f:
        t = f.read().strip()
    if not t or t.startswith("PASTE_") or t.startswith("ВСТАВЬ"):
        fail("Токен не заменён — всё ещё заглушка.")
    return t

def api(path, token, method="GET", body=None):
    url = f"https://api.notion.com/v1/{path}"
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        fail(f"HTTP {e.code}: {e.read().decode('utf-8')}")

def fail(msg):
    print(f"❌ {msg}")
    sys.exit(1)

def ok(msg):
    print(f"✅ {msg}")

def query_all(db_id, token):
    results = []
    cursor = None
    while True:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        data = api(f"databases/{db_id}/query", token, method="POST", body=body)
        results.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
        time.sleep(0.4)
    return results

def extract(page):
    p = page.get("properties", {})
    def txt(prop):
        if not prop:
            return None
        t = prop.get("type")
        if t == "title":
            return "".join(x["plain_text"] for x in prop["title"]) or None
        if t == "rich_text":
            return "".join(x["plain_text"] for x in prop["rich_text"]) or None
        if t == "select":
            return (prop["select"] or {}).get("name")
        if t == "checkbox":
            return prop["checkbox"]
        if t == "date":
            d = prop["date"] or {}
            return d.get("start")
        if t == "last_edited_time":
            return prop.get("last_edited_time")
        return None
    return {
        "notion_page_id": page["id"],
        "title": txt(p.get("Название")),
        "status": txt(p.get("Статус")),
        "column": txt(p.get("Столбец")),
        "urgency": txt(p.get("Срочность")),
        "assignee": txt(p.get("Ответственный")),
        "deadline": txt(p.get("Дедлайн")),
        "closed": txt(p.get("Закрыта")),
        "closed_at": txt(p.get("Дата закрытия")),
        "description": txt(p.get("Описание")),
    }

def rotate_snapshots(prefix):
    files = sorted(
        [f for f in os.listdir(SNAPSHOTS) if f.startswith(prefix) and f.endswith(".json")]
    )
    while len(files) >= MAX_SNAPSHOTS:
        old = files.pop(0)
        os.remove(os.path.join(SNAPSHOTS, old))
        print(f"  удалён старый снапшот: {old}")

def cmd_list(token):
    print("Доступные команды:")
    print("  list             — этот список")
    print("  pull_taskboard   — выгрузить задачи Notion в снапшот")
    print("  db_taskboard     — показать метаданные базы Taskboard")

def cmd_db_taskboard(token):
    db_id = DATABASES["taskboard"]
    data = api(f"databases/{db_id}", token)
    ok(f"База: {(data.get('title') or [{}])[0].get('plain_text', '—')}")
    print("Свойства:")
    for name, prop in data.get("properties", {}).items():
        print(f"  - {name}: {prop.get('type')}")

def cmd_pull_taskboard(token):
    db_id = DATABASES["taskboard"]
    print("Читаю Taskboard из Notion...")
    pages = query_all(db_id, token)
    print(f"  получено страниц: {len(pages)}")
    items = [extract(p) for p in pages]
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    prefix = f"notion_taskboard_"
    rotate_snapshots(prefix)
    path = os.path.join(SNAPSHOTS, f"{prefix}{ts}.json")
    with io.open(path, "w", encoding="utf-8") as f:
        json.dump({"timestamp": ts, "count": len(items), "items": items}, f, ensure_ascii=False, indent=2)
    ok(f"Снапшот сохранён: {os.path.relpath(path, KURTOCH)}")
    by_status, by_column = {}, {}
    for it in items:
        by_status[it["status"]] = by_status.get(it["status"], 0) + 1
        by_column[it["column"]] = by_column.get(it["column"], 0) + 1
    print("\nПо статусам:")
    for k, v in sorted(by_status.items(), key=lambda x: -x[1]):
        print(f"  {k or '—'}: {v}")
    print("\nПо столбцам:")
    for k, v in sorted(by_column.items(), key=lambda x: -x[1]):
        print(f"  {k or '—'}: {v}")

COMMANDS = {
    "list": cmd_list,
    "db_taskboard": cmd_db_taskboard,
    "pull_taskboard": cmd_pull_taskboard,
}

def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print("Использование: python3 notion_sync.py <command>")
        print("Доступные команды:", ", ".join(COMMANDS.keys()))
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "list":
        COMMANDS[cmd](None)
        return
    token = load_token()
    COMMANDS[cmd](token)

if __name__ == "__main__":
    main()
