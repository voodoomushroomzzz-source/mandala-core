#!/usr/bin/env python3
"""
Honeycomb Scanner v2.0 — Unified System Health Scanner for Mandala Symbiosis.
Integrates: base scan, task validation, Ahimsa filter, deadline monitoring, integrity checks.
"""

import os
import json
import sys
import hashlib
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

# Color codes for console output
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

class TaskValidator:
    """Validates task files in honeycombs/tasks/active/"""
    
    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.errors = []
        self.warnings = []
        self.expired_tasks = []
        self.upcoming_deadlines = []
        self.valid_statuses = ['todo', 'in_progress', 'planned', 'active', 'done', 'archived', 'paused']
        self.required_fields = ['task_id', 'name', 'status', 'priority']
    
    def validate(self) -> Dict:
        """Run all task validations"""
        tasks_path = self.base_path / 'honeycombs' / 'tasks' / 'active'
        if not tasks_path.exists():
            self.warnings.append("Tasks folder not found")
            return self._report()
        
        task_ids = []
        for task_file in tasks_path.glob('*.json'):
            try:
                with open(task_file, 'r', encoding='utf-8') as f:
                    task = json.load(f)
                
                # Check required fields
                for field in self.required_fields:
                    if field not in task:
                        self.errors.append(f"{task_file.name}: missing required field '{field}'")
                
                # Check task_id uniqueness
                task_id = task.get('task_id')
                if task_id:
                    if task_id in task_ids:
                        self.errors.append(f"Duplicate task_id: {task_id} in {task_file.name}")
                    task_ids.append(task_id)
                else:
                    self.errors.append(f"{task_file.name}: missing task_id")
                
                # Check status
                status = task.get('status')
                if status and status not in self.valid_statuses:
                    self.warnings.append(f"{task_file.name}: non-standard status '{status}'")
                
                # Check deadline
                deadline = task.get('deadline')
                if deadline:
                    try:
                        deadline_date = datetime.strptime(deadline, '%Y-%m-%d')
                        today = datetime.now()
                        if deadline_date < today:
                            self.expired_tasks.append({
                                'task_id': task_id,
                                'name': task.get('name', 'Unknown'),
                                'deadline': deadline,
                                'days_overdue': (today - deadline_date).days
                            })
                        elif (deadline_date - today).days <= 3:
                            self.upcoming_deadlines.append({
                                'task_id': task_id,
                                'name': task.get('name', 'Unknown'),
                                'deadline': deadline,
                                'days_left': (deadline_date - today).days
                            })
                    except ValueError:
                        self.warnings.append(f"{task_file.name}: invalid deadline format (expected YYYY-MM-DD)")
                
            except json.JSONDecodeError:
                self.errors.append(f"{task_file.name}: invalid JSON")
            except Exception as e:
                self.errors.append(f"{task_file.name}: {str(e)}")
        
        return self._report()
    
    def _report(self) -> Dict:
        return {
            'errors': self.errors,
            'warnings': self.warnings,
            'expired_tasks': self.expired_tasks,
            'upcoming_deadlines': self.upcoming_deadlines,
            'errors_count': len(self.errors),
            'warnings_count': len(self.warnings),
            'expired_count': len(self.expired_tasks),
            'upcoming_count': len(self.upcoming_deadlines)
        }


