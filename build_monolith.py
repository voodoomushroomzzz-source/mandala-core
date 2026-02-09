#!/usr/bin/env python3
"""
Mandala Core Monolith Builder (исправленная версия).
Корректно загружает все модули, включая Sphaerae и Akasha Chronicorum.
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional

# Конфигурация путей
REPO_ROOT = Path(os.getenv("GITHUB_WORKSPACE", "."))
BUILD_DIR = REPO_ROOT / "build"
OUTPUT_FILE = BUILD_DIR / "mandala_core.monolith.latest.json"

def extract_relative_path(github_url: str) -> Optional[str]:
    """
    Извлекает относительный путь из GitHub URL.
    Обрабатывает оба формата: /blob/main/ и /tree/main/
    """
    patterns = ["/blob/main/", "/tree/main/"]
    
    for pattern in patterns:
        if pattern in github_url:
            return github_url.split(pattern)[-1]
    
    # Если не нашли стандартные паттерны, пробуем извлечь путь после /main/
    if "/main/" in github_url:
        return github_url.split("/main/")[-1]
    
    return None

def load_json_from_repo(relative_path: str) -> Dict[str, Any]:
    """Загружает JSON-файл из репозитория."""
    file_path = REPO_ROOT / relative_path
    
    # Проверяем существование файла
    if not file_path.exists():
        raise FileNotFoundError(f"Файл не найден: {relative_path}")
    
    if not file_path.is_file():
        raise ValueError(f"Путь не является файлом: {relative_path}")
    
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
    print("🔄 Сборка Mandala Core Monolith (исправленная версия)...")
    
    # 1. Загружаем ядро
    initium = load_json_from_repo("initium.json")
    core_map = initium.get("core_map", {}).get("modules", {})
    
    # 2. Собираем все модули во embedded_modules
    embedded_modules = {}
    
    for name, info in core_map.items():
        if name == "Initium":
            continue
        
        if "github_url" in info:
            github_url = info["github_url"]
            print(f"  🔗 {name}: {github_url}")
            
            # Извлекаем относительный путь
            relative_path = extract_relative_path(github_url)
            
            if not relative_path:
                print(f"    ⚠️ Не удалось извлечь путь из URL, пропускаем")
                embedded_modules[name] = {"_error": f"Cannot extract path from URL: {github_url}"}
                continue
            
            # Проверяем, является ли это папкой (заканчивается на /)
            if relative_path.endswith('/'):
                print(f"    📁 Это папка, пропускаем загрузку")
                embedded_modules[name] = {
                    "_type": "directory",
                    "_path": relative_path,
                    "_purpose": info.get("purpose", "")
                }
                continue
            
            # Пытаемся загрузить как JSON файл
            try:
                module_data = load_json_from_repo(relative_path)
                embedded_modules[name] = module_data
                print(f"    ✅ Загружен")
            except FileNotFoundError as e:
                embedded_modules[name] = {
                    "_error": str(e),
                    "_url": github_url,
                    "_path": relative_path
                }
                print(f"    ❌ Файл не найден: {relative_path}")
            except json.JSONDecodeError as e:
                embedded_modules[name] = {
                    "_error": f"Invalid JSON: {str(e)}",
                    "_url": github_url,
                    "_path": relative_path
                }
                print(f"    ❌ Ошибка JSON: {e}")
            except Exception as e:
                embedded_modules[name] = {
                    "_error": str(e),
                    "_url": github_url,
                    "_path": relative_path
                }
                print(f"    ❌ Ошибка: {e}")
        
        elif "external_url" in info:
            # Внешний ресурс
            content = fetch_url_content(info["external_url"])
            embedded_modules[name] = {
                "_source": info["external_url"],
                "_content_type": "text",
                "content": content[:50000]
            }
            print(f"  🌐 {name}: внешний ресурс загружен")
    
    print(f"✅ Собрано модулей: {len(embedded_modules)}")
    
    # 3. Формируем монолит
    monolith = {
        "module": "Mandala Core Monolith",
        "version": f"monolith-{initium.get('version', 'unknown')}",
        "runtime_mode": "monolith",
        "build_timestamp": datetime.now(timezone.utc).isoformat(),
        "build_source": os.getenv("GITHUB_SHA", "local"),
        "source_initium": initium,
        "embedded_modules": embedded_modules,
        "runtime_instruction": "Система загружена из монолита. Все модули доступны в embedded_modules. Предлагая изменения, ссылайся на исходные файлы из source_initium.core_map."
    }
    
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
        
        # Выводим список загруженных модулей
        print("\n📦 Загруженные модули:")
        for name, data in monolith.get("embedded_modules", {}).items():
            if "_error" in data:
                print(f"  ❌ {name}: ОШИБКА - {data['_error']}")
            elif "_type" in data and data["_type"] == "directory":
                print(f"  📁 {name}: папка")
            else:
                print(f"  ✅ {name}: успешно")
        
    except Exception as e:
        print(f"💥 Критическая ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
