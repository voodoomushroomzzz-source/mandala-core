#!/usr/bin/env python3
"""
Reporters for saving scan results.
Full functionality from original honeycomb_scanner.py
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

def save_scan_state(base_path: Path, honeycombs: List, stats: Dict, guard_results: Optional[Dict] = None,
                   validate_tasks: bool = False, ahimsa: bool = False, deadlines: bool = False, integrity: bool = False):
    """Save scan state to scan_state.json with Symbiosis Guard status"""
    state_path = base_path / 'honeycombs' / 'registry' / 'scan_state.json'
    
    hashes = {}
    for honeycomb in honeycombs:
        hashes[honeycomb['honeycomb_id']] = honeycomb['hash']
    
    state = {
        "last_scan": datetime.now().isoformat(),
        "honeycomb_hashes": hashes,
        "statistics": {
            "total_scanned": stats["total_scanned"],
            "valid_v2": stats["valid_v2"],
            "invalid_v2": stats["invalid_v2"],
            "errors": stats["errors"],
            "warnings": stats["warnings"],
            "total_files": stats["total_files"],
            "total_size_kb": round(stats["total_size_kb"], 2)
        }
    }
    
    if guard_results and (validate_tasks or ahimsa or deadlines or integrity or 'seed_count_validator' in guard_results):

        # Добавляем seeds_health
        if guard_results and 'seed_count_validator' in guard_results:
            state['seeds_health'] = guard_results['seed_count_validator']

        guard_summary = {
            "last_check": datetime.now().isoformat(),
            "errors_count": 0,
            "warnings_count": 0
        }
        
        for key, result in guard_results.items():
            if isinstance(result, dict):
                guard_summary['errors_count'] += result.get('errors_count', 0)
                guard_summary['warnings_count'] += result.get('warnings_count', 0)
                
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
        
        if guard_summary['errors_count'] > 0:
            guard_summary['status'] = 'critical'
        elif guard_summary['warnings_count'] > 0:
            guard_summary['status'] = 'warning'
        else:
            guard_summary['status'] = 'healthy'
        
        state['symbiosis_guard'] = guard_summary
    
    with open(state_path, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Scan state saved to {state_path}")

def save_registry(base_path: Path, honeycombs: List, stats: Dict, guard_results: Optional[Dict] = None):
    """Save main registry with health details"""
    registry_path = base_path / 'honeycombs' / 'registry' / 'registry.json'
    
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
            "total_files": len(honeycombs),
            "total_size_kb": round(stats["total_size_kb"], 2),
            "purpose": "The registry is the single source of truth about the state of all honeycombs.",
            "lifecycle": "The registry is updated automatically on every scan.",
            "change_requires": "gardener_approval",
            "guardian_lock": True
        },
        "structure": {
            "segments": {
                "core": {
                    "description": "Core registry files.",
                    "files": {
                        "scan_state": {
                            "file": "scan_state.json",
                            "description": "Current state: last scan timestamp, honeycomb hashes, statistics.",
                            "load_priority": "high"
                        }
                    }
                }
            }
        },
        "registry": {
            "total_files": len(honeycombs),
            "total_size_kb": round(stats["total_size_kb"], 2),
            "last_updated": datetime.now().strftime("%Y-%m-%d"),
            "status": "active",
            "compliance_status": "v3.1.0_lightweight"
        },
        "health": {
            "status": "healthy" if stats["errors"] == 0 else "error",
            "validation_errors": [],
            "new_honeycombs": [],
            "modified_honeycombs": [],
            "deleted_honeycombs": []
        },
        "resonance": {
            "with_boot": "100%",
            "with_core_map": "100%",
            "status": "fully_resonant"
        }
    }
    
    if guard_results:
        registry['health']['symbiosis_guard'] = guard_results

    if guard_results and 'seed_count_validator' in guard_results:
        registry['health']['seeds_health'] = guard_results['seed_count_validator']

    
    with open(registry_path, 'w', encoding='utf-8') as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Registry saved to {registry_path}")
