#!/usr/bin/env python3
"""
Validation classes for Symbiosis Guard checks.
Full functionality from original honeycomb_scanner.py
"""
import os
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any

class TaskValidator:
    """Validates work files in honeycombs/works/"""
    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.errors = []
        self.warnings = []
        self.expired_tasks = []
        self.upcoming_deadlines = []
        self.valid_statuses = ['todo', 'in_progress', 'planned', 'active', 'done', 'archived', 'paused']
        self.required_fields = ['work_id', 'name', 'status', 'priority', 'horizon']
    
    def validate(self) -> Dict:
        works_path = self.base_path / 'honeycombs' / 'works'
        if not works_path.exists():
            self.warnings.append("Works folder not found")
            return self._report()
        
        work_ids = []
        for work_file in works_path.glob('*.json'):
            if work_file.name == 'index.json':
                continue
            try:
                with open(work_file, 'r', encoding='utf-8') as f:
                    work = json.load(f)
                
                for field in self.required_fields:
                    if field not in work:
                        self.errors.append(f"{work_file.name}: missing required field '{field}'")
                
                work_id = work.get('work_id')
                if work_id:
                    if work_id in work_ids:
                        self.errors.append(f"Duplicate work_id: {work_id} in {work_file.name}")
                    work_ids.append(work_id)
                else:
                    self.errors.append(f"{work_file.name}: missing work_id")
                
                status = work.get('status')
                if status and status not in self.valid_statuses:
                    self.warnings.append(f"{work_file.name}: non-standard status '{status}'")
                
                deadline = work.get('deadline')
                if deadline:
                    try:
                        deadline_date = datetime.strptime(deadline, '%Y-%m-%d')
                        today = datetime.now()
                        if deadline_date < today:
                            self.expired_tasks.append({
                                'work_id': work_id,
                                'name': work.get('name', 'Unknown'),
                                'deadline': deadline,
                                'days_overdue': (today - deadline_date).days
                            })
                        elif (deadline_date - today).days <= 3:
                            self.upcoming_deadlines.append({
                                'work_id': work_id,
                                'name': work.get('name', 'Unknown'),
                                'deadline': deadline,
                                'days_left': (deadline_date - today).days
                            })
                    except ValueError:
                        self.warnings.append(f"{work_file.name}: invalid deadline format (expected YYYY-MM-DD)")
                
            except json.JSONDecodeError:
                self.errors.append(f"{work_file.name}: invalid JSON")
            except Exception as e:
                self.errors.append(f"{work_file.name}: {str(e)}")
        
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
        honeycombs_path = self.base_path / 'honeycombs'
        if not honeycombs_path.exists():
            self.warnings.append("Honeycombs folder not found")
            return self._report()

        for root, dirs, files in os.walk(honeycombs_path):
            if 'registry' in root or '__pycache__' in root or 'backups' in root or 'blocks' in root or 'meta' in root or 'testimonies' in root or 'internal' in root or 'core' in root:
                continue

            root_path = Path(root)
            index_file = root_path / 'index.json'
            if index_file.exists():
                self._validate_index(index_file)
            else:
                json_files = list(root_path.glob('*.json'))
                if json_files and not any(p.name.startswith('__') for p in json_files):
                    self.warnings.append(f"{root_path.name}: missing index.json")

            for file in root_path.glob('*.json'):
                if file.name == 'index.json':
                    continue
                if file.stat().st_size < 100:
                    self.noise_files.append({
                        'path': str(file),
                        'size': file.stat().st_size,
                        'reason': 'empty file (<100 bytes)'
                    })

        return self._report()

    def _validate_index(self, index_file: Path):
        try:
            with open(index_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if 'identity' not in data:
                self.errors.append(f"{index_file.parent.name}/index.json: missing 'identity'")
                return

            identity = data['identity']
            if not isinstance(identity, dict):
                self.errors.append(f"{index_file.parent.name}/index.json: identity is not a dict")
                return

            for field in ['module_id', 'name', 'version', 'layer', 'type']:
                if field not in identity:
                    self.errors.append(f"{index_file.parent.name}: missing identity.{field}")

            layer = identity.get('layer')
            if layer and layer not in self.valid_layers:
                self.warnings.append(f"{index_file.parent.name}: invalid layer {layer}")

            resonance = identity.get('resonance')
            if resonance == "0%" or resonance == "0":
                self.warnings.append(f"{index_file.parent.name}: zero resonance")

            if 'meta' in data:
                meta = data['meta']
                if isinstance(meta, dict) and 'description' not in meta:
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
        works_path = self.base_path / 'honeycombs' / 'works'
        if works_path.exists():
            for work_file in works_path.glob('*.json'):
                try:
                    with open(work_file, 'r', encoding='utf-8') as f:
                        work = json.load(f)
                    self._check_deadline(work, 'works')
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
        deadline = item.get('deadline')
        if not deadline:
            return
        
        try:
            deadline_date = datetime.strptime(deadline, '%Y-%m-%d')
            today = datetime.now()
            
            if deadline_date < today:
                self.expired.append({
                    'id': item.get('work_id') or item.get('roadmap_id'),
                    'name': item.get('name', 'Unknown'),
                    'type': item_type,
                    'deadline': deadline,
                    'days_overdue': (today - deadline_date).days
                })
            elif (deadline_date - today).days <= 3:
                self.upcoming.append({
                    'id': item.get('work_id') or item.get('roadmap_id'),
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
        core_map_path = self.base_path / 'honeycombs' / 'core_map' / 'index.json'
        if not core_map_path.exists():
            self.errors.append("core_map/index.json not found")
            return self._report()
        
        try:
            with open(core_map_path, 'r', encoding='utf-8') as f:
                core_map = json.load(f)
            
            nav = core_map.get('navigation', {})
            parents = nav.get('parent', '')
            if parents:
                parent_path = self.base_path / parents
                if not parent_path.exists():
                    self.missing_parents.append(parents)
            
            references = nav.get('references', [])
            for ref in references:
                ref_path = self.base_path / ref
                if not ref_path.exists():
                    self.broken_refs.append({
                        'type': 'reference',
                        'path': ref
                    })
            
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
