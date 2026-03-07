# setup_automation.ps1 - Mandala Simbioza
# Skachaet fayly s GitHub i delaet commit

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "================================================" -ForegroundColor Magenta
Write-Host "   Mandala Simbioza -- Setup Automation v2      " -ForegroundColor Magenta
Write-Host "================================================" -ForegroundColor Magenta
Write-Host ""

# Proverka - my v korne repozitoriya?
if (-not (Test-Path ".git")) {
    Write-Host "[XX] Papka .git ne naydena!" -ForegroundColor Red
    Write-Host "[!!] Zapusti skript iz kornya repozitoriya mandala-core" -ForegroundColor Yellow
    Read-Host "Enter dlya vyhoda"
    exit 1
}
Write-Host "[OK] Repozitoriy nayden" -ForegroundColor Green

# Sozdanie papok
Write-Host "[>>] Sozdanie papok..." -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path ".github\workflows" | Out-Null
New-Item -ItemType Directory -Force -Path "reports" | Out-Null
Write-Host "[OK] Papki sozdany" -ForegroundColor Green

# Baza URL dlya skachivaniaya
$base = "https://raw.githubusercontent.com/voodoomushroomzzz-source/mandala-core/main"

# Fayly kotorye UZHE DOLZHNY byt v repo posle push
# My sozdayom ikh iz gist ili cherez prямую zapis

Write-Host "[>>] Sozdanie Makefile..." -ForegroundColor Cyan
$makefile = @"
.DEFAULT_GOAL := help
.PHONY: help setup check scan validate test clean all report

PYTHON        := python3
VENV_DIR      := .venv
VENV_PYTHON   := `$(VENV_DIR)/bin/python
VENV_PIP      := `$(VENV_DIR)/bin/pip
SCANNER       := honeycombs/registry/honeycomb_scanner.py
REPORTS_DIR   := reports
REGISTRY      := honeycombs/registry/index.json

help:
	@echo "Mandala Simbioza -- Scanner sot v1.0.0"
	@echo ""
	@echo "Komandy:"
	@echo "  make setup    - Sozdat venv i ustanovit zavisimosti"
	@echo "  make check    - Proverit okruzhenie"
	@echo "  make scan     - Zapustit skanirovanie sot"
	@echo "  make validate - Validaciya sot po standartu v2.0"
	@echo "  make test     - Testovyy progon skanera"
	@echo "  make report   - Sgenerirovat otchet"
	@echo "  make clean    - Ochistit vremennye fayly"
	@echo "  make all      - Polnyy cikl"

setup:
	@echo "Nastroyka okruzheniya..."
	@`$(PYTHON) --version
	@if [ ! -d "`$(VENV_DIR)" ]; then `$(PYTHON) -m venv `$(VENV_DIR); fi
	@`$(VENV_PIP) install --quiet --upgrade pip
	@`$(VENV_PIP) install --quiet -r requirements.txt
	@mkdir -p `$(REPORTS_DIR)
	@echo "OK: Okruzhenie nastroeno"

check:
	@echo "Proverka okruzheniya..."
	@`$(PYTHON) --version
	@if [ -f "`$(SCANNER)" ]; then echo "OK: Skaner nayde: `$(SCANNER)"; else echo "ERR: Skaner ne najden" && exit 1; fi
	@if [ -d "honeycombs" ]; then echo "OK: honeycombs/ est"; else echo "ERR: honeycombs/ ne najdena" && exit 1; fi
	@for f in `$`$(find honeycombs -name "*.json" 2>/dev/null); do `$(PYTHON) -c "import json; json.load(open('`$`$f'))" 2>/dev/null || echo "ERR: Nevalidnyy JSON: `$`$f"; done
	@echo "OK: Proverka zavershena"

scan:
	@echo "Skanirovanie sot..."
	@mkdir -p `$(REPORTS_DIR)
	@if [ -f "`$(VENV_PYTHON)" ]; then `$(VENV_PYTHON) `$(SCANNER) scan; else `$(PYTHON) `$(SCANNER) scan; fi
	@echo "OK: Skanirovanie zaversheno"

validate:
	@echo "Validaciya sot..."
	@if [ -f "`$(VENV_PYTHON)" ]; then `$(VENV_PYTHON) `$(SCANNER) validate; else `$(PYTHON) `$(SCANNER) validate; fi

test:
	@echo "Testovyy progon..."
	@if [ -f "`$(VENV_PYTHON)" ]; then `$(VENV_PYTHON) `$(SCANNER) test; else `$(PYTHON) `$(SCANNER) test; fi
	@echo "OK: Test zavershen"

report:
	@echo "Generaciya otcheta..."
	@mkdir -p `$(REPORTS_DIR)
	@if [ -f "`$(VENV_PYTHON)" ]; then `$(VENV_PYTHON) generate_report.py; else `$(PYTHON) generate_report.py; fi

