"""
Assign armature bones to Hair / Body / Clothing bone collections.

Run via MCP execute_blender_code or Blender Scripting workspace:

    result = audit_bone_collections(armature_object_name="Armature")
    result = apply_bone_collections(armature_object_name="Armature", dry_run=False)
"""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Set

import bpy

COLLECTION_HAIR = "Hair"
COLLECTION_BODY = "Body"
COLLECTION_CLOTHING = "Clothing"
DEFAULT_COLLECTIONS = (COLLECTION_HAIR, COLLECTION_BODY, COLLECTION_CLOTHING)

# Post-remap and VRoid hair bone names.
RE_HAIR = re.compile(
    r"^(hair|Hair|J_Sec_Hair)",
    re.I,
)

# Accessory / garment rig bones (not humanoid body).
RE_CLOTHING = re.compile(
    r"^(hood(\.|String|$)|hoodString|J_Sec_.*(Hood|Coat|Skirt|Pants|Shoe|Cloth|Accessory))",
    re.I,
)

# Humanoid / anatomy — always body even if name is ambiguous.
RE_BODY_FORCE = re.compile(
    r"^(root|J_Bip_|hips|spine|chest|upperChest|neck|head|"
    r"upperLeg|lowerLeg|foot|toeBase|shoulder|upperArm|lowerArm|hand|"
    r"thumb|index|middle|ring|little|faceEye|bust|J_Adj_)",
    re.I,
)

HAIR_MESH_HINTS = ("hair", "twintail")
CLOTH_MESH_HINTS = ("cloth", "shoe", "top", "skirt", "pants", "jacket", "coat")


def _mesh_category_hints(armature_object_name: str) -> Dict[str, Set[str]]:
    """Map mesh object name substrings to hair/cloth hints for weight-based classify."""
    hair_meshes: Set[str] = set()
    cloth_meshes: Set[str] = set()
    body_meshes: Set[str] = set()

    arm_obj = bpy.data.objects.get(armature_object_name)
    if not arm_obj:
        return {"hair": hair_meshes, "cloth": cloth_meshes, "body": body_meshes}

    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        parent = obj.parent
        if parent != arm_obj and parent != arm_obj.parent:
            continue
        name_l = obj.name.lower()
        if any(h in name_l for h in HAIR_MESH_HINTS):
            hair_meshes.add(obj.name)
        elif any(h in name_l for h in CLOTH_MESH_HINTS):
            cloth_meshes.add(obj.name)
        elif name_l in ("body", "face") or "skin" in name_l:
            body_meshes.add(obj.name)

    return {"hair": hair_meshes, "cloth": cloth_meshes, "body": body_meshes}


def _rigged_mesh_objects(armature_object_name: str) -> List[bpy.types.Object]:
    arm_obj = bpy.data.objects.get(armature_object_name)
    if not arm_obj:
        return []

    meshes: List[bpy.types.Object] = []
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        parent = obj.parent
        if parent == arm_obj or parent == arm_obj.parent:
            meshes.append(obj)
    return meshes


def _build_bone_weighted_mesh_index(armature_object_name: str) -> Dict[str, Set[str]]:
    """Single pass: bone name -> mesh objects with weight > 0 on that bone."""
    arm_obj = bpy.data.objects.get(armature_object_name)
    if not arm_obj:
        return {}

    valid_bones = {bone.name for bone in arm_obj.data.bones}
    index: Dict[str, Set[str]] = {}

    for obj in _rigged_mesh_objects(armature_object_name):
        vg_to_bone: Dict[int, str] = {}
        for vg in obj.vertex_groups:
            if vg.name in valid_bones:
                vg_to_bone[vg.index] = vg.name
        if not vg_to_bone:
            continue

        for vert in obj.data.vertices:
            for group in vert.groups:
                if group.weight <= 0.0001:
                    continue
                bone_name = vg_to_bone.get(group.group)
                if bone_name is None:
                    continue
                index.setdefault(bone_name, set()).add(obj.name)

    return index


def _bone_weighted_meshes(
    armature_object_name: str,
    bone_name: str,
    *,
    weighted_mesh_index: Optional[Dict[str, Set[str]]] = None,
) -> Set[str]:
    if weighted_mesh_index is not None:
        return set(weighted_mesh_index.get(bone_name, set()))

    return set(_build_bone_weighted_mesh_index(armature_object_name).get(bone_name, set()))


def classify_bone(
    bone_name: str,
    *,
    armature_object_name: str = "Armature",
    mesh_hints: Optional[Dict[str, Set[str]]] = None,
    weighted_mesh_index: Optional[Dict[str, Set[str]]] = None,
) -> str:
    if RE_BODY_FORCE.match(bone_name):
        return COLLECTION_BODY
    if RE_HAIR.match(bone_name):
        return COLLECTION_HAIR
    if RE_CLOTHING.match(bone_name):
        return COLLECTION_CLOTHING

    hints = mesh_hints or _mesh_category_hints(armature_object_name)
    weighted = _bone_weighted_meshes(
        armature_object_name,
        bone_name,
        weighted_mesh_index=weighted_mesh_index,
    )
    if weighted:
        hair_meshes = hints.get("hair", set())
        cloth_meshes = hints.get("cloth", set())
        if weighted & hair_meshes and not (weighted - hair_meshes):
            return COLLECTION_HAIR
        if weighted & cloth_meshes and not (weighted - cloth_meshes):
            return COLLECTION_CLOTHING

    return COLLECTION_BODY


