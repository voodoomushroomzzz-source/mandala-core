#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re
from pathlib import Path

FILE_PATH = Path("honeycombs/fruits/scout_agent/collector.py")

def patch_collector():
    with open(FILE_PATH, 'r', encoding='utf-8') as f:
        content = f.read()

    if "--- ШАГ 2: Удаление старых семян" in content:
        print("✅ Патч уже применён")
        return

    # Ищем финальный блок с логами (используем более гибкий паттерн)
    if 'log("=" * 60)' not in content or 'log(f"✅ Scout Agent v2 finished")' not in content:
        print("❌ Не найден маркер для вставки")
        return

    old_block = r'(log\("=" \* 60\)\s+log\(f"✅ Scout Agent v2 finished"\)\s+log\(f"  Total saved: {total_saved}"\)\s+log\(f"  Total duplicates: {total_duplicates}"\)\s+log\("=" \* 60\))'

    new_block = '''    # --- ШАГ 2: Удаление старых семян ---
    index_path = Path("honeycombs/seeds/inbox/index.json")
    removed_count = 0
    if index_path.exists():
        try:
            with open(index_path, 'r', encoding='utf-8') as f:
                index = json.load(f)
            last_processed = index.get("meta", {}).get("last_processed")
            if last_processed:
                log(f"\\n🗑️ Cleaning old seeds (date <= {last_processed})...")
                for file in seed_dir.glob("*.json"):
                    if file.name == "index.json":
                        continue
                    match = re.search(r'(\\d{4}-\\d{2}-\\d{2})', file.name)
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
            log(f"  ⚠️ Error reading index: {e}", "WARNING")

    # --- ШАГ 3: Обновление inbox/index.json ---
    today = datetime.now().strftime("%Y-%m-%d")
    if index_path.exists():
        try:
            with open(index_path, 'r', encoding='utf-8') as f:
                index = json.load(f)
            index["meta"]["last_processed"] = today
            index["meta"]["total_processed"] = index.get("meta", {}).get("total_processed", 0) + total_saved
            with open(index_path, 'w', encoding='utf-8') as f:
                json.dump(index, f, indent=2, ensure_ascii=False)
            log(f"  📝 Updated inbox/index.json with last_processed={today}")
        except Exception as e:
            log(f"  ⚠️ Error updating index: {e}", "WARNING")
    else:
        log("  📝 inbox/index.json not found — creating new")
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

    log("=" * 60)
    log(f"✅ Scout Agent v2.2 finished")
    log(f"  Total saved: {total_saved}")
    log(f"  Total duplicates: {total_duplicates}")
    log(f"  Total removed (old): {removed_count}")
    log("=" * 60)'''

    # Применяем замену
    content = re.sub(old_block, new_block, content, flags=re.DOTALL)

    # Обновляем версию в комментариях
    content = content.replace('Scout Agent v2', 'Scout Agent v2.2')
    content = content.replace('ScoutAgent/2.0', 'ScoutAgent/2.2')

    with open(FILE_PATH, 'w', encoding='utf-8') as f:
        f.write(content)

    print("✅ Патч применён: Scout Agent v2.2")

if __name__ == "__main__":
    patch_collector()
