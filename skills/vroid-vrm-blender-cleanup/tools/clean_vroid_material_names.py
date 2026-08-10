"""
Strip VRoid material ID prefixes from bpy.data.materials names.

Source names (VRoid import) stay as-is until Phase B runs, e.g.
  N00_000_00_Face_00_SKIN (Instance)
Workflow renames use underscore identity + Title Case, e.g.
  Face_Skin

VRoid uses `_00_` as a category separator (Face_00_SKIN → Face_Skin).
Optional MToon class tail: Face_Skin-NoRim.NoOutline
Alias map on scene links source → workflow for downstream skills.
"""

from __future__ import annotations

import json
import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import bpy

# N00_005_01_ / N00_000_00_ — outfit or body slot prefix
# Named third segment (e.g. Hair) is handled by VRoid_HAIR_MAT first — do not strip it here.
VRoid_SLOT_PREFIX = re.compile(r"^N\d{2}_\d{3}_(?:\d{2}|[A-Za-z]+)_")

# Hair mat or strand: N00_000_Hair_00_HAIR / N00_000_Hair_00_HAIR_01
# Must run before SLOT_PREFIX or `Hair_` is eaten → broken tail `00_HAIR`.
VRoid_HAIR_MAT = re.compile(r"^N\d{2}_\d{3}_(Hair_\d{2}_HAIR(?:_\d+)?)$")

# Hair strand (legacy alias of VRoid_HAIR_MAT with capture)
VRoid_HAIR_STRAND_PREFIX = re.compile(r"^N\d{2}_\d{3}_Hair_\d{2}_HAIR_(\d+)$")

INSTANCE_SUFFIX = re.compile(r" \(Instance\)$")
# Blender auto-dup on datablock collision (ARKit .001 mats)
BLENDER_DUP_SUFFIX = re.compile(r"(\.\d{3})$")
# Botched outline inner from earlier buggy Phase B: N00_000.Face_00_skin.001
BROKEN_FACE_SKIN_INNER = re.compile(r"^N\d{2}_\d{3}\.Face_00_skin$", re.IGNORECASE)

SCENE_RENAME_MAP_KEY = "vroid_material_rename_map"

# VRoid clothing tail (after slot prefix strip) → workflow basename
CLOTHING_ITEM_ALIASES: Dict[str, str] = {
    "Tops_01_CLOTH": "Hoodie",
}

# VRoid eye tail (before _00_EYE) → workflow feature for {Feature}_Eye
EYE_FEATURE_NAMES: Dict[str, str] = {
    "EyeIris": "Iris",
    "EyeHighlight": "EyeHighlight",
    "EyeWhite": "EyeWhite",
}

# Inverted ARKit .001 names from when `.001` broke category parse (Eye.Iris vs Iris_Eye)
WORKFLOW_REPAIR: Dict[str, str] = {
    "Eye.Highlight": "EyeHighlight_Eye",
    "Eye.Iris": "Iris_Eye",
    "Eye.White": "EyeWhite_Eye",
    "Face.Brow": "Brow_Face",
    "Face.Eyelash": "Eyelash_Face",
    "Face.Eyeline": "Eyeline_Face",
    "Face.Mouth": "Mouth_Face",
    "EyeHighlight.Eye": "EyeHighlight_Eye",
    "Iris.Eye": "Iris_Eye",
    "EyeWhite.Eye": "EyeWhite_Eye",
    "Brow.Face": "Brow_Face",
    "Eyelash.Face": "Eyelash_Face",
    "Eyeline.Face": "Eyeline_Face",
    "Mouth.Face": "Mouth_Face",
    "Face.Skin": "Face_Skin",
    "Body.Skin": "Body_Skin",
    "Hair.Back": "Hair_Back",
    "Hair.Secondary": "Hair_Secondary",
}

KNOWN_MTOON_CLASSES = frozenset(
    {
        "NoRim",
        "NoOutline",
        "NoShade",
        "Highlight",
        "EmissionAccent",
        "InvertEmissionAccent",
    }
)
LEGACY_DROPPED_CLASSES = frozenset({"NoMatcap", "NoHighlight", "Glow", "InvertRim"})
CLASS_ORDER = (
    "NoRim",
    "NoOutline",
    "NoShade",
    "Highlight",
    "EmissionAccent",
    "InvertEmissionAccent",
)
OUTLINE_PREFIX = "MToon Outline ("

DRY_RUN = True


def strip_instance_suffix(name: str) -> str:
    """Remove VRoid ` (Instance)` suffix; preserve `MToon Outline (...)` wrapper."""
    if name.startswith("MToon Outline ("):
        if name.endswith(" (Instance))"):
            return name[: -len(" (Instance))")] + ")"
        return name
    return INSTANCE_SUFFIX.sub("", name)


