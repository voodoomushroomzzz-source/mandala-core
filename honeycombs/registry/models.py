#!/usr/bin/env python3
"""
Pydantic models for honeycomb index.json validation.
Auto-generated from schema.json.
"""
from typing import Optional, List, Dict, Any
from datetime import date, datetime
from pydantic import BaseModel, Field, field_validator
import re

class Identity(BaseModel):
    module_id: str = Field(..., pattern=r'^[A-Z0-9-]+$')
    name: str = Field(..., min_length=1)
    version: str = Field(..., pattern=r'^v\d+\.\d+\.\d+$')
    created: Optional[date] = None
    updated: Optional[date] = None
    layer: int = Field(..., ge=1, le=5)
    type: str = Field(..., pattern=r'^[a-z_]+$')
    description: str = Field(..., min_length=1)
    status: Optional[str] = Field(None, pattern=r'^(active|in_progress|archived|deprecated)$')
    priority: Optional[str] = Field(None, pattern=r'^(critical|high|medium|low)$')
    resonance: Optional[str] = Field(None, pattern=r'^\d+%$')
    tags: Optional[List[str]] = None
    
    @field_validator('version')
    def validate_version(cls, v):
        if not re.match(r'^v\d+\.\d+\.\d+$', v):
            raise ValueError(f'Version must be in format vX.Y.Z, got {v}')
        return v

class Meta(BaseModel):
    description: str = Field(..., min_length=1)
    audience: Optional[str] = None
    purpose: Optional[str] = None
    how_to_use: Optional[str] = None
    change_requires: Optional[str] = Field(None, pattern=r'^(gardener_approval|sr_proposal|auto)$')
    guardian_lock: Optional[bool] = False
    total_size_kb: Optional[float] = Field(None, ge=0)
    total_files: Optional[int] = Field(None, ge=0)
    segments: Optional[int] = Field(None, ge=0)
    parent_honeycomb: Optional[str] = None
    honeycomb_name: Optional[str] = None
    resonance_with_awareness: Optional[str] = Field(None, pattern=r'^\d+%$')
    status: Optional[str] = Field(None, pattern=r'^(active|in_progress|archived|deprecated)$')
    priority: Optional[str] = Field(None, pattern=r'^(critical|high|medium|low)$')

class Resonance(BaseModel):
    status: Optional[str] = Field(None, pattern=r'^(fully_resonant|partial|critical)$')
    with_boot: Optional[str] = Field(None, pattern=r'^\d+%$')
    with_core_map: Optional[str] = Field(None, pattern=r'^\d+%$')

class Health(BaseModel):
    status: Optional[str] = Field(None, pattern=r'^(healthy|warning|critical)$')
    last_check: Optional[date] = None
    notes: Optional[str] = None

class RegistryStats(BaseModel):
    total_blocks: Optional[int] = Field(None, ge=0)
    total_testimonies: Optional[int] = Field(None, ge=0)
    last_updated: Optional[date] = None

class HoneycombIndex(BaseModel):
    identity: Identity
    meta: Meta
    content: Optional[Dict[str, Any]] = None
    structure: Optional[Dict[str, Any]] = None
    resonance: Optional[Resonance] = None
    health: Optional[Health] = None
    registry: Optional[RegistryStats] = None

def validate_honeycomb_index(data: Dict[str, Any]) -> HoneycombIndex:
    """Validate honeycomb index.json data and return Pydantic model."""
    return HoneycombIndex(**data)

def validate_honeycomb_index_file(file_path: str) -> HoneycombIndex:
    """Validate honeycomb index.json file and return Pydantic model."""
    import json
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return validate_honeycomb_index(data)
