#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import io, json, os, sys, time, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
KURTOCH = os.path.dirname(HERE)
TOKEN_FILE = os.path.join(HERE, "notion_token.txt")
INDEX_FILE = os.path.join(KURTOCH, "index.json")

TOKEN = io.open(TOKEN_FILE, encoding="utf-8").read().strip()
H = {"Authorization": f"Bearer {TOKEN}", "Notion-Version": "2022-06-28", "Content-Type": "application/json"}

def api(path, method="GET", body=None):
    req = urllib.request.Request(f"https://api.notion.com/v1/{path}", data=json.dumps(body).encode() if body else None, method=method, headers=H)
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()}")
        sys.exit(1)

def get_children(block_id):
    out, cursor = [], None
    while True:
        path = f"blocks/{block_id}/children?page_size=100"
        if cursor: path += f"&start_cursor={cursor}"
        d = api(path)
        out.extend(d.get("results", []))
        if not d.get("has_more"): break
        cursor = d.get("next_cursor")
        time.sleep(0.35)
    return out

with io.open(INDEX_FILE, encoding="utf-8") as f:
    idx = json.load(f)

links = idx["workspace_mirror"]["notion_links"]
main_id = links["page_id"]
pages = links["child_pages"]

# 1. Чистим главную страницу от старых блоков (column_list, child_page, старый заголовок)
children = get_children(main_id)
for c in children:
    if c["type"] in ("column_list", "child_page") or (c["type"] == "heading_2" and "Разделы" in str(c.get("heading_2", {}).get("rich_text", []))):
        api(f"blocks/{c['id']}", method="DELETE")
        time.sleep(0.35)

# 2. Убираем иконки у самих страниц, чтобы не было дублей
for title, pid in pages.items():
    api(f"pages/{pid}", method="PATCH", body={"icon": None})
    time.sleep(0.35)

# 3. Строим чистые плитки (без эмодзи в тексте, только иконка и ссылка)
tiles_order = [
    {"emoji": "📅", "title": "График",     "desc": "Смены, замены, отпуска"},
    {"emoji": "📋", "title": "Инструкции", "desc": "Открытие, закрытие, чистота"},
    {"emoji": "☕", "title": "ТТК",        "desc": "Рецептуры и стандарты"},
    {"emoji": "🎓", "title": "Обучение",   "desc": "Программа стажёра, аттестация"},
    {"emoji": "📞", "title": "Контакты",   "desc": "Команда и сервисы"},
    {"emoji": "🆘", "title": "Аварии",     "desc": "Что делать, если..."},
]

def callout_link(tile):
    pid = pages[tile["title"]]
    return {
        "object": "block", "type": "callout",
        "callout": {
            "icon": {"type": "emoji", "emoji": tile["emoji"]},
            "color": "gray_background",
            "rich_text": [
                {"type": "mention", "mention": {"type": "page", "page": {"id": pid}}},
                {"type": "text", "text": {"content": "\n" + tile["desc"]}, "annotations": {"color": "gray"}},
            ],
        }
    }

row1 = {"object": "block", "type": "column_list", "column_list": {"children": [
    {"object": "block", "type": "column", "column": {"children": [callout_link(tiles_order[0])]}},
    {"object": "block", "type": "column", "column": {"children": [callout_link(tiles_order[1])]}},
    {"object": "block", "type": "column", "column": {"children": [callout_link(tiles_order[2])]}},
]}}
row2 = {"object": "block", "type": "column_list", "column_list": {"children": [
    {"object": "block", "type": "column", "column": {"children": [callout_link(tiles_order[3])]}},
    {"object": "block", "type": "column", "column": {"children": [callout_link(tiles_order[4])]}},
    {"object": "block", "type": "column", "column": {"children": [callout_link(tiles_order[5])]}},
]}}

header = {"object": "block", "type": "heading_2", "heading_2": {"rich_text": [{"type": "text", "text": {"content": "Разделы"}}]}}
api(f"blocks/{main_id}/children", method="PATCH", body={"children": [header, row1, row2]})

print("OK: Tiles cleaned (no duplicate emojis).")
