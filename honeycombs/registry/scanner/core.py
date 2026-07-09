#!/usr/bin/env python3
"""
Core scanner logic for Mandala Symbiosis.
Full functionality from original honeycomb_scanner.py
"""
import os
import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from .validators import TaskValidator, AhimsaFilter, DeadlineSentinel, IntegrityCheck, SeedCountValidator
from .reporters import save_scan_state, save_registry

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
        self.stats = {
            "total_scanned": 0,
            "valid_v2": 0,
            "invalid_v2": 0,
            "errors": 0,
            "warnings": 0,
            "total_files": 0,
            "total_size_kb": 0
        }
        self.previous_scan_cache = {}
        self.guard_results = {}

    def _load_previous_state(self):
        if self.no_cache:
            print("--no-cache set: skipping previous-state load")
            return
        state_path = self.base_path / 'honeycombs' / 'registry' / 'scan_state.json'
        try:
            if state_path.exists():
                with open(state_path, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                    cache = state.get('honeycomb_hashes')
                    if isinstance(cache, dict):
                        self.previous_scan_cache = cache
                        print(f"Loaded {len(self.previous_scan_cache)} entries from previous registry")
        except Exception as e:
            print(f"Error loading previous state (ignored): {e}")
            self.previous_scan_cache = {}

    def _calculate_hash(self, data: Dict) -> str:
        try:
            json_str = json.dumps(data, sort_keys=True, ensure_ascii=False)
            return hashlib.md5(json_str.encode('utf-8')).hexdigest()
        except:
            return "error"

    def _validate_v2_structure(self, honeycomb_data: Dict) -> Tuple[bool, Dict]:
        details = {"errors": [], "warnings": [], "missing_sections": [], "missing_fields": []}
        
        required_sections = ["identity", "meta"]
        for section in required_sections:
            if section not in honeycomb_data:
                details["errors"].append(f"Missing required section: {section}")
                details["missing_sections"].append(section)
        
        if "identity" in honeycomb_data:
            identity = honeycomb_data["identity"]
            if isinstance(identity, dict):
                required_fields = ["module_id", "name", "version", "layer", "type"]
                for field in required_fields:
                    if field not in identity:
                        details["errors"].append(f"Missing required field identity.{field}")
                        details["missing_fields"].append(f"identity.{field}")
            else:
                details["errors"].append(f"identity is not a dict, got {type(identity).__name__}")
        
        if "meta" in honeycomb_data:
            meta = honeycomb_data["meta"]
            if isinstance(meta, dict) and "description" not in meta:
                details["warnings"].append("Recommended to add description in meta.description")
        else:
            details["warnings"].append("meta section is missing")
        
        return len(details["errors"]) == 0, details

    def _count_honeycomb_files(self, honeycomb_dir: Path) -> Tuple[int, float]:
        file_count = 0
        total_size_bytes = 0
        try:
            for root, dirs, files in os.walk(honeycomb_dir):
                for file in files:
                    if file.endswith('.json'):
                        file_count += 1
                        file_path = Path(root) / file
                        total_size_bytes += file_path.stat().st_size
        except Exception as e:
            print(f"Error counting files in {honeycomb_dir}: {e}")
            self.stats["errors"] += 1
        return file_count, round(total_size_bytes / 1024, 2)

    def _detect_changes(self, honeycomb_id: str, honeycomb_info: Dict):
        try:
            if honeycomb_id in self.previous_scan_cache:
                previous = self.previous_scan_cache[honeycomb_id]
                if isinstance(previous, dict):
                    previous_hash = previous.get("hash")
                elif isinstance(previous, str):
                    previous_hash = previous
                else:
                    previous_hash = None
                if previous_hash != honeycomb_info["hash"]:
                    self.modified_honeycombs.append(honeycomb_id)
                    print(f"   Modified: {honeycomb_id}")
            else:
                self.new_honeycombs.append(honeycomb_id)
                print(f"   + New: {honeycomb_id}")
        except Exception as e:
            print(f"   (change detection skipped for {honeycomb_id}: {e})")

    def _analyze_honeycomb(self, index_path: Path):
        try:
            with open(index_path, 'r', encoding='utf-8-sig') as f:
                data = json.load(f)
            
            honeycomb_dir = index_path.parent
            relative_path = honeycomb_dir.relative_to(self.base_path)
            honeycomb_id = str(relative_path).replace(os.sep, '/')
            
            identity = data.get("identity", {})
            if not isinstance(identity, dict):
                identity = {}
                self.validation_errors.append({
                    "honeycomb_id": honeycomb_id,
                    "error": f"identity is not a dict, got {type(data.get('identity')).__name__}"
                })
            
            content_hash = self._calculate_hash(data)
            is_valid, validation_details = self._validate_v2_structure(data)
            file_count, total_size_kb = self._count_honeycomb_files(honeycomb_dir)
            
            honeycomb_info = {
                "honeycomb_id": honeycomb_id,
                "path": str(index_path),
                "relative_path": str(relative_path),
                "name": identity.get("name", "Unknown"),
                "module_id": identity.get("module_id", "Unknown"),
                "version": identity.get("version", "Unknown"),
                "layer": identity.get("layer", 0),
                "type": identity.get("type", "Unknown"),
                "status": identity.get("status", "active"),
                "description": identity.get("description", ""),
                "tags": identity.get("tags", []),
                "resonance": identity.get("resonance", "0%"),
                "is_v2_compliant": is_valid,
                "validation_details": validation_details,
                "hash": content_hash,
                "last_modified": os.path.getmtime(index_path),
                "file_count": file_count,
                "total_size_kb": total_size_kb,
                "scan_timestamp": datetime.now().isoformat()
            }
            
            self.honeycombs.append(honeycomb_info)
            self.stats["total_scanned"] += 1
            self.stats["total_files"] += file_count
            self.stats["total_size_kb"] += total_size_kb

            self._detect_changes(honeycomb_id, honeycomb_info)
            
            if is_valid:
                self.stats["valid_v2"] += 1
                print(f"[OK] {honeycomb_id}: {identity.get('name', 'Unknown')} v{identity.get('version', 'Unknown')}")
            else:
                self.stats["invalid_v2"] += 1
                self.stats["warnings"] += 1
                print(f"[WARN] {honeycomb_id}: Not v2.0 compliant")
                self.validation_errors.append({
                    "honeycomb_id": honeycomb_id,
                    "name": identity.get("name", "Unknown"),
                    "errors": validation_details.get("errors", []),
                    "warnings": validation_details.get("warnings", [])
                })
                
        except json.JSONDecodeError as e:
            print(f"[ERROR] {index_path}: JSON error: {e}")
            self.stats["errors"] += 1
        except Exception as e:
            print(f"[ERROR] {index_path}: Analysis error: {e}")
            self.stats["errors"] += 1

    def _recursive_scan(self, directory: Path):
        try:
            for item in directory.iterdir():
                if item.is_dir() and not item.name.startswith('.'):
                    index_file = item / "index.json"
                    if index_file.exists():
                        self._analyze_honeycomb(index_file)
                    self._recursive_scan(item)
        except Exception as e:
            print(f"Error scanning directory {directory}: {e}")
            self.stats["errors"] += 1

    def _run_symbiosis_guard(self):
        print("\n" + "=" * 60)
        print("SYMBIOSIS GUARD — SYSTEM HEALTH CHECK")
        print("=" * 60)
        
        results = {}
        
        if self.validate_tasks:
            print("\n[1] Task Validator...")
            validator = TaskValidator(self.base_path)
            results['task_validator'] = validator.validate()
            print(f"    Errors: {results['task_validator']['errors_count']}, Warnings: {results['task_validator']['warnings_count']}, Expired: {results['task_validator']['expired_count']}")
        
        if self.ahimsa:
            print("\n[2] Ahimsa Filter...")
            filter_ = AhimsaFilter(self.base_path)
            results['ahimsa_filter'] = filter_.scan()
            print(f"    Errors: {results['ahimsa_filter']['errors_count']}, Warnings: {results['ahimsa_filter']['warnings_count']}, Noise files: {results['ahimsa_filter']['noise_count']}")
        
        if self.deadlines:
            print("\n[3] Deadline Sentinel...")
            sentinel = DeadlineSentinel(self.base_path)
            results['deadline_sentinel'] = sentinel.check()
            print(f"    Expired: {results['deadline_sentinel']['expired_count']}, Upcoming: {results['deadline_sentinel']['upcoming_count']}")
        
        if self.integrity:
            print("\n[4] Integrity Check...")
            integrity = IntegrityCheck(self.base_path)
            results['integrity_check'] = integrity.check()
            print(f"    Errors: {results['integrity_check']['errors_count']}, Broken refs: {results['integrity_check']['broken_count']}, Missing parents: {results['integrity_check']['missing_count']}")

        if self.ahimsa or self.full_check:
            print("\n[5] Seed Count Validator...")
            from .validators import SeedCountValidator
            seeds_health = SeedCountValidator.check()
            results['seed_count_validator'] = seeds_health
            print(f"    Корень: {seeds_health['root_count']}/{seeds_health['root_threshold']} {'✅' if seeds_health['root_status'] == 'ok' else '⚠️'}")
            print(f"    Inbox:  {seeds_health['inbox_count']}/{seeds_health['inbox_threshold']} {'✅' if seeds_health['inbox_status'] == 'ok' else '⚠️'}")
            if seeds_health['warnings']:
                for w in seeds_health['warnings']:
                    print(f"    ⚠️ {w}")

        
        self.guard_results = results
        
        errors = sum(r.get('errors_count', 0) for r in results.values())
        warnings = sum(r.get('warnings_count', 0) for r in results.values())
        status = "critical" if errors > 0 else ("warning" if warnings > 0 else "healthy")
        
        print("\n" + "=" * 60)
        print_colored(f"SYMBIOSIS GUARD STATUS: {status.upper()}", Colors.BOLD)
        print(f"Errors: {errors}, Warnings: {warnings}")
        print("=" * 60)
        
        return results

    def scan_all_honeycombs(self):
        print("=" * 60)
        print_colored("HONEYCOMB SCANNER v2.0 — SYSTEM HEALTH SCAN", Colors.BOLD)
        print("=" * 60)
        print(f"Base path: {self.base_path}")
        print(f"Full check: {self.full_check}")
        print(f"Flags: validate_tasks={self.validate_tasks}, ahimsa={self.ahimsa}, deadlines={self.deadlines}, integrity={self.integrity}")
        print("=" * 60)
        
        self._load_previous_state()
        
        print("\n📂 Scanning honeycombs...")
        honeycombs_path = self.base_path / 'honeycombs'
        if honeycombs_path.exists():
            self._recursive_scan(honeycombs_path)
        else:
            print(f"❌ Honeycombs folder not found: {honeycombs_path}")
            return
        
        guard_results = None
        if self.full_check or self.validate_tasks or self.ahimsa or self.deadlines or self.integrity:
            guard_results = self._run_symbiosis_guard()
        
        save_scan_state(self.base_path, self.honeycombs, self.stats, guard_results,
                       self.validate_tasks, self.ahimsa, self.deadlines, self.integrity)
        save_registry(self.base_path, self.honeycombs, self.stats, guard_results)
        
        print("\n" + "=" * 60)
        print_colored("SCAN COMPLETE", Colors.BOLD)
        print("=" * 60)
        print(f"Found honeycombs: {len(self.honeycombs)}")
        print(f"New: {len(self.new_honeycombs)}")
        print(f"Modified: {len(self.modified_honeycombs)}")
        print(f"Validation errors: {len(self.validation_errors)}")
        print(f"Total errors: {self.stats['errors']}")
        print(f"Total warnings: {self.stats['warnings']}")
        print("=" * 60)
        
        if self.stats["errors"] > 0:
            print_colored("⚠️  Scan completed with ERRORS", Colors.WARNING)
        else:
            print_colored("✅ Scan completed successfully", Colors.OKGREEN)
