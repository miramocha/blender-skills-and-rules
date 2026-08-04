"""
Create Animasa-standard MMD shape keys from existing VRoid / ARKit keys.

Never renames, deletes, or overwrites ARKit / vroid* / Fcl_* sources.
Bakes new MMD-named keys via temporary shape-key mix.

    report = create_mmd_shape_keys("Face", dry_run=True)
    result = create_mmd_shape_keys("Face", dry_run=False, set_scope="core")
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import bpy

SCENE_MAP_KEY = "mmd_shapekey_map"
DEFAULT_OBJECT = "Face"

# ---------------------------------------------------------------------------
# Mapping tables: each target → ordered candidate groups.
# A group is a list of (source_name, weight). First group where ALL sources
# exist on the mesh wins.
# ---------------------------------------------------------------------------

SourceSpec = Tuple[str, float]
CandidateGroup = List[SourceSpec]


def _g(*pairs: SourceSpec) -> CandidateGroup:
    return list(pairs)


CORE_MAPPINGS: Dict[str, List[CandidateGroup]] = {
    "あ": [
        _g(("vroidMouthA", 1.0)),
        _g(("Fcl_MTH_A", 1.0)),
        _g(("jawOpen", 1.0)),
    ],
    "い": [
        _g(("vroidMouthI", 1.0)),
        _g(("Fcl_MTH_I", 1.0)),
        _g(("mouthStretchLeft", 1.0), ("mouthStretchRight", 1.0)),
    ],
    "う": [
        _g(("vroidMouthU", 1.0)),
        _g(("Fcl_MTH_U", 1.0)),
        _g(("mouthFunnel", 1.0)),
        _g(("mouthPucker", 1.0)),
    ],
    "え": [
        _g(("vroidMouthE", 1.0)),
        _g(("Fcl_MTH_E", 1.0)),
        _g(
            ("jawOpen", 0.5),
            ("mouthStretchLeft", 0.7),
            ("mouthStretchRight", 0.7),
        ),
    ],
    "お": [
        _g(("vroidMouthO", 1.0)),
        _g(("Fcl_MTH_O", 1.0)),
        _g(("jawOpen", 0.7), ("mouthFunnel", 0.5)),
        _g(("jawOpen", 0.7), ("mouthPucker", 0.5)),
    ],
    "まばたき": [
        _g(("vroidEyeClose", 1.0)),
        _g(("Fcl_EYE_Close", 1.0)),
        _g(("vroidEyeCloseL", 1.0), ("vroidEyeCloseR", 1.0)),
        _g(("Fcl_EYE_Close_L", 1.0), ("Fcl_EYE_Close_R", 1.0)),
        _g(("eyeBlinkLeft", 1.0), ("eyeBlinkRight", 1.0)),
    ],
    "ウィンク": [
        _g(("vroidEyeCloseL", 1.0)),
        _g(("Fcl_EYE_Close_L", 1.0)),
        _g(("eyeBlinkLeft", 1.0)),
    ],
    "ウィンク右": [
        _g(("vroidEyeCloseR", 1.0)),
        _g(("Fcl_EYE_Close_R", 1.0)),
        _g(("eyeBlinkRight", 1.0)),
    ],
    "ウィンク２": [
        _g(("vroidEyeJoyL", 1.0)),
        _g(("Fcl_EYE_Joy_L", 1.0)),
        _g(("vroidEyeCloseL", 1.0), ("vroidEyeJoy", 0.5)),
        _g(("eyeBlinkLeft", 1.0), ("eyeSquintLeft", 0.6)),
        _g(("eyeBlinkLeft", 1.0)),
    ],
    # Animasa halfwidth katakana + fullwidth digit — do not "normalize"
    "ｳｨﾝｸ２右": [
        _g(("vroidEyeJoyR", 1.0)),
        _g(("Fcl_EYE_Joy_R", 1.0)),
        _g(("vroidEyeCloseR", 1.0), ("vroidEyeJoy", 0.5)),
        _g(("eyeBlinkRight", 1.0), ("eyeSquintRight", 0.6)),
        _g(("eyeBlinkRight", 1.0)),
    ],
    "笑い": [
        _g(("vroidEyeJoy", 1.0)),
        _g(("Fcl_EYE_Joy", 1.0)),
        _g(("vroidAllJoy", 1.0)),
        _g(("Fcl_ALL_Joy", 1.0)),
        _g(("mouthSmileLeft", 1.0), ("mouthSmileRight", 1.0)),
    ],
    "にやり": [
        _g(("vroidMouthFun", 1.0)),
        _g(("Fcl_MTH_Fun", 1.0)),
        _g(("vroidMouthSmile", 1.0)),
        _g(("mouthSmileLeft", 1.0), ("mouthSmileRight", 1.0)),
    ],
    "怒り": [
        _g(("vroidBrowAngry", 1.0)),
        _g(("Fcl_BRW_Angry", 1.0)),
        _g(("vroidAllAngry", 1.0)),
        _g(("Fcl_ALL_Angry", 1.0)),
        _g(("browDownLeft", 1.0), ("browDownRight", 1.0)),
    ],
    "困る": [
        _g(("vroidBrowSorrow", 1.0)),
        _g(("Fcl_BRW_Sorrow", 1.0)),
        _g(("vroidAllSorrow", 1.0)),
        _g(
            ("browInnerUp", 1.0),
            ("browDownLeft", 0.4),
            ("browDownRight", 0.4),
        ),
    ],
    "にこり": [
        _g(("vroidBrowFun", 1.0)),
        _g(("Fcl_BRW_Fun", 1.0)),
        _g(("vroidBrowJoy", 1.0)),
        _g(("Fcl_BRW_Joy", 1.0)),
        _g(
            ("browOuterUpLeft", 0.5),
            ("browOuterUpRight", 0.5),
            ("mouthSmileLeft", 0.3),
            ("mouthSmileRight", 0.3),
        ),
    ],
    "真面目": [
        _g(("vroidBrowAngry", 0.5)),
        _g(("Fcl_BRW_Angry", 0.5)),
        _g(("browDownLeft", 0.6), ("browDownRight", 0.6)),
    ],
    "上": [
        _g(("browOuterUpLeft", 1.0), ("browOuterUpRight", 1.0)),
        _g(("browInnerUp", 1.0)),
    ],
    "下": [
        _g(("browDownLeft", 1.0), ("browDownRight", 1.0)),
    ],
    "びっくり": [
        _g(("vroidEyeSurprised", 1.0)),
        _g(("Fcl_EYE_Surprised", 1.0)),
        _g(("vroidBrowSurprised", 1.0)),
        _g(("Fcl_BRW_Surprised", 1.0)),
        _g(
            ("eyeWideLeft", 1.0),
            ("eyeWideRight", 1.0),
            ("browInnerUp", 0.8),
        ),
    ],
    "はぅ": [
        _g(("vroidEyeSpread", 1.0)),
        _g(("Fcl_EYE_Spread", 1.0)),
        _g(("eyeWideLeft", 0.7), ("eyeWideRight", 0.7)),
    ],
    "なごみ": [
        _g(("vroidEyeJoy", 0.5)),
        _g(("Fcl_EYE_Joy", 0.5)),
        _g(("eyeSquintLeft", 0.7), ("eyeSquintRight", 0.7)),
    ],
    "じと目": [
        _g(
            ("eyeSquintLeft", 0.8),
            ("eyeSquintRight", 0.8),
            ("browDownLeft", 0.3),
            ("browDownRight", 0.3),
        ),
    ],
    "なぬ！": [
        _g(("vroidEyeSurprised", 1.0), ("vroidBrowSurprised", 1.0)),
        _g(("Fcl_EYE_Surprised", 1.0), ("Fcl_BRW_Surprised", 1.0)),
        _g(
            ("eyeWideLeft", 1.0),
            ("eyeWideRight", 1.0),
            ("browInnerUp", 0.8),
            ("browOuterUpLeft", 0.5),
            ("browOuterUpRight", 0.5),
        ),
    ],
}

# Extended: only create when a real source exists; no invented proxies for
# decorative morphs that need hand sculpt.
EXTENDED_MAPPINGS: Dict[str, List[CandidateGroup]] = {
    "瞳小": [],  # typically custom / unmapped
    "瞳大": [],
    "▲": [],
    "∧": [],
    "ω": [],
    "ω□": [],
    "はんっ！": [],
    "えー": [
        _g(("vroidMouthE", 0.8)),
        _g(("Fcl_MTH_E", 0.8)),
        _g(
            ("jawOpen", 0.3),
            ("mouthStretchLeft", 0.5),
            ("mouthStretchRight", 0.5),
        ),
    ],
    "口角上げ": [
        _g(("mouthSmileLeft", 0.8), ("mouthSmileRight", 0.8)),
    ],
    "口角下げ": [
        _g(("mouthFrownLeft", 1.0), ("mouthFrownRight", 1.0)),
    ],
    "ぺろっ": [
        _g(("tongueOut", 1.0)),
    ],
    "頬染め": [
        _g(("cheekPuff", 0.5)),
    ],
    "青ざめ": [],
    "下まぶた上げ": [],
    "ハイライト消し": [
        _g(("vroidEyeHighlightHide", 1.0)),
        _g(("Fcl_EYE_Highlight_Hide", 1.0)),
    ],
    "はぁと": [],
    "星目": [],
    "はちゅ目": [],
    "恐ろしい子！": [],
    "睨み": [
        _g(("vroidEyeAngry", 1.0)),
        _g(("Fcl_EYE_Angry", 1.0)),
        _g(("browDownLeft", 0.8), ("browDownRight", 0.8)),
    ],
    "白目": [],
}


def _name_set(key_blocks: Iterable) -> set:
    return {kb.name for kb in key_blocks}


def _group_available(group: CandidateGroup, names: set) -> bool:
    return all(src in names for src, _w in group)


def resolve_sources(
    mmd_name: str,
    existing_names: Iterable[str],
    mappings: Optional[Dict[str, List[CandidateGroup]]] = None,
) -> Optional[List[Dict[str, Any]]]:
    """Return chosen [{source, weight}, ...] or None if no candidate group fits."""
    table = mappings if mappings is not None else CORE_MAPPINGS
    groups = table.get(mmd_name)
    if not groups:
        return None
    names = set(existing_names)
    for group in groups:
        if _group_available(group, names):
            return [{"source": s, "weight": float(w)} for s, w in group]
    return None


def mappings_for_scope(set_scope: str = "core") -> Dict[str, List[CandidateGroup]]:
    scope = (set_scope or "core").lower()
    if scope == "extended":
        out = dict(CORE_MAPPINGS)
        out.update(EXTENDED_MAPPINGS)
        return out
    if scope == "core":
        return dict(CORE_MAPPINGS)
    raise ValueError(f"unknown set_scope: {set_scope!r} (use 'core' or 'extended')")


def build_mmd_mapping(
    existing_names: Iterable[str],
    set_scope: str = "core",
    prefer: Sequence[str] = ("vroid", "fcl", "arkit"),
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Build mmd_name → source list for keys that can be created.

    `prefer` is documented for callers; resolution order is already
    VRoid → Fcl → ARKit inside each CORE_MAPPINGS entry.
    """
    _ = prefer  # order baked into candidate groups
    names = list(existing_names)
    name_set = set(names)
    table = mappings_for_scope(set_scope)
    planned: Dict[str, List[Dict[str, Any]]] = {}
    for mmd_name in table:
        if mmd_name in name_set:
            continue
        resolved = resolve_sources(mmd_name, names, mappings=table)
        if resolved:
            planned[mmd_name] = resolved
    return planned


