import io, json, os, sys, time, urllib.request, urllib.error

TOKEN = io.open("notion_token.txt", encoding="utf-8").read().strip()
DB = "f6ffa784e7594df9add4fd1c697d4ada"
FRANCHISE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "franchise.json")
FRANCHISE = os.path.abspath(FRANCHISE)
H = {"Authorization": f"Bearer {TOKEN}", "Notion-Version": "2022-06-28", "Content-Type": "application/json"}

def api(path, method="GET", body=None):
    req = urllib.request.Request(
        f"https://api.notion.com/v1/{path}",
        data=json.dumps(body).encode() if body else None,
        method=method, headers=H,
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode())

def query_all():
    out, cursor = [], None
    while True:
        body = {"page_size": 100}
        if cursor: body["start_cursor"] = cursor
        d = api(f"databases/{DB}/query", "POST", body)
        out.extend(d.get("results", []))
        if not d.get("has_more"): break
        cursor = d.get("next_cursor")
        time.sleep(0.35)
    return out

def prop_text(p, name):
    x = (p.get("properties") or {}).get(name)
    if not x: return None
    t = x.get("type")
    if t == "title": return "".join(i["plain_text"] for i in x["title"]) or None
    if t == "rich_text": return "".join(i["plain_text"] for i in x["rich_text"]) or None
    if t == "select": return (x["select"] or {}).get("name")
    return None

# --- 1. Читаем Mandala ---
f = json.load(io.open(FRANCHISE, encoding="utf-8"))
tasks = f["taskboard"]["tasks"]
by_title = {t["title"]: t["id"] for t in tasks}
print(f"Mandala: {len(tasks)} задач")

MILESTONE_IDS = {
    "Возрождение Нижки": "M-001",
    "Возрождение Центра": "M-002",
}
RECOLUMN = {
    "Зона посадки Нижка: перекомпоновка (проект)": "Операционка — Нижка",
    "Уличная вывеска Нижка: новая (проект)": "Операционка — Нижка",
}
ARCHIVE = {"Стратегия Нижка: 4 фазы"}

# --- 2. Читаем Notion ---
pages = query_all()
print(f"Notion: {len(pages)} страниц\n")

updated_id, updated_col, archived, no_match = 0, 0, 0, []

for p in pages:
    pid = p["id"]
    title = prop_text(p, "Название")
    if not title:
        continue

    # --- архивация ---
    if title in ARCHIVE:
        api(f"pages/{pid}", "PATCH", {"in_trash": True})
        archived += 1
        print(f"  [ARCHIVED] {title}")
        time.sleep(0.35)
        continue

    # --- ID ---
    new_id = None
    if title in MILESTONE_IDS:
        new_id = MILESTONE_IDS[title]
    elif title in by_title:
        new_id = by_title[title]
    else:
        no_match.append(title)

    # --- column ---
    new_col = RECOLUMN.get(title)

    patch_props = {}
    if new_id:
        current_id = prop_text(p, "ID")
        if current_id != new_id:
            patch_props["ID"] = {"rich_text": [{"text": {"content": new_id}}]}
    if new_col:
        current_col = prop_text(p, "Столбец")
        if current_col != new_col:
            patch_props["Столбец"] = {"select": {"name": new_col}}

    if patch_props:
        api(f"pages/{pid}", "PATCH", {"properties": patch_props})
        if "ID" in patch_props: updated_id += 1
        if "Столбец" in patch_props: updated_col += 1
        tag = []
        if "ID" in patch_props: tag.append(f"ID={new_id}")
        if "Столбец" in patch_props: tag.append(f"col={new_col}")
        print(f"  [{', '.join(tag)}] {title}")
        time.sleep(0.35)

print(f"\nИтог:")
print(f"  Обновлено ID: {updated_id}")
print(f"  Обновлено столбцов: {updated_col}")
print(f"  Архивировано: {archived}")
if no_match:
    print(f"  Без пары в Mandala: {len(no_match)}")
    for t in no_match:
        print(f"    - {t}")
