#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Push taskboard.json -> Notion.
Обновляет: ID, Столбец, Статус, Закрыта, Срочность, Дедлайн.
Создаёт новые задачи, если в Mandala есть K-ID, которого нет в Notion.
Идемпотентно."""
import io, json, os, sys, time, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
KURTOCH = os.path.dirname(HERE)
TOKEN_FILE = os.path.join(HERE, "notion_token.txt")
TB_FILE = os.path.join(KURTOCH, "taskboard.json")
DB = "f6ffa784e7594df9add4fd1c697d4ada"

# --- Маппинг priority -> Срочность (Notion select) ---
PRIORITY_TO_URGENCY = {
    "critical": "\U0001F534 \u0413\u043e\u0440\u0438\u0442",
    "high":     "\U0001F7E1 \u0421\u0440\u0435\u0434\u043d\u044f\u044f",
    "medium":   "\U0001F535 \u0424\u043e\u043d",
    "low":      "\U0001F535 \u0424\u043e\u043d",
}
DEFAULT_ASSIGNEE = "\u0414\u043c\u0438\u0442\u0440\u0438\u0439 (\u0443\u043f\u0440\u0430\u0432\u043b\u044f\u044e\u0449\u0438\u0439)"

def build_milestone_blocks(task):
    """Строит структурированные блоки для milestone с payment_tracker."""
    blocks = []
    meta = task.get("metadata", {})
    phases = meta.get("phases", [])
    tracker = meta.get("tracker", {})
    if not phases:
        return None
    for ph in phases:
        # heading
        h = f"\u0424\u0430\u0437\u0430 {ph.get('phase','?')}: {ph.get('name','')} ({ph.get('period','')})"
        blocks.append({
            "object": "block", "type": "heading_3",
            "heading_3": {"rich_text": [{"text": {"content": h}}]}
        })
        # summary
        summary = f"\u0412\u0441\u0435\u0433\u043e: {ph.get('total',0):,} \u20bd  \u00b7  \u041a\u0435\u0448: {ph.get('cash',0):,} \u20bd  \u00b7  \u041d\u0430\u043a\u043e\u043f\u043b\u0435\u043d\u0438\u0435: {ph.get('accumulation',0):,} \u20bd".replace(",", " ")
        blocks.append({
            "object": "block", "type": "paragraph",
            "paragraph": {"rich_text": [{"text": {"content": summary}}]}
        })
        # to-do
        for p in ph.get("payments", []):
            check = p.get("status") == "paid"
            line = f"{p.get('date','')} \u2014 {p.get('amount',0):,} \u20bd \u2014 {p.get('type','')}".replace(",", " ")
            blocks.append({
                "object": "block", "type": "to_do",
                "to_do": {
                    "rich_text": [{"text": {"content": line}}],
                    "checked": check
                }
            })
    # итого
    blocks.append({
        "object": "block", "type": "divider", "divider": {}
    })
    total_line = f"\u0418\u0442\u043e\u0433\u043e: {tracker.get('total_planned',0):,} \u20bd \u00b7 \u041a\u0435\u0448: {tracker.get('total_cash_planned',0):,} \u20bd \u00b7 \u041d\u0430\u043a\u043e\u043f\u043b\u0435\u043d\u0438\u0435: {tracker.get('total_accumulation_planned',0):,} \u20bd".replace(",", " ")
    blocks.append({
        "object": "block", "type": "heading_3",
        "heading_3": {"rich_text": [{"text": {"content": total_line}}]}
    })
    return blocks


H = {"Authorization": f"Bearer {io.open(TOKEN_FILE, encoding='utf-8').read().strip()}",
     "Notion-Version": "2022-06-28", "Content-Type": "application/json"}

def api(path, method="GET", body=None, retries=3):
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                f"https://api.notion.com/v1/{path}",
                data=json.dumps(body).encode() if body else None,
                method=method, headers=H)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())
        except (urllib.error.URLError, OSError) as e:
            last_err = e
            wait = 2 ** attempt
            print(f"  ! network error ({e.__class__.__name__}), retry in {wait}s...")
            time.sleep(wait)
    raise last_err

def prop_text(p, name):
    x = (p.get("properties") or {}).get(name)
    if not x: return None
    t = x.get("type")
    if t == "title": return "".join(i["plain_text"] for i in x["title"]) or None
    if t == "rich_text": return "".join(i["plain_text"] for i in x["rich_text"]) or None
    if t == "select": return (x["select"] or {}).get("name")
    if t == "checkbox": return x["checkbox"]
    if t == "date": return (x["date"] or {}).get("start")
    return None

def normalize(name):
    if not name: return name
    return name.replace(" (проект)", "").strip()

def build_title(t):
    """Notion-префикс для cancelled-задач. Mandala хранит чистый title."""
    if t.get("status") != "cancelled":
        return t["title"]
    meta = t.get("metadata", {}) or {}
    if meta.get("merged_into"):
        return "\U0001F4E6 \u041f\u043e\u0433\u043b\u043e\u0449\u0435\u043d\u0430: " + t["title"]
    return "\u274C \u041e\u0442\u043c\u0435\u043d\u0435\u043d\u0430: " + t["title"]

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

# ===== 1. Читаем Mandala (активные + архив) =====
ARCHIVE_FILE = os.path.join(KURTOCH, "taskboard_archive.json")
f = json.load(io.open(TB_FILE, encoding="utf-8"))
tasks = list(f["taskboard"]["tasks"])
if os.path.exists(ARCHIVE_FILE):
    with io.open(ARCHIVE_FILE, encoding="utf-8") as af:
        arch = json.load(af)
    tasks.extend(arch["archive"]["tasks"])
    print(f"  + архив: {len(arch['archive']['tasks'])} задач")
by_title_norm = {normalize(t["title"]): t for t in tasks}
by_id_mandala = {t["id"]: t for t in tasks}
print(f"Mandala: {len(tasks)} задач")

# ===== 2. Читаем Notion =====
pages = query_all()
print(f"Notion: {len(pages)} страниц\n")

notion_by_id = {}      # K-ID -> page
notion_by_title = {}   # normalized title -> page
for p in pages:
    pid = prop_text(p, "ID")
    title = normalize(prop_text(p, "Название"))
    if pid: notion_by_id[pid] = p
    if title: notion_by_title[title] = p

updated_status, updated_id, updated_col, updated_date, updated_title, created = 0, 0, 0, 0, 0, 0
no_match = []

for t in tasks:
    tid = t["id"]
    title_norm = normalize(t["title"])
    p = notion_by_id.get(tid) or notion_by_title.get(title_norm)

    if not p:
        # создаём новую задачу
        body = {
            "parent": {"database_id": DB},
            "properties": {
                "Название": {"title": [{"text": {"content": build_title(t)}}]},
                "ID": {"rich_text": [{"text": {"content": tid}}]},
                "Статус": {"select": {"name": t["status"]}},
                "Столбец": {"select": {"name": t["metadata"]["column"]}},
                "Срочность": {"select": {"name": PRIORITY_TO_URGENCY.get(t.get("priority", "medium"), PRIORITY_TO_URGENCY["medium"])}},
                "Ответственный": {"select": {"name": t.get("metadata", {}).get("assignee") or DEFAULT_ASSIGNEE}},
                "Закрыта": {"checkbox": t["status"] in ("done", "cancelled")},
            }
        }
        # milestones — структурированные блоки
        ms_blocks = build_milestone_blocks(t) if t.get("metadata", {}).get("subtype") == "payment_tracker" else None
        if ms_blocks:
            body["children"] = ms_blocks
        if t.get("deadline"):
            body["properties"]["Дедлайн"] = {"date": {"start": t["deadline"]}}
        if t.get("description") and not ms_blocks:
            body["children"] = [{"object": "block", "type": "paragraph",
                "paragraph": {"rich_text": [{"text": {"content": t["description"]}}]}}]
        api("pages", "POST", body)
        created += 1
        print(f"  [NEW {tid}] {t['title']}")
        time.sleep(0.35)
        continue

    # обновляем свойства, если отличаются
    props = {}
    cur_status = prop_text(p, "Статус")
    cur_closed = prop_text(p, "Закрыта")
    cur_id = prop_text(p, "ID")
    cur_col = prop_text(p, "Столбец")
    cur_dl = prop_text(p, "Дедлайн")

    cur_title = prop_text(p, "Название")
    need_title = build_title(t)
    if cur_title != need_title:
        props["Название"] = {"title": [{"text": {"content": need_title}}]}
        updated_title += 1

    need_closed = t["status"] in ("done", "cancelled")
    if cur_status != t["status"]:
        props["Статус"] = {"select": {"name": t["status"]}}
        updated_status += 1
    if cur_closed != need_closed:
        props["Закрыта"] = {"checkbox": need_closed}
    if cur_id != tid:
        props["ID"] = {"rich_text": [{"text": {"content": tid}}]}
        updated_id += 1
    if cur_col != t["metadata"]["column"]:
        props["Столбец"] = {"select": {"name": t["metadata"]["column"]}}
        updated_col += 1
    if t.get("deadline") and cur_dl != t["deadline"]:
        props["Дедлайн"] = {"date": {"start": t["deadline"]}}
        updated_date += 1

    # Срочность и Ответственный (всегда проверяем)
    cur_urg = prop_text(p, "Срочность")
    need_urg = PRIORITY_TO_URGENCY.get(t.get("priority", "medium"), PRIORITY_TO_URGENCY["medium"])
    if cur_urg != need_urg:
        props["Срочность"] = {"select": {"name": need_urg}}
    cur_resp = prop_text(p, "Ответственный")
    need_resp = t.get("metadata", {}).get("assignee") or DEFAULT_ASSIGNEE
    if cur_resp != need_resp:
        props["Ответственный"] = {"select": {"name": need_resp}}

    if props:
        api(f"pages/{p['id']}", "PATCH", {"properties": props})
        tag = ", ".join(props.keys())
        print(f"  [{tid} | {tag}] {t['title']}")
        time.sleep(0.35)

# проверка обратного — что в Notion есть, но в Mandala нет
notion_ids = {prop_text(p, "ID") for p in pages if prop_text(p, "ID")}
mandala_ids = set(by_id_mandala.keys())
orphans = notion_ids - mandala_ids

print(f"\n=== Итог ===")
print(f"  Обновлено Статус: {updated_status}")
print(f"  Обновлено ID: {updated_id}")
print(f"  Обновлено Столбец: {updated_col}")
print(f"  Обновлено Дедлайн: {updated_date}")
print(f"  Обновлено Название (префикс): {updated_title}")
print(f"  Создано новых: {created}")
if orphans:
    print(f"  В Notion есть, в Mandala нет: {sorted(orphans)}")
