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


def build_personal_step(source_data: Dict[str, Any]) -> Dict[str, Any]:
    """Build step_7_personal — Personal Hub + Deep Profile."""
    personal_data = source_data.get("personal", {})
    profile_deep_data = source_data.get("profile_deep", {})
    
    if not personal_data and not profile_deep_data:
        return {}
    
    return {
        "order": 7,
        "mandatory": True,
        "name": "Personal Hub — Личные векторы + Deep Profile",
        "description": "Личная сота Gardener: карьера, обучение, YouTube, e-commerce, франшиза + глубокий профиль личности.",
        "ai_instruction": "Прочитай вшитые personal_index и profile_deep. Подтверди понимание.",
        "personal_index": personal_data,
        "profile_deep": profile_deep_data
    }


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
            "based_on": "boot_online + core_map + philosophy + cosmic_manifesto + first_gardener + external_sr_workflow + mobile_workflow + fruits + works + protocols"
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
            "step_7_personal",
            "step_8_fruits",
            "step_9_works",
            "step_10_knowledge",
            "step_11_protocols",
            "step_12_handoff",
            "step_13_optional"
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


    # Step 7: personal (Personal Hub + Deep Profile)
    personal_step = build_personal_step(source_data)
    if personal_step:
        onboarding["step_7_personal"] = personal_step

    # Step 8: fruits
    fruits_data = source_data.get("fruits", {})
    if fruits_data:
        onboarding["step_8_fruits"] = {
            "order": 8,
            "mandatory": True,
            "name": "Fruits — Product Registry",
            "description": "Продукты Mandala: Gentle Companion, Engineer Chat, Architect Bot, Manus",
            "ai_instruction": "Прочитай вшитый fruits_index. Сверь с API при необходимости. Подтверди список продуктов, их статус и версии.",
            "embedded_ref": "fruits_index",
            "data": fruits_data
        }

    # Step 9: works
    works_data = source_data.get("works", {})
    if works_data:
        onboarding["step_9_works"] = {
            "order": 9,
            "mandatory": True,
            "name": "Works — Unified Work Items",
            "description": "Все активные и архивные работы (заменяет tasks/ и roadmaps/)",
            "ai_instruction": "Прочитай вшитый works_index. Сверь с API. Подтверди общее количество, активные, стратегические/тактические.",
            "embedded_ref": "works_index",
            "data": works_data
        }

    # Step 10: knowledge
    knowledge_data = source_data.get("knowledge", {})
    if knowledge_data:
        onboarding["step_10_knowledge"] = {
            "order": 10,
            "mandatory": False,
            "recommended": True,
            "name": "Knowledge Base — Curated Resources",
            "description": "База знаний Mandala: инструменты, гайды, фреймворки",
            "ai_instruction": "Прочитай вшитый knowledge_index. Подтверди список ресурсов и их статус.",
            "embedded_ref": "knowledge_index",
            "data": knowledge_data
        }

    # Step 11: protocols
    protocols_data = source_data.get("protocols", {})
    if protocols_data:
        onboarding["step_11_protocols"] = {
            "order": 11,
            "mandatory": True,
            "name": "Protocols — Activation Protocols Hub",
            "description": "Протоколы активации: Onboarding, Internal-Onboarding, Ideas-Roadmaps, Scan-and-Push",
            "ai_instruction": "Прочитай вшитый protocols_index. Подтверди список активных протоколов и их статус.",
            "embedded_ref": "protocols_index",
            "data": protocols_data
        }

    # Step 12: handoff (optional, but recommended)
    onboarding["step_12_handoff"] = {
        "order": 12,
        "mandatory": False,
        "recommended": True,
        "description": "Загрузить handoff-файлы для непрерывности сессии",
        "ai_instruction": "Спроси у Садовника: 'Загрузить handoff_claude.json и/или handoff_deepseek.json для продолжения сессии?'",
        "files": {
            "handoff_claude": {
                "url": "honeycombs/sessions/handoff_claude.json",
                "optional": True
            },
            "handoff_deepseek": {
                "url": "honeycombs/sessions/handoff_deepseek.json",
                "optional": True
            }
        }
    }

    # Step 13: optional_load (repo_tree, etc.)
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

    onboarding["step_13_optional"] = {
        "order": 13,
        "mandatory": False,
        "description": "Загрузить опциональные файлы для углублённого контекста",
        "ai_instruction": "Спроси: 'Загрузить repo_tree (полное дерево репозитория)?' Предоставь ссылку.",
        "files": optional_files
    }

    # Add embedded blocks that didn't go into steps
    for key, value in embedded.items():
        if key not in ["first_touch"] and key not in onboarding:
            onboarding[key] = value

    # Add system_flow, api_patterns, hetzner_vps, completion from embedded
    for key in ["system_flow", "api_patterns", "hetzner_vps", "completion", "fruits_index", "protocols_index", "works_index", "onboarding_procedure_override"]:
        if key in embedded and embedded[key]:
            onboarding[key] = embedded[key]

    # Add platform_choice from builder
    build_rules = builder.get("build_rules", {})
    platform_choice = build_rules.get("platform_choice", {})
    if platform_choice:
        onboarding["platform_choice"] = platform_choice

    # Add language_selector
    lang_selector = embedded.get("language_selector", {})
    if lang_selector:
        onboarding["language_selector"] = lang_selector

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
