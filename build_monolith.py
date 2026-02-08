#!/usr/bin/env python3
"""
Mandala Core Monolith Builder (для GitHub Actions и ручного запуска).
Создаёт единый файл с маркером 'runtime_mode': 'monolith'.
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

# Конфигурация путей (работает в GitHub Actions и локально)
REPO_ROOT = Path(os.getenv("GITHUB_WORKSPACE", "."))
BUILD_DIR = REPO_ROOT / "build"
OUTPUT_FILE = BUILD_DIR / "mandala_core.monolith.latest.json"

def load_json_from_repo(relative_path: str) -> Dict[str, Any]:
    """Загружает JSON-файл из репозитория."""
    file_path = REPO_ROOT / relative_path
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def fetch_url_content(url: str) -> str:
    """Загружает содержимое по URL (для внешних ресурсов)."""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'MandalaCoreBuilder/1.0'})
        with urllib.request.urlopen(req, timeout=15) as response:
            return response.read().decode('utf-8')
    except Exception as e:
        return f"⚠️ Не удалось загрузить: {url}\nОшибка: {e}"

def build_monolith() -> Dict[str, Any]:
    """Основная функция сборки монолита."""
    print("🔄 Сборка Mandala Core Monolith...")
    
    # 1. Загружаем ядро
    initium = load_json_from_repo("initium.json")
    core_map = initium.get("core_map", {}).get("modules", {})
    
    # 2. Собираем все модули во embedded_modules
    embedded_modules = {}
    for name, info in core_map.items():
        if name == "Initium":
            continue
        
        if "github_url" in info:
            # Локальный модуль: загружаем из файла
            relative_path = info["github_url"].split("/main/")[-1]
            try:
                module_data = load_json_from_repo(relative_path)
                embedded_modules[name] = module_data
                print(f"  ✓ {name}")
            except Exception as e:
                embedded_modules[name] = {"_load_error": str(e)}
                print(f"  ⚠️ {name} (ошибка: {e})")
        
        elif "external_url" in info:
            # Внешний ресурс: загружаем как текст
            content = fetch_url_content(info["external_url"])
            embedded_modules[name] = {
                "_source": info["external_url"],
                "_content_type": "text",
                "content": content[:50000]  # Лимит
            }
            print(f"  🌐 {name}")
    
    # 3. Формируем монолит с явным маркером
    monolith = {
        "module": "Mandala Core Monolith",
        "version": f"monolith-{initium.get('version', 'unknown')}",
        "runtime_mode": "monolith",  # ЯВНЫЙ МАРКЕР для ИИ
        "build_timestamp": datetime.now(timezone.utc).isoformat(),
        "build_source": os.getenv("GITHUB_SHA", "local"),
        
        # Полная копия ядра
        "source_initium": initium,
        
        # Все модули внутри
        "embedded_modules": embedded_modules,
        
        # Инструкция для ИИ
        "runtime_instruction": "Система загружена из монолита. Все модули доступны в embedded_modules. Предлагая изменения, ссылайся на исходные файлы из source_initium.core_map."
    }
    
    print(f"✅ Собрано модулей: {len(embedded_modules)}")
    return monolith

def main():
    """Точка входа."""
    BUILD_DIR.mkdir(exist_ok=True)
    
    try:
        monolith = build_monolith()
        
        # Сохраняем
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(monolith, f, indent=2, ensure_ascii=False)
        
        print(f"💾 Монолит сохранён: {OUTPUT_FILE}")
        print(f"📏 Размер: {os.path.getsize(OUTPUT_FILE) / 1024:.1f} KB")
        
    except Exception as e:
        print(f"💥 Критическая ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
