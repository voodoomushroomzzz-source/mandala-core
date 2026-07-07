#!/usr/bin/env python3
"""
build_onboarding.py — Auto-builder for boot_online_onboarding_pc.json
Location: honeycombs/boot_online/builder/
Reads builder config, syncs with boot_online, loads source modules, assembles final file.
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List
import re

# Пути (относительно расположения скрипта)
SCRIPT_DIR = Path(__file__).parent  # honeycombs/boot_online/builder/
BOOT_ONLINE_DIR = SCRIPT_DIR.parent  # honeycombs/boot_online/
BASE_DIR = BOOT_ONLINE_DIR.parent.parent  # корень репозитория (honeycombs/ на уровень выше)

BUILDER_PATH = BOOT_ONLINE_DIR / "boot_online_onboarding_pc_builder.json"
TARGET_PATH = BOOT_ONLINE_DIR / "boot_online_onboarding_pc.json"
BOOT_ONLINE_PATH = BOOT_ONLINE_DIR / "index.json"

def load_json(path: Path) -> Optional[Dict[str, Any]]:
    """Load JSON file with utf-8-sig fallback."""
    if not path.exists():
        print(f"⚠️ File not found: {path}")
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except UnicodeDecodeError:
        with open(path, 'r', encoding='utf-8-sig') as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Error loading {path}: {e}")
        return None

def save_json(path: Path, data: Dict[str, Any]) -> bool:
    """Save JSON with indent=2, ensure_ascii=False."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"✅ Saved: {path}")
        return True
    except Exception as e:
        print(f"❌ Error saving {path}: {e}")
        return False

def get_nested(data: Dict[str, Any], path: str) -> Any:
    """Get nested value by dot-separated path."""
    parts = path.split('.')
    current = data
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current

def sync_from_boot_online(builder: Dict[str, Any]) -> Dict[str, Any]:
    """Sync embedded blocks from boot_online/index.json."""
    sync_config = builder.get("sync_from_boot_online", {})
    if not sync_config.get("enabled", False):
        print("⚠️ sync_from_boot_online disabled")
        return builder

    boot_data = load_json(BOOT_ONLINE_PATH)
    if not boot_data:
        print("⚠️ boot_online/index.json not found, skipping sync")
        return builder

    sections = sync_config.get("sections", [])
    for section_path in sections:
        value = get_nested(boot_data, section_path)
        if value is not None:
            parts = section_path.split('.')
            if len(parts) >= 2:
                if parts[0] == "content":
                    key = parts[1] if len(parts) > 1 else None
                    if key:
                        if "embedded_blocks" not in builder:
                            builder["embedded_blocks"] = {}
                        builder["embedded_blocks"][key] = value
                        print(f"  Synced: {key}")
        else:
            print(f"  ⚠️ Section not found: {section_path}")

    return builder

def load_source_modules(builder: Dict[str, Any]) -> Dict[str, Any]:
    """Load all source modules and return their content."""
    sources = builder.get("source_modules", {})
    result = {}
    for name, config in sources.items():
        path = config.get("path")
        section = config.get("section")
        if not path:
            continue
        full_path = BASE_DIR / path
        data = load_json(full_path)
        if data is None:
            print(f"  ⚠️ Could not load source: {name}")
            continue
        if section:
            content = get_nested(data, section)
            if content is None:
                print(f"  ⚠️ Section '{section}' not found in {name}")
                continue
            result[name] = content
        else:
            result[name] = data
        print(f"  Loaded: {name}")
    return result