def dry_run_mmd_mapping(
    existing_names: Iterable[str],
    set_scope: str = "core",
) -> dict:
    names = list(existing_names)
    name_set = set(names)
    table = mappings_for_scope(set_scope)

    exists: List[str] = []
    will_create: Dict[str, List[Dict[str, Any]]] = {}
    missing_sources: List[str] = []
    empty_extended: List[str] = []

    for mmd_name, groups in table.items():
        if mmd_name in name_set:
            exists.append(mmd_name)
            continue
        if not groups:
            empty_extended.append(mmd_name)
            continue
        resolved = resolve_sources(mmd_name, names, mappings=table)
        if resolved:
            will_create[mmd_name] = resolved
        else:
            missing_sources.append(mmd_name)

    return {
        "set_scope": set_scope,
        "existing_mmd_count": len(exists),
        "existing_mmd": sorted(exists),
        "will_create_count": len(will_create),
        "will_create": {
            k: will_create[k] for k in sorted(will_create.keys())
        },
        "missing_sources_count": len(missing_sources),
        "missing_sources": sorted(missing_sources),
        "unmapped_no_candidates": sorted(empty_extended),
        "preview": [
            {"mmd": k, "sources": will_create[k]}
            for k in sorted(will_create.keys())
        ],
    }


def classify_shape_keys(existing_names: Iterable[str]) -> dict:
    arkit = []
    vroid = []
    fcl = []
    mmd = []
    other = []
    core_names = set(CORE_MAPPINGS)
    extended_names = set(EXTENDED_MAPPINGS)
    mmd_all = core_names | extended_names

    for name in existing_names:
        if name == "Basis":
            continue
        if name.startswith("Fcl_"):
            fcl.append(name)
        elif name.startswith("vroid"):
            vroid.append(name)
        elif name in mmd_all:
            mmd.append(name)
        elif name[:1].islower() and any(
            name.startswith(p)
            for p in (
                "brow",
                "eye",
                "jaw",
                "mouth",
                "cheek",
                "nose",
                "tongue",
            )
        ):
            arkit.append(name)
        else:
            other.append(name)

    return {
        "arkit": sorted(arkit),
        "vroid": sorted(vroid),
        "fcl": sorted(fcl),
        "mmd": sorted(mmd),
        "other": sorted(other),
        "counts": {
            "arkit": len(arkit),
            "vroid": len(vroid),
            "fcl": len(fcl),
            "mmd": len(mmd),
            "other": len(other),
        },
    }


