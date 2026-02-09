#!/usr/bin/env python3
"""
Mandala Core Monolith Builder (версия 3.0 с поддержкой raw.githubusercontent).
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

# Ключевые модули
REQUIRED_MODULES = ["Sphaerae", "Akasha Chronicorum"]

def log(message: str, level: str = "INFO"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {level}: {message}")

def github_to_raw_url(github_url: str) -> str:
    """Конвертирует GitHub URL в raw.githubusercontent.com URL."""
    # Пример: https://github.com/voodoomushroomzzz-source/mandala-core/blob/main/sphaerae.json
    # Станет: https://raw.githubusercontent.com/voodoomushroomzzz-source/mandala-core/main/sphaerae.json
    
    if "github.com" not in github_url:
        return github_url
    
    # Заменяем домен и убираем /blob/
    raw_url = github_url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
    return raw_url

def extract_relative_path(github_url: str) -> Optional[str]:
    """
    Извлекает относительный путь из GitHub URL.
    Работает с raw.githubusercontent.com.
    """
    # Ваши файлы доступны по:
    # https://raw.githubusercontent.com/voodoomushroomzzz-source/mandala-core/main/initium.json
    
    if "raw.githubusercontent.com" in github_url:
        # Извлекаем путь после /main/
        parts = github_url.split("/main/")
        if len(parts) > 1:
            return parts[1]
    
    # Если это обычный GitHub URL
    if "github.com" in github_url:
        patterns = ["/blob/main/", "/tree/main/"]
        for pattern in patterns:
            if pattern in github_url:
                path = github_url.split(pattern)[-1]
                if pattern == "/tree/main/" and not path.endswith('/'):
                    path += '/'
                return path
    
    return None

def load_local_json(file_path: Path) -> Dict[str, Any]:
    """Загружает JSON из локального файла."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Невалидный JSON в {file_path}: {e}")
    except Exception as e:
        raise Exception(f"Ошибка чтения {file_path}: {e}")

def load_json_from_url(url: str) -> Dict[str, Any]:
    """Загружает JSON по URL."""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'MandalaCoreBuilder/3.0'})
        with urllib.request.urlopen(req, timeout=30) as response:
            content = response.read().decode('utf-8')
            return json.loads(content)
    except Exception as e:
        raise Exception(f"Не удалось загрузить {url}: {e}")

def build_monolith() -> Dict[str, Any]:
    """Основная функция сборки монолита."""
    log("Начало сборки Mandala Core Monolith v3.0")
    
    # Проверяем локальные файлы
    log(f"Рабочая директория: {REPO_ROOT}")
    log(f"Файлы в корне: {[f.name for f in REPO_ROOT.glob('*.json')]}")
    
    # Сначала пробуем загрузить локально
    embedded_modules = {}
    failed_modules = []
    
    # Список файлов для загрузки
    files_to_load = [
        ("Initium", "initium.json"),
        ("Sphaerae", "sphaerae.json"),
        ("Akasha Chronicorum", "akasha_chronicorum.json")
    ]
    
    for module_name, filename in files_to_load:
        log(f"Загрузка {module_name} из {filename}")
        
        file_path = REPO_ROOT / filename
        if file_path.exists():
            try:
                data = load_local_json(file_path)
                embedded_modules[module_name] = data
                log(f"  ✅ {module_name} загружен локально")
            except Exception as e:
                error_msg = str(e)
                log(f"  ❌ Ошибка загрузки {module_name}: {error_msg}", "ERROR")
                embedded_modules[module_name] = {"_error": error_msg}
                failed_modules.append(module_name)
        else:
            log(f"  ⚠️ Файл {filename} не найден локально, пробуем URL", "WARNING")
            
            # Пробуем загрузить по URL
            raw_url = f"https://raw.githubusercontent.com/voodoomushroomzzz-source/mandala-core/main/{filename}"
            try:
                data = load_json_from_url(raw_url)
                embedded_modules[module_name] = data
                log(f"  ✅ {module_name} загружен по URL: {raw_url}")
            except Exception as e:
                error_msg = str(e)
                log(f"  ❌ Ошибка загрузки {module_name} по URL: {error_msg}", "ERROR")
                embedded_modules[module_name] = {"_error": error_msg}
                failed_modules.append(module_name)
    
    # Проверяем ключевые модули
    for mod_name in REQUIRED_MODULES:
        if mod_name not in embedded_modules:
            raise ValueError(f"Ключевой модуль {mod_name} отсутствует")
        if "_error" in embedded_modules[mod_name]:
            raise ValueError(f"Ключевой модуль {mod_name} с ошибкой: {embedded_modules[mod_name]['_error']}")
    
    # Загружаем initium для core_map
    if "Initium" not in embedded_modules or "_error" in embedded_modules["Initium"]:
        raise ValueError("Не удалось загрузить Initium")
    
    initium = embedded_modules["Initium"]
    
    # Формируем монолит с уникальной версией
    current_time = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    version_hash = hashlib.md5(current_time.encode()).hexdigest()[:8]
    
    monolith = {
        "module": "Mandala Core Monolith",
        "version": f"monolith-{initium.get('version', 'unknown')}-{version_hash}",
        "runtime_mode": "monolith",
        "build_timestamp": datetime.now(timezone.utc).isoformat(),
        "build_source": os.getenv("GITHUB_SHA", "local"),
        "embedded_modules": embedded_modules,
        "build_info": {
            "successful_modules": [name for name in embedded_modules if "_error" not in embedded_modules[name]],
            "failed_modules": failed_modules,
            "total_modules": len(embedded_modules),
            "required_modules_loaded": all(mod in embedded_modules and "_error" not in embedded_modules[mod] for mod in REQUIRED_MODULES)
        },
        "runtime_instruction": "Система загружена из монолита. Все модули доступны в embedded_modules."
    }
    
    return monolith

def main():
    """Точка входа."""
    try:
        BUILD_DIR.mkdir(exist_ok=True)
        
        monolith = build_monolith()
        
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(monolith, f, indent=2, ensure_ascii=False)
        
        log(f"Монолит сохранён: {OUTPUT_FILE}")
        log(f"Размер: {os.path.getsize(OUTPUT_FILE) / 1024:.1f} KB")
        
        # Статистика
        print("\n" + "="*50)
        print("📊 СТАТИСТИКА СБОРКИ:")
        print("="*50)
        
        build_info = monolith.get("build_info", {})
        print(f"✅ Успешных модулей: {len(build_info.get('successful_modules', []))}")
        print(f"⚠️  Модулей с ошибками: {len(build_info.get('failed_modules', []))}")
        
        if build_info.get("failed_modules"):
            print("\n❌ Модули с ошибками:")
            for mod in build_info["failed_modules"]:
                error = monolith["embedded_modules"][mod].get("_error", "Неизвестная ошибка")
                print(f"  - {mod}: {error[:100]}...")
        
        print(f"\n📦 Всего модулей: {build_info.get('total_modules', 0)}")
        print(f"🏷️  Версия: {monolith.get('version')}")
        print("="*50)
        
        # Проверяем ключевые модули
        embedded = monolith.get("embedded_modules", {})
        print("\n🔍 Проверка ключевых модулей:")
        for mod in ["Initium", "Sphaerae", "Akasha Chronicorum"]:
            if mod in embedded and "_error" not in embedded[mod]:
                print(f"  ✅ {mod}: загружен, версия: {embedded[mod].get('version', 'unknown')}")
            else:
                print(f"  ❌ {mod}: ошибка")
        
    except Exception as e:
        log(f"Критическая ошибка: {e}", "ERROR")
        sys.exit(1)

if __name__ == "__main__":
    main()
