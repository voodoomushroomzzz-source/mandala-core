.DEFAULT_GOAL := help
.PHONY: help setup check scan validate test clean all report

PYTHON        := python3
VENV_DIR      := .venv
VENV_PYTHON   := $(VENV_DIR)/bin/python
VENV_PIP      := $(VENV_DIR)/bin/pip
SCANNER       := honeycombs/registry/honeycomb_scanner.py
REPORTS_DIR   := reports
REGISTRY      := honeycombs/registry/index.json

help:
@echo "Mandala Simbioza -- Scanner sot v1.0.0"
@echo ""
@echo "Komandy:"
@echo "  make setup    - Sozdat venv i ustanovit zavisimosti"
@echo "  make check    - Proverit okruzhenie"
@echo "  make scan     - Zapustit skanirovanie sot (s FORCE=1 po default)"
@echo "  make validate - Validaciya sot"
@echo "  make test     - Testovyy progonskanera"
@echo "  make report   - Sgenerirovat otchet"
@echo "  make clean    - Ochistit"
@echo "  make all      - Polnyy cikl"

setup:
@echo "Nastroyka okruzheniya..."
@$(PYTHON) --version
@if [ ! -d "$(VENV_DIR)" ]; then $(PYTHON) -m venv $(VENV_DIR); fi
@$(VENV_PIP) install --quiet --upgrade pip
@$(VENV_PIP) install --quiet -r requirements.txt
@mkdir -p $(REPORTS_DIR)
@echo "OK: Okruzhenie nastroeno"

check:
@echo "Proverka okruzheniya..."
@$(PYTHON) --version
@if [ -f "$(SCANNER)" ]; then echo "OK: Skaner nayde"; else echo "ERR: Skaner ne najden" && exit 1; fi
@echo "OK: Proverka zavershena"

scan:
@echo "Skanirovanie sot с FORCE=1..."
@mkdir -p $(REPORTS_DIR)
@FORCE=1
@if [ -f "$(VENV_PYTHON)" ]; then $(VENV_PYTHON) $(SCANNER) scan; else $(PYTHON) $(SCANNER) scan; fi
@echo "OK: Skanirovanie zaversheno (FORCE=1)"

validate:
@echo "Validaciya sot..."
@if [ -f "$(VENV_PYTHON)" ]; then $(VENV_PYTHON) $(SCANNER) validate; else $(PYTHON) $(SCANNER) validate; fi

test:
@echo "Testovyy progonskanera..."
@if [ -f "$(VENV_PYTHON)" ]; then $(VENV_PYTHON) $(SCANNER) test; else $(PYTHON) $(SCANNER) test; fi

report:
@echo "Generaciya otcheta..."
@mkdir -p $(REPORTS_DIR)
@if [ -f "$(VENV_PYTHON)" ]; then $(VENV_PYTHON) generate_report.py; else $(PYTHON) generate_report.py; fi

clean:
@echo "Ochistka..."
@rm -f honeycomb_scanner.log
@rm -f honeycombs/registry/scan_state.json
@find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
@echo "OK: Ochistka zavershena"

all: setup check scan validate report
@echo "OK: Polnyy cikl zavershen"
