"""
Phase A — VRM Add-on humanoid bone rename.
Run via MCP execute_blender_code or Blender Scripting workspace.

    result = run_phase_a(armature_object_name="Armature", dry_run=True)
    result = run_phase_a(armature_object_name="Armature", dry_run=False)
"""

from __future__ import annotations

from typing import List

import bpy

DRY_RUN = True


def run_phase_a(
    armature_object_name: str = "Armature",
    dry_run: bool = DRY_RUN,
) -> dict:
    arm = bpy.data.objects.get(armature_object_name)
    if not arm or arm.type != "ARMATURE":
        return {
            "phase": "A",
            "error": f"armature object not found: {armature_object_name}",
            "applied": False,
        }

    if not hasattr(bpy.ops.vrm, "bones_rename"):
        return {
            "phase": "A",
            "error": "bpy.ops.vrm.bones_rename not available — enable VRM Add-on for Blender.",
            "applied": False,
        }

    before = [b.name for b in arm.data.bones]

    if dry_run:
        return {
            "phase": "A",
            "dry_run": True,
            "armature_object": armature_object_name,
            "bone_count": len(before),
            "sample_bones_before": before[:20],
            "message": f"Would run bpy.ops.vrm.bones_rename(armature_object_name={armature_object_name!r})",
        }

    op_result = bpy.ops.vrm.bones_rename(armature_object_name=armature_object_name)
    applied = op_result == {"FINISHED"}
    after = [b.name for b in arm.data.bones]

    renamed: List[dict] = []
    for old, new in zip(before, after):
        if old != new:
            renamed.append({"old": old, "new": new})

    return {
        "phase": "A",
        "dry_run": False,
        "applied": applied,
        "operator_result": list(op_result) if op_result is not None else None,
        "armature_object": armature_object_name,
        "bone_count": len(after),
        "renamed_count": len(renamed),
        "renamed_sample": renamed[:30],
        "sample_bones_after": after[:20],
    }

