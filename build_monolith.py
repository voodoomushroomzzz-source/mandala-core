#!/usr/bin/env python3
"""
Mandala Core Monolith Builder (версия 5.1)
ПОЛНАЯ АРХИТЕКТУРА С GRACEFUL FALLBACK:
- Initium, Sphaerae, Akasha Chronicorum, Philosophia — КРИТИЧЕСКИЕ
- Geometria Sacra, Incubae — ОПЦИОНАЛЬНЫЕ (логируются, но не валят сборку)
- Монолит собирается всегда, даже если новых модулей ещё нет
"""

import json
import os
import sys
import hashlib
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional

REPO_ROOT = Path(os.getenv("GITHUB_WORKSPACE", "."))
BUILD_DIR = REPO_ROOT / "build"
OUTPUT_FILE = BUILD_DIR / "mandala_core.monolith.latest.json"

# ========== ПОЛНЫЙ СПИСОК МОДУЛЕЙ МАНДАЛЫ ==========
ALL_MODULES = [
    ("Initium", "initium.json"),
    ("Sphaerae", "sphaerae.json"),
    ("Akasha Chronicorum", "akasha_chronicorum.json"),
    ("Philosophia", "philosophia.json"),
    ("Geometria Sacra", "geometria_sacra.json"),      # 🔺 Опциональный
    ("Incubae", "incubae.json")                       # 🌱 Опциональный
]

# ========== 🔴 ТОЛЬКО 4 КРИТИЧЕСКИХ МОДУЛЯ ==========
# Без них монолит бессмыслен. Без Geometria/Incubae — можно жить.
CRITICAL_MODULES = [
    "Initium",
    "Philosophia",
    "Sphaerae",
    "Akasha Chronicorum"
]

