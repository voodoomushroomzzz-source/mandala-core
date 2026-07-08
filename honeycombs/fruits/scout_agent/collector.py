#!/usr/bin/env python3
import feedparser
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Загружаем конфиг
CONFIG_PATH = Path(__file__).parent / "config.json"
SEEDS_DIR = Path("honeycombs/seeds")
SEEDS_DIR.mkdir(parents=True, exist_ok=True)

with open(CONFIG_PATH, 'r') as f:
    config = json.load(f)

counter = 0

def get_seed_id():
    global counter
    counter += 1
    return f"SEED-{datetime.now().strftime('%Y%m%d')}-{datetime.now().strftime('%H%M%S')}-{counter:03d}"

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
        items = collect_rss(source["url"])
        for item in items:
            save_seed(item, source["name"])
            total += 1
    print(f"🎯 Итого собрано семян: {total}")

if __name__ == "__main__":
    main()
