"""
Strip VRoid material ID prefixes from bpy.data.materials names.

Source names (VRoid import) stay as-is until Phase B runs, e.g.
  N00_000_00_Face_00_SKIN (Instance)
Workflow renames them to friendly names, e.g.
  Face_Skin

Alias map on scene links source → workflow for downstream skills.
"""

from __future__ import annotations

import json
import re
from typing import Dict, List, Optional, Tuple

import bpy

# N00_006_01_ — third segment is 2 digits (body, shoes, cloth outfit slots)
VRoid_NUMERIC_PREFIX = re.compile(r"N\d{2}_\d{3}_\d{2}_")

# N00_000_Hair_00_ — third segment is a word (hair, etc.)
VRoid_NAMED_PREFIX = re.compile(r"N\d{2}_\d{3}_[A-Za-z]+_\d{2}_")

INSTANCE_SUFFIX = re.compile(r" \(Instance\)$")

# Scene JSON: { "N00_…_Tops_01_CLOTH_01 (Instance)": "Hoodie_01", … }
SCENE_RENAME_MAP_KEY = "vroid_material_rename_map"

# VRoid tail (after prefix strip) → friendly material name.
CLOTHING_TAIL_ALIASES: Dict[str, str] = {
    "Tops_01_CLOTH": "Hoodie",
}

SKIN_TAIL_ALIASES: Dict[str, str] = {
    "Body_00_SKIN": "Body_Skin",
    "Face_00_SKIN": "Face_Skin",
}

DRY_RUN = True


def strip_instance_suffix(name: str) -> str:
    """Remove VRoid ` (Instance)` suffix; preserve `MToon Outline (...)` wrapper."""
    if name.startswith("MToon Outline ("):
        if name.endswith(" (Instance))"):
            return name[: -len(" (Instance))")] + ")"
        return name
    return INSTANCE_SUFFIX.sub("", name)


def friendly_clothing_tail(tail: str) -> str:
    if tail in CLOTHING_TAIL_ALIASES:
        return CLOTHING_TAIL_ALIASES[tail]
    for vroid_tail, friendly in CLOTHING_TAIL_ALIASES.items():
        layer_prefix = f"{vroid_tail}_"
        if tail.startswith(layer_prefix):
            layer = tail[len(layer_prefix) :]
            if layer.isdigit():
                return f"{friendly}_{layer}"
    return tail


def friendly_skin_tail(tail: str) -> str:
    return SKIN_TAIL_ALIASES.get(tail, tail)


def apply_friendly_tail(tail: str) -> str:
    return friendly_skin_tail(friendly_clothing_tail(tail))


def apply_friendly_material_name(cleaned: str) -> str:
    if cleaned.startswith("MToon Outline ("):
        inner = cleaned[len("MToon Outline (") : -1]
        friendly = apply_friendly_tail(inner)
        if friendly != inner:
            return f"MToon Outline ({friendly})"
        return cleaned
    return apply_friendly_tail(cleaned)


def clean_vroid_material_name(name: str) -> str:
    cleaned = VRoid_NUMERIC_PREFIX.sub("", name)
    cleaned = VRoid_NAMED_PREFIX.sub("", cleaned)
    cleaned = strip_instance_suffix(cleaned)
    return apply_friendly_material_name(cleaned)


def needs_cleanup(name: str) -> bool:
    return (
        VRoid_NUMERIC_PREFIX.search(name) is not None
        or VRoid_NAMED_PREFIX.search(name) is not None
    )


def load_stored_rename_map(scene: Optional[bpy.types.Scene] = None) -> Dict[str, str]:
    """Phase B old_name → new_name map persisted on the scene."""
    scene = scene or bpy.context.scene
    raw = scene.get(SCENE_RENAME_MAP_KEY) if scene else None
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def store_rename_map(
    mapping: Dict[str, str],
    scene: Optional[bpy.types.Scene] = None,
    *,
    merge: bool = True,
) -> Dict[str, str]:
    scene = scene or bpy.context.scene
    combined = {**load_stored_rename_map(scene), **mapping} if merge else dict(mapping)
    scene[SCENE_RENAME_MAP_KEY] = json.dumps(combined, sort_keys=True)
    return combined


