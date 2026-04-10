#!/usr/bin/env python3
"""
Honeycomb Scanner v1.1.0
Module for scanning honeycomb system state for Mandala Symbiosis

Automatically scans honeycombs/ directory and registers all hives in the system.
"""

import os
import json
import sys
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
import hashlib

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('honeycomb_scanner.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class HoneycombScanner:
    """Main class for scanning and registering hives"""
    
    def __init__(self, base_path: str = "honeycombs"):
        """
        Initialize scanner
        
        Args:
            base_path: Base path to honeycombs directory
        """
        self.base_path = Path(base_path)
        self.registry_path = Path("honeycombs/registry/scan_state.json")
        self.scanner_config_path = Path("honeycombs/registry/scanner.json")
        
        # Load scanner configuration
        self.config = self._load_config()
        
        # Scan results
        self.honeycombs: List[Dict[str, Any]] = []
        self.new_honeycombs: List[str] = []
        self.modified_honeycombs: List[str] = []
        self.deleted_honeycombs: List[str] = []
        self.validation_errors: List[Dict[str, Any]] = []
        
        # Statistics
        self.stats = {
            "total_scanned": 0,
            "valid_v2": 0,
            "invalid_v2": 0,
            "errors": 0,
            "warnings": 0,
            "total_files": 0,
            "total_size_kb": 0
        }
        
        # Cache of previous scan
        self.previous_scan_cache: Dict[str, Any] = {}
        
    def _load_config(self) -> Dict[str, Any]:
        """Load scanner configuration"""
        try:
            with open(self.scanner_config_path, 'r', encoding='utf-8-sig') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading scanner config: {e}")
            return {
                "scanning_logic": {
                    "depth": "recursive all levels of nesting",
                    "target_files": ["index.json"],
                    "validation_rules": ["Structure validation v2.0"],
                    "update_triggers": ["New hive detected", "Hive modified"]
                }
            }
    
    def scan_all_honeycombs(self, force_rescan: bool = False) -> Dict[str, Any]:
        """
        Main scanning of all hives
        
        Args:
            force_rescan: Force full rescan
            
        Returns:
            Dictionary with scan results
        """
        logger.info("=" * 60)
        logger.info("STARTING HONEYCOMB SCAN")
        logger.info(f"Base path: {self.base_path}")
        logger.info(f"Scanner config: {self.config.get('identity', {}).get('name', 'Unknown')}")
        logger.info("=" * 60)
        
        # Load previous registry state
        self._load_previous_state()
        
        # Recursive scan
        self._recursive_scan(self.base_path)
        
        # Update registry
        if self.honeycombs:
            registry_updated = self._update_registry()
        else:
            logger.warning("No hives found!")
            registry_updated = False
        
        # Generate report
        report = self._generate_report()
        
        # Save scan state
        self._save_scan_state()
        
        logger.info("=" * 60)
        logger.info("SCAN COMPLETE")
        logger.info(f"Found hives: {len(self.honeycombs)}")
        logger.info(f"New: {len(self.new_honeycombs)}")
        logger.info(f"Modified: {len(self.modified_honeycombs)}")
        logger.info(f"Deleted: {len(self.deleted_honeycombs)}")
        logger.info(f"Validation errors: {len(self.validation_errors)}")
        logger.info("=" * 60)
        
        return report
    
    def _load_previous_state(self):
        """Load previous registry state for comparison"""
        try:
            if self.registry_path.exists():
                with open(self.registry_path, 'r', encoding='utf-8-sig') as f:
                    registry = json.load(f)
                
                # Cache info about previous hives
                if "honeycombs" in registry:
                    for honeycomb in registry["honeycombs"]:
                        honeycomb_id = honeycomb.get("honeycomb_id", "")
                        if honeycomb_id:
                            self.previous_scan_cache[honeycomb_id] = {
                                "hash": honeycomb.get("hash", ""),
                                "last_modified": honeycomb.get("last_modified", 0),
                                "file_count": honeycomb.get("file_count", 0)
                            }
                logger.info(f"Loaded {len(self.previous_scan_cache)} entries from previous registry")
        except Exception as e:
            logger.error(f"Error loading previous state: {e}")
    
    def _recursive_scan(self, directory: Path):
        """
        Recursively scan directory for hives
        
        Args:
            directory: Directory to scan
        """
        try:
            for item in directory.iterdir():
                if item.is_dir():
                    # Skip system directories
                    if item.name.startswith('.') or item.name.startswith('__'):
                        continue
                    
                    # Check for index.json in directory
                    index_file = item / "index.json"
                    if index_file.exists():
                        self._analyze_honeycomb(index_file)
                    
                    # Recursive call for subdirectories
                    self._recursive_scan(item)
        except Exception as e:
            logger.error(f"Error scanning directory {directory}: {e}")
            self.stats["errors"] += 1
    
    def _analyze_honeycomb(self, honeycomb_path: Path):
        """
        Analyze and validate hive
        
        Args:
            honeycomb_path: Path to index.json file
        """
        try:
            # Read file
            with open(honeycomb_path, 'r', encoding='utf-8-sig') as f:
                honeycomb_data = json.load(f)
            
            # Extract identity information
            honeycomb_dir = honeycomb_path.parent
            relative_path = honeycomb_dir.relative_to(self.base_path)
            honeycomb_id = str(relative_path).replace(os.sep, '/')
            
            # Calculate content hash
            content_hash = self._calculate_hash(honeycomb_data)
            
            # Validate v2.0 structure
            is_valid, validation_details = self._validate_v2_structure(honeycomb_data)
            
            # Count files and size
            file_count, total_size_kb = self._count_honeycomb_files(honeycomb_dir)
            
            # Extract identity info
            identity = honeycomb_data.get("identity", {})
            
            # Form hive info
            honeycomb_info = {
                "honeycomb_id": honeycomb_id,
                "path": str(honeycomb_path),
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
                
                # Technical info
                "is_v2_compliant": is_valid,
                "validation_details": validation_details,
                "hash": content_hash,
                "last_modified": os.path.getmtime(honeycomb_path),
                "file_count": file_count,
                "total_size_kb": total_size_kb,
                "scan_timestamp": datetime.now().isoformat()
            }
            
            # Detect changes
            self._detect_changes(honeycomb_id, honeycomb_info)
            
            # Add to list
            self.honeycombs.append(honeycomb_info)
            
            # Update stats
            self.stats["total_scanned"] += 1
            self.stats["total_files"] += file_count
            self.stats["total_size_kb"] += total_size_kb
            
            if is_valid:
                self.stats["valid_v2"] += 1
                logger.info(f"[OK] {honeycomb_id}: {honeycomb_info['name']} v{honeycomb_info['version']}")
            else:
                self.stats["invalid_v2"] += 1
                self.stats["warnings"] += 1
                logger.warning(f" {honeycomb_id}: Not v2.0 compliant")
                self.validation_errors.append({
                    "honeycomb_id": honeycomb_id,
                    "name": honeycomb_info["name"],
                    "errors": validation_details.get("errors", []),
                    "warnings": validation_details.get("warnings", [])
                })
                
        except json.JSONDecodeError as e:
            logger.error(f"{honeycomb_path}: JSON error: {e}")
            self.stats["errors"] += 1
        except Exception as e:
            logger.error(f"{honeycomb_path}: Analysis error: {e}")
            self.stats["errors"] += 1
    
    def _calculate_hash(self, data: Dict[str, Any]) -> str:
        """Calculate MD5 hash of JSON data"""
        try:
            # Sort keys for consistency
            json_str = json.dumps(data, sort_keys=True, ensure_ascii=False)
            return hashlib.md5(json_str.encode('utf-8')).hexdigest()
        except:
            return "error"
    
    def _validate_v2_structure(self, honeycomb_data: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        Validate hive structure against v2.0 standard
        
        Returns:
            Tuple (is_valid, validation_details)
        """
        details = {
            "errors": [],
            "warnings": [],
            "missing_sections": [],
            "missing_fields": []
        }
        
        # Check required sections
        required_sections = ["identity", "meta"]
        for section in required_sections:
            if section not in honeycomb_data:
                details["errors"].append(f"Missing required section: {section}")
                details["missing_sections"].append(section)
        
        # Validate identity section
        if "identity" in honeycomb_data:
            identity = honeycomb_data["identity"]
            required_fields = ["module_id", "name", "version", "layer", "type"]
            
            for field in required_fields:
                if field not in identity:
                    details["errors"].append(f"Missing required field identity.{field}")
                    details["missing_fields"].append(f"identity.{field}")
            
            # Check module_id format
            if "module_id" in identity:
                module_id = identity["module_id"]
                if not isinstance(module_id, str) or len(module_id.strip()) == 0:
                    details["warnings"].append("module_id should be non-empty string")
        
        # Validate meta section
        if "meta" in honeycomb_data:
            meta = honeycomb_data["meta"]
            if "description" not in meta:
                details["warnings"].append("Recommended to add description in meta.description")
        
        # Determine validity
        is_valid = len(details["errors"]) == 0
        
        return is_valid, details
    
    def _count_honeycomb_files(self, honeycomb_dir: Path) -> Tuple[int, float]:
        """Count JSON files in hive"""
        file_count = 0
        total_size_bytes = 0
        
        try:
            for root, dirs, files in os.walk(honeycomb_dir):
                for file in files:
                    if file.endswith('.json'):
                        file_path = Path(root) / file
                        file_count += 1
                        total_size_bytes += os.path.getsize(file_path)
        except Exception as e:
            logger.warning(f"Error counting files in {honeycomb_dir}: {e}")
            self.stats["errors"] += 1
        
        total_size_kb = round(total_size_bytes / 1024, 2)
        return file_count, total_size_kb
    
    def _detect_changes(self, honeycomb_id: str, honeycomb_info: Dict[str, Any]):
        """Detect if hive is new or modified"""
        if honeycomb_id in self.previous_scan_cache:
            previous = self.previous_scan_cache[honeycomb_id]
            
            # Check hash
            if previous.get("hash") != honeycomb_info["hash"]:
                self.modified_honeycombs.append(honeycomb_id)
                logger.info(f"   Modified: {honeycomb_id}")
        else:
            # New hive
            self.new_honeycombs.append(honeycomb_id)
            logger.info(f"  + New: {honeycomb_id}")
    
    def _update_registry(self) -> bool:
        """Update main registry file (registry.json)"""
        try:
            registry_file = Path("honeycombs/registry/registry.json")
            
            if registry_file.exists():
                with open(registry_file, 'r', encoding='utf-8-sig') as f:
                    registry = json.load(f)
            else:
                registry = {}

            # Ensure content.registry structure
            if "content" not in registry:
                registry["content"] = {}
            if "registry" not in registry["content"]:
                registry["content"]["registry"] = {}

            reg = registry["content"]["registry"]

            # Update data
            reg["honeycombs"] = self.honeycombs
            reg["statistics"] = {
                "total_honeycombs": len(self.honeycombs),
                "valid_v2": self.stats.get("valid_v2", 0),
                "invalid_v2": self.stats.get("invalid_v2", 0),
                "total_files": self.stats.get("total_files", 0),
                "total_size_kb": round(self.stats.get("total_size_kb", 0), 2),
                "new_honeycombs": len(self.new_honeycombs),
                "modified_honeycombs": len(self.modified_honeycombs),
                "deleted_honeycombs": len(self.deleted_honeycombs),
                "validation_errors": len(self.validation_errors),
                "scan_errors": self.stats.get("errors", 0),
                "last_scan_timestamp": datetime.now().isoformat()
            }
            reg["health_status"] = {
                "status": "healthy" if self.stats.get("errors", 0) == 0 else "error",
                "validation_errors": self.validation_errors,
                "new_honeycombs": self.new_honeycombs,
                "modified_honeycombs": self.modified_honeycombs,
                "deleted_honeycombs": self.deleted_honeycombs
            }
            reg["last_updated"] = datetime.now().isoformat()
            reg["scanner_version"] = self.config.get("identity", {}).get("version", "v1.1.0")

            # Write registry.json
            with open(registry_file, 'w', encoding='utf-8-sig') as f:
                json.dump(registry, f, indent=2, ensure_ascii=False)

            # Save scan_state.json
            self._save_scan_state()

            logger.info(f" Registry updated: content.registry in {registry_file}")
            return True

        except Exception as e:
            logger.error(f" Error updating registry: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def _generate_report(self) -> Dict[str, Any]:
        """Generate scan report"""
        return {
            "scan_report": {
                "timestamp": datetime.now().isoformat(),
                "scanner_version": self.config.get("identity", {}).get("version", "v1.1.0"),
                "base_path": str(self.base_path),
                "duration_seconds": None,
                "status": "completed"
            },
            "summary": {
                "total_honeycombs_found": len(self.honeycombs),
                "new_honeycombs": self.new_honeycombs,
                "modified_honeycombs": self.modified_honeycombs,
                "deleted_honeycombs": self.deleted_honeycombs,
                "validation_errors_count": len(self.validation_errors)
            },
            "statistics": self.stats,
            "validation_errors": self.validation_errors,
            "honeycombs_by_layer": self._group_by_layer(),
            "honeycombs_by_type": self._group_by_type()
        }
    
    def _group_by_layer(self) -> Dict[int, List[str]]:
        """Group hives by layer"""
        layers = {}
        for honeycomb in self.honeycombs:
            layer = honeycomb.get("layer", 0)
            if layer not in layers:
                layers[layer] = []
            layers[layer].append(honeycomb["honeycomb_id"])
        return layers
    
    def _group_by_type(self) -> Dict[str, List[str]]:
        """Group hives by type"""
        types = {}
        for honeycomb in self.honeycombs:
            honeycomb_type = honeycomb.get("type", "unknown")
            if honeycomb_type not in types:
                types[honeycomb_type] = []
            types[honeycomb_type].append(honeycomb["honeycomb_id"])
        return types
    
    def _save_scan_state(self):
        """Save scan state for future comparison"""
        try:
            state_file = Path("honeycombs/registry/scan_state.json")
            state_data = {
                "last_scan": datetime.now().isoformat(),
                "honeycomb_hashes": {
                    honeycomb["honeycomb_id"]: honeycomb["hash"] 
                    for honeycomb in self.honeycombs
                },
                "statistics": self.stats,
                "scanner_config": self.config.get("identity", {})
            }
            
            with open(state_file, 'w', encoding='utf-8-sig') as f:
                json.dump(state_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Scan state saved: {state_file}")
        except Exception as e:
            logger.error(f"Error saving scan state: {e}")


def main():
    """CLI entry point"""
    if len(sys.argv) < 2:
        print("=" * 60)
        print("HONEYCOMB SCANNER v1.1.0")
        print("Module for scanning Mandala Symbiosis hives")
        print("=" * 60)
        print("\nUsage:")
        print("  python honeycomb_scanner.py scan     # Run scan")
        print("  python honeycomb_scanner.py test     # Test run")
        print("  python honeycomb_scanner.py validate # Validate only")
        print("  python honeycomb_scanner.py report   # Generate report")
        print("\nOptions:")
        print("  --force      # Force full rescan")
        print("  --verbose    # Verbose output")
        print("  --log-file   # Save logs to file")
        return
    
    command = sys.argv[1]
    force_rescan = "--force" in sys.argv
    verbose = "--verbose" in sys.argv
    
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    scanner = HoneycombScanner()
    
    if command == "scan":
        print("Starting hive scan...")
        report = scanner.scan_all_honeycombs(force_rescan)
        
        print("\n" + "=" * 60)
        print("SCAN REPORT")
        print("=" * 60)
        print(f"Total hives: {len(scanner.honeycombs)}")
        print(f"New: {len(scanner.new_honeycombs)}")
        print(f"Modified: {len(scanner.modified_honeycombs)}")
        print(f"Deleted: {len(scanner.deleted_honeycombs)}")
        print(f"Validation errors: {len(scanner.validation_errors)}")
        print(f"Registry updated: {'Yes' if scanner.honeycombs else 'No'}")
        
        if scanner.validation_errors:
            print("\nVALIDATION ERRORS:")
            for error in scanner.validation_errors[:5]:
                print(f"   {error['honeycomb_id']}: {error['name']}")
                for err in error.get('errors', [])[:3]:
                    print(f"    - {err}")
            if len(scanner.validation_errors) > 5:
                print(f"    ... and {len(scanner.validation_errors) - 5} more")
        
        print("\nSCAN COMPLETE")
        
    elif command == "test":
        print("Test scan...")
        scanner.scan_all_honeycombs(force_rescan)
        print(f"Found hives: {len(scanner.honeycombs)}")
        print(f"Valid v2.0: {scanner.stats['valid_v2']}")
        print(f"Invalid v2.0: {scanner.stats['invalid_v2']}")
        
        if scanner.honeycombs:
            print("\nFirst 5 hives:")
            for honeycomb in scanner.honeycombs[:5]:
                print(f"   {honeycomb['honeycomb_id']}: {honeycomb['name']} (v{honeycomb['version']})")
        
    elif command == "validate":
        print("Validation mode...")
        scanner.scan_all_honeycombs(force_rescan)
        
        if scanner.validation_errors:
            print(f"\nFound {len(scanner.validation_errors)} validation errors:")
            for error in scanner.validation_errors:
                print(f"\n{error['honeycomb_id']}: {error['name']}")
                for err in error.get('errors', []):
                    print(f"   {err}")
                for warn in error.get('warnings', []):
                    print(f"  ! {warn}")
        else:
            print("All hives are v2.0 compliant!")
            
    elif command == "report":
        print("Generating report...")
        print("Report functionality in development")
        
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
