#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys, json, io, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import notion_sync as ns

token = ns.load_token()

# Словарь: ID страницы -> эмодзи
ICONS = {
    "40930c88-dcb5-811e-a39c-cdd4091428aa": "📖", # Главная ТТК
    "40930c88-dcb5-81fe-86cc-f409ebf7943c": "🥛", # Классика
    "40930c88-dcb5-8156-aa24-dc904c38d02f": "✨", # Спешлы
    "40e30c88-dcb5-8048-b34c-ff4745d3d6ed": "🍂", # Бар: Сезонка
    "40930c88-dcb5-8111-92f2-cc25b0d38588": "🧪", # Бар: Заготовки
    "40930c88-dcb5-8192-830e-fc138c0797fa": "🌾", # Тесто
    "40930c88-dcb5-817a-b632-e46abed7c380": "🥨", # Калачи
    "40e30c88-dcb5-80b2-8176-d3b37cf6a532": "🥧", # Кухня: Сезонка
    "40930c88-dcb5-8177-b5c2-de8e2f2a5f24": "🥣", # Кухня: Заготовки
    "40e30c88-dcb5-8003-aaf0-ea51b16be77e": "🗃", # Все ТТК (страница)
    "0850869e-b474-4506-9ec9-fbb3285b4ca4": "🗃", # Все ТТК (сама база)
}

print("--- Обновляем иконки в Notion ---")
for pid, emoji in ICONS.items():
    try:
        ns.api(f"pages/{pid}", token, method="PATCH", body={
            "icon": {"type": "emoji", "emoji": emoji}
        })
        print(f"  ✅ {emoji} обновлено ({pid})")
        time.sleep(0.4)
    except Exception as e:
        print(f"  ❌ ошибка для {pid}: {e}")

# --- Обновляем Мандалу ---
HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(os.path.dirname(HERE), "index.json")
TODAY = "2026-11-04"

with io.open(INDEX, "r", encoding="utf-8") as f:
    data = json.load(f)

kb = data["notion_hub"]["branches"]["kb"]["sections"]

# Прописываем иконки в карту
kb["ttk"]["icon"] = "📖"
kb["ttk"]["children"]["bar"]["children"]["classic"]["icon"] = "🥛"
kb["ttk"]["children"]["bar"]["children"]["specials"]["icon"] = "✨"
kb["ttk"]["children"]["bar"]["children"]["seasonal"]["icon"] = "🍂"
kb["ttk"]["children"]["bar"]["children"]["prep"]["icon"] = "🧪"

kb["ttk"]["children"]["kitchen"]["children"]["dough"]["icon"] = "🌾"
kb["ttk"]["children"]["kitchen"]["children"]["kalach"]["icon"] = "🥨"
kb["ttk"]["children"]["kitchen"]["children"]["seasonal"]["icon"] = "🥧"
kb["ttk"]["children"]["kitchen"]["children"]["prep"]["icon"] = "🥣"

kb["ttk"]["database"]["icon"] = "🗃"

data["identity"]["version"] = "v2.21.0"
data["identity"]["updated"] = TODAY
data["identity"]["description"] = data["identity"]["description"].replace(
    "v2.20.2: база ТТК перенесена на отдельную страницу 'Все ТТК' (host_page_id).",
    "v2.21.0: добавлены иконки (emoji) для всех страниц ТТК, зафиксированы в карте."
)

with io.open(INDEX, "w", encoding="utf-8", newline="\n") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
    f.write("\n")

print("OK: index.json updated (v2.21.0) — иконки зафиксированы.")
