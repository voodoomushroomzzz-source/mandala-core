#!/usr/bin/env python3
import json, os
from datetime import datetime
from pathlib import Path

REGISTRY = Path("honeycombs/registry/index.json")
REPORTS_DIR = Path("reports")

def safe_load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8").strip())
    except json.JSONDecodeError as e:
        text = path.read_text(encoding="utf-8").strip()
        for i in range(10):
            try:
                return json.loads(text + ('}' * i))
            except:
                continue
        print(f"[error] Cannot read {path}: {e}")
        return None

def generate():
    REPORTS_DIR.mkdir(exist_ok=True)
    ts = datetime.now()
    ts_str = ts.strftime("%Y-%m-%d %H:%M:%S")
    ts_file = ts.strftime("%Y-%m-%d_%H-%M-%S")
    lines = [
        "# Honeycomb Scan Report - Mandala Simbioza", "",
        f"**Sistema:** Mandala Simbioza v1.2.0  ",
        f"**Data:** {ts_str}  ",
        "**Skaner:** honeycomb_scanner.py v1.0.0  ", "",
    ]
    reg = safe_load_json(REGISTRY) if REGISTRY.exists() else None
    if reg:
        content = reg.get("content", {})
        stats = content.get("registry", {})
        health = content.get("health", {})
        cats = content.get("categories", {})
        lines += [
            "## Statistika", "",
            "| Parametr | Znachenie |", "|----------|-----------|",
            f"| Vsego sot | {stats.get('total_honeycombs', 0)} |",
            f"| Poslednee skanirovanie | {stats.get('last_scan', 'N/A')} |",
            f"| Status zdorovya | {health.get('overall_health', 'unknown')} |",
            f"| Problem naydeno | {health.get('issues_found', 0)} |",
            "", "## Kategorii", "",
        ]
        for cat, data in cats.items():
            lines.append(f"- **{cat}**: {data.get('count', 0)} sot")
    else:
        lines += ["## Registry", "", "Run `make scan` first."]
    lines += ["", "## Struktura sot", ""]
    hc_count = 0
    for root, dirs, files in os.walk("honeycombs"):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        if "index.json" in files:
            rel = os.path.relpath(root, "honeycombs")
            lines.append(f"- honeycombs/{rel}/")
            hc_count += 1
    lines += ["", f"**Itogo:** {hc_count} sot s index.json", "", "---", f"*Sgenerirovano: {ts_str}*"]
    out = "\n".join(lines)
    out_path = REPORTS_DIR / f"scan_{ts_file}.md"
    out_path.write_text(out, encoding="utf-8")
    (REPORTS_DIR / "scan_report.md").write_text(out, encoding="utf-8")
    print(f"OK: {out_path}")

if __name__ == "__main__":
    generate()