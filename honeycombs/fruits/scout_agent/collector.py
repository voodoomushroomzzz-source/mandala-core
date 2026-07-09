#!/usr/bin/env python3
"""
Scout Agent — Autonomous Seed Collector
Собирает семена из RSS/API, логирует каждый источник.
"""
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
import xml.etree.ElementTree as ET
import requests

# --- Конфиг ---
CONFIG_PATH = Path(__file__).parent / "config.json"
LOG_PATH = Path("honeycombs/seeds/scout_log.txt")

def log(message, level="INFO"):
    """Запись в лог и консоль"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [{level}] {message}"
    print(line)
    try:
        with open(LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(line + "\n")
    except:
        pass

# Загружаем конфиг
try:
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        config = json.load(f)
    log("Config loaded successfully")
except Exception as e:
    log(f"Failed to load config: {e}", "ERROR")
    sys.exit(1)

# Путь для сохранения
SEEDS_DIR = Path(config.get("output_dir", "honeycombs/seeds/inbox"))
SEEDS_DIR.mkdir(parents=True, exist_ok=True)
log(f"Output directory: {SEEDS_DIR}")

# --- Вспомогательные функции ---

def is_duplicate(url):
    """Проверка дубликата по url во всех семенах"""
    for folder in [SEEDS_DIR, Path("honeycombs/seeds")]:
        if not folder.exists():
            continue
        for file in folder.glob("*.json"):
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if data.get("url") == url:
                        return True
            except:
                continue
    return False

def get_seed_id():
    """Генерация ID семени"""
    counter = 1
    # Находим максимальный счетчик среди существующих файлов
    existing = list(SEEDS_DIR.glob("SEED-*.json"))
    if existing:
        # Извлекаем последние 3 цифры из имен файлов
        nums = []
        for f in existing:
            try:
                parts = f.stem.split('-')
                if len(parts) >= 4:
                    nums.append(int(parts[-1]))
            except:
                pass
        if nums:
            counter = max(nums) + 1
    return f"SEED-{datetime.now().strftime('%Y%m%d')}-{datetime.now().strftime('%H%M%S')}-{counter:03d}"

def collect_rss(url, source_name):
    """Сбор из RSS с заголовками и логированием"""
    log(f"Fetching RSS: {source_name} ({url})")
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; ScoutAgent/1.0; +https://mandala.symbiosis)',
            'Accept': 'application/rss+xml, application/xml, text/xml, */*'
        }
        response = requests.get(url, timeout=15, headers=headers)
        response.raise_for_status()
        
        # Парсим XML
        root = ET.fromstring(response.content)
        entries = []
        for item in root.findall('.//item')[:15]:
            title = item.find('title')
            link = item.find('link')
            description = item.find('description')
            pub_date = item.find('pubDate')
            entries.append({
                "title": title.text.strip() if title is not None and title.text else "No title",
                "url": link.text.strip() if link is not None and link.text else "",
                "description": (description.text[:300] if description is not None and description.text else ""),
                "published": pub_date.text.strip() if pub_date is not None and pub_date.text else ""
            })
        log(f"  → Found {len(entries)} items in {source_name}")
        return entries
    except requests.exceptions.RequestException as e:
        log(f"  ❌ Request error for {source_name}: {e}", "ERROR")
        return []
    except ET.ParseError as e:
        log(f"  ❌ XML parsing error for {source_name}: {e}", "ERROR")
        return []
    except Exception as e:
        log(f"  ❌ Unexpected error for {source_name}: {e}", "ERROR")
        return []

def collect_api(url, source_name):
    """Сбор из API (например, GitHub)"""
    log(f"Fetching API: {source_name} ({url})")
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; ScoutAgent/1.0; +https://mandala.symbiosis)',
            'Accept': 'application/json'
        }
        response = requests.get(url, timeout=15, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        items = []
        if isinstance(data, list):
            for item in data[:10]:
                items.append({
                    "title": f"{item.get('repositoryName', '')} ({item.get('language', '')})",
                    "url": item.get('url', ''),
                    "description": item.get('description', '')[:300],
                    "published": item.get('builtBy', [{}])[0].get('username', '') if 'builtBy' in item else ''
                })
        elif isinstance(data, dict) and 'items' in data:
            for item in data['items'][:10]:
                items.append({
                    "title": item.get('name', ''),
                    "url": item.get('html_url', ''),
                    "description": item.get('description', '')[:300],
                    "published": item.get('updated_at', '')
                })
        log(f"  → Found {len(items)} items in {source_name}")
        return items
    except Exception as e:
        log(f"  ❌ API error for {source_name}: {e}", "ERROR")
        return []

def save_seed(item, source_name):
    """Сохранение семени"""
    if not item.get('url'):
        log(f"  ⚠️ Skipping item without URL: {item.get('title', '')[:30]}...", "WARNING")
        return False
    
    if is_duplicate(item['url']):
        log(f"  ⏭️ Duplicate: {item['title'][:50]}...")
        return False
    
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
    log(f"  ✅ Saved: {filename.name}")
    return True

# --- Основной процесс ---
def main():
    log("=" * 60)
    log("🚀 Scout Agent started")
    log(f"Sources: {len(config['sources'])}")
    
    total_saved = 0
    total_duplicates = 0
    total_errors = 0
    
    for source in config['sources']:
        if not source.get("enabled", True):
            log(f"⏭️ Source disabled: {source['name']}")
            continue
        
        log(f"\n📡 Processing: {source['name']} (type: {source['type']})")
        
        if source["type"] == "api":
            items = collect_api(source["url"], source["name"])
        else:
            items = collect_rss(source["url"], source["name"])
        
        if not items:
            log(f"  ⚠️ No items received from {source['name']}", "WARNING")
            total_errors += 1
            continue
        
        saved = 0
        duplicates = 0
        for item in items:
            if save_seed(item, source["name"]):
                saved += 1
            else:
                duplicates += 1
        
        total_saved += saved
        total_duplicates += duplicates
        log(f"  📊 {source['name']}: saved {saved}, duplicates {duplicates}")
    
    log("\n" + "=" * 60)
    log(f"✅ Scout Agent finished")
    log(f"  Total saved: {total_saved}")
    log(f"  Total duplicates: {total_duplicates}")
    log(f"  Total errors (empty sources): {total_errors}")
    log("=" * 60)

if __name__ == "__main__":
    main()