def split_blender_dup_suffix(name: str) -> Tuple[str, str]:
    """Split trailing `.001` Blender duplicate suffix. Returns (base, suffix_or_empty)."""
    match = BLENDER_DUP_SUFFIX.search(name)
    if not match:
        return name, ""
    return name[: match.start()], match.group(1)


def strip_vroid_slot_prefix(name: str) -> str:
    """Remove leading N{xx}_{xxx}_{slot}_ import prefix."""
    bare = strip_instance_suffix(name)
    base, _dup = split_blender_dup_suffix(bare)
    hair = VRoid_HAIR_MAT.match(base)
    if hair:
        return hair.group(1)
    return VRoid_SLOT_PREFIX.sub("", base)


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


def dotted_workflow_to_underscore(identity: str) -> str:
    """Face.Skin / Hair.01 → Face_Skin / Hair_01. Keeps trailing .001 on caller."""
    if "." not in identity:
        return identity
    return identity.replace(".", "_")


def parse_material_name(name: str) -> Dict[str, object]:
    """Split outline wrapper, Blender dup, identity, and -Class.Class tail."""
    outline = False
    working = name
    if working.startswith(OUTLINE_PREFIX) and working.endswith(")"):
        working = working[len(OUTLINE_PREFIX) : -1]
        outline = True

    bare = strip_instance_suffix(working)
    base, dup = split_blender_dup_suffix(bare)

    classes: List[str] = []
    unknown: List[str] = []
    identity = base
    invalid_class_dots = False
    kind = "identity"

    if "-" in base:
        left, right = base.split("-", 1)
        identity = left
        for tok in right.split("."):
            if not tok:
                continue
            if tok in LEGACY_DROPPED_CLASSES:
                continue
            if tok in KNOWN_MTOON_CLASSES:
                if tok not in classes:
                    classes.append(tok)
            else:
                unknown.append(tok)
        kind = "identity_classes"
    elif "." in base:
        segs = [s for s in base.split(".") if s]
        first, rest = (segs[0], segs[1:]) if segs else ("", [])
        rest_are_classes = bool(rest) and all(
            s in KNOWN_MTOON_CLASSES or s in LEGACY_DROPPED_CLASSES for s in rest
        )
        if rest_are_classes and first not in KNOWN_MTOON_CLASSES:
            # Glow.NoRim → identity Glow + class NoRim (legacy dotted class grammar)
            identity = first
            for tok in rest:
                if tok in LEGACY_DROPPED_CLASSES:
                    continue
                if tok in KNOWN_MTOON_CLASSES and tok not in classes:
                    classes.append(tok)
            kind = "identity_classes"
        elif segs and all(
            s in KNOWN_MTOON_CLASSES or s in LEGACY_DROPPED_CLASSES for s in segs
        ):
            invalid_class_dots = True
            kind = "invalid_class_dots"

    if outline:
        kind = "outline"

    return {
        "identity": identity,
        "classes": classes,
        "unknown_classes": unknown,
        "kind": kind,
        "dup": dup,
        "outline": outline,
        "invalid_class_dots": invalid_class_dots,
    }


def rebuild_material_name(
    identity: str,
    classes: Optional[Sequence[str]] = None,
    *,
    outline: bool = False,
    dup: str = "",
) -> str:
    ordered: List[str] = []
    wanted = list(classes or [])
    for token in CLASS_ORDER:
        if token in wanted and token not in ordered:
            ordered.append(token)
    for token in wanted:
        if token in KNOWN_MTOON_CLASSES and token not in ordered:
            ordered.append(token)
    core = f"{identity}-{'.'.join(ordered)}{dup}" if ordered else f"{identity}{dup}"
    return f"{OUTLINE_PREFIX}{core})" if outline else core


def identity_slug(name: str) -> str:
    """Texture slug from identity only: Face_Skin-NoRim → face_skin."""
    parsed = parse_material_name(name)
    identity = dotted_workflow_to_underscore(str(parsed["identity"]))
    return identity.lower()