def _get_mesh_object(object_name: str) -> Tuple[Optional[bpy.types.Object], Optional[str]]:
    obj = bpy.data.objects.get(object_name)
    if not obj:
        return None, f'object not found: "{object_name}"'
    if obj.type != "MESH":
        return None, f'object "{object_name}" is not a mesh'
    if not obj.data or not obj.data.shape_keys:
        return None, f'object "{object_name}" has no shape keys'
    return obj, None


def _zero_all_shape_keys(shape_keys) -> Dict[str, float]:
    saved: Dict[str, float] = {}
    for kb in shape_keys.key_blocks:
        saved[kb.name] = kb.value
        kb.value = 0.0
    return saved


def _bake_mmd_key_from_mix(
    obj: bpy.types.Object,
    mmd_name: str,
    sources: List[Dict[str, Any]],
) -> dict:
    """Bake one MMD key from mix. Caller must ensure name does not exist."""
    shape_keys = obj.data.shape_keys
    blocks = shape_keys.key_blocks
    source_names = {s["source"] for s in sources}

    if mmd_name in blocks:
        return {"mmd": mmd_name, "status": "skipped_exists"}

    for spec in sources:
        if spec["source"] not in blocks:
            return {
                "mmd": mmd_name,
                "status": "error",
                "error": f'missing source "{spec["source"]}"',
            }

    saved = _zero_all_shape_keys(shape_keys)
    try:
        for spec in sources:
            blocks[spec["source"]].value = float(spec["weight"])

        obj.shape_key_add(name=mmd_name, from_mix=True)
        new_kb = blocks.get(mmd_name)
        if new_kb is None or new_kb.name != mmd_name:
            if new_kb is not None:
                obj.shape_key_remove(new_kb)
            return {
                "mmd": mmd_name,
                "status": "error",
                "error": f"name collision creating {mmd_name!r}",
            }
        new_kb.value = 0.0
    finally:
        # Restore prior values; leave baked MMD + used sources at 0
        for name, val in saved.items():
            if name not in blocks:
                continue
            if name in source_names:
                blocks[name].value = 0.0
            else:
                blocks[name].value = val
        if mmd_name in blocks:
            blocks[mmd_name].value = 0.0

    return {
        "mmd": mmd_name,
        "status": "created",
        "sources": sources,
    }


