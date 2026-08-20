#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Автосборка литературного вектора Mandala Symbiosis.
Собирает все стихи и прозу из папки poetry/ в единый JSON-файл literary_core_boot.json
и помещает его в honeycombs/boot_online/.
"""

import json
import os
import sys
import shutil
from datetime import datetime
from pathlib import Path

# Пути
BASE_DIR = Path(__file__).parent
POEMS_DIR = BASE_DIR / "poems"
PROSE_DIR = BASE_DIR / "prose"
INDEX_PATH = BASE_DIR / "index.json"
OUTPUT_DIR = Path("honeycombs/boot_online")
OUTPUT_PATH = OUTPUT_DIR / "literary_core_boot.json"

def scan_files(directory):
    """Сканирует папку и возвращает словарь {имя_файла: содержимое}"""
    result = {}
    if not directory.exists():
        return result
    
    for file_path in sorted(directory.glob("*.json")):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                result[file_path.stem] = json.load(f)
        except Exception as e:
            print(f"⚠️ Ошибка при чтении {file_path.name}: {e}")
    return result

def build_literary_core():
    """Основная функция сборки"""
    print("📦 Начинаю сборку литературного ядра...")
    
    # 1. Читаем индекс
    if not INDEX_PATH.exists():
        print("❌ index.json не найден!")
        sys.exit(1)
    
    with open(INDEX_PATH, 'r', encoding='utf-8') as f:
        index_data = json.load(f)
    
    # 2. Сканируем стихи
    print(f"📖 Сканирую {POEMS_DIR}...")
    poems = scan_files(POEMS_DIR)
    print(f"   Найдено стихотворений: {len(poems)}")
    
    # 3. Сканируем прозу
    print(f"📝 Сканирую {PROSE_DIR}...")
    prose = scan_files(PROSE_DIR)
    print(f"   Найдено прозаических текстов: {len(prose)}")
    
    # 4. Формируем выходную структуру
    total_works = len(poems) + len(prose)
    output = {
        "identity": {
            "name": "Literary Core Boot — Poetry & Prose",
            "version": "v1.0.0",
            "created": index_data.get("created", datetime.now().strftime("%Y-%m-%d")),
            "updated": datetime.now().strftime("%Y-%m-%d"),
            "description": "Полный слепок литературного вектора: все стихи, вся проза, индекс и заключения.",
            "total_poems": len(poems),
            "total_prose": len(prose),
            "total_works": total_works,
            "author": "Дмитрий Лёвин (voodookida)",
            "years_span": "2015–2026"
        },
        "index": index_data,
        "poems": poems,
        "prose": prose
    }
    
    # 5. Создаём папку назначения (если её нет)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # 6. Сохраняем результат
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Сборка завершена: {OUTPUT_PATH}")
    print(f"   Всего произведений: {total_works}")
    
    # 7. Обновляем index.json
    index_data["total"] = {
        "poems": len(poems),
        "prose": len(prose),
        "works": total_works
    }
    index_data["last_updated"] = datetime.now().strftime("%Y-%m-%d")
    
    with open(INDEX_PATH, 'w', encoding='utf-8') as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)
    
    print(f"📋 index.json обновлён (total_works = {total_works})")
    return True

if __name__ == "__main__":
    try:
        build_literary_core()
    except Exception as e:
        print(f"❌ Ошибка сборки: {e}")
        sys.exit(1)
