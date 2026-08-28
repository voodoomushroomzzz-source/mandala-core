#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Патч для core_map/index.json:
- Добавляет ссылку на directives/
- Добавляет directives в references и children
- Обновляет дату и версию
"""

import json
from pathlib import Path
from datetime import datetime

FILE_PATH = Path("honeycombs/core_map/index.json")

def patch_core_map():
    with open(FILE_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Проверяем, что патч уже применён
    if "directives" in data.get("honeycombs", {}):
        print("✅ Патч уже применён (directives already in honeycombs)")
        return

    # Добавляем directives в honeycombs
    data["honeycombs"]["directives"] = {
        "description": "Директивы для фокусировки внимания SR по векторам",
        "path": "honeycombs/directives/index.json"
    }

    # Добавляем в references
    if "honeycombs/directives/index.json" not in data["navigation"]["references"]:
        data["navigation"]["references"].append("honeycombs/directives/index.json")

    # Добавляем в children
    if "honeycombs/directives/index.json" not in data["navigation"]["children"]:
        data["navigation"]["children"].append("honeycombs/directives/index.json")

    # Обновляем версию и дату
    data["identity"]["version"] = "v3.11.0"
    data["identity"]["updated"] = datetime.now().strftime("%Y-%m-%d")
    data["health"]["last_check"] = datetime.now().strftime("%Y-%m-%d")
    data["health"]["notes"] = "v3.11.0: added directives to honeycombs, references, and children."

    # Сохраняем
    with open(FILE_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print("✅ Патч применён: core_map/index.json обновлён")
    print(f"  version: {data['identity']['version']}")
    print(f"  directives added to honeycombs, references, children")

if __name__ == "__main__":
    patch_core_map()
