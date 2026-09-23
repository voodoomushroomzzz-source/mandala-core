import io, json, time, urllib.request
TOKEN = io.open("notion_token.txt", encoding="utf-8").read().strip()
DB = "f6ffa784e7594df9add4fd1c697d4ada"
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

FIXES = {
    "Зона посадки Нижка: перекомпоновка (проект)": "K-064",
    "Уличная вывеска Нижка: новая (проект)": "K-065",
}

for p in query_all():
    props = p.get("properties", {})
    title = "".join(i["plain_text"] for i in (props.get("Название", {}).get("title") or [])) or None
    if title not in FIXES:
        continue
    new_id = FIXES[title]
    api(f"pages/{p['id']}", "PATCH", {
        "properties": {"ID": {"rich_text": [{"text": {"content": new_id}}]}}
    })
    print(f"OK: {new_id} -> {title}")
    time.sleep(0.35)