def log(message: str, level: str = "INFO"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {level}: {message}")

def load_local_json(file_path: Path) -> Optional[Dict[str, Any]]:
    """Загружает JSON из локального файла. Возвращает None, если файла нет."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        log(f"  ✅ Загружен локально: {file_path.name}")
        return data
    except FileNotFoundError:
        log(f"  ⚠️ Файл не найден локально: {file_path.name}", "WARNING")
        return None
    except json.JSONDecodeError as e:
        log(f"  ❌ Невалидный JSON в {file_path.name}: {str(e)[:100]}", "ERROR")
        return None
    except Exception as e:
        log(f"  ❌ Ошибка чтения {file_path.name}: {str(e)[:100]}", "ERROR")
        return None

def load_json_from_url(url: str, module_name: str) -> Optional[Dict[str, Any]]:
    """Загружает JSON по URL. Возвращает None при ошибке."""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'MandalaCoreBuilder/5.1'})
        with urllib.request.urlopen(req, timeout=10) as response:
            content = response.read().decode('utf-8')
            data = json.loads(content)
            log(f"  ✅ Загружено по URL: {module_name}")
            return data
    except Exception as e:
        log(f"  ⚠️ Не удалось загрузить {module_name} по URL: {str(e)[:100]}", "WARNING")
        return None

def build_monolith() -> Dict[str, Any]:
    """Основная функция сборки монолита."""
    log("=" * 60)
    log("🌀 Mandala Core Monolith Builder v5.1 (graceful fallback)")
    log("=" * 60)

    embedded_modules = {}
    failed_modules = []
    missing_optional = []
    loaded_modules = []

    # Загружаем все модули Мандалы (критические + опциональные)
    for module_name, filename in ALL_MODULES:
        log(f"\n📦 Загрузка: {module_name}")
        
        # Пробуем локальный файл
        file_path = REPO_ROOT / filename
        data = load_local_json(file_path)
        
        # Если локально нет — пробуем URL
        if data is None:
            raw_url = f"https://raw.githubusercontent.com/voodoomushroomzzz-source/mandala-core/main/{filename}"
            data = load_json_from_url(raw_url, module_name)
        
        # Если данные получены — сохраняем
        if data is not None:
            embedded_modules[module_name] = data
            loaded_modules.append(module_name)
        else:
            # Модуль не загрузился
            error_info = {
                "_error": "Module not found locally or via URL",
                "_status": "missing",
                "_module": module_name,
                "_filename": filename,
                "_critical": module_name in CRITICAL_MODULES
            }
            embedded_modules[module_name] = error_info
            failed_modules.append(module_name)
            
            if module_name in CRITICAL_MODULES:
                log(f"  ❌ КРИТИЧЕСКИЙ МОДУЛЬ ОТСУТСТВУЕТ: {module_name}", "ERROR")
            else:
                log(f"  ⚠️ Опциональный модуль отсутствует: {module_name}", "WARNING")
                missing_optional.append(module_name)

    # Проверка критических модулей
    log("\n" + "=" * 60)
    log("🔍 ПРОВЕРКА КРИТИЧЕСКИХ МОДУЛЕЙ")
    log("=" * 60)

    critical_missing = []
    for mod in CRITICAL_MODULES:
        if mod in embedded_modules and "_error" not in embedded_modules[mod]:
            version = embedded_modules[mod].get("version", "unknown")
            log(f"  ✅ {mod}: {version}")
        else:
            log(f"  ❌ {mod}: ОТСУТСТВУЕТ", "ERROR")
            critical_missing.append(mod)

    # Если нет критических модулей — останавливаем сборку
    if critical_missing:
        error_msg = f"НЕВОЗМОЖНО СОБРАТЬ МОНОЛИТ: отсутствуют критические модули: {', '.join(critical_missing)}"
        log(error_msg, "ERROR")
        raise ValueError(error_msg)

    # Формируем мета-информацию о сборке
    current_time = datetime.now(timezone.utc)
    version_hash = hashlib.md5(current_time.isoformat().encode()).hexdigest()[:8]

    # Определяем версию из Initium
    initium_version = "unknown"
    if "Initium" in embedded_modules and "_error" not in embedded_modules["Initium"]:
        initium_version = embedded_modules["Initium"].get("version", "unknown")

    monolith = {
        "module": "Mandala Core Monolith",
        "version": f"monolith-v{initium_version}-{version_hash}",
        "runtime_mode": "monolith",
        "build_timestamp": current_time.isoformat(),
        "build_source": os.getenv("GITHUB_SHA", "local-build"),
        "build_source_url": f"https://github.com/voodoomushroomzzz-source/mandala-core/commit/{os.getenv('GITHUB_SHA', 'local')}",
        "embedded_modules": embedded_modules,
        "build_info": {
            "timestamp": current_time.isoformat(),
            "builder_version": "5.1",
            "successful_modules": [name for name in embedded_modules if "_error" not in embedded_modules[name]],
            "failed_modules": failed_modules,
            "missing_optional_modules": missing_optional,
            "total_modules": len(ALL_MODULES),
            "loaded_modules": len(loaded_modules),
            "critical_modules_ok": len(critical_missing) == 0
        },
        "runtime_instruction": "Система загружена из монолита.",
        "manifest": {
            "description": "Mandala Core Monolith",
            "modules": [name for name, _ in ALL_MODULES],
            "critical_modules": CRITICAL_MODULES,
            "built_at": current_time.strftime("%Y-%m-%d %H:%M:%S UTC")
        }
    }

    return monolith

def main():
    """Точка входа."""
    try:
        BUILD_DIR.mkdir(exist_ok=True)
        log(f"📁 Рабочая директория: {REPO_ROOT}")

        monolith = build_monolith()

        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(monolith, f, indent=2, ensure_ascii=False)

        log(f"\n💾 Монолит сохранён: {OUTPUT_FILE}")
        log(f"📊 Размер: {os.path.getsize(OUTPUT_FILE)} байт")

        # Финальный отчёт
        print("\n" + "=" * 60)
        print("✨ СБОРКА ЗАВЕРШЕНА")
        print("=" * 60)
        print(f"🏷️  Версия: {monolith.get('version')}")
        print(f"📦 Модулей загружено: {len(monolith['embedded_modules'])}")
        print(f"✅ Успешно: {len(monolith['build_info']['successful_modules'])}")
        
        if monolith['build_info']['failed_modules']:
            print(f"❌ Ошибки: {len(monolith['build_info']['failed_modules'])}")
            for mod in monolith['build_info']['failed_modules']:
                status = "КРИТИЧЕСКИЙ" if mod in CRITICAL_MODULES else "опциональный"
                print(f"   - {mod} ({status})")
        
        if monolith['build_info']['missing_optional_modules']:
            print(f"⚠️ Отсутствуют опциональные: {', '.join(monolith['build_info']['missing_optional_modules'])}")
        
        print("=" * 60)

    except Exception as e:
        log(f"💥 Критическая ошибка: {e}", "ERROR")
        sys.exit(1)

if __name__ == "__main__":
    main()
