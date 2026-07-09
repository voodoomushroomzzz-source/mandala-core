#!/usr/bin/env python3
"""
Core scanner logic for Mandala Symbiosis.
"""
import os
import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from .validators import TaskValidator, AhimsaFilter, DeadlineSentinel, IntegrityCheck
from .reporters import save_scan_state, save_registry
from .models import HoneycombIndex, Identity, Meta

class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def print_colored(text: str, color: str = Colors.OKGREEN):
    print(f"{color}{text}{Colors.ENDC}")

class HoneycombScanner:
    def __init__(self, base_path: str = ".", full_check: bool = False,
                 validate_tasks: bool = False, ahimsa: bool = False,
                 deadlines: bool = False, integrity: bool = False,
                 no_cache: bool = False, verbose: bool = False):
        self.base_path = Path(base_path)
        self.full_check = full_check
        self.validate_tasks = validate_tasks or full_check
        self.ahimsa = ahimsa or full_check
        self.deadlines = deadlines or full_check
        self.integrity = integrity or full_check
        self.no_cache = no_cache
        self.verbose = verbose
        self.honeycombs = []
        self.new_honeycombs = []
        self.modified_honeycombs = []
        self.deleted_honeycombs = []
        self.validation_errors = []
        self.stats = {"total_scanned": 0, "valid_v2": 0, "invalid_v2": 0, "errors": 0, "warnings": 0, "total_files": 0, "total_size_kb": 0}
        self.previous_scan_cache = {}
        self.guard_results = {}

    def scan_all_honeycombs(self):
        print("=" * 60)
        print_colored("HONEYCOMB SCANNER v2.0 — SYSTEM HEALTH SCAN", Colors.BOLD)
        print("=" * 60)
        honeycombs_path = self.base_path / 'honeycombs'
        if honeycombs_path.exists():
            self._recursive_scan(honeycombs_path)
        else:
            print(f"❌ Honeycombs folder not found: {honeycombs_path}")
            return
        print(f"\n✅ Scan complete. Found {len(self.honeycombs)} honeycombs.")

    def _recursive_scan(self, directory: Path):
        for item in directory.iterdir():
            if item.is_dir() and not item.name.startswith('.'):
                index_file = item / "index.json"
                if index_file.exists():
                    self._analyze_honeycomb(index_file)
                self._recursive_scan(item)

    def _analyze_honeycomb(self, index_path: Path):
        try:
            with open(index_path, 'r', encoding='utf-8-sig') as f:
                data = json.load(f)
            honeycomb_id = str(index_path.parent.relative_to(self.base_path))
            self.honeycombs.append({"id": honeycomb_id, "path": str(index_path), "data": data})
            self.stats["total_scanned"] += 1
            print(f"[OK] {honeycomb_id}")
        except Exception as e:
            print(f"[ERROR] {index_path}: {e}")
            self.stats["errors"] += 1
