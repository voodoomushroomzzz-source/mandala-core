#!/usr/bin/env python3
"""
Mandala Core Monolith Builder (версия 5.0)
ПОЛНАЯ АРХИТЕКТУРА:
- Initium, Sphaerae, Akasha Chronicorum, Philosophia
- Geometria Sacra, Incubae
- Tectosphaera (в будущем)
- Все модули Мандалы в одном кристалле
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

# ========== 🔴 ПОЛНЫЙ СПИСОК МОДУЛЕЙ МАНДАЛЫ ==========
ALL_MODULES = [
    ("Initium", "initium.json"),
    ("Sphaerae", "sphaerae.json"),
    ("Akasha Chronicorum", "akasha_chronicorum.json"),
    ("Philosophia", "philosophia.json"),
    ("Geometria Sacra", "geometria_sacra.json"),      # 🔺 НОВЫЙ
    ("Incubae", "incubae.json")                       # 🌱 НОВЫЙ
]

# Модули, без которых монолит считается невалидным
CRITICAL_MODULES = [
    "Initium",
    "Philosophia",
    "Sphaerae",
    "Akasha Chronicorum",
    "Geometria Sacra",
    "Incubae"
]

def log(message: str, level: str = "INFO"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {level}: {message}")

def load_local_json(file_path: Path) -> Dict[str, Any]:
    """Загружает JSON из локального файла."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        log(f"  ✅ Загружен локально: {file_path.name}")
        return data
    except json.JSONDecodeError as e:
        raise ValueError(f"Невалидный JSON в {file_path.name}: {str(e)[:100]}")
    except FileNotFoundError:
        log(f"  ⚠️ Файл не найден локально: {file_path.name}", "WARNING")
        raise
    except Exception as e:
        raise Exception(f"Ошибка чтения {file_path.name}: {str(e)[:100]}")

def load_json_from_url(url: str, module_name: str) -> Dict[str, Any]:
    """Загружает JSON по URL."""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'MandalaCoreBuilder/5.0'})
        with urllib.request.urlopen(req, timeout=30) as response:
            content = response.read().decode('utf-8')
            data = json.loads(content)
            log(f"  ✅ Загружено по URL: {module_name}")
            return data
    except Exception as e:
        raise Exception(f"Не удалось загрузить {module_name} по URL {url}: {str(e)[:100]}")

def build_monolith() -> Dict[str, Any]:
    """Основная функция сборки монолита."""
    log("=" * 60)
    log("🌀 Mandala Core Monolith Builder v5.0")
    log("=" * 60)

    embedded_modules = {}
    failed_modules = []
    missing_modules = []
    loaded_modules = []

    # Загружаем все модули Мандалы
    for module_name, filename in ALL_MODULES:
        log(f"\n📦 Загрузка: {module_name}")

        # Сначала пробуем локальный файл
        file_path = REPO_ROOT / filename
        if file_path.exists():
            try:
                data = load_local_json(file_path)
                embedded_modules[module_name] = data
                loaded_modules.append(module_name)
                continue
            except Exception as e:
                log(f"  ❌ Ошибка локальной загрузки: {e}", "ERROR")
                # Пробуем URL как fallback

        # Пробуем загрузить с GitHub
        raw_url = f"https://raw.githubusercontent.com/voodoomushroomzzz-source/mandala-core/main/{filename}"
        try:
            data = load_json_from_url(raw_url, module_name)
            embedded_modules[module_name] = data
            loaded_modules.append(module_name)
        except Exception as e:
            log(f"  ❌ Ошибка URL: {e}", "ERROR")
            embedded_modules[module_name] = {
                "_error": str(e),
                "_status": "missing",
                "_module": module_name,
                "_filename": filename
            }
            failed_modules.append(module_name)
            if module_name in CRITICAL_MODULES:
                missing_modules.append(module_name)

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

    if critical_missing:
        error_msg = f"Невозможно собрать монолит: отсутствуют критические модули: {', '.join(critical_missing)}"
        log(error_msg, "ERROR")
        raise ValueError(error_msg)

    # Формируем мета-информацию о сборке
    current_time = datetime.now(timezone.utc)
    version_hash = hashlib.md5(current_time.isoformat().encode()).hexdigest()[:8]

    # Определяем версию из Initium (если есть)
    initium_version = embedded_modules.get("Initium", {}).get("version", "unknown")
    if initium_version == "unknown" and "Initium" in embedded_modules:
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
            "successful_modules": [name for name in embedded_modules if "_error" not in embedded_modules[name]],
            "failed_modules": failed_modules,
            "total_modules": len(ALL_MODULES),
            "loaded_modules": len(loaded_modules),
            "critical_modules_ok": len(critical_missing) == 0,
            "builder_version": "5.0"
        },
        "runtime_instruction": "Система загружена из монолита. Все модули Мандалы доступны.",
        "manifest": {
            "description": "Полный кристалл Mandala Core",
            "modules": [name for name, _ in ALL_MODULES],
            "critical_modules": CRITICAL_MODULES,
            "built_at": current_time.strftime("%Y-%m-%d %H:%M:%S UTC")
        }
    }

    return monolith

def validate_monolith(monolith: Dict[str, Any]) -> bool:
    """Дополнительная валидация собранного монолита."""
    log("\n" + "=" * 60)
    log("🧪 ВАЛИДАЦИЯ МОНОЛИТА")
    log("=" * 60)

    issues = []

    # Проверяем наличие всех критических модулей
    for mod in CRITICAL_MODULES:
        if mod not in monolith["embedded_modules"]:
            issues.append(f"❌ Отсутствует: {mod}")
        elif "_error" in monolith["embedded_modules"][mod]:
            issues.append(f"❌ Ошибка в {mod}: {monolith['embedded_modules'][mod]['_error'][:50]}")

    # Проверяем структуру модулей
    for mod_name, module_data in monolith["embedded_modules"].items():
        if "_error" not in module_data:
            if "module" not in module_data and "version" not in module_data:
                issues.append(f"⚠️ {mod_name}: отсутствует стандартное поле 'module' или 'version'")

    if issues:
        log("\n".join(issues), "WARNING")
        return False
    else:
        log("✅ Все проверки пройдены")
        return True

def main():
    """Точка входа."""
    try:
        # Создаём директорию для сборки
        BUILD_DIR.mkdir(exist_ok=True)
        log(f"📁 Рабочая директория: {REPO_ROOT}")

        # Собираем монолит
        monolith = build_monolith()

        # Сохраняем
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(monolith, f, indent=2, ensure_ascii=False)

        log(f"\n💾 Монолит сохранён: {OUTPUT_FILE}")
        log(f"📊 Размер: {os.path.getsize(OUTPUT_FILE)} байт")

        # Валидируем
        validate_monolith(monolith)

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
                print(f"   - {mod}")
        
        print("=" * 60)

    except Exception as e:
        log(f"💥 Критическая ошибка: {e}", "ERROR")
        sys.exit(1)

if __name__ == "__main__":
    main()
