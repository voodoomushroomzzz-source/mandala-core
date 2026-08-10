#!/usr/bin/env python3
"""
Scout Agent v2.2 — с keyword-фильтром, лимитом 5 семян с источника
и автоматической очисткой инбокса по индексу
"""
import json
import re
from datetime import datetime
from pathlib import Path
import xml.etree.ElementTree as ET
from difflib import SequenceMatcher
import requests
from urllib.parse import urlparse

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
    'emergent', 'collective', 'distributed', 'multi-agent',
    'artificial intelligence', 'machine learning', 'deep learning',
    'research', 'paper', 'study', 'model', 'dataset', 'algorithm',
    'framework', 'tool', 'library', 'api', 'open source', 'github',
    'innovation', 'breakthrough', 'state-of-the-art', 'sota',
    'pretrained', 'fine-tune', 'benchmark', 'evaluation'
]


def normalize_url(url):
    """Удаляет параметры запроса из URL для сравнения."""
    if not url:
        return url
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}".lower()


def is_similar(a, b, threshold=0.85):
    """Проверяет, похожи ли две строки (нечёткое сравнение)."""
    if not a or not b:
        return False
    a_clean = a.lower()[:200].strip()
    b_clean = b.lower()[:200].strip()
    if not a_clean or not b_clean:
        return False
    if a_clean in b_clean or b_clean in a_clean:
        return True
    ratio = SequenceMatcher(None, a_clean, b_clean).ratio()
    return ratio >= threshold


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
            # ISO 8601: 2026-07-18T10:21:19+00:00
            dt = datetime.fromisoformat(published_str.replace('Z', '+00:00'))
        elif ',' in published_str:
            # RFC 2822: Sat, 18 Jul 2026 10:21:19 +0000
            dt = datetime.strptime(published_str, '%a, %d %b %Y %H:%M:%S %z')
        elif '-' in published_str:
            # YYYY-MM-DD
            dt = datetime.strptime(published_str[:10], '%Y-%m-%d')
        else:
            return False
        now = datetime.now().astimezone()
        # Приводим dt к тому же часовому поясу, что и now
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=now.tzinfo)
        return (now - dt).total_seconds() <= hours * 3600
    except Exception as e:
        # Если парсинг не удался, считаем статью старой
        return False


def filter_items(items, max_items=5):
    """Оставляет до 5 релевантных семян"""
    relevant = []
    for item in items:
        title = item.get('title', '')
        description = item.get('description', '')
        if is_relevant(title) or is_relevant(description):
            relevant.append(item)
            if len(relevant) >= max_items:
                break
    return relevant


def is_duplicate(item, seed_dir):
    """Проверяет дубликаты по URL, заголовку и описанию (с нечётким сравнением)."""
    url = item.get('url', '')
    title = item.get('title', '')
    desc = item.get('description', '')

    # Нормализуем URL
    url_norm = normalize_url(url) if url else ''

    for folder in [seed_dir, Path("honeycombs/seeds")]:
        if not folder.exists():
            continue
        for file in folder.glob("*.json"):
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                    # 1. Проверка по нормализованному URL
                    data_url = data.get("url", "")
                    if url_norm and data_url:
                        data_url_norm = normalize_url(data_url)
                        if url_norm == data_url_norm:
                            return True

                    # 2. Проверка по заголовку + описанию (нечёткое)
                    data_title = data.get("title", "")
                    data_desc = data.get("description", "")

                    title_similar = is_similar(title, data_title)
                    desc_similar = is_similar(desc, data_desc)

                    if title_similar and desc_similar:
                        return True

                    # 3. Если описания пустые — проверяем только заголовок
                    if not desc and not data_desc and title_similar:
                        return True

            except Exception:
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
            'User-Agent': 'Mozilla/5.0 (compatible; ScoutAgent/2.2; +https://mandala.symbiosis)',
            'Accept': 'application/rss+xml, application/xml, text/xml, */*'
        }
        # allow_redirects=True — для arXiv (302 Found)
        response = requests.get(url, timeout=15, headers=headers, allow_redirects=True)
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
        filtered = filter_items(recent_entries, max_items=5)
        log(f"  → Filtered to {len(filtered)} relevant items")
        return filtered
    except Exception as e:
        log(f"  ❌ RSS error: {e}", "ERROR")
        return []


def collect_api(url, source_name):
    log(f"Fetching API: {source_name} ({url})")
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; ScoutAgent/2.2; +https://mandala.symbiosis)',
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
        filtered = filter_items(recent_items, max_items=5)
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


