#!/usr/bin/env python3
"""
Mandala Core Monolith Builder (версия 4.0 с полной обработкой ошибок).
"""

import json
import os
import sys
import hashlib
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional

REPO_ROOT = Path(os.getenv("GITHUB_WORKSPACE", "."))
BUILD_DIR = REPO_ROOT / "build"
OUTPUT_FILE = BUILD_DIR / "mandala_core.monolith.latest.json"
REQUIRED_MODULES = ["Sphaerae", "Akasha Chronicorum"]

def log(message: str, level: str = "INFO"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {level}: {message}")

def load_local_json(file_path: Path) -> Dict[str, Any]:
    """Загружает JSON из локального файла."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        log(f"Загружен локальный файл: {file_path.name}")
        return data
    except json.JSONDecodeError as e:
        raise ValueError(f"Невалидный JSON в {file_path.name}: {str(e)[:100]}")
    except Exception as e:
        raise Exception(f"Ошибка чтения {file_path.name}: {str(e)[:100]}")

def load_json_from_url(url: str) -> Dict[str, Any]:
    """Загружает JSON по URL."""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'MandalaCoreBuilder/4.0'})
        with urllib.request.urlopen(req, timeout=30) as response:
            content = response.read().decode('utf-8')
            return json.loads(content)
    except Exception as e:
        raise Exception(f"Не удалось загрузить {url}: {str(e)[:100]}")

def build_monolith() -> Dict[str, Any]:
    """Основная функция сборки монолита."""
    log("Начало сборки Mandala Core Monolith v4.0")
    
    # Список файлов для загрузки
    files_to_load = [
        ("Initium", "initium.json"),
        ("Sphaerae", "sphaerae.json"),
        ("Akasha Chronicorum", "akasha_chronicorum.json")
    ]
    
    embedded_modules = {}
    failed_modules = []
    
    for module_name, filename in files_to_load:
        log(f"Загрузка {module_name}")
        
        # Пробуем локальный файл
        file_path = REPO_ROOT / filename
        if file_path.exists():
            try:
                data = load_local_json(file_path)
                embedded_modules[module_name] = data
                log(f"  ✅ Успешно")
            except Exception as e:
                log(f"  ❌ Ошибка: {e}", "ERROR")
                embedded_modules[module_name] = {"_error": str(e)}
                failed_modules.append(module_name)
        else:
            # Пробуем URL
            raw_url = f"https://raw.githubusercontent.com/voodoomushroomzzz-source/mandala-core/main/{filename}"
            try:
                data = load_json_from_url(raw_url)
                embedded_modules[module_name] = data
                log(f"  ✅ Загружено по URL")
            except Exception as e:
                log(f"  ❌ Ошибка URL: {e}", "ERROR")
                embedded_modules[module_name] = {"_error": str(e)}
                failed_modules.append(module_name)
    
    # Проверяем ключевые модули
    for mod_name in REQUIRED_MODULES:
        if mod_name not in embedded_modules:
            raise ValueError(f"Ключевой модуль {mod_name} отсутствует")
        if "_error" in embedded_modules[mod_name]:
            raise ValueError(f"Ключевой модуль {mod_name} с ошибкой")
    
    # Формируем монолит
    current_time = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    version_hash = hashlib.md5(current_time.encode()).hexdigest()[:8]
    
    monolith = {
        "module": "Mandala Core Monolith",
        "version": f"monolith-{embedded_modules.get('Initium', {}).get('version', 'unknown')}-{version_hash}",
        "runtime_mode": "monolith",
        "build_timestamp": datetime.now(timezone.utc).isoformat(),
        "build_source": os.getenv("GITHUB_SHA", "local"),
        "embedded_modules": embedded_modules,
        "build_info": {
            "successful_modules": [name for name in embedded_modules if "_error" not in embedded_modules[name]],
            "failed_modules": failed_modules,
            "required_modules_ok": all(mod in embedded_modules and "_error" not in embedded_modules[mod] for mod in REQUIRED_MODULES)
        },
        "runtime_instruction": "Система загружена из монолита."
    }
    
    return monolith

def main():
    """Точка входа."""
    try:
        BUILD_DIR.mkdir(exist_ok=True)
        log(f"Рабочая директория: {REPO_ROOT}")
        
        monolith = build_monolith()
        
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(monolith, f, indent=2, ensure_ascii=False)
        
        log(f"Монолит сохранён: {OUTPUT_FILE}")
        log(f"Размер: {os.path.getsize(OUTPUT_FILE)} байт")
        
        # Валидация
        print("\n" + "="*60)
        print("ПРОВЕРКА:")
        print("="*60)
        
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        print(f"✅ JSON валиден")
        print(f"🏷️  Версия: {data.get('version')}")
        print(f"📦 Модулей: {len(data.get('embedded_modules', {}))}")
        
        print("\n🔍 Ключевые модули:")
        for mod in ["Initium", "Sphaerae", "Akasha Chronicorum"]:
            if mod in data["embedded_modules"]:
                if "_error" not in data["embedded_modules"][mod]:
                    ver = data["embedded_modules"][mod].get("version", "unknown")
                    print(f"  ✅ {mod}: {ver}")
                else:
                    print(f"  ❌ {mod}: ОШИБКА")
            else:
                print(f"  ❌ {mod}: ОТСУТСТВУЕТ")
        
        print("="*60)
        
    except Exception as e:
        log(f"Критическая ошибка: {e}", "ERROR")
        sys.exit(1)

if __name__ == "__main__":
    main()