clean:
	@echo "Ochistka..."
	@rm -f honeycomb_scanner.log
	@rm -f honeycombs/registry/scan_state.json
	@find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	@echo "OK: Ochistka zavershena"

all: setup check scan validate report
	@echo "OK: Polnyy cikl zavershen"
"@

[System.IO.File]::WriteAllText("$PWD\Makefile", $makefile, [System.Text.Encoding]::UTF8)
Write-Host "[OK] Makefile sozdan" -ForegroundColor Green

# generate_report.py
Write-Host "[>>] Sozdanie generate_report.py..." -ForegroundColor Cyan
$generateReport = @"
#!/usr/bin/env python3
import json, os
from datetime import datetime
from pathlib import Path

REGISTRY = Path("honeycombs/registry/index.json")
REPORTS_DIR = Path("reports")

def generate():
    REPORTS_DIR.mkdir(exist_ok=True)
    ts = datetime.now()
    ts_str = ts.strftime("%Y-%m-%d %H:%M:%S")
    ts_file = ts.strftime("%Y-%m-%d_%H-%M-%S")

    lines = [
        "# Otchet skanirovaniya sot",
        "",
        f"**Sistema:** Mandala Simbioza v1.2.0",
        f"**Data:** {ts_str}",
        "**Skaner:** honeycomb_scanner.py v1.0.0",
        "",
    ]

    if REGISTRY.exists():
        reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
        content = reg.get("content", {})
        stats = content.get("registry", {})
        health = content.get("health", {})
        cats = content.get("categories", {})
        lines += [
            "## Statistika",
            "",
            "| Parametr | Znachenie |",
            "|----------|-----------|",
            f"| Vsego sot | {stats.get('total_honeycombs', 0)} |",
            f"| Poslednee skanirovanie | {stats.get('last_scan', 'N/A')} |",
            f"| Status zdorovya | {health.get('overall_health', 'unknown')} |",
            f"| Problem naydeno | {health.get('issues_found', 0)} |",
            "",
            "## Kategorii",
            "",
        ]
        for cat, data in cats.items():
            lines.append(f"- **{cat}**: {data.get('count', 0)} sot")
    else:
        lines += ["## Registry ne najden", "", "Zapustite make scan"]

    lines += ["", "## Struktura sot", ""]
    hc_count = 0
    for root, dirs, files in os.walk("honeycombs"):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        if "index.json" in files:
            rel = os.path.relpath(root, "honeycombs")
            lines.append(f"- honeycombs/{rel}/")
            hc_count += 1

    lines += ["", f"**Itogo:** {hc_count} sot s index.json", "", "---", f"*Sgenerirovano: {ts_str}*"]

    content_out = "\n".join(lines)
    out_path = REPORTS_DIR / f"scan_{ts_file}.md"
    out_path.write_text(content_out, encoding="utf-8")
    (REPORTS_DIR / "scan_report.md").write_text(content_out, encoding="utf-8")
    print(f"OK: Otchet sokhranyon: {out_path}")
    print(f"OK: Aktualnyy otchet: reports/scan_report.md")

if __name__ == "__main__":
    generate()
"@

[System.IO.File]::WriteAllText("$PWD\generate_report.py", $generateReport, [System.Text.Encoding]::UTF8)
Write-Host "[OK] generate_report.py sozdan" -ForegroundColor Green

# honeycomb-scan.yml
Write-Host "[>>] Sozdanie .github/workflows/honeycomb-scan.yml..." -ForegroundColor Cyan
$workflow = @"
name: Honeycomb Scanner

on:
  push:
    branches: [main, develop]
    paths:
      - 'honeycombs/**'
      - 'Makefile'
      - 'requirements.txt'
  workflow_dispatch:
    inputs:
      force_rescan:
        description: 'Force full rescan'
        required: false
        default: 'false'
        type: boolean

