import io, json, sys, urllib.request
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

db = api(f"databases/{DB}")
props = db["properties"]
status_opts = [o["name"] for o in props.get("Статус", {}).get("select", {}).get("options", [])]
print("ID:", "есть" if "ID" in props else "НЕТ")
print("planning:", "есть" if "planning" in status_opts else "НЕТ")

patch = {"properties": {}}
if "ID" not in props:
    patch["properties"]["ID"] = {"rich_text": {}}
if "planning" not in status_opts:
    new_opts = [{"name": n, "color": "default"} for n in status_opts] + [{"name": "planning", "color": "blue"}]
    patch["properties"]["Статус"] = {"select": {"options": new_opts}}

if not patch["properties"]:
    print("Нечего менять — уже всё есть.")
    sys.exit(0)

print("Отправляю PATCH автоматически...")
r = api(f"databases/{DB}", "PATCH", patch)
p2 = r["properties"]
print("OK. Свойств:", len(p2))
print("ID:", "есть" if "ID" in p2 else "НЕТ")
print("Статусы:", [o["name"] for o in p2.get("Статус", {}).get("select", {}).get("options", [])])