def standardize_workflow_tail(tail: str) -> str:
    """VRoid tail after prefix strip → workflow underscore name."""
    if not tail:
        return tail

    tail, _dup = split_blender_dup_suffix(tail)

    # Clothing: Shoes_01_CLOTH → Shoes_Cloth; Accessory_RabbitEar_01_CLOTH → RabbitEar_Cloth
    cloth = re.match(
        r"^(?:Accessory_)?([A-Za-z]+)_(\d{2})_CLOTH(?:_(\d+))?$",
        tail,
    )
    if cloth:
        item, slot, layer = cloth.group(1), cloth.group(2), cloth.group(3)
        base_key = f"{item}_{slot}_CLOTH"
        item_name = CLOTHING_ITEM_ALIASES.get(base_key, item)
        if layer:
            return f"{item_name}_{layer}_Cloth"
        return f"{item_name}_Cloth"

    # Category separator _00_ (Face_00_SKIN, FaceMouth_00_FACE, Hair_00_HAIR_01)
    if "_00_" in tail:
        left, right = tail.split("_00_", 1)
        right, _ = split_blender_dup_suffix(right)
        category = _title_word(right.lower())

        strand = re.match(r"^HAIR_(\d+)$", right)
        if strand:
            return f"Hair_{strand.group(1)}"

        # Primary / non-stranded hair: Hair_00_HAIR → Hair_Back
        if left == "Hair" and right == "HAIR":
            return "Hair_Back"

        region, sub = _split_region_subpart(left)

        # FACE category: FaceMouth_00_FACE → Mouth_Face
        if right == "FACE" and sub:
            return f"{sub}_{category}"

        # EYE category: EyeIris_00_EYE → Iris_Eye
        if right == "EYE":
            feature = EYE_FEATURE_NAMES.get(left, sub if sub else _title_word(left))
            return f"{feature}_{category}"

        if sub:
            return f"{region}_{sub}"

        return f"{region}_{category}"

    return dotted_workflow_to_underscore(tail)


def apply_workflow_material_name(cleaned: str) -> str:
    parsed = parse_material_name(cleaned)
    inner = clean_vroid_material_name(str(parsed["identity"]) + str(parsed["dup"]))
    inner_parsed = parse_material_name(inner)
    return rebuild_material_name(
        dotted_workflow_to_underscore(str(inner_parsed["identity"])),
        list(parsed["classes"]),  # type: ignore[arg-type]
        outline=bool(parsed["outline"]),
        dup=str(inner_parsed["dup"] or parsed["dup"]),
    )


def _clean_identity_core(identity: str, dup: str) -> Tuple[str, str]:
    base = identity
    if base in WORKFLOW_REPAIR:
        cleaned = WORKFLOW_REPAIR[base]
        return dotted_workflow_to_underscore(cleaned), dup

    if BROKEN_FACE_SKIN_INNER.match(base):
        return "Face_Skin", dup

    hair = VRoid_HAIR_MAT.match(base)
    if hair:
        stripped = hair.group(1)
    else:
        stripped = VRoid_SLOT_PREFIX.sub("", base)

    workflow = standardize_workflow_tail(stripped)
    workflow = dotted_workflow_to_underscore(workflow)
    return workflow, dup


def clean_vroid_material_name(name: str) -> str:
    """Full import / botched / inverted name → workflow name (keeps `.001` + class tail)."""
    parsed = parse_material_name(name)
    ident, dup = _clean_identity_core(str(parsed["identity"]), str(parsed["dup"]))
    return rebuild_material_name(
        ident,
        list(parsed["classes"]),  # type: ignore[arg-type]
        outline=bool(parsed["outline"]),
        dup=dup,
    )


