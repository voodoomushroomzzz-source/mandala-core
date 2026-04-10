.DEFAULT_GOAL := help
.PHONY: help scan validate

SCANNER := honeycombs/registry/honeycomb_scanner.py

help:
@echo "Mandala Symbiosis  Honeycomb Scanner"
@echo ""
@echo "Commands:"
@echo "  make scan      Run honeycomb scanner"
@echo "  make validate  Validate honeycombs"

scan:
@py $(SCANNER) scan

validate:
@py $(SCANNER) validate