def store_scene_mmd_map(mapping: Dict[str, List[Dict[str, Any]]]) -> None:
    scene = bpy.context.scene
    # Blender ID properties need JSON-friendly plain dicts
    payload = {
        mmd: [{"source": s["source"], "weight": float(s["weight"])} for s in srcs]
        for mmd, srcs in mapping.items()
    }
    scene[SCENE_MAP_KEY] = payload


def create_mmd_shape_keys(
    object_name: str = DEFAULT_OBJECT,
    dry_run: bool = True,
    set_scope: str = "core",
    prefer: Sequence[str] = ("vroid", "fcl", "arkit"),
) -> dict:
    """
    Dry-run or create MMD shape keys on a mesh.

    Hard guarantee: does not rename/delete ARKit, vroid*, or Fcl_* keys.
    """
    obj, err = _get_mesh_object(object_name)
    if err:
        return {"error": err, "object": object_name, "dry_run": dry_run}

    names = [kb.name for kb in obj.data.shape_keys.key_blocks]
    classification = classify_shape_keys(names)
    report = dry_run_mmd_mapping(names, set_scope=set_scope)
    planned = build_mmd_mapping(names, set_scope=set_scope, prefer=prefer)

    result = {
        "object": object_name,
        "dry_run": dry_run,
        "set_scope": set_scope,
        "classification": classification,
        "report": report,
        "planned_count": len(planned),
        "created": [],
        "skipped": [],
        "errors": [],
        "sources_untouched": True,
        "scene_map_key": SCENE_MAP_KEY,
    }

    if dry_run:
        result["message"] = (
            f"Dry-run: would create {len(planned)} MMD keys on {object_name!r}; "
            "ARKit/VRoid sources unchanged."
        )
        return result

    # Apply
    applied_map: Dict[str, List[Dict[str, Any]]] = {}
    # Snapshot source names before any create
    protected = set(classification["arkit"]) | set(classification["vroid"]) | set(
        classification["fcl"]
    )
    names_before = set(names)

    for mmd_name, sources in sorted(planned.items()):
        # Re-check existence each iteration
        if mmd_name in obj.data.shape_keys.key_blocks:
            result["skipped"].append({"mmd": mmd_name, "reason": "already_exists"})
            continue
        bake = _bake_mmd_key_from_mix(obj, mmd_name, sources)
        if bake.get("status") == "created":
            result["created"].append(bake)
            applied_map[mmd_name] = sources
        elif bake.get("status") == "skipped_exists":
            result["skipped"].append(bake)
        else:
            result["errors"].append(bake)

    # Verify protected sources still present with same names
    names_after = {kb.name for kb in obj.data.shape_keys.key_blocks}
    missing_protected = sorted(protected - names_after)
    if missing_protected:
        result["sources_untouched"] = False
        result["errors"].append(
            {
                "status": "integrity_error",
                "missing_protected_keys": missing_protected,
            }
        )

    # Merge with any prior scene map
    prior = dict(bpy.context.scene.get(SCENE_MAP_KEY, {}))
    prior.update(applied_map)
    store_scene_mmd_map(prior)

    result["created_count"] = len(result["created"])
    result["names_added"] = sorted(names_after - names_before)
    result["message"] = (
        f"Created {result['created_count']} MMD keys on {object_name!r}; "
        "ARKit/VRoid sources preserved."
    )
    return result


def audit_object_mmd_keys(
    object_name: str = DEFAULT_OBJECT,
    set_scope: str = "core",
) -> dict:
    obj, err = _get_mesh_object(object_name)
    if err:
        return {"error": err}
    names = [kb.name for kb in obj.data.shape_keys.key_blocks]
    return {
        "object": object_name,
        "classification": classify_shape_keys(names),
        "dry_run": dry_run_mmd_mapping(names, set_scope=set_scope),
        "scene_map": dict(bpy.context.scene.get(SCENE_MAP_KEY, {})),
    }
