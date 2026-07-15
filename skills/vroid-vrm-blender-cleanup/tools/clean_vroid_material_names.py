"""
Strip VRoid material ID prefixes from bpy.data.materials names.

Source names (VRoid import) stay as-is until Phase B runs, e.g.
  N00_000_00_Face_00_SKIN (Instance)
Workflow renames use dot notation + Title Case, e.g.
  Face.Skin

VRoid uses `_00_` as a category separator (Face_00_SKIN → Face.Skin).
Alias map on scene links source → workflow for downstream skills.
"""

from __future__ import annotations

import json
import re
from typing import Dict, List, Optional, Tuple

import bpy

# N00_005_01_ / N00_000_00_ — outfit or body slot prefix
VRoid_SLOT_PREFIX = re.compile(r"^N\d{2}_\d{3}_(?:\d{2}|[A-Za-z]+)_")

# Hair strand: N00_000_Hair_00_HAIR_01 → Hair.01
VRoid_HAIR_STRAND_PREFIX = re.compile(r"^N\d{2}_\d{3}_Hair_\d{2}_HAIR_(\d+)$")

INSTANCE_SUFFIX = re.compile(r" \(Instance\)$")

SCENE_RENAME_MAP_KEY = "vroid_material_rename_map"

# VRoid clothing tail (after slot prefix strip) → workflow basename
CLOTHING_ITEM_ALIASES: Dict[str, str] = {
    "Tops_01_CLOTH": "Hoodie",
}

# VRoid eye tail (before _00_EYE) → workflow feature for {Feature}.Eye
EYE_FEATURE_NAMES: Dict[str, str] = {
    "EyeIris": "Iris",
    "EyeHighlight": "EyeHighlight",
    "EyeWhite": "EyeWhite",
}

DRY_RUN = True


def strip_instance_suffix(name: str) -> str:
    """Remove VRoid ` (Instance)` suffix; preserve `MToon Outline (...)` wrapper."""
    if name.startswith("MToon Outline ("):
        if name.endswith(" (Instance))"):
            return name[: -len(" (Instance))")] + ")"
        return name
    return INSTANCE_SUFFIX.sub("", name)


def strip_vroid_slot_prefix(name: str) -> str:
    """Remove leading N{xx}_{xxx}_{slot}_ import prefix."""
    bare = strip_instance_suffix(name)
    m = VRoid_HAIR_STRAND_PREFIX.match(bare)
    if m:
        return f"Hair_00_HAIR_{m.group(1)}"
    return VRoid_SLOT_PREFIX.sub("", bare)


def _title_word(word: str) -> str:
    if not word:
        return word
    return word[0].upper() + word[1:].lower()


def _split_region_subpart(left: str) -> Tuple[str, str]:
    """FaceMouth → (Face, Mouth), EyeIris → (Eye, Iris), HairBack → (Hair, Back)."""
    for region in ("Face", "Eye", "Hair", "Body"):
        if left == region:
            return region, ""
        if left.startswith(region) and len(left) > len(region):
            return region, _title_word(left[len(region) :])
    return _title_word(left), ""


def standardize_workflow_tail(tail: str) -> str:
    """VRoid tail after prefix strip → workflow dot name."""
    if not tail:
        return tail

    # Clothing: Shoes_01_CLOTH → Shoes.Cloth; Tops_01_CLOTH_01 → Hoodie_01.Cloth
    cloth = re.match(r"^([A-Za-z]+)_(\d{2})_CLOTH(?:_(\d+))?$", tail)
    if cloth:
        item, slot, layer = cloth.group(1), cloth.group(2), cloth.group(3)
        base_key = f"{item}_{slot}_CLOTH"
        item_name = CLOTHING_ITEM_ALIASES.get(base_key, _title_word(item))
        if layer:
            return f"{item_name}_{layer}.Cloth"
        return f"{item_name}.Cloth"

    # Category separator _00_ (Face_00_SKIN, FaceMouth_00_FACE, Hair_00_HAIR_01)
    if "_00_" in tail:
        left, right = tail.split("_00_", 1)
        category = _title_word(right.lower())

        strand = re.match(r"^HAIR_(\d+)$", right)
        if strand:
            return f"Hair.{strand.group(1)}"

        region, sub = _split_region_subpart(left)

        # FACE category: FaceMouth_00_FACE → Mouth.Face (feature.category)
        if right == "FACE" and sub:
            return f"{sub}.{category}"

        # EYE category: EyeIris_00_EYE → Iris.Eye; EyeHighlight_00_EYE → EyeHighlight.Eye
        if right == "EYE":
            feature = EYE_FEATURE_NAMES.get(left, sub if sub else _title_word(left))
            return f"{feature}.{category}"

        if sub:
            return f"{region}.{sub}"

        return f"{region}.{category}"

    return tail