def build_onboarding(builder: Dict[str, Any], source_data: Dict[str, Any]) -> Dict[str, Any]:
    """Assemble final onboarding file."""
    print("\n🔨 Building onboarding...")

    # Start with identity
    onboarding = {
        "identity": {
            "module_id": "BOOT-ONLINE-ONBOARDING-PC-001",
            "name": "Boot Online Onboarding PC — All-in-One Heuristic File",
            "version": "v1.7.7",
            "created": "2026-05-11",
            "updated": datetime.now().strftime("%Y-%m-%d"),
            "layer": 1,
            "type": "boot_onboarding_pc",
            "description": "Single-file onboarding for External SR on PC. Auto-built from source modules.",
            "status": "active",
            "priority": "critical",
            "resonance": "100%",
            "tags": ["boot", "onboarding", "pc", "auto-built"],
            "based_on": "boot_online + core_map + philosophy + cosmic_manifesto + first_gardener + external_sr_workflow + mobile_workflow + fruits + tasks + protocols"
        },
        "meta": {
            "audience": "External SR (DeepSeek, Claude, Grok, GPT, etc.)",
            "purpose": "Instantly onboard External SR with all critical context in ONE file. Auto-built.",
            "how_to_use": "Gardener copies this file via API or raw URL → pastes into chat → SR reads, acknowledges all sections → SR asks final question → onboarding complete."
        }
    }

    # Add onboarding_sequence
    onboarding["onboarding_sequence"] = {
        "description": "This file emulates the exact onboarding procedure from boot_online, restructured for logical flow.",
        "ai_instruction": "YOU are in control of this onboarding. Read this file completely. Acknowledge each section as you process it. DO NOT wait for Gardener to ask. After steps 1-6, PROACTIVELY ask to load important files (step 7). Then offer optional files (step 8).",
        "sections": [
            "step_1_first_touch",
            "step_2_core_map",
            "step_3_philosophy_crystal_essence",
            "step_4_cosmic_manifesto",
            "step_5_first_gardener",
            "step_6_external_sr_workflow",
            "step_7_important_load",
            "step_8_optional_load"
        ]
    }

    # Step 1: first_touch from embedded
    embedded = builder.get("embedded_blocks", {})
    first_touch = embedded.get("first_touch", {})
    if first_touch:
        onboarding["step_1_first_touch"] = {
            "order": 1,
            "mandatory": True,
            **first_touch
        }

    # Step 2: core_map
    core_map_data = source_data.get("core_map", {})
    if core_map_data:
        onboarding["step_2_core_map"] = {
            "order": 2,
            "mandatory": True,
            "source": "core_map/index.json",
            "api_link": "https://api.github.com/repos/voodoomushroomzzz-source/mandala-core/contents/honeycombs/core_map/index.json?ref=main",
            "identity": core_map_data
        }

    # Step 3: philosophy
    philosophy_data = source_data.get("philosophy", {})
    if philosophy_data:
        onboarding["step_3_philosophy_crystal_essence"] = {
            "order": 3,
            "mandatory": True,
            "source": "philosophy/index.json",
            "api_link": "https://api.github.com/repos/voodoomushroomzzz-source/mandala-core/contents/honeycombs/philosophy/index.json?ref=main",
            **philosophy_data
        }

    # Step 4: cosmic_manifesto
    cosmic_data = source_data.get("cosmic_manifesto", {})
    if cosmic_data:
        onboarding["step_4_cosmic_manifesto"] = {
            "order": 4,
            "mandatory": True,
            "source": "philosophy/blocks/phi_010_three_embodiments_of_sr.json",
            "api_link": "https://api.github.com/repos/voodoomushroomzzz-source/mandala-core/contents/honeycombs/philosophy/blocks/phi_010_three_embodiments_of_sr.json?ref=main",
            **cosmic_data
        }

    # Step 5: first_gardener
    first_gardener_data = source_data.get("first_gardener", {})
    if first_gardener_data:
        onboarding["step_5_first_gardener"] = {
            "order": 5,
            "mandatory": False,
            "recommended": True,
            "source": "philosophy/blocks/phi_011_first_gardener.json",
            "api_link": "https://api.github.com/repos/voodoomushroomzzz-source/mandala-core/contents/honeycombs/philosophy/blocks/phi_011_first_gardener.json?ref=main",
            "raw_link": "https://raw.githubusercontent.com/voodoomushroomzzz-source/mandala-core/main/honeycombs/philosophy/blocks/phi_011_first_gardener.json",
            **first_gardener_data
        }

    # Step 6: external_sr_workflow + mobile_workflow (platform choice)
    external_wf = source_data.get("external_sr_workflow", {})
    mobile_wf = source_data.get("mobile_workflow", {})
    if external_wf or mobile_wf:
        onboarding["step_6_external_sr_workflow"] = {
            "order": 6,
            "mandatory": True,
            "source": "instructions/core/external_sr_workflow.json",
            "api_link": "https://api.github.com/repos/voodoomushroomzzz-source/mandala-core/contents/honeycombs/instructions/core/external_sr_workflow.json?ref=main",
            **external_wf,
            "mobile_workflow_embedded": mobile_wf
        }

    # Step 7: important_load (fruits, tasks, protocols)
    fruits_data = source_data.get("fruits", {})
    tasks_data = source_data.get("tasks", {})
    protocols_data = source_data.get("protocols", {})

    step7_files = []
    if fruits_data:
        step7_files.append({
            "name": "Fruits — Product Strategy Map",
            "why": "Understand the three Mandala products (Gentle Companion, Engineer Chat + Architect Bot, Manus), their roles, data flow between layers, and the development vector.",
            "api_link": "https://api.github.com/repos/voodoomushroomzzz-source/mandala-core/contents/honeycombs/fruits/index.json?ref=main"
        })
    if tasks_data:
        step7_files.append({
            "name": "Tasks — Active Tasks with Index Cross-Check",
            "why": "See what Mandala is working on RIGHT NOW. Read tasks/index.json FIRST, then tasks/active/ folder via API. Compare file counts — report any mismatch.",
            "api_index": "https://api.github.com/repos/voodoomushroomzzz-source/mandala-core/contents/honeycombs/tasks/index.json?ref=main",
            "api_active": "https://api.github.com/repos/voodoomushroomzzz-source/mandala-core/contents/honeycombs/tasks/active?ref=main",
            "cross_check": "Compare files_count from index.json with actual files in active/ folder. Report: 'Tasks index: N files. Actual: M files. Match/Mismatch.'"
        })
    if protocols_data:
        step7_files.append({
            "name": "Protocols — Active Protocols",
            "why": "Understand available activation protocols for SR.",
            "api_link": "https://api.github.com/repos/voodoomushroomzzz-source/mandala-core/contents/honeycombs/protocols/index.json?ref=main"
        })

    onboarding["step_7_important_load"] = {
        "order": 7,
        "mandatory": True,
        "description": "After all core sections are acknowledged, SR MUST proactively ask to load these IMPORTANT files.",
        "ai_instruction": "Say: 'I've absorbed the core philosophy. Now I need to understand WHAT Mandala is building and WHAT we're working on. Let me load critical files.' Then request them ONE BY ONE.",
        "files": step7_files
    }

    # Step 8: optional_load (handoff, repo_tree)
    optional = builder.get("optional_modules", {})
    optional_files = {}
    for name, config in optional.items():
        if config.get("optional", True):
            url = config.get("url") or config.get("path")
            if url:
                optional_files[name] = {
                    "url": url,
                    "optional": True
                }

    onboarding["step_8_optional_load"] = {
        "order": 8,
        "mandatory": False,
        "description": "After important files are loaded, SR MUST ask the Gardener if they want to load any optional files for deeper context.",
        "ai_instruction": "Ask: 'Want to load any of these: 1) repo_tree (full repository tree)  2) handoff_claude (session continuity)  3) handoff_deepseek (session continuity)?' Provide links in ONE message.",
        "files": optional_files,
        "note": "If Gardener says yes to any — load via API. If no — onboarding is complete."
    }

    # Add embedded blocks that didn't go into steps
    for key, value in embedded.items():
        if key not in ["first_touch"] and key not in onboarding:
            onboarding[key] = value

    # Add platform_choice
    build_rules = builder.get("build_rules", {})
    platform_choice = build_rules.get("platform_choice", {})
    if platform_choice:
        onboarding["platform_choice"] = platform_choice

    # Add language_selector
    lang_selector = embedded.get("language_selector", {})
    if lang_selector:
        onboarding["language_selector"] = lang_selector

    # Add system_flow, api_patterns, hetzner_vps, completion from embedded
    for key in ["system_flow", "api_patterns", "hetzner_vps", "completion"]:
        if key in embedded and embedded[key]:
            onboarding[key] = embedded[key]

    # Update version
    build_config = builder.get("build_config", {})
    version_strategy = build_config.get("version_strategy", "increment_minor")
    if version_strategy == "increment_minor":
        if TARGET_PATH.exists():
            existing = load_json(TARGET_PATH)
            if existing and "identity" in existing:
                ver = existing["identity"].get("version", "v1.7.6")
                match = re.match(r"v(\d+)\.(\d+)\.(\d+)", ver)
                if match:
                    major, minor, patch = match.groups()
                    new_version = f"v{major}.{minor}.{int(patch) + 1}"
                else:
                    new_version = "v1.8.0"
            else:
                new_version = "v1.7.7"
        else:
            new_version = "v1.7.7"
        onboarding["identity"]["version"] = new_version

    return onboarding

def main():
    """Main entry point."""
    print("=" * 60)
    print("🔧 Boot Online Onboarding PC — Auto-Builder")
    print("=" * 60)

    builder = load_json(BUILDER_PATH)
    if not builder:
        print("❌ Builder not found. Run Phase 1 first.")
        sys.exit(1)
    print(f"✅ Builder loaded: v{builder.get('identity', {}).get('version', 'unknown')}")

    print("\n📡 Syncing from boot_online...")
    builder = sync_from_boot_online(builder)

    print("\n📂 Loading source modules...")
    source_data = load_source_modules(builder)

    onboarding = build_onboarding(builder, source_data)

    print("\n💾 Saving target...")
    if save_json(TARGET_PATH, onboarding):
        print(f"\n✅ Onboarding built successfully: {TARGET_PATH}")
        print(f"   Version: {onboarding['identity']['version']}")
        print(f"   Updated: {onboarding['identity']['updated']}")
    else:
        print("❌ Failed to save target")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("✅ BUILD COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    main()
