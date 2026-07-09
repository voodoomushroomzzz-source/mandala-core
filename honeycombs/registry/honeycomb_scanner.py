#!/usr/bin/env python3
"""
Honeycomb Scanner v2.0 — Unified System Health Scanner for Mandala Symbiosis.
This is a wrapper that imports and runs the modular scanner from scanner/ package.
Integrates: base scan, task validation, Ahimsa filter, deadline monitoring, integrity checks.
"""
from scanner.cli import main

if __name__ == "__main__":
    main()
