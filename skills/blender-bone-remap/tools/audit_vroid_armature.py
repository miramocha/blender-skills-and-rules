"""
Audit VRoid/VRM armature bone prefixes and mesh vertex groups.
Run inside Blender (bpy) via MCP execute_blender_code.

    report = audit_vroid_armature("Armature")
    vgs = scan_mesh_vertex_groups(armature_object_name="Armature")
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Dict, Iterable, List, Optional

import bpy

J_SUBPREFIXES = ("J_Bip_", "J_Sec_", "J_Adj_", "J_Opt_")


def _bone_side_token(name: str) -> str:
    if "_L_" in name or name.endswith("_L"):
        return "_L"
    if "_R_" in name or name.endswith("_R"):
        return "_R"
    if "_C_" in name:
        return "_C"
    return "none"


def _j_sec_category(name: str) -> Optional[str]:
    if not name.startswith("J_Sec_"):
        return None
    rest = name[6:]
    if rest.startswith(("L_", "R_", "C_")):
        rest = rest[2:]
    return rest.split("_")[0] if rest else None


def _bust_vertex_weights(mesh_obj: bpy.types.Object, bust_names: Iterable[str]) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    for vg_name in bust_names:
        vg = mesh_obj.vertex_groups.get(vg_name)
        if not vg:
            continue
        weighted_verts = 0
        weight_sum = 0.0
        for v in mesh_obj.data.vertices:
            for g in v.groups:
                if g.group == vg.index and g.weight > 0.0001:
                    weighted_verts += 1
                    weight_sum += g.weight
        if weighted_verts:
            out[vg_name] = {
                "weighted_verts": weighted_verts,
                "weight_sum": round(weight_sum, 4),
            }
    return out


def audit_vroid_armature(armature_object_name: str = "Armature") -> dict:
    arm = bpy.data.objects.get(armature_object_name)
    if not arm or arm.type != "ARMATURE":
        return {"error": f"armature not found: {armature_object_name}"}

    bones = [b.name for b in arm.data.bones]
    subprefix = Counter()
    side = Counter()
    for name in bones:
        if name == "Root":
            subprefix["Root"] += 1
        elif name.startswith("J_Bip_"):
            subprefix["J_Bip_"] += 1
        elif name.startswith("J_Sec_"):
            subprefix["J_Sec_"] += 1
        elif name.startswith("J_Adj_"):
            subprefix["J_Adj_"] += 1
        elif name.startswith("J_Opt_"):
            subprefix["J_Opt_"] += 1
        elif name.startswith("J_"):
            subprefix["J_other"] += 1
        else:
            subprefix["non-J"] += 1
        side[_bone_side_token(name)] += 1

    categories = {
        "bust": [n for n in bones if "Bust" in n or "bust" in n],
        "hair": [n for n in bones if re.search(r"Hair", n, re.I)],
        "skirt": [n for n in bones if "Skirt" in n],
        "hood": [n for n in bones if "Hood" in n],
        "j_opt": [n for n in bones if n.startswith("J_Opt_")],
        "cat_tail": [n for n in bones if "CatTail" in n or "cattail" in n.lower()],
    }

    sec_cat = Counter()
    for n in bones:
        cat = _j_sec_category(n)
        if cat:
            sec_cat[cat] += 1

    bust_names = categories["bust"]
    bust_weights: Dict[str, dict] = {}
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        found = _bust_vertex_weights(obj, bust_names)
        for k, v in found.items():
            bust_weights[f"{obj.name}/{k}"] = v

    return {
        "armature_object": arm.name,
        "bone_count": len(bones),
        "has_j_prefix": any(n.startswith("J_") for n in bones),
        "subprefix_counts": dict(subprefix),
        "side_token_counts": dict(side),
        "j_sec_categories": dict(sec_cat.most_common()),
        "categories": {k: {"count": len(v), "sample": v[:8]} for k, v in categories.items() if v},
        "bust_vertex_weights": bust_weights or None,
        "gender_from_prefix": None,
        "gender_note": "VRoid uses same J_* skeleton for male/female; do not infer gender from prefix or Bust* alone.",
        "sample_bones": bones[:25],
    }


def scan_mesh_vertex_groups(
    armature_object_name: Optional[str] = None,
    name_patterns: Optional[List[str]] = None,
) -> dict:
    """
    List vertex groups on meshes bound to an armature.
    name_patterns: optional substrings (e.g. ['Hair', 'hair', 'Bust']).
    """
    patterns = name_patterns or ["Hair", "hair", "Bust", "bust"]
    meshes: List[dict] = []

    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        arm = obj.find_armature()
        if armature_object_name and (not arm or arm.name != armature_object_name):
            continue
        if not arm and armature_object_name:
            continue

        bone_named: List[str] = []
        stale: List[str] = []
        for vg in obj.vertex_groups:
            if any(p in vg.name for p in patterns):
                bone_named.append(vg.name)
            if vg.name.startswith("J_") or re.match(r"^Hair\d+_", vg.name):
                stale.append(vg.name)

        weighted = 0
        for v in obj.data.vertices:
            if v.groups:
                weighted += 1

        meshes.append(
            {
                "object": obj.name,
                "armature": arm.name if arm else None,
                "vertex_group_count": len(obj.vertex_groups),
                "verts_with_weights": weighted,
                "matching_groups": sorted(bone_named),
                "possibly_stale_groups": sorted(stale)[:20],
            }
        )

    return {
        "armature_filter": armature_object_name,
        "patterns": patterns,
        "meshes": meshes,
    }