def _intermediate_stripped_name(name: str) -> str:
    """Prefix + Instance strip only — before friendly clothing alias."""
    cleaned = VRoid_NUMERIC_PREFIX.sub("", name)
    cleaned = VRoid_NAMED_PREFIX.sub("", cleaned)
    return strip_instance_suffix(cleaned)


def skin_name_variants(token: str) -> List[str]:
    variants = {token}
    for vroid_tail, friendly in SKIN_TAIL_ALIASES.items():
        if token in (vroid_tail, friendly):
            variants.add(vroid_tail)
            variants.add(friendly)
    return sorted(variants)


def clothing_name_variants(token: str) -> List[str]:
    """Friendly name ↔ VRoid tail (e.g. Hoodie_01 ↔ Tops_01_CLOTH_01)."""
    variants = {token}
    for vroid_tail, friendly in CLOTHING_TAIL_ALIASES.items():
        if token == friendly:
            variants.add(vroid_tail)
        elif token.startswith(f"{friendly}_"):
            layer = token[len(friendly) + 1 :]
            if layer.isdigit():
                variants.add(f"{vroid_tail}_{layer}")
        if token == vroid_tail:
            variants.add(friendly)
        elif token.startswith(f"{vroid_tail}_"):
            layer = token[len(vroid_tail) + 1 :]
            if layer.isdigit():
                variants.add(f"{friendly}_{layer}")
    return sorted(variants)


def material_name_variants(token: str, scene: Optional[bpy.types.Scene] = None) -> List[str]:
    """Import name, VRoid tail, friendly name, and stored aliases."""
    variants = set(skin_name_variants(token))
    variants.update(clothing_name_variants(token))
    if needs_cleanup(token):
        variants.add(_intermediate_stripped_name(token))
        variants.add(clean_vroid_material_name(token))
    else:
        variants.add(apply_friendly_material_name(token))

    fwd = load_stored_rename_map(scene)
    for old, new in fwd.items():
        if token in (old, new):
            variants.add(old)
            variants.add(new)
            continue
        if needs_cleanup(old):
            variants.add(_intermediate_stripped_name(old))
        stripped = _intermediate_stripped_name(old) if needs_cleanup(old) else old
        if token in stripped or token in new or token in old:
            variants.add(old)
            variants.add(new)
        variants.update(clothing_name_variants(new))
        variants.update(clothing_name_variants(stripped))
        variants.update(skin_name_variants(new))
        variants.update(skin_name_variants(stripped))

    return sorted(variants)


def resolve_material_by_token(
    token: str,
    scene: Optional[bpy.types.Scene] = None,
) -> Optional[bpy.types.Material]:
    """Match material by Phase B name, VRoid import name, or stored rename alias."""
    for name in material_name_variants(token, scene):
        mat = bpy.data.materials.get(name)
        if mat:
            return mat

    candidates = [m for m in bpy.data.materials if token in m.name]
    if not candidates:
        return None
    return min(candidates, key=lambda m: (token not in m.name, len(m.name), m.name))


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
        "stored_aliases": load_stored_rename_map(),
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

    if renamed:
        stored = store_rename_map({old: new for old, new in renamed})
    else:
        stored = load_stored_rename_map()

    return {
        "phase": "B",
        "dry_run": False,
        "renamed_count": len(renamed),
        "renamed": renamed,
        "skipped_count": len(skipped),
        "stored_rename_map_count": len(stored),
    }


def run_phase_b(dry_run: bool = DRY_RUN) -> dict:
    if dry_run:
        return dry_run_materials()
    report = dry_run_materials()
    apply_result = apply_material_renames(report["mapping"])
    return {**report, **apply_result}


if __name__ == "__main__":
    result = run_phase_b(dry_run=DRY_RUN)
