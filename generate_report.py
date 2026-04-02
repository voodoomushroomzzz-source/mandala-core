#!/usr/bin/env python3
"""
Honeycomb Scan Report Generator
Генерирует красивый Markdown-отчёт на основе scan_state.json и структуры сот.
"""

import json
import os
from datetime import datetime
from pathlib import Path

SCAN_STATE = Path("honeycombs/registry/scan_state.json")
REPORTS_DIR = Path("reports")

def safe_load_json(path: Path):
    try:
        if path.exists():
            content = path.read_text(encoding="utf-8").strip()
            return json.loads(content) if content else None
        return None
    except Exception as e:
        print(f"[ERROR] Cannot read {path}: {e}")
        return None

def generate():
    REPORTS_DIR.mkdir(exist_ok=True)
    ts = datetime.now()
    ts_str = ts.strftime("%Y-%m-%d %H:%M:%S")
    ts_file = ts.strftime("%Y-%m-%d_%H-%M-%S")

    state = safe_load_json(SCAN_STATE)

    lines = [
        "# Honeycomb Scan Report  Mandala Simbioza",
        "",
        f"**Система:** Mandala Simbioza v1.2.0",
        f"**Дата:** {ts_str}",
        "**Сканер:** honeycomb_scanner.py v1.0.0",
        "",
    ]

    if state:
        stats = state.get("statistics", {})
        last_scan = state.get("last_scan", "N/A")
        lines += [
            "## Статистика",
            "",
            "| Параметр                  | Значение          |",
            "|---------------------------|-------------------|",
            f"| Всего сот                 | {stats.get('total_scanned', 0)} |",
            f"| Валидных v2               | {stats.get('valid_v2', 0)} |",
            f"| Невалидных v2             | {stats.get('invalid_v2', 0)} |",
            f"| Ошибок                    | {stats.get('errors', 0)} |",
            f"| Всего файлов              | {stats.get('total_files', 0)} |",
            f"| Общий размер              | {stats.get('total_size_kb', 0)} KB |",
            f"| Последнее сканирование    | {last_scan} |",
            "",
        ]

    # Структура сот
    lines += ["## Структура сот", ""]
    hc_count = 0
    for root, dirs, files in os.walk("honeycombs"):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        if "index.json" in files:
            rel = os.path.relpath(root, "honeycombs").replace("\\", "/")
            lines.append(f"- honeycombs/{rel}/")
            hc_count += 1

    lines += ["", f"**Итого сот с index.json:** {hc_count}", "", "---", f"*Сгенерировано: {ts_str}*"]

    out = "\n".join(lines)
    out_path = REPORTS_DIR / f"scan_{ts_file}.md"
    out_path.write_text(out, encoding="utf-8")
    (REPORTS_DIR / "scan_report.md").write_text(out, encoding="utf-8")
    print(f" Отчёт успешно сохранён: {out_path}")

if __name__ == "__main__":
    generate()