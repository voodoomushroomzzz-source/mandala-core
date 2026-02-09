#!/usr/bin/env python3
"""
Mandala Core Monolith Builder (исправленная версия 2.0).
С упрощённой логикой извлечения путей и принудительным обновлением версии.
"""

import json
import os
import sys
import hashlib
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional

# Конфигурация
REPO_ROOT = Path(os.getenv("GITHUB_WORKSPACE", "."))
BUILD_DIR = REPO_ROOT / "build"
OUTPUT_FILE = BUILD_DIR / "mandala_core.monolith.latest.json"

# Ключевые модули, которые должны быть загружены обязательно
REQUIRED_MODULES = ["Sphaerae", "Akasha Chronicorum"]

def log(message: str, level: str = "INFO"):
    """Логирование с меткой времени."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {level}: {message}")

def extract_relative_path(github_url: str) -> Optional[str]:
    """
    Извлекает относительный путь из GitHub URL.
    Упрощённая логика для URL формата GitHub.
    """
    # Пример URL: https://github.com/voodoomushroomzzz-source/mandala-core/blob/main/sphaerae.json
    
    if "github.com" not in github_url:
        return None
    
    # Ищем паттерн /blob/main/ или /tree/main/
    patterns = ["/blob/main/", "/tree/main/"]
    
    for pattern in patterns:
        if pattern in github_url:
            path = github_url.split(pattern)[-1]
            # Если это папка, убедимся, что путь заканчивается на /
            if pattern == "/tree/main/" and not path.endswith('/'):
                path += '/'
            return path
    
    # Если паттерны не найдены, пробуем извлечь путь после репозитория
    parts = github_url.split("github.com/")[-1].split("/")
    if len(parts) >= 3:
        # Пропускаем user/repo (первые две части)
        return "/".join(parts[2:])
    
    return None

def load_json_from_repo(relative_path: str) -> Dict[str, Any]:
    """Загружает JSON-файл из репозитория с валидацией."""
    file_path = REPO_ROOT / relative_path
    
    if not file_path.exists():
        raise FileNotFoundError(f"Файл не найден: {relative_path} (полный путь: {file_path})")
    
    if not file_path.is_file():
        raise ValueError(f"Путь не является файлом: {relative_path}")
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = json.load(f)
        log(f"Файл {relative_path} успешно загружен")
        return content
    except json.JSONDecodeError as e:
        raise ValueError(f"Невалидный JSON в файле {relative_path}: {e}")
    except Exception as e:
        raise Exception(f"Ошибка при чтении файла {relative_path}: {e}")

def fetch_url_content(url: str) -> str:
    """Загружает содержимое по URL (для внешних ресурсов)."""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'MandalaCoreBuilder/2.0'})
        with urllib.request.urlopen(req, timeout=20) as response:
            return response.read().decode('utf-8')
    except Exception as e:
        log(f"Не удалось загрузить URL {url}: {e}", "WARNING")
        return f"⚠️ Не удалось загрузить: {url}\nОшибка: {e}"

def build_monolith() -> Dict[str, Any]:
    """Основная функция сборки монолита."""
    log("Начало сборки Mandala Core Monolith")
    
    # Проверяем существование initium.json
    initium_path = REPO_ROOT / "initium.json"
    if not initium_path.exists():
        raise FileNotFoundError("Файл initium.json не найден в корне репозитория")
    
    log(f"Рабочая директория: {REPO_ROOT}")
    log(f"Файлы в корне: {list(REPO_ROOT.glob('*.json'))}")
    
    # Загружаем ядро
    initium = load_json_from_repo("initium.json")
    core_map = initium.get("core_map", {}).get("modules", {})
    
    if not core_map:
        raise ValueError("В initium.json не найден core_map.modules")
    
    log(f"Найдено модулей в core_map: {len(core_map)}")
    
    # Собираем все модули
    embedded_modules = {}
    failed_modules = []
    
    for name, info in core_map.items():
        if name == "Initium":
            continue
        
        log(f"Обработка модуля: {name}")
        
        if "github_url" in info:
            github_url = info["github_url"]
            log(f"  URL: {github_url}")
            
            relative_path = extract_relative_path(github_url)
            
            if not relative_path:
                error_msg = f"Не удалось извлечь путь из URL: {github_url}"
                log(error_msg, "ERROR")
                embedded_modules[name] = {"_error": error_msg}
                failed_modules.append(name)
                continue
            
            log(f"  Относительный путь: {relative_path}")
            
            # Если это папка
            if relative_path.endswith('/'):
                log(f"  Модуль {name} - это папка")
                embedded_modules[name] = {
                    "_type": "directory",
                    "_path": relative_path,
                    "_purpose": info.get("purpose", "")
                }
                continue
            
            # Загружаем JSON файл
            try:
                module_data = load_json_from_repo(relative_path)
                embedded_modules[name] = module_data
                log(f"  Модуль {name} успешно загружен")
            except Exception as e:
                error_msg = str(e)
                log(f"  Ошибка загрузки модуля {name}: {error_msg}", "ERROR")
                embedded_modules[name] = {
                    "_error": error_msg,
                    "_url": github_url,
                    "_path": relative_path
                }
                failed_modules.append(name)
        
        elif "external_url" in info:
            # Внешний ресурс
            log(f"Загрузка внешнего ресурса: {name}")
            content = fetch_url_content(info["external_url"])
            embedded_modules[name] = {
                "_source": info["external_url"],
                "_content_type": "text",
                "content": content[:50000]  # Ограничение размера
            }
    
    # Проверяем, что ключевые модули загружены
    for mod_name in REQUIRED_MODULES:
        if mod_name not in embedded_modules:
            raise ValueError(f"Ключевой модуль {mod_name} отсутствует в embedded_modules")
        if "_error" in embedded_modules[mod_name]:
            raise ValueError(f"Ключевой модуль {mod_name} загружен с ошибкой: {embedded_modules[mod_name]['_error']}")
    
    log(f"Успешно загружено модулей: {len(embedded_modules) - len(failed_modules)}")
    if failed_modules:
        log(f"Модулей с ошибками: {len(failed_modules)}: {failed_modules}", "WARNING")
    
    # Формируем монолит с уникальной версией
    current_time = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    version_hash = hashlib.md5(current_time.encode()).hexdigest()[:8]
    
    monolith = {
        "module": "Mandala Core Monolith",
        "version": f"monolith-{initium.get('version', 'unknown')}-{version_hash}",
        "runtime_mode": "monolith",
        "build_timestamp": datetime.now(timezone.utc).isoformat(),
        "build_source": os.getenv("GITHUB_SHA", "local"),
        "source_initium": initium,
        "embedded_modules": embedded_modules,
        "build_info": {
            "successful_modules": [name for name in embedded_modules if "_error" not in embedded_modules[name]],
            "failed_modules": failed_modules,
            "total_modules": len(embedded_modules),
            "required_modules_loaded": all(mod in embedded_modules and "_error" not in embedded_modules[mod] for mod in REQUIRED_MODULES)
        },
        "runtime_instruction": "Система загружена из монолита. Все модули доступны в embedded_modules. Предлагая изменения, ссылайся на исходные файлы из source_initium.core_map."
    }
    
    return monolith

def main():
    """Точка входа."""
    try:
        # Создаем папку build
        BUILD_DIR.mkdir(exist_ok=True)
        
        # Сборка
        monolith = build_monolith()
        
        # Сохраняем
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(monolith, f, indent=2, ensure_ascii=False)
        
        log(f"Монолит сохранён: {OUTPUT_FILE}")
        log(f"Размер: {os.path.getsize(OUTPUT_FILE) / 1024:.1f} KB")
        
        # Вывод статистики
        print("\n" + "="*50)
        print("📊 СТАТИСТИКА СБОРКИ:")
        print("="*50)
        
        build_info = monolith.get("build_info", {})
        print(f"✅ Успешных модулей: {len(build_info.get('successful_modules', []))}")
        print(f"⚠️  Модулей с ошибками: {len(build_info.get('failed_modules', []))}")
        print(f"🔑 Ключевые модули загружены: {build_info.get('required_modules_loaded', False)}")
        
        if build_info.get("failed_modules"):
            print("\n❌ Модули с ошибками:")
            for mod in build_info["failed_modules"]:
                error = monolith["embedded_modules"][mod].get("_error", "Неизвестная ошибка")
                print(f"  - {mod}: {error}")
        
        print(f"\n📦 Всего модулей: {build_info.get('total_modules', 0)}")
        print(f"🏷️  Версия монолита: {monolith.get('version')}")
        print("="*50)
        
    except Exception as e:
        log(f"Критическая ошибка: {e}", "ERROR")
        sys.exit(1)

if __name__ == "__main__":
    main()