def clean_old_seeds(seed_dir):
    """Удаляет старые семена на основе last_processed из inbox/index.json"""
    index_path = Path("honeycombs/seeds/inbox/index.json")
    removed_count = 0

    if not index_path.exists():
        log("  📝 inbox/index.json not found — skipping cleanup")
        return 0

    try:
        with open(index_path, 'r', encoding='utf-8') as f:
            index = json.load(f)

        last_processed = index.get("meta", {}).get("last_processed")
        if not last_processed:
            log("  ⚠️ No last_processed in index — skipping cleanup")
            return 0

        log(f"  🗑️ Cleaning old seeds (date <= {last_processed})...")

        for file in seed_dir.glob("*.json"):
            if file.name == "index.json":
                continue
            match = re.search(r'(\d{4}-\d{2}-\d{2})', file.name)
            if match:
                file_date = match.group(1)
                if file_date <= last_processed:
                    file.unlink()
                    removed_count += 1
                    log(f"  🗑️ Removed old seed: {file.name}")

        if removed_count > 0:
            log(f"  ✅ Removed {removed_count} old seeds")
        else:
            log("  ✅ No old seeds to remove")

    except Exception as e:
        log(f"  ⚠️ Error cleaning old seeds: {e}", "WARNING")

    return removed_count


def update_inbox_index(total_saved, total_duplicates, removed_count):
    """Обновляет inbox/index.json с датой обработки"""
    index_path = Path("honeycombs/seeds/inbox/index.json")
    today = datetime.now().strftime("%Y-%m-%d")

    try:
        if index_path.exists():
            with open(index_path, 'r', encoding='utf-8') as f:
                index = json.load(f)

            index["meta"]["last_processed"] = today
            index["meta"]["total_processed"] = index.get("meta", {}).get("total_processed", 0) + total_saved
            index["meta"]["processed_by"] = "Scout Agent"

            with open(index_path, 'w', encoding='utf-8') as f:
                json.dump(index, f, indent=2, ensure_ascii=False)

            log(f"  📝 Updated inbox/index.json with last_processed={today}")
        else:
            # Создаём новый индекс
            new_index = {
                "identity": {
                    "module_id": "SEEDS-INBOX-INDEX-001",
                    "name": "Seeds Inbox Index",
                    "version": "v2.0.0",
                    "created": today,
                    "updated": today,
                    "layer": 3,
                    "type": "seed_inbox_index",
                    "status": "active",
                    "description": "Inbox processing log. Contains last_processed date and promoted seeds list."
                },
                "meta": {
                    "description": "Inbox index for tracking processed seeds. Scout Agent uses last_processed to clean old seeds.",
                    "last_processed": today,
                    "processed_by": "Scout Agent",
                    "total_processed": total_saved,
                    "promoted_to_root": 0
                },
                "promoted_seeds": [],
                "navigation": {
                    "parent": "honeycombs/seeds/index.json",
                    "related": [
                        "honeycombs/seeds/index.json",
                        "honeycombs/registry/scan_state.json",
                        "honeycombs/protocols/seed_to_work.json"
                    ]
                },
                "health": {
                    "status": "ok",
                    "last_check": today,
                    "notes": f"Auto-created by Scout Agent v2.2 on {today}"
                }
            }

            with open(index_path, 'w', encoding='utf-8') as f:
                json.dump(new_index, f, indent=2, ensure_ascii=False)

            log(f"  ✅ Created new inbox/index.json with last_processed={today}")

    except Exception as e:
        log(f"  ⚠️ Error updating index: {e}", "WARNING")


def main():
    log("=" * 60)
    log("🚀 Scout Agent v2.2 started (keyword filter, max 5 per source, auto-cleanup)")

    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        config = json.load(f)

    seed_dir = Path(config.get("output_dir", "honeycombs/seeds/inbox"))
    seed_dir.mkdir(parents=True, exist_ok=True)

    total_saved = 0
    total_duplicates = 0

    # --- ШАГ 1: Сбор новых семян ---
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

    # --- ШАГ 2: Удаление старых семян ---
    removed_count = clean_old_seeds(seed_dir)

    # --- ШАГ 3: Обновление индекса ---
    update_inbox_index(total_saved, total_duplicates, removed_count)

    # --- Финальный лог ---
    log("\n" + "=" * 60)
    log(f"✅ Scout Agent v2.2 finished")
    log(f"  Total saved: {total_saved}")
    log(f"  Total duplicates: {total_duplicates}")
    log(f"  Total removed (old): {removed_count}")
    log("=" * 60)


if __name__ == "__main__":
    main()
