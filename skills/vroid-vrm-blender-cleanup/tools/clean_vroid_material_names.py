"""
Strip VRoid material ID prefixes from bpy.data.materials names.
Run via MCP execute_blender_code or Blender Scripting workspace.

    report = dry_run_materials()
    apply_material_renames(report["mapping"])
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

import bpy

# N00_006_01_ — third segment is 2 digits (body, shoes, cloth slots)
VRoid_NUMERIC_PREFIX = re.compile(r"N\d{2}_\d{3}_\d{2}_")

# N00_000_Hair_00_ — third segment is a word (hair, etc.)
VRoid_NAMED_PREFIX = re.compile(r"N\d{2}_\d{3}_[A-Za-z]+_\d{2}_")

DRY_RUN = True


def clean_vroid_material_name(name: str) -> str:
    cleaned = VRoid_NUMERIC_PREFIX.sub("", name)
    cleaned = VRoid_NAMED_PREFIX.sub("", cleaned)
    return cleaned


def needs_cleanup(name: str) -> bool:
    return (
        VRoid_NUMERIC_PREFIX.search(name) is not None
        or VRoid_NAMED_PREFIX.search(name) is not None
    )


def unique_material_name(desired: str, current: bpy.types.Material) -> str:
    if desired == current.name:
        return desired

    existing = bpy.data.materials.get(desired)
    if existing is None or existing == current:
        return desired

    index = 1
    while True:
        candidate = f"{desired}.{index:03d}"
        other = bpy.data.materials.get(candidate)
        if other is None or other == current:
            return candidate
        index += 1


def build_material_rename_map() -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for mat in bpy.data.materials:
        old_name = mat.name
        if not needs_cleanup(old_name):
            continue
        new_name = clean_vroid_material_name(old_name)
        if new_name == old_name:
            continue
        new_name = unique_material_name(new_name, mat)
        mapping[old_name] = new_name
    return mapping


def dry_run_materials() -> dict:
    mapping = build_material_rename_map()
    rows: List[dict] = []
    for old, new in sorted(mapping.items(), key=lambda item: item[1]):
        rows.append({"old_name": old, "new_name": new})

    inv: Dict[str, List[str]] = {}
    for old, new in mapping.items():
        inv.setdefault(new, []).append(old)
    collisions = {target: sources for target, sources in inv.items() if len(sources) > 1}

    return {
        "phase": "B",
        "dry_run": True,
        "count": len(mapping),
        "rows": rows,
        "collisions": collisions,
        "mapping": mapping,
    }


def apply_material_renames(mapping: Dict[str, str]) -> dict:
    renamed: List[Tuple[str, str]] = []
    skipped: List[str] = []

    for mat in list(bpy.data.materials):
        old_name = mat.name
        new_name = mapping.get(old_name)
        if not new_name:
            skipped.append(old_name)
            continue
        if new_name == old_name:
            continue
        new_name = unique_material_name(new_name, mat)
        mat.name = new_name
        renamed.append((old_name, new_name))

    return {
        "phase": "B",
        "dry_run": False,
        "renamed_count": len(renamed),
        "renamed": renamed,
        "skipped_count": len(skipped),
    }


def run_phase_b(dry_run: bool = DRY_RUN) -> dict:
    if dry_run:
        return dry_run_materials()
    report = dry_run_materials()
    apply_result = apply_material_renames(report["mapping"])
    return {**report, **apply_result}


if __name__ == "__main__":
    result = run_phase_b(dry_run=DRY_RUN)
