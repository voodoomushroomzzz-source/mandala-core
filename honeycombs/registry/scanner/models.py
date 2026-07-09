#!/usr/bin/env python3
"""
Simple dataclass models for honeycomb index.json (no external dependencies).
"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

@dataclass
class Identity:
    module_id: str = ""
    name: str = ""
    version: str = ""
    created: Optional[str] = None
    updated: Optional[str] = None
    layer: int = 0
    type: str = ""
    description: str = ""
    status: Optional[str] = None
    priority: Optional[str] = None
    resonance: Optional[str] = None
    tags: Optional[List[str]] = field(default_factory=list)

@dataclass
class Meta:
    description: str = ""
    audience: Optional[str] = None
    purpose: Optional[str] = None
    how_to_use: Optional[str] = None
    change_requires: Optional[str] = None
    guardian_lock: bool = False
    total_size_kb: Optional[float] = None
    total_files: Optional[int] = None
    segments: Optional[int] = None
    parent_honeycomb: Optional[str] = None
    honeycomb_name: Optional[str] = None
    resonance_with_awareness: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None

@dataclass
class Resonance:
    status: Optional[str] = None
    with_boot: Optional[str] = None
    with_core_map: Optional[str] = None

@dataclass
class Health:
    status: Optional[str] = None
    last_check: Optional[str] = None
    notes: Optional[str] = None

@dataclass
class RegistryStats:
    total_blocks: Optional[int] = None
    total_testimonies: Optional[int] = None
    last_updated: Optional[str] = None

@dataclass
class HoneycombIndex:
    identity: Identity
    meta: Meta
    content: Optional[Dict[str, Any]] = None
    structure: Optional[Dict[str, Any]] = None
    resonance: Optional[Resonance] = None
    health: Optional[Health] = None
    registry: Optional[RegistryStats] = None
