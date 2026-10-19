#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_bundle.py — собирает kurtoch_bundle.json из всех модулей + скриптов.

Назначение: единый файл для онбординга новых SR-чатов.
Выход: honeycombs/boot_online/Personal/kurtoch_bundle.json
Идемпотентно. Запускается вручную или из GitHub Action.
"""
import io, json, os, sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
KURTOCH = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(os.path.dirname(KURTOCH)))
OUTPUT = os.path.join(REPO, "honeycombs", "boot_online", "personal", "kurtoch_bundle.json")

MODULES = {
    "index": "index.json",
    "taskboard": "taskboard.json",
    "taskboard_archive": "taskboard_archive.json",
    "team": "team.json",
    "knowledge_base": "knowledge_base.json",
}

EXCLUDE_SCRIPTS = {"notion_token.txt", "__pycache__"}
EXCLUDE_EXT = {".pyc"}

def read_text(path):
    with io.open(path, "r", encoding="utf-8") as f:
        return f.read()

def read_json(path):
    return json.loads(read_text(path))

def collect_scripts():
    out = {}
    for fname in sorted(os.listdir(HERE)):
        if fname in EXCLUDE_SCRIPTS or fname.startswith("."):
            continue
        if any(fname.endswith(e) for e in EXCLUDE_EXT):
            continue
        fpath = os.path.join(HERE, fname)
        if not os.path.isfile(fpath):
            continue
        if fname == "notion_token.txt":
            continue
        try:
            out[fname] = read_text(fpath)
        except Exception as e:
            print(f"  ! пропущен {fname}: {e}")
    return out

def main():
    print(f"Собираю bundle из {KURTOCH}")
    bundle = {
        "meta": {
            "bundle_version": "v1.0.0",
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source": "honeycombs/personal/kurtoch/",
            "generator": "scripts/build_bundle.py",
            "modules": list(MODULES.keys()),
            "scripts_included": [],
            "note": "Единый файл для онбординга нового SR. Содержит все модули хаба + полные тексты скриптов. Исключены: notion_token.txt, _snapshots/, _logs/, __pycache__/.",
        }
    }
    for key, fname in MODULES.items():
        path = os.path.join(KURTOCH, fname)
        if os.path.exists(path):
            bundle[key] = read_json(path)
            print(f"  ✅ {key:20} ({fname})")
        else:
            print(f"  ⚠  {key:20} — файл не найден: {fname}")

    scripts = collect_scripts()
    bundle["scripts"] = scripts
    bundle["meta"]["scripts_included"] = sorted(scripts.keys())
    print(f"  ✅ scripts: {len(scripts)} файлов")

    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with io.open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(bundle, f, ensure_ascii=False, indent=2)
        f.write("\n")
    size = os.path.getsize(OUTPUT)
    print(f"\n✅ saved: {os.path.relpath(OUTPUT, REPO)} ({size:,} байт)")

if __name__ == "__main__":
    main()
