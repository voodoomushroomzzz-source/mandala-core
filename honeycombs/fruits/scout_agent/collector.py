#!/usr/bin/env python3
import feedparser
import json
import os
import sys
from datetime import datetime
from pathlib import Path
import json


def is_duplicate(url):
    """Проверяет, есть ли уже семя с таким url в inbox/ или seeds/"""
    for folder in ["honeycombs/seeds/inbox", "honeycombs/seeds"]:
        folder_path = Path(folder)
        if not folder_path.exists():
            continue
        for file in folder_path.glob("*.json"):
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if data.get("url") == url:
                        return True
            except:
                continue
    return False


# Загружаем конфиг
CONFIG_PATH = Path(__file__).parent / "config.json"
SEEDS_DIR = Path("honeycombs/seeds/inbox")
SEEDS_DIR.mkdir(parents=True, exist_ok=True)
SEEDS_DIR.mkdir(parents=True, exist_ok=True)

with open(CONFIG_PATH, 'r') as f:
    config = json.load(f)

counter = 0

def get_seed_id():
    global counter
    counter += 1
    return f"SEED-{datetime.now().strftime('%Y%m%d')}-{datetime.now().strftime('%H%M%S')}-{counter:03d}"


def collect_api(url):
    """Собирает данные из JSON API (GitHub Trending)"""
    try:
        import requests
        response = requests.get(url, timeout=10)
        data = response.json()
        items = []
        if isinstance(data, list):
            for item in data:
                items.append({
                    "title": f"{item.get('repositoryName', '')} ({item.get('language', '')})",
                    "url": item.get('url', ''),
                    "description": item.get('description', '')[:300],
                    "published": item.get('builtBy', [{}])[0].get('username', '') if 'builtBy' in item else ''
                })
        return items
    except Exception as e:
        print(f"⚠️ Ошибка API {url}: {e}")
        return []


def collect_rss(url):
    """Парсит RSS-ленту, возвращает список записей"""
    try:
        feed = feedparser.parse(url)
        entries = []
        for entry in feed.entries[:10]:
            entries.append({
                "title": entry.get("title", "").strip(),
                "url": entry.get("link", ""),
                "description": entry.get("description", entry.get("summary", ""))[:300],
                "published": entry.get("published", entry.get("updated", ""))
            })
        return entries
    except Exception as e:
        print(f"⚠️ Ошибка RSS {url}: {e}")
        return []

def save_seed(item, source_name):
    """Сохраняет семя в honeycombs/seeds/"""

    # Проверка на дубликат
    if is_duplicate(item["url"]):
        print(f"⏭️ Пропущен дубликат: {item["title"][:50]}...")
        return

    seed_id = get_seed_id()
    seed = {
        "seed_id": seed_id,
        "title": item["title"],
        "url": item["url"],
        "description": item["description"],
        "source": source_name,
        "collected_at": datetime.now().isoformat(),
        "status": "raw"
    }
    filename = SEEDS_DIR / f"{seed_id}.json"
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(seed, f, indent=2, ensure_ascii=False)
    print(f"✅ Сохранено: {filename.name}")

def main():
    total = 0
    for source in config["sources"]:
        if not source.get("enabled", True):
            continue
        print(f"📡 Сбор: {source['name']}")
        if source["type"] == "api":
            items = collect_api(source["url"])
        else:
            items = collect_rss(source["url"])
        for item in items:
            save_seed(item, source["name"])
            total += 1
    print(f"🎯 Итого собрано семян: {total}")

if __name__ == "__main__":
    main()
