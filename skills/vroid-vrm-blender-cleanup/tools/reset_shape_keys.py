"""
Reset all shape key values to 0 on a mesh object by object or mesh data name.

Run only after Phase D (ARKit transfer) was applied successfully.
Run via MCP execute_blender_code or Blender Scripting workspace.

    report = reset_shape_keys("Face", dry_run=True)
    result = run_phase_e(mesh_name="Face", phase_d_result=phase_d_result)
"""

from __future__ import annotations

from typing import Optional

import bpy

DRY_RUN = True
DEFAULT_MESH_NAME = "Face"


def find_mesh_object(name: str) -> Optional[bpy.types.Object]:
    obj = bpy.data.objects.get(name)
    if obj and obj.type == "MESH":
        return obj

    for candidate in bpy.data.objects:
        if candidate.type == "MESH" and candidate.data and candidate.data.name == name:
            return candidate

    return None


def reset_shape_keys(mesh_name: str = DEFAULT_MESH_NAME, dry_run: bool = DRY_RUN) -> dict:
    obj = find_mesh_object(mesh_name)
    if obj is None:
        return {
            "phase": "E",
            "error": f'No mesh object found with object or mesh data name "{mesh_name}"',
        }

    shape_keys = obj.data.shape_keys
    if shape_keys is None:
        return {
            "phase": "E",
            "error": f'Object "{obj.name}" has no shape keys',
        }

    key_names = [kb.name for kb in shape_keys.key_blocks]
    count = len(key_names)

    if not dry_run:
        for key_block in shape_keys.key_blocks:
            key_block.value = 0.0

    return {
        "phase": "E",
        "dry_run": dry_run,
        "object_name": obj.name,
        "mesh_data_name": obj.data.name,
        "shape_key_count": count,
        "shape_keys": key_names,
    }


def run_phase_e(
    mesh_name: str = DEFAULT_MESH_NAME,
    dry_run: bool = DRY_RUN,
    phase_d_result: Optional[dict] = None,
) -> dict:
    if phase_d_result is not None and not phase_d_result.get("applied"):
        return {
            "phase": "E",
            "skipped": True,
            "reason": "phase_d_not_applied",
            "message": (
                "Phase E skipped: reset shape keys only runs after Phase D ARKit transfer."
            ),
        }
    return reset_shape_keys(mesh_name=mesh_name, dry_run=dry_run)


if __name__ == "__main__":
    result = run_phase_e(mesh_name=DEFAULT_MESH_NAME, dry_run=DRY_RUN)