def apply_workflow_material_name(cleaned: str) -> str:
    if cleaned.startswith("MToon Outline ("):
        inner = cleaned[len("MToon Outline (") : -1]
        workflow = standardize_workflow_tail(inner)
        if workflow != inner:
            return f"MToon Outline ({workflow})"
        return cleaned
    return standardize_workflow_tail(cleaned)


def clean_vroid_material_name(name: str) -> str:
    cleaned = strip_vroid_slot_prefix(name)
    return apply_workflow_material_name(cleaned)


def needs_cleanup(name: str) -> bool:
    bare = strip_instance_suffix(name)
    if VRoid_SLOT_PREFIX.search(bare):
        return True
    if VRoid_HAIR_STRAND_PREFIX.match(bare):
        return True
    return False


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
    """Prefix strip only — before workflow standardize."""
    return strip_vroid_slot_prefix(name)


def _clothing_variants(token: str) -> List[str]:
    variants = {token}
    for vroid_base, friendly in CLOTHING_ITEM_ALIASES.items():
        if token == f"{friendly}.Cloth":
            variants.add(vroid_base)
        layered = re.match(rf"^{re.escape(friendly)}_(\d+)\.Cloth$", token)
        if layered:
            variants.add(f"{vroid_base}_{layered.group(1)}")
        legacy = re.match(rf"^{re.escape(friendly)}\.(\d+)$", token)
        if legacy:
            variants.add(f"{vroid_base}_{legacy.group(1)}")
            variants.add(f"{friendly}_{legacy.group(1)}.Cloth")
        if token == vroid_base:
            variants.add(f"{friendly}.Cloth")
        elif token.startswith(vroid_base + "_"):
            layer = token[len(vroid_base) + 1 :]
            if layer.isdigit():
                variants.add(f"{friendly}_{layer}.Cloth")
    return sorted(variants)


def material_name_variants(token: str, scene: Optional[bpy.types.Scene] = None) -> List[str]:
    """Import name, VRoid tail, workflow name, and stored aliases."""
    variants = {token}
    variants.update(_clothing_variants(token))
    if needs_cleanup(token):
        variants.add(_intermediate_stripped_name(token))
        variants.add(clean_vroid_material_name(token))
    else:
        stripped = _intermediate_stripped_name(token) if VRoid_SLOT_PREFIX.search(token) else token
        variants.add(apply_workflow_material_name(stripped))
        variants.add(apply_workflow_material_name(token))

    fwd = load_stored_rename_map(scene)
    for old, new in fwd.items():
        stripped = _intermediate_stripped_name(old) if needs_cleanup(old) else old
        related = token in (old, new, stripped)
        if not related:
            continue
        variants.add(old)
        variants.add(new)
        if needs_cleanup(old):
            variants.add(stripped)
        variants.update(_clothing_variants(new))
        variants.update(_clothing_variants(stripped))

    return sorted(variants)


def resolve_material_by_token(
    token: str,
    scene: Optional[bpy.types.Scene] = None,
) -> Optional[bpy.types.Material]:
    """Match material by workflow name, VRoid import name, or stored rename alias."""
    mat = bpy.data.materials.get(token)
    if mat:
        return mat

    names = material_name_variants(token, scene)
    if token in names:
        names = [token] + [n for n in names if n != token]

    for name in names:
        mat = bpy.data.materials.get(name)
        if mat:
            return mat

    candidates = [m for m in bpy.data.materials if token in m.name]
    if not candidates:
        return None
    return min(candidates, key=lambda m: (m.name != token, len(m.name), m.name))


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
