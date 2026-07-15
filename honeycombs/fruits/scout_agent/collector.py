#!/usr/bin/env python3
"""
Scout Agent v2 — с keyword-фильтром и лимитом 3 семени с источника
"""
import json
import re
from datetime import datetime
from pathlib import Path
import xml.etree.ElementTree as ET
import requests

CONFIG_PATH = Path(__file__).parent / "config.json"
LOG_PATH = Path("honeycombs/seeds/scout_log.txt")

# Ключевые слова для фильтрации
RELEVANT_KEYWORDS = [
    'symbiosis', 'symbiotic', 'ai', 'agent', 'llm', 'memory', 'recall',
    'reasoning', 'planning', 'self-organizing', 'resonance', 'co-creation',
    'garden', 'gardener', 'ecosystem', 'autonomous', 'adaptive',
    'knowledge', 'learning', 'collaboration', 'human-ai', 'cooperation',
    'architecture', 'system', 'consciousness', 'awareness',
    'mandala', 'honeycomb', 'scout', 'seed', 'collector',
    'neural', 'network', 'deep', 'reinforcement', 'cognitive',
    'emergent', 'collective', 'distributed', 'multi-agent'
]

def log(message, level="INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [{level}] {message}"
    print(line)
    try:
        with open(LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(line + "\n")
    except:
        pass

def is_relevant(text):
    """Проверяет текст на наличие ключевых слов."""
    if not text:
        return False
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in RELEVANT_KEYWORDS)

def is_recent(published_str, hours=24):
    """Проверяет, что дата публикации за последние 24 часа."""
    if not published_str:
        return False
    try:
        # Пробуем разные форматы
        if 'T' in published_str:
            dt = datetime.fromisoformat(published_str.replace('Z', '+00:00'))
        elif '-' in published_str:
            dt = datetime.strptime(published_str[:10], '%Y-%m-%d')
        else:
            return False
        now = datetime.now()
        return (now - dt).total_seconds() <= hours * 3600
    except:
        return False

    if not text:
        return False
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in RELEVANT_KEYWORDS)

def filter_items(items, max_items=3):
    """Оставляет до 3 релевантных семян"""
    relevant = []
    for item in items:
        title = item.get('title', '')
        description = item.get('description', '')
        if is_relevant(title) or is_relevant(description):
            relevant.append(item)
            if len(relevant) >= max_items:
                break
    return relevant

def is_duplicate(url, seed_dir):
    for folder in [seed_dir, Path("honeycombs/seeds")]:
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

def get_seed_id(seed_dir):
    counter = 1
    existing = list(seed_dir.glob("SEED-*.json"))
    if existing:
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
    log(f"Fetching RSS: {source_name} ({url})")
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; ScoutAgent/2.0; +https://mandala.symbiosis)',
            'Accept': 'application/rss+xml, application/xml, text/xml, */*'
        }
        response = requests.get(url, timeout=15, headers=headers)
        response.raise_for_status()
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
                "description": (description.text[:500] if description is not None and description.text else ""),
                "published": pub_date.text.strip() if pub_date is not None and pub_date.text else ""
            })
        # Фильтруем по времени (последние 24 часа)
        recent_entries = [e for e in entries if is_recent(e.get('published', ''))]
        log(f"  → Found {len(entries)} raw items, {len(recent_entries)} recent")
        filtered = filter_items(recent_entries, max_items=3)
        log(f"  → Filtered to {len(filtered)} relevant items")
        return filtered
    except Exception as e:
        log(f"  ❌ RSS error: {e}", "ERROR")
        return []

def collect_api(url, source_name):
    log(f"Fetching API: {source_name} ({url})")
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; ScoutAgent/2.0; +https://mandala.symbiosis)',
            'Accept': 'application/json'
        }
        response = requests.get(url, timeout=15, headers=headers)
        response.raise_for_status()
        data = response.json()
        items = []
        if isinstance(data, list):
            for item in data[:15]:
                items.append({
                    "title": f"{item.get('repositoryName', '')} ({item.get('language', '')})",
                    "url": item.get('url', ''),
                    "description": item.get('description', '')[:500],
                    "published": item.get('builtBy', [{}])[0].get('username', '') if 'builtBy' in item else ''
                })
        elif isinstance(data, dict) and 'items' in data:
            for item in data['items'][:15]:
                items.append({
                    "title": item.get('name', ''),
                    "url": item.get('html_url', ''),
                    "description": item.get('description', '')[:500],
                    "published": item.get('updated_at', '')
                })
        # Фильтруем по времени (последние 24 часа)
        recent_items = [i for i in items if is_recent(i.get('published', ''))]
        log(f"  → Found {len(items)} raw items, {len(recent_items)} recent")
        filtered = filter_items(recent_items, max_items=3)
        log(f"  → Filtered to {len(filtered)} relevant items")
        return filtered
    except Exception as e:
        log(f"  ❌ API error: {e}", "ERROR")
        return []

def save_seed(item, source_name, seed_dir):
    if not item.get('url'):
        return False
    if is_duplicate(item, seed_dir):
        log(f"  ⏭️ Duplicate: {item['title'][:50]}...")
        return False
    seed_id = get_seed_id(seed_dir)
    seed = {
        "seed_id": seed_id,
        "title": item["title"],
        "url": item["url"],
        "description": item["description"],
        "source": source_name,
        "collected_at": datetime.now().isoformat(),
        "status": "raw",
        "evaluation": {
            "score_novelty": 0,
            "score_feasibility": 0,
            "score_relevance": 0,
            "score_impact": 0,
            "total_score": 0,
            "mandala_relevance": "",
            "reason_selected": "",
            "action": "keep"
        },
        "promotion_notes": {
            "promoted_at": "",
            "promoted_by": "",
            "work_created": ""
        },
        "work_analysis": {
            "analysis_date": "",
            "source_links": [],
            "research_summary": "",
            "key_insights": [],
            "related_work": [],
            "implementation_notes": ""
        }
    }
    filename = seed_dir / f"{seed_id}.json"
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(seed, f, indent=2, ensure_ascii=False)
    log(f"  ✅ Saved: {filename.name}")
    return True

def main():
    log("=" * 60)
    log("🚀 Scout Agent v2 started (keyword filter, max 3 per source)")
    
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    seed_dir = Path(config.get("output_dir", "honeycombs/seeds/inbox"))
    seed_dir.mkdir(parents=True, exist_ok=True)
    
    total_saved = 0
    total_duplicates = 0
    
    for source in config['sources']:
        if not source.get("enabled", True):
            log(f"⏭️ Source disabled: {source['name']}")
            continue
        
        log(f"\n📡 Processing: {source['name']} (type: {source['type']})")
        
        if source["type"] == "api":
            items = collect_api(source["url"], source["name"])
        else:
            items = collect_rss(source["url"], source["name"])
        
        saved = 0
        duplicates = 0
        for item in items:
            if save_seed(item, source["name"], seed_dir):
                saved += 1
            else:
                duplicates += 1
        
        total_saved += saved
        total_duplicates += duplicates
        log(f"  📊 {source['name']}: saved {saved}, duplicates {duplicates}")
    
    log("\n" + "=" * 60)
    log(f"✅ Scout Agent v2 finished")
    log(f"  Total saved: {total_saved}")
    log(f"  Total duplicates: {total_duplicates}")
    log("=" * 60)

if __name__ == "__main__":
    main()
