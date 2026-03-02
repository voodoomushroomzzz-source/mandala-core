#!/usr/bin/env python3
"""
Simbiosis Monolith Builder v2.0
Собирает все модули из simbiosis/ в единый монолитный файл.
Запускается из корня репозитория.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── Конфигурация модулей ──────────────────────────────────────────────────────
# Ключ — имя в монолите, значение — файл в simbiosis/
MODULE_MAP = {
    "Boot":         "simbiosis/boot.json",
    "CoreMap":      "simbiosis/core_map.json",
    "Philosophy":   "simbiosis/philosophy.json",
    "EngineerChat": "simbiosis/engineer_chat.json",
    "Roadmaps":     "simbiosis/roadmaps.json",
    "Seeds":        "simbiosis/seeds.json",
    "TelegramBot":  "simbiosis/telegram_bot.json",
    "Instructions": "simbiosis/instructions.json",  # ← добавлен
    "Tasks":        "simbiosis/tasks.json",          # ← добавлен
}

CRITICAL_MODULES = ["Boot", "CoreMap", "Philosophy"]
BUILDER_VERSION  = "simbiosis-2.0"
OUTPUT_FILE      = "simbiosis/monolith.json"


def load_module(name: str, path: str) -> tuple[dict | None, str | None]:
    """Загружает JSON-модуль. Возвращает (data, error)."""
    if not Path(path).exists():
        return None, f"файл не найден: {path}"
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f), None
    except json.JSONDecodeError as e:
        return None, f"JSON ошибка: {e}"


def get_commit_sha() -> str:
    """Читает SHA текущего коммита из git."""
    try:
        import subprocess
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"


def get_repo_url(sha: str) -> str:
    try:
        import subprocess
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, check=True
        )
        url = result.stdout.strip().replace(".git", "")
        return f"{url}/commit/{sha}"
    except Exception:
        return ""


def build_monolith() -> dict:
    embedded   = {}
    successful = []
    failed     = []
    missing_optional = []
    commit_sha = get_commit_sha()
    repo_url   = get_repo_url(commit_sha)
    timestamp  = datetime.now(timezone.utc).isoformat()

    print(f"🏗️  Simbiosis Monolith Builder {BUILDER_VERSION}")
    print(f"📅 {timestamp}")
    print(f"🔖 commit: {commit_sha[:12]}")
    print("─" * 50)

    for name, path in MODULE_MAP.items():
        data, err = load_module(name, path)
        if data is not None:
            embedded[name] = data
            successful.append(name)
            size = Path(path).stat().st_size
            print(f"  ✅ {name:<15} ({size:,} bytes)")
        else:
            failed.append(name)
            if name in CRITICAL_MODULES:
                print(f"  ❌ {name:<15} КРИТИЧЕСКИЙ: {err}")
            else:
                missing_optional.append(name)
                print(f"  ⚠️  {name:<15} пропущен: {err}")

    critical_ok = all(m in successful for m in CRITICAL_MODULES)
    if not critical_ok:
        print("\n❌ Критические модули не загружены — сборка прервана")
        sys.exit(1)

    monolith = {
        "module":          "Mandala Simbiosis Monolith",
        "version":         f"simbiosis-v2.0.0-{commit_sha[:8]}",
        "runtime_mode":    "monolith",
        "build_timestamp": timestamp,
        "build_source":    commit_sha,
        "build_source_url": repo_url,
        "build_info": {
            "timestamp":              timestamp,
            "builder_version":        BUILDER_VERSION,
            "successful_modules":     successful,
            "failed_modules":         [m for m in failed if m not in missing_optional],
            "missing_optional_modules": missing_optional,
            "total_modules":          len(MODULE_MAP),
            "loaded_modules":         len(successful),
            "critical_modules_ok":    critical_ok,
        },
        "embedded_modules": embedded,
        "runtime_instruction": (
            "Система Simbiosis загружена из монолита. "
            "Используй embedded_modules для доступа к модулям."
        ),
        "manifest": {
            "description":      "Mandala Simbiosis Monolith — инженерное ядро Mandala Core.",
            "modules":          successful,
            "critical_modules": CRITICAL_MODULES,
            "built_at":         timestamp.replace("T", " ").split(".")[0] + " UTC",
        },
    }

    # Записываем
    Path(OUTPUT_FILE).parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(monolith, f, ensure_ascii=False, separators=(",", ":"))

    size_kb = Path(OUTPUT_FILE).stat().st_size / 1024
    print("─" * 50)
    print(f"✅ Монолит собран: {OUTPUT_FILE} ({size_kb:.1f} KB)")
    print(f"   Модули: {len(successful)}/{len(MODULE_MAP)}")
    return monolith


if __name__ == "__main__":
    build_monolith()