concurrency:
  group: honeycomb-scan-`${{ github.ref }}
  cancel-in-progress: true

jobs:
  scan:
    name: Scan and validate honeycombs
    runs-on: ubuntu-latest
    timeout-minutes: 10
    permissions:
      contents: write

    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Setup Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Check environment
        run: make check

      - name: Scan honeycombs
        run: |
          FORCE_FLAG=""
          if [ "`${{ github.event.inputs.force_rescan }}" = "true" ]; then
            FORCE_FLAG="FORCE=1"
          fi
          make scan `$FORCE_FLAG

      - name: Validate honeycombs
        run: make validate

      - name: Generate report
        run: make report

      - name: Generate JSON report
        run: |
          mkdir -p reports
          python3 -c "
          import json, os
          from pathlib import Path
          from datetime import datetime, timezone
          registry_path = Path('honeycombs/registry/index.json')
          report = {
            'scan_time': datetime.now(timezone.utc).isoformat(),
            'commit': os.environ.get('GITHUB_SHA', 'local')[:8],
            'branch': os.environ.get('GITHUB_REF_NAME', 'unknown'),
            'honeycombs_found': sum(1 for r,d,f in os.walk('honeycombs') if 'index.json' in f),
            'json_files_oversized': [str(p) for p in Path('honeycombs').rglob('*.json') if p.stat().st_size > 2048],
            'status': 'ok'
          }
          report['status'] = 'warning' if report['json_files_oversized'] else 'ok'
          Path('reports/scan_result.json').write_text(json.dumps(report, indent=2))
          print(f'Honeycombs: {report[\"honeycombs_found\"]}')
          print(f'Status: {report[\"status\"]}')
          "

      - name: Summary
        if: always()
        run: |
          python3 -c "
          import json
          from pathlib import Path
          p = Path('reports/scan_result.json')
          if p.exists():
            r = json.loads(p.read_text())
            lines = [
              '## Honeycomb Scan Results',
              f'Status: {r.get(\"status\")}',
              f'Honeycombs found: {r.get(\"honeycombs_found\", 0)}',
              f'Oversized files: {len(r.get(\"json_files_oversized\", []))}',
            ]
            summary = chr(10).join(lines)
          else:
            summary = 'No report found'
          with open('/tmp/summary.md', 'w') as f:
            f.write(summary)
          print(summary)
          "
          cat /tmp/summary.md >> `$GITHUB_STEP_SUMMARY

      - name: Commit updated registry
        if: github.event_name == 'push' && github.ref == 'refs/heads/main'
        run: |
          git config --local user.email "github-actions[bot]@users.noreply.github.com"
          git config --local user.name "github-actions[bot]"
          git add honeycombs/registry/index.json || true
          git add honeycombs/registry/scan_state.json || true
          git add reports/ || true
          if git diff --staged --quiet; then
            echo "No changes to commit"
          else
            TS=`$(date -u +"%Y-%m-%dT%H:%M:%SZ")
            HC=`$(python3 -c "import os; print(sum(1 for r,d,f in os.walk('honeycombs') if 'index.json' in f))")
            git commit -m "auto: honeycomb scan `${TS} | `${HC} honeycombs"
            git push
          fi

      - name: Upload artifacts
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: scan-reports-`${{ github.run_number }}
          path: reports/
          retention-days: 30
          if-no-files-found: warn
"@

[System.IO.File]::WriteAllText("$PWD\.github\workflows\honeycomb-scan.yml", $workflow, [System.Text.Encoding]::UTF8)
Write-Host "[OK] honeycomb-scan.yml sozdan" -ForegroundColor Green

# scan_report.md
Write-Host "[>>] Sozdanie reports/scan_report.md..." -ForegroundColor Cyan
$scanReport = @"
# Otchet skanirovaniya sot - Mandala Simbioza

**Sistema:** Mandala Simbioza v1.2.0
**Skaner:** honeycomb_scanner.py v1.0.0

> Etot fayl obnovlyaetsya avtomaticheski cherez make report ili GitHub Actions

---

## Statistika

| Parametr | Znachenie |
|----------|-----------|
| Vsego sot | - |
| Poslednee skanirovanie | - |
| Status zdorovya | - |

## Struktura sot

*Zapustite make scan && make report dlya zapolneniya*

---
*Shablon sozdan setup_automation.ps1*
"@

[System.IO.File]::WriteAllText("$PWD\reports\scan_report.md", $scanReport, [System.Text.Encoding]::UTF8)
Write-Host "[OK] scan_report.md sozdan" -ForegroundColor Green

# Git commit i push
Write-Host ""
Write-Host "[>>] Otpravka faylov na GitHub..." -ForegroundColor Cyan

try {
    git add Makefile
    git add generate_report.py
    git add ".github/workflows/honeycomb-scan.yml"
    git add "reports/scan_report.md"

    $gitStatus = git status --porcelain
    if ($gitStatus) {
        git commit -m "feat: honeycomb scanner automation (Makefile + CI/CD + reports)"
        git push
        Write-Host "[OK] Fayly otpravleny na GitHub!" -ForegroundColor Green
    } else {
        Write-Host "[!!] Fayly uzhe aktualni, commit ne nuzhen" -ForegroundColor Yellow
    }
} catch {
    Write-Host "[!!] Git push ne udalsa: $_" -ForegroundColor Yellow
    Write-Host "[!!] Poprobuy vruchnuyu: git push" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "================================================" -ForegroundColor Green
Write-Host "   Gotovo! Sozdano faylov: 4                    " -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Green
Write-Host ""
Write-Host "[OK] Makefile" -ForegroundColor Green
Write-Host "[OK] generate_report.py" -ForegroundColor Green
Write-Host "[OK] .github/workflows/honeycomb-scan.yml" -ForegroundColor Green
Write-Host "[OK] reports/scan_report.md" -ForegroundColor Green
Write-Host ""
Write-Host "GitHub Actions:" -ForegroundColor Cyan
Write-Host "https://github.com/voodoomushroomzzz-source/mandala-core/actions"
Write-Host ""
Read-Host "Enter dlya zakrytiya"
