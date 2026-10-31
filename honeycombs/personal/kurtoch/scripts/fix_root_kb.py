#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import io, json, os, sys, time, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
KURTOCH = os.path.dirname(HERE)
TOKEN_FILE = os.path.join(HERE, "notion_token.txt")
INDEX_FILE = os.path.join(KURTOCH, "index.json")

TOKEN = io.open(TOKEN_FILE, encoding="utf-8").read().strip()
H = {"Authorization": f"Bearer {TOKEN}", "Notion-Version": "2026-03-11", "Content-Type": "application/json"}

def api(path, method="GET", body=None):
    req = urllib.request.Request(f"https://api.notion.com/v1/{path}", data=json.dumps(body).encode() if body else None, method=method, headers=H)
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return None

def get_children(block_id):
    out, cursor = [], None
    while True:
        path = f"blocks/{block_id}/children?page_size=100"
        if cursor: path += f"&start_cursor={cursor}"
        d = api(path)
        if not d: break
        out.extend(d.get("results", []))
        if not d.get("has_more"): break
        cursor = d.get("next_cursor")
        time.sleep(0.35)
    return out

def create_page(parent_id, title, icon=None):
    body = {"parent": {"page_id": parent_id}, "properties": {"title": [{"type": "text", "text": {"content": title}}]}}
    if icon: body["icon"] = {"type": "emoji", "emoji": icon}
    res = api("pages", method="POST", body=body)
    time.sleep(0.4)
    return res["id"] if res else None

with io.open(INDEX_FILE, encoding="utf-8") as f:
    idx = json.load(f)
links = idx["workspace_mirror"]["notion_links"]
old_main_id = links.get("old_main_id") # Это первая база (внутри Куртош & Кофе)
current_main_id = links["page_id"]     # Это матрешка (внутри old_main)

# 1. Узнаем ID корня "Куртош & Кофе"
root_parent_id = None
old_info = api(f"pages/{old_main_id}")
if old_info and old_info.get("parent", {}).get("type") == "page_id":
    root_parent_id = old_info["parent"]["page_id"]

if not root_parent_id:
    print("ERR: Could not find root parent. Aborting.")
    sys.exit(1)

# 2. Создаем АБСОЛЮТНО НОВУЮ страницу в корне
new_kb_id = create_page(root_parent_id, "База знаний", "📚")
if not new_kb_id:
    print("ERR: Failed to create new KB root page.")
    sys.exit(1)

# 3. Создаем 6 главных разделов
new_pages = {}
for title, icon in [("График", "📅"), ("Инструкции", "📋"), ("ТТК", "☕"), ("Обучение", "🎓"), ("Контакты", "📞"), ("Аварии", "🆘")]:
    pid = create_page(new_kb_id, title, icon)
    if pid: new_pages[title] = pid

# 4. Верстаем Главную
main_blocks = [
    {"object": "block", "type": "callout", "callout": {
        "icon": {"type": "emoji", "emoji": "👋"}, "color": "blue_background",
        "rich_text": [{"type": "text", "text": {"content": "Добро пожаловать в Базу знаний команды Куртош! Выбирай нужный раздел ниже."}}]
    }},
    {"object": "block", "type": "heading_2", "heading_2": {"rich_text": [{"type": "text", "text": {"content": "Разделы"}}]}}
]
for title in ["График", "Инструкции", "ТТК", "Обучение", "Контакты", "Аварии"]:
    main_blocks.append({"object": "block", "type": "link_to_page", "link_to_page": {"type": "page_id", "page_id": new_pages[title]}})
api(f"blocks/{new_kb_id}/children", method="PATCH", body={"children": main_blocks})

# 5. Верстаем ТТК
ttk_id = new_pages["ТТК"]
ttk_children = {}
for title in ["Кофе", "Какао и чай", "Спешлы", "Заготовки Бар", "Тесто", "Калачи", "Заготовки Кухня"]:
    pid = create_page(ttk_id, title)
    if pid: ttk_children[title] = pid

ttk_blocks = [
    {"object": "block", "type": "heading_1", "heading_1": {"rich_text": [{"type": "text", "text": {"content": "☕ БАР"}}]}}
]
for title in ["Кофе", "Какао и чай", "Спешлы", "Заготовки Бар"]:
    ttk_blocks.append({"object": "block", "type": "link_to_page", "link_to_page": {"type": "page_id", "page_id": ttk_children[title]}})

ttk_blocks.append({"object": "block", "type": "divider", "divider": {}})
ttk_blocks.append({"object": "block", "type": "heading_1", "heading_1": {"rich_text": [{"type": "text", "text": {"content": "🥐 КУХНЯ"}}]}})

for title in ["Тесто", "Калачи", "Заготовки Кухня"]:
    ttk_blocks.append({"object": "block", "type": "link_to_page", "link_to_page": {"type": "page_id", "page_id": ttk_children[title]}})

api(f"blocks/{ttk_id}/children", method="PATCH", body={"children": ttk_blocks})

# 6. Архивируем старые версии
print("Archiving old versions...")
api(f"pages/{old_main_id}", method="PATCH", body={"archived": True})
api(f"pages/{current_main_id}", method="PATCH", body={"archived": True})

# 7. Сохраняем новые ID
idx["workspace_mirror"]["notion_links"]["page_id"] = new_kb_id
idx["workspace_mirror"]["notion_links"]["old_main_id"] = None
idx["workspace_mirror"]["notion_links"]["child_pages"] = new_pages
with io.open(INDEX_FILE, "w", encoding="utf-8", newline="\n") as f:
    json.dump(idx, f, ensure_ascii=False, indent=2)
    f.write("\n")

print(f"OK: Successfully created clean KB at root. New ID: {new_kb_id}")