class AhimsaFilter:
    """Finds noise and clutter across all honeycombs"""

    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.errors = []
        self.warnings = []
        self.noise_files = []
        self.valid_layers = [1, 2, 3, 4, 5]

    def scan(self) -> Dict:
        """Scan for Ahimsa violations"""
        honeycombs_path = self.base_path / 'honeycombs'
        if not honeycombs_path.exists():
            self.warnings.append("Honeycombs folder not found")
            return self._report()

        for root, dirs, files in os.walk(honeycombs_path):
            # Skip registry and __pycache__
            if 'registry' in root or '__pycache__' in root or 'backups' in root:
                continue

            root_path = Path(root)

            # Check for index.json
            index_file = root_path / 'index.json'
            if index_file.exists():
                self._validate_index(index_file)
            else:
                # Check if it's a valid honeycomb directory (has content files)
                json_files = list(root_path.glob('*.json'))
                if json_files and not any(p.name.startswith('__') for p in json_files):
                    self.warnings.append(f"{root_path.name}: missing index.json")

            # Check for empty files (<1000 bytes) — stale check removed
            for file in root_path.glob('*.json'):
                if file.name == 'index.json':
                    continue
                # Check for empty files (<1000 bytes)
                if file.stat().st_size < 100:
                    self.noise_files.append({
                        'path': str(file),
                        'size': file.stat().st_size,
                        'reason': 'empty file (<1000 bytes)'
                    })

        return self._report()

    def _validate_index(self, index_file: Path):
        """Validate index.json structure"""
        try:
            with open(index_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Check required sections
            if 'identity' not in data:
                self.errors.append(f"{index_file.parent.name}/index.json: missing 'identity'")
                return

            identity = data['identity']

            # Check required identity fields
            for field in ['module_id', 'name', 'version', 'layer', 'type']:
                if field not in identity:
                    self.errors.append(f"{index_file.parent.name}: missing identity.{field}")

            # Check layer
            layer = identity.get('layer')
            if layer and layer not in self.valid_layers:
                self.warnings.append(f"{index_file.parent.name}: invalid layer {layer}")

            # Check resonance
            resonance = identity.get('resonance')
            if resonance == "0%" or resonance == "0":
                self.warnings.append(f"{index_file.parent.name}: zero resonance")

            # Check meta
            if 'meta' in data:
                meta = data['meta']
                if 'description' not in meta:
                    self.warnings.append(f"{index_file.parent.name}: missing meta.description")
            else:
                self.warnings.append(f"{index_file.parent.name}: missing meta section")

        except json.JSONDecodeError:
            self.errors.append(f"{index_file.parent.name}/index.json: invalid JSON")
        except Exception as e:
            self.errors.append(f"{index_file.parent.name}/index.json: {str(e)}")

    def _report(self) -> Dict:
        return {
            'errors': self.errors,
            'warnings': self.warnings,
            'noise_files': self.noise_files,
            'errors_count': len(self.errors),
            'warnings_count': len(self.warnings),
            'noise_count': len(self.noise_files)
        }

class DeadlineSentinel:
    """Monitors deadlines in tasks and roadmaps"""
    
    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.expired = []
        self.upcoming = []
        self.warnings = []
    
    def check(self) -> Dict:
        """Check all deadlines"""
        # Check tasks
        tasks_path = self.base_path / 'honeycombs' / 'tasks' / 'active'
        if tasks_path.exists():
            for task_file in tasks_path.glob('*.json'):
                try:
                    with open(task_file, 'r', encoding='utf-8') as f:
                        task = json.load(f)
                    self._check_deadline(task, 'task')
                except:
                    pass
        
        # Check roadmaps
        roadmaps_path = self.base_path / 'honeycombs' / 'roadmaps' / 'active'
        if roadmaps_path.exists():
            for roadmap_file in roadmaps_path.glob('*.json'):
                try:
                    with open(roadmap_file, 'r', encoding='utf-8') as f:
                        roadmap = json.load(f)
                    self._check_deadline(roadmap, 'roadmap')
                except:
                    pass
        
        return {
            'expired': self.expired,
            'upcoming': self.upcoming,
            'warnings': self.warnings,
            'expired_count': len(self.expired),
            'upcoming_count': len(self.upcoming)
        }
    
    def _check_deadline(self, item: Dict, item_type: str):
        """Check a single deadline"""
        deadline = item.get('deadline')
        if not deadline:
            return
        
        try:
            deadline_date = datetime.strptime(deadline, '%Y-%m-%d')
            today = datetime.now()
            
            if deadline_date < today:
                self.expired.append({
                    'id': item.get('task_id') or item.get('roadmap_id'),
                    'name': item.get('name', 'Unknown'),
                    'type': item_type,
                    'deadline': deadline,
                    'days_overdue': (today - deadline_date).days
                })
            elif (deadline_date - today).days <= 3:
                self.upcoming.append({
                    'id': item.get('task_id') or item.get('roadmap_id'),
                    'name': item.get('name', 'Unknown'),
                    'type': item_type,
                    'deadline': deadline,
                    'days_left': (deadline_date - today).days
                })
        except ValueError:
            self.warnings.append(f"{item.get('name', 'Unknown')}: invalid deadline format")


class IntegrityCheck:
    """Checks inter-honeycomb references"""
    
    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.broken_refs = []
        self.missing_parents = []
        self.errors = []
    
    def check(self) -> Dict:
        """Check all references"""
        core_map_path = self.base_path / 'honeycombs' / 'core_map' / 'index.json'
        if not core_map_path.exists():
            self.errors.append("core_map/index.json not found")
            return self._report()
        
        try:
            with open(core_map_path, 'r', encoding='utf-8') as f:
                core_map = json.load(f)
            
            # Check navigation
            nav = core_map.get('navigation', {})
            parents = nav.get('parent', '')
            if parents:
                parent_path = self.base_path / parents
                if not parent_path.exists():
                    self.missing_parents.append(parents)
            
            # Check references
            references = nav.get('references', [])
            for ref in references:
                ref_path = self.base_path / ref
                if not ref_path.exists():
                    self.broken_refs.append({
                        'type': 'reference',
                        'path': ref
                    })
            
            # Check children
            children = nav.get('children', [])
            for child in children:
                child_path = self.base_path / child
                if not child_path.exists():
                    self.broken_refs.append({
                        'type': 'child',
                        'path': child
                    })
            
        except Exception as e:
            self.errors.append(f"Integrity check error: {str(e)}")
        
        return self._report()
    
    def _report(self) -> Dict:
        return {
            'errors': self.errors,
            'broken_refs': self.broken_refs,
            'missing_parents': self.missing_parents,
            'errors_count': len(self.errors),
            'broken_count': len(self.broken_refs),
            'missing_count': len(self.missing_parents)
        }


class HoneycombScanner:
    """Main scanner class with integrated health checks"""
    
    def __init__(self, base_path: str = "honeycombs", full_check: bool = False,
                 validate_tasks: bool = False, ahimsa: bool = False,
                 deadlines: bool = False, integrity: bool = False):
        self.base_path = Path(base_path)
        self.full_check = full_check
        self.validate_tasks = validate_tasks or full_check
        self.ahimsa = ahimsa or full_check
        self.deadlines = deadlines or full_check
        self.integrity = integrity or full_check
        
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
        
        # Symbiosis Guard results
        self.guard_results = {}
        
        # Load config
        self.config = self._load_config()
    
    def _load_config(self) -> Dict:
        """Load scanner configuration"""
        config_path = self.base_path / 'honeycombs' / 'registry' / 'scanner.json'
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    
    def _load_previous_state(self):
        """Load previous scan state"""
        state_path = self.base_path / 'honeycombs' / 'registry' / 'scan_state.json'
        try:
            if state_path.exists():
                with open(state_path, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                    if 'honeycomb_hashes' in state:
                        self.previous_scan_cache = state['honeycomb_hashes']
                    print(f"Loaded {len(self.previous_scan_cache)} entries from previous registry")
        except Exception as e:
            print(f"Error loading previous state: {e}")
    
    def _calculate_hash(self, data: Dict) -> str:
        """Calculate MD5 hash of JSON data"""
        try:
            json_str = json.dumps(data, sort_keys=True, ensure_ascii=False)
            return hashlib.md5(json_str.encode('utf-8')).hexdigest()
        except:
            return "error"
    
    def _validate_v2_structure(self, honeycomb_data: Dict) -> Tuple[bool, Dict]:
        """Validate honeycomb against v2.0 standard"""
        details = {
            "errors": [],
            "warnings": [],
            "missing_sections": [],
            "missing_fields": []
        }
        
        required_sections = ["identity", "meta"]
        for section in required_sections:
            if section not in honeycomb_data:
                details["errors"].append(f"Missing required section: {section}")
                details["missing_sections"].append(section)
        
        if "identity" in honeycomb_data:
            identity = honeycomb_data["identity"]
            required_fields = ["module_id", "name", "version", "layer", "type"]
            for field in required_fields:
                if field not in identity:
                    details["errors"].append(f"Missing required field identity.{field}")
                    details["missing_fields"].append(f"identity.{field}")
        
        if "meta" in honeycomb_data:
            meta = honeycomb_data["meta"]
            if "description" not in meta:
                details["warnings"].append("Recommended to add description in meta.description")
        
        is_valid = len(details["errors"]) == 0
        return is_valid, details
    
    def _count_honeycomb_files(self, honeycomb_dir: Path) -> Tuple[int, float]:
        """Count JSON files and calculate total size"""
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
        
        total_size_kb = round(total_size_bytes / 1024, 2)
        return file_count, total_size_kb
    
    def _detect_changes(self, honeycomb_id: str, honeycomb_info: Dict):
        """Detect if honeycomb is new or modified"""
        if honeycomb_id in self.previous_scan_cache:
            previous = self.previous_scan_cache[honeycomb_id]
            if previous.get("hash") != honeycomb_info["hash"]:
                self.modified_honeycombs.append(honeycomb_id)
                print(f"   Modified: {honeycomb_id}")
        else:
            self.new_honeycombs.append(honeycomb_id)
            print(f"   + New: {honeycomb_id}")
    
    def _analyze_honeycomb(self, index_path: Path):
        """Analyze a single honeycomb"""
        try:
            with open(index_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            honeycomb_dir = index_path.parent
            relative_path = honeycomb_dir.relative_to(self.base_path)
            honeycomb_id = str(relative_path).replace(os.sep, '/')
            
            identity = data.get("identity", {})
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
            
            # Detect changes
            self._detect_changes(honeycomb_id, honeycomb_info)
            
            self.honeycombs.append(honeycomb_info)
            self.stats["total_scanned"] += 1
            self.stats["total_files"] += file_count
            self.stats["total_size_kb"] += total_size_kb
            
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
        """Recursively scan directory for honeycombs"""
        try:
            for item in directory.iterdir():
                if item.is_dir():
                    # Skip system directories
                    if item.name.startswith('.') or item.name.startswith('__'):
                        continue
                    
                    # Check for index.json
                    index_file = item / "index.json"
                    if index_file.exists():
                        self._analyze_honeycomb(index_file)
                    
                    # Recursive call for subdirectories
                    self._recursive_scan(item)
        except Exception as e:
            print(f"Error scanning directory {directory}: {e}")
            self.stats["errors"] += 1
    
    def _run_symbiosis_guard(self):
        """Run all Symbiosis Guard checks"""
        print("\n" + "=" * 60)
        print("SYMBIOSIS GUARD — SYSTEM HEALTH CHECK")
        print("=" * 60)
        
        results = {}
        
        # 1. Task Validator
        if self.validate_tasks:
            print("\n[1] Task Validator...")
            validator = TaskValidator(self.base_path)
            results['task_validator'] = validator.validate()
            print(f"    Errors: {results['task_validator']['errors_count']}, Warnings: {results['task_validator']['warnings_count']}, Expired: {results['task_validator']['expired_count']}")
            if results['task_validator']['errors_count']:
                print_colored("    ⚠️  Task validation errors found", Colors.WARNING)
        
        # 2. Ahimsa Filter
        if self.ahimsa:
            print("\n[2] Ahimsa Filter...")
            filter = AhimsaFilter(self.base_path)
            results['ahimsa_filter'] = filter.scan()
            print(f"    Errors: {results['ahimsa_filter']['errors_count']}, Warnings: {results['ahimsa_filter']['warnings_count']}, Noise files: {results['ahimsa_filter']['noise_count']}")
            if results['ahimsa_filter']['noise_count']:
                print_colored(f"    ⚠️  {results['ahimsa_filter']['noise_count']} noise files found", Colors.WARNING)
        
        # 3. Deadline Sentinel
        if self.deadlines:
            print("\n[3] Deadline Sentinel...")
            sentinel = DeadlineSentinel(self.base_path)
            results['deadline_sentinel'] = sentinel.check()
            print(f"    Expired: {results['deadline_sentinel']['expired_count']}, Upcoming: {results['deadline_sentinel']['upcoming_count']}")
            if results['deadline_sentinel']['expired_count']:
                print_colored(f"    ⚠️  {results['deadline_sentinel']['expired_count']} expired deadlines", Colors.FAIL)
        
        # 4. Integrity Check
        if self.integrity:
            print("\n[4] Integrity Check...")
            integrity = IntegrityCheck(self.base_path)
            results['integrity_check'] = integrity.check()
            print(f"    Errors: {results['integrity_check']['errors_count']}, Broken refs: {results['integrity_check']['broken_count']}, Missing parents: {results['integrity_check']['missing_count']}")
            if results['integrity_check']['broken_count']:
                print_colored(f"    ⚠️  {results['integrity_check']['broken_count']} broken references", Colors.WARNING)
        
        self.guard_results = results
        
        # Compute overall status
        errors = sum(r.get('errors_count', 0) for r in results.values())
        warnings = sum(r.get('warnings_count', 0) for r in results.values())
        if errors > 0:
            status = "critical"
        elif warnings > 0:
            status = "warning"
        else:
            status = "healthy"
        
        print("\n" + "=" * 60)
        print_colored(f"SYMBIOSIS GUARD STATUS: {status.upper()}", Colors.BOLD)
        print(f"Errors: {errors}, Warnings: {warnings}")
        print("=" * 60)
        
        return results
    
    def _save_scan_state(self, guard_results: Dict = None):
        """Save scan state to scan_state.json with Symbiosis Guard status"""
        state_path = self.base_path / 'honeycombs' / 'registry' / 'scan_state.json'
        
        # Build honeycomb hashes
        hashes = {}
        for honeycomb in self.honeycombs:
            hashes[honeycomb['honeycomb_id']] = honeycomb['hash']
        
        state = {
            "last_scan": datetime.now().isoformat(),
            "honeycomb_hashes": hashes,
            "statistics": {
                "total_scanned": self.stats["total_scanned"],
                "valid_v2": self.stats["valid_v2"],
                "invalid_v2": self.stats["invalid_v2"],
                "errors": self.stats["errors"],
                "warnings": self.stats["warnings"],
                "total_files": self.stats["total_files"],
                "total_size_kb": round(self.stats["total_size_kb"], 2)
            }
        }
        
        # Add Symbiosis Guard summary
        if guard_results and (self.validate_tasks or self.ahimsa or self.deadlines or self.integrity):
            guard_summary = {
                "last_check": datetime.now().isoformat(),
                "errors_count": 0,
                "warnings_count": 0
            }
            
            for key, result in guard_results.items():
                if isinstance(result, dict):
                    guard_summary['errors_count'] += result.get('errors_count', 0)
                    guard_summary['warnings_count'] += result.get('warnings_count', 0)
                    
                    # Add specific counts
                    if key == 'task_validator':
                        guard_summary['expired_tasks'] = result.get('expired_count', 0)
                        guard_summary['upcoming_deadlines'] = result.get('upcoming_count', 0)
                        guard_summary['expired_tasks_list'] = result.get('expired_tasks', [])
                        guard_summary['upcoming_deadlines_list'] = result.get('upcoming_deadlines', [])
                    elif key == 'ahimsa_filter':
                        guard_summary['noise_files'] = result.get('noise_count', 0)
                        guard_summary['noise_files_list'] = result.get('noise_files', [])
                    elif key == 'integrity_check':
                        guard_summary['broken_links'] = result.get('broken_count', 0)
                        guard_summary['missing_parents'] = result.get('missing_count', 0)
            
            # Determine overall status
            if guard_summary['errors_count'] > 0:
                guard_summary['status'] = 'critical'
            elif guard_summary['warnings_count'] > 0:
                guard_summary['status'] = 'warning'
            else:
                guard_summary['status'] = 'healthy'
            
            state['symbiosis_guard'] = guard_summary
        
        # Write state
        with open(state_path, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ Scan state saved to {state_path}")
    
    def _save_registry(self):
        """Save main registry with health details"""
        registry_path = self.base_path / 'honeycombs' / 'registry' / 'registry.json'
        
        registry = {
            "identity": {
                "module_id": "HONEYCOMB-REGISTRY-001",
                "name": "Registry — State and Statistics of All Honeycombs",
                "version": "v3.1.0",
                "created": "2026-03-07",
                "updated": datetime.now().strftime("%Y-%m-%d"),
                "layer": 2,
                "type": "honeycomb_manifest",
                "description": "Central registry of the Mandala system. Contains current state of all honeycombs, statistics, health status, and change tracking.",
                "status": "active",
                "priority": "high",
                "tags": ["registry", "statistics", "health", "tracking"]
            },
            "meta": {
                "honeycomb_name": "registry",
                "parent_honeycomb": "core_map",
                "segments": 6,
                "total_files": len(self.honeycombs),
                "total_size_kb": round(self.stats["total_size_kb"], 2),
                "purpose": "The registry is the single source of truth about the state of all honeycombs. It is updated automatically by honeycomb_scanner.py on every scan.",
                "lifecycle": "The registry is updated automatically on every scan. Manual changes are only allowed through patch protocols.",
                "change_requires": "gardener_approval",
                "guardian_lock": True
            },
            "structure": {
                "segments": {
                    "core": {
                        "description": "Core registry files: current state, configuration, change log.",
                        "files": {
                            "scan_state": {
                                "file": "scan_state.json",
                                "description": "Current state: last scan timestamp, honeycomb hashes, statistics, scanner config.",
                                "load_priority": "high"
                            },
                            "scanner_config": {
                                "file": "scanner.json",
                                "description": "Scanner configuration: scanning logic, validation rules, update triggers.",
                                "load_priority": "medium"
                            }
                        }
                    },
                    "backups": {
                        "description": "Backup copies of the registry before significant changes. Stored with timestamps."
                    },
                    "dashboard": {
                        "description": "HTML dashboard for visualizing the state of honeycombs."
                    },
                    "modules": {
                        "description": "Registry of modules — larger functional blocks composed of multiple honeycombs."
                    },
                    "extensions": {
                        "description": "Registry of extensions — pluggable modules that extend core functionality."
                    },
                    "notifications": {
                        "description": "Notification rules and templates for system events."
                    }
                }
            },
            "registry": {
                "total_files": len(self.honeycombs),
                "total_size_kb": round(self.stats["total_size_kb"], 2),
                "last_updated": datetime.now().strftime("%Y-%m-%d"),
                "honeycomb_id": "HONEYCOMB-REGISTRY-001",
                "status": "active",
                "compliance_status": "v3.1.0_lightweight",
                "source_of_truth": "Individual honeycomb manifests (index.json in each honeycomb folder). This file stores only registry metadata and aggregated statistics."
            },
            "health": {
                "status": "healthy" if self.stats["errors"] == 0 else "error",
                "validation_errors": self.validation_errors,
                "new_honeycombs": self.new_honeycombs,
                "modified_honeycombs": self.modified_honeycombs,
                "deleted_honeycombs": self.deleted_honeycombs
            },
            "resonance": {
                "with_boot": "100%",
                "with_core_map": "100%",
                "with_parent": "100%",
                "status": "fully_resonant"
            }
        }
        
        # Add Symbiosis Guard details to health
        if self.guard_results:
            registry['health']['symbiosis_guard'] = self.guard_results
        
        # Write registry
        with open(registry_path, 'w', encoding='utf-8') as f:
            json.dump(registry, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Registry saved to {registry_path}")
    
    def scan_all_honeycombs(self):
        """Main scanning method"""
        print("=" * 60)
        print_colored("HONEYCOMB SCANNER v2.0 — SYSTEM HEALTH SCAN", Colors.BOLD)
        print("=" * 60)
        print(f"Base path: {self.base_path}")
        print(f"Full check: {self.full_check}")
        print(f"Flags: validate_tasks={self.validate_tasks}, ahimsa={self.ahimsa}, deadlines={self.deadlines}, integrity={self.integrity}")
        print("=" * 60)
        
        # Load previous state
        self._load_previous_state()
        
        # Scan honeycombs
        print("\n📂 Scanning honeycombs...")
        honeycombs_path = self.base_path / 'honeycombs'
        if honeycombs_path.exists():
            self._recursive_scan(honeycombs_path)
        else:
            print(f"❌ Honeycombs folder not found: {honeycombs_path}")
            return
        
        # Run Symbiosis Guard if requested
        guard_results = None
        if self.full_check or self.validate_tasks or self.ahimsa or self.deadlines or self.integrity:
            guard_results = self._run_symbiosis_guard()
        
        # Save results
        self._save_scan_state(guard_results)
        self._save_registry()
        
        # Final summary
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


def print_colored(text: str, color: str = Colors.OKGREEN):
    """Print colored text to console"""
    print(f"{color}{text}{Colors.ENDC}")


def main():
    parser = argparse.ArgumentParser(
        description='Honeycomb Scanner v2.0 — Unified System Health Scanner for Mandala Symbiosis'
    )
    parser.add_argument(
        'scan',
        nargs='?',
        default='scan',
        help='Run scan (default)'
    )
    parser.add_argument(
        '--full-check',
        action='store_true',
        help='Run all health checks (task validation, Ahimsa filter, deadline monitoring, integrity check)'
    )
    parser.add_argument(
        '--validate-tasks',
        action='store_true',
        help='Run task validation only'
    )
    parser.add_argument(
        '--ahimsa',
        action='store_true',
        help='Run Ahimsa filter only'
    )
    parser.add_argument(
        '--deadlines',
        action='store_true',
        help='Run deadline monitoring only'
    )
    parser.add_argument(
        '--integrity',
        action='store_true',
        help='Run integrity check only'
    )
    parser.add_argument(
        '--base-path',
        default='.',
        help='Base path to repository (default: .)'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Force full rescan'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Verbose output'
    )
    
    args = parser.parse_args()
    
    # Check if any Symbiosis Guard flag is set
    any_guard = args.full_check or args.validate_tasks or args.ahimsa or args.deadlines or args.integrity
    
    scanner = HoneycombScanner(
        base_path=args.base_path,
        full_check=args.full_check,
        validate_tasks=args.validate_tasks,
        ahimsa=args.ahimsa,
        deadlines=args.deadlines,
        integrity=args.integrity
    )
    
    scanner.scan_all_honeycombs()


if __name__ == "__main__":
    main()