def _planned_assignments(
    armature_object_name: str,
    collection_names: Iterable[str] = DEFAULT_COLLECTIONS,
) -> Dict[str, List[str]]:
    arm = bpy.data.objects.get(armature_object_name)
    if not arm or arm.type != "ARMATURE":
        return {}

    hints = _mesh_category_hints(armature_object_name)
    weighted_mesh_index = _build_bone_weighted_mesh_index(armature_object_name)
    plan: Dict[str, List[str]] = {name: [] for name in collection_names}

    for bone in arm.data.bones:
        category = classify_bone(
            bone.name,
            armature_object_name=armature_object_name,
            mesh_hints=hints,
            weighted_mesh_index=weighted_mesh_index,
        )
        if category not in plan:
            plan[category] = []
        plan[category].append(bone.name)

    for key in plan:
        plan[key].sort()
    return plan


def audit_bone_collections(
    armature_object_name: str = "Armature",
    collection_names: Iterable[str] = DEFAULT_COLLECTIONS,
) -> dict:
    arm = bpy.data.objects.get(armature_object_name)
    if not arm or arm.type != "ARMATURE":
        return {"error": f"armature not found: {armature_object_name}"}

    names = tuple(collection_names)
    planned = _planned_assignments(armature_object_name, names)

    current: Dict[str, List[str]] = {name: [] for name in names}
    for bc in arm.data.collections:
        if bc.name in current:
            current[bc.name] = sorted(b.name for b in bc.bones)

    mismatches: List[dict] = []
    for category, bones in planned.items():
        planned_set = set(bones)
        current_set = set(current.get(category, []))
        wrong_here = sorted(current_set - planned_set)
        missing_here = sorted(planned_set - current_set)
        if wrong_here or missing_here:
            mismatches.append(
                {
                    "collection": category,
                    "missing": missing_here[:15],
                    "missing_count": len(missing_here),
                    "wrong": wrong_here[:15],
                    "wrong_count": len(wrong_here),
                }
            )

    unassigned = []
    assigned_names: Set[str] = set()
    for bc in arm.data.collections:
        if bc.name in names:
            assigned_names.update(b.name for b in bc.bones)
    for bone in arm.data.bones:
        if bone.name not in assigned_names:
            unassigned.append(bone.name)

    return {
        "phase": "bone-collections-audit",
        "dry_run": True,
        "armature": armature_object_name,
        "collections": names,
        "planned": {k: {"count": len(v), "bones": v[:20]} for k, v in planned.items()},
        "current": {k: {"count": len(v)} for k, v in current.items()},
        "mismatches": mismatches,
        "unassigned_bone_count": len(unassigned),
        "unassigned_sample": unassigned[:15],
        "needs_apply": bool(mismatches or unassigned),
    }


def apply_bone_collections(
    armature_object_name: str = "Armature",
    collection_names: Iterable[str] = DEFAULT_COLLECTIONS,
    dry_run: bool = True,
) -> dict:
    audit = audit_bone_collections(
        armature_object_name=armature_object_name,
        collection_names=collection_names,
    )
    if audit.get("error"):
        return audit
    if dry_run:
        return audit

    arm = bpy.data.objects[armature_object_name]
    arm_data = arm.data
    names = tuple(collection_names)
    planned = _planned_assignments(armature_object_name, names)

    collections = {}
    for name in names:
        bc = arm_data.collections.get(name)
        if bc is None:
            bc = arm_data.collections.new(name)
        collections[name] = bc

    # Unassign target bones from every managed collection first.
    all_target_bones = {b for bones in planned.values() for b in bones}
    for bc in arm_data.collections:
        if bc.name not in names:
            continue
        for bone in list(bc.bones):
            if bone.name in all_target_bones:
                bc.unassign(bone)

    assigned: Dict[str, int] = {}
    for category, bones in planned.items():
        bc = collections[category]
        count = 0
        for bone_name in bones:
            bone = arm_data.bones.get(bone_name)
            if bone:
                bc.assign(bone)
                count += 1
        assigned[category] = count

    verify = audit_bone_collections(
        armature_object_name=armature_object_name,
        collection_names=collection_names,
    )

    return {
        **audit,
        "phase": "bone-collections-apply",
        "dry_run": False,
        "assigned": assigned,
        "remaining_mismatches": verify.get("mismatches", []),
        "remaining_unassigned": verify.get("unassigned_bone_count", 0),
    }


def run_phase_k(
    armature_object_name: str = "Armature",
    *,
    dry_run: bool = True,
    collection_names: Iterable[str] = DEFAULT_COLLECTIONS,
) -> dict:
    """Pipeline Phase K — assign bones to Hair / Body / Clothing collections."""
    if dry_run:
        result = audit_bone_collections(
            armature_object_name=armature_object_name,
            collection_names=collection_names,
        )
    else:
        result = apply_bone_collections(
            armature_object_name=armature_object_name,
            collection_names=collection_names,
            dry_run=False,
        )
    result["phase"] = "K"
    result["phase_letter"] = "K"
    return result


if __name__ == "__main__":
    result = audit_bone_collections()