def needs_cleanup(name: str) -> bool:
    parsed = parse_material_name(name)
    ident = str(parsed["identity"])
    if bool(parsed.get("invalid_class_dots")):
        return True
    ident_base, _ = split_blender_dup_suffix(ident)
    if "." in ident_base:
        return True
    if ident_base in WORKFLOW_REPAIR:
        return True
    if BROKEN_FACE_SKIN_INNER.match(ident_base):
        return True
    if VRoid_HAIR_MAT.match(ident_base):
        return True
    if VRoid_SLOT_PREFIX.search(ident_base):
        return True
    if VRoid_HAIR_STRAND_PREFIX.match(ident_base):
        return True
    return clean_vroid_material_name(name) != name


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
    # RabbitEar_Cloth / RabbitEar.Cloth ↔ Accessory_RabbitEar_01_CLOTH
    cloth_wf = re.match(r"^([A-Za-z]+)(?:_(\d+))?[._]Cloth$", token)
    if cloth_wf:
        item, layer = cloth_wf.group(1), cloth_wf.group(2)
        base = f"{item}_01_CLOTH"
        variants.add(base)
        variants.add(f"Accessory_{base}")
        variants.add(f"{item}.Cloth")
        variants.add(f"{item}_Cloth")
        if layer:
            variants.add(f"{base}_{layer}")
            variants.add(f"Accessory_{base}_{layer}")
            variants.add(f"{item}_{layer}.Cloth")
            variants.add(f"{item}_{layer}_Cloth")
    acc = re.match(r"^(?:Accessory_)?([A-Za-z]+)_(\d{2})_CLOTH(?:_(\d+))?$", token)
    if acc:
        item, slot, layer = acc.group(1), acc.group(2), acc.group(3)
        base_key = f"{item}_{slot}_CLOTH"
        friendly = CLOTHING_ITEM_ALIASES.get(base_key, item)
        if layer:
            variants.add(f"{friendly}_{layer}.Cloth")
            variants.add(f"{friendly}_{layer}_Cloth")
        else:
            variants.add(f"{friendly}.Cloth")
            variants.add(f"{friendly}_Cloth")
        variants.add(base_key)
        variants.add(f"Accessory_{base_key}")

    for vroid_base, friendly in CLOTHING_ITEM_ALIASES.items():
        if token in (f"{friendly}.Cloth", f"{friendly}_Cloth"):
            variants.add(vroid_base)
        layered = re.match(rf"^{re.escape(friendly)}_(\d+)[._]Cloth$", token)
        if layered:
            variants.add(f"{vroid_base}_{layered.group(1)}")
        legacy = re.match(rf"^{re.escape(friendly)}\.(\d+)$", token)
        if legacy:
            variants.add(f"{vroid_base}_{legacy.group(1)}")
            variants.add(f"{friendly}_{legacy.group(1)}.Cloth")
            variants.add(f"{friendly}_{legacy.group(1)}_Cloth")
        if token == vroid_base:
            variants.add(f"{friendly}.Cloth")
            variants.add(f"{friendly}_Cloth")
        elif token.startswith(vroid_base + "_"):
            layer = token[len(vroid_base) + 1 :]
            if layer.isdigit():
                variants.add(f"{friendly}_{layer}.Cloth")
                variants.add(f"{friendly}_{layer}_Cloth")
    return sorted(variants)


def workflow_material_names_in_scene(token: str) -> List[str]:
    """Scene datablock names that standardize to this workflow token."""
    names: List[str] = []
    for mat in bpy.data.materials:
        if clean_vroid_material_name(mat.name) == token:
            names.append(mat.name)
    return sorted(names)


def _prefer_material_match(
    token: str, candidates: List[bpy.types.Material]
) -> bpy.types.Material:
    """Prefer exact workflow name, then VRoid (Instance), then shortest name."""

    def rank(mat: bpy.types.Material) -> tuple:
        name = mat.name
        bare = strip_instance_suffix(name)
        return (
            0 if name == token else 1,
            0 if name.endswith(" (Instance)") else 1,
            0 if bare == token else 1,
            1 if re.search(r"\.\d{3}$", bare) else 0,
            len(name),
            name,
        )

    return min(candidates, key=rank)


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

    variants.update(workflow_material_names_in_scene(token))

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
    """Match material by workflow name, VRoid import name, class tail, or stored alias."""
    mat = bpy.data.materials.get(token)
    if mat:
        return mat

    parsed = parse_material_name(token)
    ident = dotted_workflow_to_underscore(str(parsed["identity"]))
    # Face_Skin → Face.Skin alias (two-part legacy). Hair_01 → Hair.01.
    legacy_dot = ident.replace("_", ".")

    names = material_name_variants(token, scene)
    names.extend(material_name_variants(ident, scene))
    if legacy_dot != ident:
        names.extend(material_name_variants(legacy_dot, scene))
    names = list(dict.fromkeys([token, ident, legacy_dot] + names))

    for name in names:
        mat = bpy.data.materials.get(name)
        if mat:
            return mat

    # Match datablocks whose parsed identity equals token identity (Face_Skin-NoRim).
    ident_matches = [
        m
        for m in bpy.data.materials
        if dotted_workflow_to_underscore(str(parse_material_name(m.name)["identity"]))
        in {ident, legacy_dot, str(parsed["identity"])}
    ]
    if ident_matches:
        return _prefer_material_match(ident, ident_matches)

    workflow_matches = [
        bpy.data.materials.get(name)
        for name in workflow_material_names_in_scene(token)
    ]
    workflow_matches = [m for m in workflow_matches if m is not None]
    if workflow_matches:
        return _prefer_material_match(token, workflow_matches)

    candidates = [m for m in bpy.data.materials if token in m.name or ident in m.name]
    if not candidates:
        return None
    return _prefer_material_match(token, candidates)


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
    """N00 import names and Phase-B intermediate tails → workflow dot names."""
    mapping: Dict[str, str] = {}
    for mat in bpy.data.materials:
        old_name = mat.name
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
