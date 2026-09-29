#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Push taskboard.json -> Notion.
Обновляет: ID, Столбец, Статус, Закрыта, Срочность, Дедлайн, Описание (blocks).
Создаёт новые задачи, если в Mandala есть K-ID, которого нет в Notion.
Идемпотентно.
"""
import io, json, os, re, sys, time, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
KURTOCH = os.path.dirname(HERE)
TOKEN_FILE = os.path.join(HERE, "notion_token.txt")
TB_FILE = os.path.join(KURTOCH, "taskboard.json")
DB = "f6ffa784e7594df9add4fd1c697d4ada"

PRIORITY_TO_URGENCY = {
    "critical": "\U0001F534 \u0413\u043e\u0440\u0438\u0442",
    "high":     "\U0001F7E1 \u0421\u0440\u0435\u0434\u043d\u044f\u044f",
    "medium":   "\U0001F535 \u0424\u043e\u043d",
    "low":      "\U0001F535 \u0424\u043e\u043d",
}
DEFAULT_ASSIGNEE = "\u0414\u043c\u0438\u0442\u0440\u0438\u0439 (\u0443\u043f\u0440\u0430\u0432\u043b\u044f\u044e\u0449\u0438\u0439)"


def build_milestone_blocks(task):
    blocks = []
    meta = task.get("metadata", {})
    phases = meta.get("phases", [])
    tracker = meta.get("tracker", {})
    if not phases:
        return None
    for ph in phases:
        h = f"\u0424\u0430\u0437\u0430 {ph.get('phase','?')}: {ph.get('name','')} ({ph.get('period','')})"
        blocks.append({"object": "block", "type": "heading_3",
                       "heading_3": {"rich_text": [{"text": {"content": h}}]}})
        summary = f"\u0412\u0441\u0435\u0433\u043e: {ph.get('total',0):,} \u20bd \u00b7 \u041a\u0435\u0448: {ph.get('cash',0):,} \u20bd \u00b7 \u041d\u0430\u043a\u043e\u043f\u043b\u0435\u043d\u0438\u0435: {ph.get('accumulation',0):,} \u20bd".replace(",", " ")
        blocks.append({"object": "block", "type": "paragraph",
                       "paragraph": {"rich_text": [{"text": {"content": summary}}]}})
        for p in ph.get("payments", []):
            check = p.get("status") == "paid"
            line = f"{p.get('date','')} \u2014 {p.get('amount',0):,} \u20bd \u2014 {p.get('type','')}".replace(",", " ")
            blocks.append({"object": "block", "type": "to_do",
                           "to_do": {"rich_text": [{"text": {"content": line}}], "checked": check}})
    blocks.append({"object": "block", "type": "divider", "divider": {}})
    total_line = f"\u0418\u0442\u043e\u0433\u043e: {tracker.get('total_planned',0):,} \u20bd \u00b7 \u041a\u0435\u0448: {tracker.get('total_cash_planned',0):,} \u20bd \u00b7 \u041d\u0430\u043a\u043e\u043f\u043b\u0435\u043d\u0438\u0435: {tracker.get('total_accumulation_planned',0):,} \u20bd".replace(",", " ")
    blocks.append({"object": "block", "type": "heading_3",
                   "heading_3": {"rich_text": [{"text": {"content": total_line}}]}})
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
    if t.get("status") != "cancelled":
        return t["title"]
    meta = t.get("metadata", {}) or {}
    if meta.get("merged_into"):
        return "\U0001F4E6 \u041f\u043e\u0433\u043b\u043e\u0449\u0435\u043d\u0430: " + t["title"]
    return "\u274C \u041e\u0442\u043c\u0435\u043d\u0435\u043d\u0430: " + t["title"]


def normalize_desc(text):
    """Нормализация для честного сравнения описаний.
    Схлопывает \n\n+ в один \n, множественные пробелы в один."""
    if not text:
        return ""
    t = text.replace("\r\n", "\n")
    t = re.sub(r"\n\s*\n+", "\n", t)
    t = re.sub(r"[ \t]+", " ", t)
    return t.strip()


def get_page_description(page_id):
    try:
        r = api(f"blocks/{page_id}/children?page_size=100")
    except Exception:
        return ""
    parts = []
    for b in r.get("results", []):
        btype = b.get("type")
        if btype == "paragraph":
            rt = b.get("paragraph", {}).get("rich_text", [])
            parts.append("".join(x.get("plain_text", "") for x in rt))
        elif btype == "to_do":
            rt = b.get("to_do", {}).get("rich_text", [])
            parts.append("".join(x.get("plain_text", "") for x in rt))
    return "\n".join(parts).strip()


def delete_all_children(page_id):
    while True:
        r = api(f"blocks/{page_id}/children?page_size=100")
        results = r.get("results", [])
        if not results:
            break
        for b in results:
            try:
                api(f"blocks/{b['id']}", "DELETE")
            except Exception:
                pass
        time.sleep(0.2)


def set_page_description(page_id, text):
    delete_all_children(page_id)
    if not text:
        return
    chunks = []
    for para in text.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        while len(para) > 1900:
            chunks.append(para[:1900])
            para = para[1900:]
        if para:
            chunks.append(para)
    if not chunks:
        return
    children = [{"object": "block", "type": "paragraph",
                 "paragraph": {"rich_text": [{"text": {"content": c}}]}}
                for c in chunks[:100]]
    api(f"blocks/{page_id}/children", "PATCH", {"children": children})


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


ARCHIVE_FILE = os.path.join(KURTOCH, "taskboard_archive.json")
f = json.load(io.open(TB_FILE, encoding="utf-8"))
tasks = list(f["taskboard"]["tasks"])
if os.path.exists(ARCHIVE_FILE):
    with io.open(ARCHIVE_FILE, encoding="utf-8") as af:
        arch = json.load(af)
    tasks.extend(arch["archive"]["tasks"])
    print(f"  + архив: {len(arch['archive']['tasks'])} задач")
by_id_mandala = {t["id"]: t for t in tasks}
print(f"Mandala: {len(tasks)} задач")

pages = query_all()
print(f"Notion: {len(pages)} страниц\n")

notion_by_id = {}
notion_by_title = {}
for p in pages:
    pid = prop_text(p, "ID")
    title = normalize(prop_text(p, "Название"))
    if pid: notion_by_id[pid] = p
    if title: notion_by_title[title] = p

updated_status, updated_id, updated_col, updated_date, updated_title, updated_desc, created = 0, 0, 0, 0, 0, 0, 0

for t in tasks:
    tid = t["id"]
    title_norm = normalize(t["title"])
    p = notion_by_id.get(tid) or notion_by_title.get(title_norm)

    if not p:
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
        ms_blocks = build_milestone_blocks(t) if t.get("metadata", {}).get("subtype") == "payment_tracker" else None
        if t.get("deadline"):
            body["properties"]["Дедлайн"] = {"date": {"start": t["deadline"]}}
        if ms_blocks:
            body["children"] = ms_blocks
        elif t.get("description"):
            body["children"] = [{"object": "block", "type": "paragraph",
                                 "paragraph": {"rich_text": [{"text": {"content": t["description"]}}]}}]
        api("pages", "POST", body)
        created += 1
        print(f"  [NEW {tid}] {t['title']}")
        time.sleep(0.35)
        continue

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

    # ---- ОПИСАНИЕ ----
    need_desc = (t.get("description") or "").strip()
    if need_desc and t.get("metadata", {}).get("subtype") != "payment_tracker":
        cur_desc = get_page_description(p["id"])
        if normalize_desc(cur_desc) != normalize_desc(need_desc):
            set_page_description(p["id"], need_desc)
            updated_desc += 1
            print(f"  [{tid} | Описание обновлено] {t['title']}")
            time.sleep(0.35)

notion_ids = {prop_text(p, "ID") for p in pages if prop_text(p, "ID")}
mandala_ids = set(by_id_mandala.keys())
orphans = notion_ids - mandala_ids

print(f"\n=== Итог ===")
print(f"  Обновлено Статус: {updated_status}")
print(f"  Обновлено ID: {updated_id}")
print(f"  Обновлено Столбец: {updated_col}")
print(f"  Обновлено Дедлайн: {updated_date}")
print(f"  Обновлено Название (префикс): {updated_title}")
print(f"  Обновлено Описание: {updated_desc}")
print(f"  Создано новых: {created}")
if orphans:
    print(f"  В Notion есть, в Mandala нет: {sorted(orphans)}")
