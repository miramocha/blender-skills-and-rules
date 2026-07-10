"""
Rename VRM spring-bone collider Empty objects and sync VRM1 metadata strings.

After bone remap (J_Bip_* -> lowercase), collider helper Empties and
spring_bone1.collider_display_name still use old J_Bip object names.
Run via MCP execute_blender_code or Blender Scripting workspace.

    audit = audit_vrm_colliders(armature_object_name="Armature", bone_mapping=mapping)
    result = apply_vrm_collider_renames(armature_object_name="Armature", bone_mapping=mapping)
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

import bpy

RE_COLLIDER_OBJECT = re.compile(
    r"^(J_Bip_(?:C|L|R)_[A-Za-z0-9]+)_collider_(\d+)(?:\.(\d+))?$"
)
# VRoid import: "J_Bip_C_Head Collider", "J_Bip_L_UpperArm Collider.001", …
RE_COLLIDER_VROID = re.compile(
    r"^(J_Bip_(?:C|L|R)_[A-Za-z0-9]+) Collider(?:\.(\d{3}))?$"
)

# VRoid humanoid colliders after Phase 0 bones_rename (J_Bip_* -> PascalCase) then bone remap.
DEFAULT_J_BIP_TO_BONE: Dict[str, str] = {
    "J_Bip_C_Head": "head",
    "J_Bip_C_Neck": "neck",
    "J_Bip_C_Spine": "spine",
    "J_Bip_C_UpperChest": "upperChest",
    "J_Bip_L_Hand": "hand.l",
    "J_Bip_L_LowerArm": "lowerArm.l",
    "J_Bip_L_UpperArm": "upperArm.l",
    "J_Bip_R_Hand": "hand.r",
    "J_Bip_R_LowerArm": "lowerArm.r",
    "J_Bip_R_UpperArm": "upperArm.r",
}


def convert_collider_object_name(
    old_name: str,
    bone_mapping: Optional[Dict[str, str]] = None,
) -> Optional[str]:
    cmap = bone_mapping or DEFAULT_J_BIP_TO_BONE

    m = RE_COLLIDER_OBJECT.match(old_name)
    if m:
        old_bone, idx, dup = m.group(1), m.group(2), m.group(3)
        new_bone = cmap.get(old_bone)
        if not new_bone:
            return None
        suffix = f".{dup}" if dup else ""
        return f"{new_bone}.collider.{idx}{suffix}"

    m = RE_COLLIDER_VROID.match(old_name)
    if m:
        old_bone, dup = m.group(1), m.group(2)
        new_bone = cmap.get(old_bone)
        if not new_bone:
            return None
        idx = str(int(dup)) if dup else "0"
        return f"{new_bone}.collider.{idx}"

    return None


def _is_collider_object_name(name: str) -> bool:
    return "_collider_" in name or RE_COLLIDER_VROID.match(name) is not None


def _armature_vrm_extension(armature_object_name: str):
    arm = bpy.data.objects.get(armature_object_name)
    if not arm or arm.type != "ARMATURE":
        return None, {"error": f"armature not found: {armature_object_name}"}
    ext = getattr(arm.data, "vrm_addon_extension", None)
    if not ext:
        return None, {"error": "no vrm_addon_extension on armature"}
    return ext, None


def _unique_object_name(desired: str, obj: bpy.types.Object) -> str:
    if desired == obj.name:
        return desired
    existing = bpy.data.objects.get(desired)
    if existing is None or existing == obj:
        return desired
    i = 1
    while True:
        candidate = f"{desired}.{i:03d}"
        other = bpy.data.objects.get(candidate)
        if other is None or other == obj:
            return candidate
        i += 1


def _remap_vrm_name_prefix(old_vrm_name: str, bone_mapping: Dict[str, str]) -> Optional[str]:
    if not old_vrm_name:
        return None
    if "-" in old_vrm_name:
        prefix, suffix = old_vrm_name.split("-", 1)
        new_bone = bone_mapping.get(prefix)
        if not new_bone:
            return None
        new_name = f"{new_bone}-{suffix}"
        return new_name if new_name != old_vrm_name else None
    new_bone = bone_mapping.get(old_vrm_name)
    if not new_bone:
        return None
    return new_bone if new_bone != old_vrm_name else None


def audit_vrm_colliders(
    armature_object_name: str = "Armature",
    bone_mapping: Optional[Dict[str, str]] = None,
) -> dict:
    cmap = bone_mapping or DEFAULT_J_BIP_TO_BONE
    ext, err = _armature_vrm_extension(armature_object_name)
    if err:
        return err

    object_plans: List[dict] = []
    for obj in bpy.data.objects:
        if not _is_collider_object_name(obj.name):
            continue
        new_name = convert_collider_object_name(obj.name, cmap)
        if new_name and new_name != obj.name:
            object_plans.append({"old": obj.name, "new": new_name, "type": "object"})

    metadata_plans: List[dict] = []
    sb1 = ext.spring_bone1
    for gi, group in enumerate(sb1.collider_groups):
        for ci, collider in enumerate(group.colliders):
            display = getattr(collider, "collider_display_name", "") or ""
            new_display = convert_collider_object_name(display, cmap)
            if new_display and new_display != display:
                metadata_plans.append(
                    {
                        "where": f"collider_groups[{gi}].colliders[{ci}].collider_display_name",
                        "old": display,
                        "new": new_display,
                        "type": "collider_display_name",
                    }
                )
        vrm_name = getattr(group, "vrm_name", "") or ""
        new_vrm_name = _remap_vrm_name_prefix(vrm_name, cmap)
        if new_vrm_name:
            metadata_plans.append(
                {
                    "where": f"collider_groups[{gi}].vrm_name",
                    "old": vrm_name,
                    "new": new_vrm_name,
                    "type": "vrm_name",
                }
            )

    return {
        "phase": "collider-audit",
        "armature": armature_object_name,
        "object_plans": object_plans,
        "metadata_plans": metadata_plans,
        "object_count": len(object_plans),
        "metadata_count": len(metadata_plans),
    }


def apply_vrm_collider_renames(
    armature_object_name: str = "Armature",
    bone_mapping: Optional[Dict[str, str]] = None,
    dry_run: bool = False,
) -> dict:
    audit = audit_vrm_colliders(
        armature_object_name=armature_object_name,
        bone_mapping=bone_mapping,
    )
    if audit.get("error"):
        return audit
    if dry_run:
        return audit

    cmap = bone_mapping or DEFAULT_J_BIP_TO_BONE
    ext, err = _armature_vrm_extension(armature_object_name)
    if err:
        return err

    renamed_objects: List[Tuple[str, str]] = []
    name_lookup = {p["old"]: p["new"] for p in audit["object_plans"]}

    # Pass 1: temp names to avoid collisions
    for old, new in name_lookup.items():
        obj = bpy.data.objects.get(old)
        if obj:
            obj.name = f"__tmp_collider__{old}"

    for old, new in name_lookup.items():
        tmp = f"__tmp_collider__{old}"
        obj = bpy.data.objects.get(tmp)
        if obj:
            final = _unique_object_name(new, obj)
            obj.name = final
            renamed_objects.append((old, final))
            name_lookup[old] = final

    renamed_metadata: List[dict] = []
    sb1 = ext.spring_bone1
    for gi, group in enumerate(sb1.collider_groups):
        for ci, collider in enumerate(group.colliders):
            display = collider.collider_display_name or ""
            if display in name_lookup:
                new_display = name_lookup[display]
                collider.collider_display_name = new_display
                renamed_metadata.append(
                    {
                        "where": f"collider_groups[{gi}].colliders[{ci}].collider_display_name",
                        "old": display,
                        "new": new_display,
                    }
                )
            else:
                new_display = convert_collider_object_name(display, cmap)
                if new_display and new_display != display:
                    collider.collider_display_name = new_display
                    renamed_metadata.append(
                        {
                            "where": f"collider_groups[{gi}].colliders[{ci}].collider_display_name",
                            "old": display,
                            "new": new_display,
                        }
                    )

        vrm_name = group.vrm_name or ""
        new_vrm_name = _remap_vrm_name_prefix(vrm_name, cmap)
        if new_vrm_name:
            group.vrm_name = new_vrm_name
            renamed_metadata.append(
                {
                    "where": f"collider_groups[{gi}].vrm_name",
                    "old": vrm_name,
                    "new": new_vrm_name,
                }
            )

    verify = audit_vrm_colliders(
        armature_object_name=armature_object_name,
        bone_mapping=bone_mapping,
    )

    return {
        **audit,
        "phase": "collider-apply",
        "renamed_objects": renamed_objects,
        "renamed_object_count": len(renamed_objects),
        "renamed_metadata": renamed_metadata,
        "renamed_metadata_count": len(renamed_metadata),
        "remaining_object_plans": verify.get("object_count", 0),
        "remaining_metadata_plans": verify.get("metadata_count", 0),
    }


if __name__ == "__main__":
    result = audit_vrm_colliders()
