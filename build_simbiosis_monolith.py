#!/usr/bin/env python3
"""
Mandala Simbiosis Monolith Builder (версия 1.0)
ПОЛНАЯ АРХИТЕКТУРА С GRACEFUL FALLBACK:
- Boot, CoreMap, Philosophy — КРИТИЧЕСКИЕ
- EngineerChat, Roadmaps, Seeds, TelegramBot — ОПЦИОНАЛЬНЫЕ (логируются, но не валят сборку)
- Монолит собирается всегда, даже если опциональных модулей ещё нет
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
OUTPUT_FILE = BUILD_DIR / "mandala_simbiosis.monolith.latest.json"
SIMBIOSIS_DIR = "simbiosis"

# ========== ПОЛНЫЙ СПИСОК МОДУЛЕЙ SIMBIOSIS ==========
ALL_MODULES = [
    ("Boot",          "boot.json"),
    ("CoreMap",       "core_map.json"),
    ("Philosophy",    "philosophy.json"),
    ("EngineerChat",  "engineer_chat.json"),   # ⚙️ Опциональный
    ("Roadmaps",      "roadmaps.json"),         # 🗺️ Опциональный
    ("Seeds",         "seeds.json"),            # 🌱 Опциональный
    ("TelegramBot",   "telegram_bot.json"),     # 🤖 Опциональный
]

# ========== 🔴 КРИТИЧЕСКИЕ МОДУЛИ ==========
# Без них монолит Simbiosis бессмыслен.
CRITICAL_MODULES = [
    "Boot",
    "CoreMap",
    "Philosophy",
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
        req = urllib.request.Request(url, headers={'User-Agent': 'MandalaSimbiosisBuilder/1.0'})
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
    log("🌀 Mandala Simbiosis Monolith Builder v1.0 (graceful fallback)")
    log("=" * 60)

    embedded_modules = {}
    failed_modules = []
    missing_optional = []
    loaded_modules = []

    # Загружаем все модули Simbiosis (критические + опциональные)
    for module_name, filename in ALL_MODULES:
        log(f"\n📦 Загрузка: {module_name}")

        # Пробуем локальный файл из папки simbiosis/
        file_path = REPO_ROOT / SIMBIOSIS_DIR / filename
        data = load_local_json(file_path)

        # Если локально нет — пробуем URL
        if data is None:
            raw_url = (
                f"https://raw.githubusercontent.com/voodoomushroomzzz-source/"
                f"mandala-core/main/{SIMBIOSIS_DIR}/{filename}"
            )
            data = load_json_from_url(raw_url, module_name)

        # Если данные получены — сохраняем
        if data is not None:
            embedded_modules[module_name] = data
            loaded_modules.append(module_name)
        else:
            error_info = {
                "_error": "Module not found locally or via URL",
                "_status": "missing",
                "_module": module_name,
                "_filename": f"{SIMBIOSIS_DIR}/{filename}",
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

    if critical_missing:
        error_msg = (
            f"НЕВОЗМОЖНО СОБРАТЬ МОНОЛИТ: отсутствуют критические модули: "
            f"{', '.join(critical_missing)}"
        )
        log(error_msg, "ERROR")
        raise ValueError(error_msg)

    # Версия и мета-информация
    current_time = datetime.now(timezone.utc)
    version_hash = hashlib.md5(current_time.isoformat().encode()).hexdigest()[:8]

    # Определяем версию из Boot, затем CoreMap
    boot_version = "unknown"
    for mod in ("Boot", "CoreMap"):
        if mod in embedded_modules and "_error" not in embedded_modules[mod]:
            v = (
                embedded_modules[mod].get("version")
                or embedded_modules[mod].get("schema_version")
            )
            if v:
                boot_version = v
                break

    monolith = {
        "module": "Mandala Simbiosis Monolith",
        "version": f"simbiosis-v{boot_version}-{version_hash}",
        "runtime_mode": "monolith",
        "build_timestamp": current_time.isoformat(),
        "build_source": os.getenv("GITHUB_SHA", "local-build"),
        "build_source_url": (
            f"https://github.com/voodoomushroomzzz-source/mandala-core/commit/"
            f"{os.getenv('GITHUB_SHA', 'local')}"
        ),
        "embedded_modules": embedded_modules,
        "build_info": {
            "timestamp": current_time.isoformat(),
            "builder_version": "simbiosis-1.0",
            "successful_modules": [
                name for name in embedded_modules
                if "_error" not in embedded_modules[name]
            ],
            "failed_modules": failed_modules,
            "missing_optional_modules": missing_optional,
            "total_modules": len(ALL_MODULES),
            "loaded_modules": len(loaded_modules),
            "critical_modules_ok": len(critical_missing) == 0
        },
        "runtime_instruction": "Система Simbiosis загружена из монолита.",
        "manifest": {
            "description": "Mandala Simbiosis Monolith — инженерное ядро Mandala Core.",
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
            print(
                f"⚠️ Отсутствуют опциональные: "
                f"{', '.join(monolith['build_info']['missing_optional_modules'])}"
            )

        print("=" * 60)

    except Exception as e:
        log(f"💥 Критическая ошибка: {e}", "ERROR")
        sys.exit(1)

if __name__ == "__main__":
    main()
