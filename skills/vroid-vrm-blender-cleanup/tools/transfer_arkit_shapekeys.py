"""
Transfer ARKit shape keys onto a VRoid Face mesh (Beyond Expressions).

Requires user-declared body type (male/female) and a ready Beyond addon.
Phase C (reset shape keys) should only run after this phase is applied.

Run via MCP execute_blender_code or Blender Scripting workspace.
Exec check_beyond_expressions.py first, or rely on the built-in check below.

    result = run_phase_d(body_type="female", face_mesh_name="Face", dry_run=True)
"""

from __future__ import annotations

from typing import Literal, Optional

import bpy

BodyType = Literal["male", "female"]

BODY_TYPE_TO_SOURCE = {
    "female": "VROID_Female_Face",
    "male": "VROID_Male_Face",
}

DEFAULT_FACE_MESH_NAME = "Face"
DRY_RUN = True


def _normalize_body_type(body_type: Optional[str]) -> Optional[BodyType]:
    if body_type is None:
        return None
    normalized = body_type.strip().lower()
    if normalized in BODY_TYPE_TO_SOURCE:
        return normalized  # type: ignore[return-value]
    return None


def find_mesh_object(name: str) -> Optional[bpy.types.Object]:
    obj = bpy.data.objects.get(name)
    if obj and obj.type == "MESH":
        return obj

    for candidate in bpy.data.objects:
        if candidate.type == "MESH" and candidate.data and candidate.data.name == name:
            return candidate

    return None


def _select_active_mesh(obj: bpy.types.Object) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def beyond_expressions_ready() -> dict:
    """Inline fallback when check_beyond_expressions.py was not exec'd."""
    import importlib
    import os

    import addon_utils

    result = {
        "ready": False,
        "messages": [],
        "blend_file_exists": False,
    }

    module_name = None
    for mod in addon_utils.modules():
        name = mod.__name__.lower()
        if "beyond_vrm" in name or "beyond_vrm_extension" in name:
            module_name = mod.__name__
            break

    if module_name is None:
        result["messages"].append("Beyond VRM Extension Suite not found.")
        return result

    if not addon_utils.check(module_name)[1]:
        result["messages"].append("Beyond VRM Extension Suite is not enabled.")
        return result

    if not (hasattr(bpy.ops, "vrm") and hasattr(bpy.ops.vrm, "transfer_shapekeys")):
        result["messages"].append("bpy.ops.vrm.transfer_shapekeys not available.")
        return result

    if not hasattr(bpy.types.Scene, "vrm_shapekey_transfer_source"):
        result["messages"].append("vrm_shapekey_transfer_source scene property missing.")
        return result

    try:
        mod = importlib.import_module(module_name)
        blend_path = os.path.join(
            os.path.dirname(os.path.realpath(mod.__file__)),
            "Expression_Tools_Blender.blend",
        )
        result["blend_file_exists"] = os.path.exists(blend_path)
        if not result["blend_file_exists"]:
            result["messages"].append("Expression_Tools_Blender.blend missing.")
    except Exception as exc:
        result["messages"].append(str(exc))
        return result

    result["ready"] = True
    return result


def run_phase_d(
    body_type: Optional[str] = None,
    face_mesh_name: str = DEFAULT_FACE_MESH_NAME,
    dry_run: bool = DRY_RUN,
) -> dict:
    normalized = _normalize_body_type(body_type)
    if normalized is None:
        return {
            "phase": "D",
            "skipped": True,
            "applied": False,
            "reason": "body_type_not_specified",
            "message": (
                "Phase D skipped: user must specify male or female for ARKit transfer."
            ),
        }

    check = beyond_expressions_ready()
    if not check.get("ready"):
        return {
            "phase": "D",
            "skipped": True,
            "applied": False,
            "reason": "beyond_expressions_not_ready",
            "body_type": normalized,
            "messages": check.get("messages", []),
        }

    face = find_mesh_object(face_mesh_name)
    if face is None:
        return {
            "phase": "D",
            "skipped": True,
            "applied": False,
            "reason": "face_mesh_not_found",
            "body_type": normalized,
            "face_mesh_name": face_mesh_name,
        }

    source = BODY_TYPE_TO_SOURCE[normalized]
    plan = {
        "phase": "D",
        "skipped": False,
        "applied": False,
        "dry_run": dry_run,
        "body_type": normalized,
        "transfer_source": source,
        "face_object_name": face.name,
        "face_mesh_data_name": face.data.name,
        "shape_key_count_before": (
            len(face.data.shape_keys.key_blocks) if face.data.shape_keys else 0
        ),
    }

    if dry_run:
        plan["message"] = (
            f"Would set vrm_shapekey_transfer_source={source!r}, "
            f"select {face.name!r}, run bpy.ops.vrm.transfer_shapekeys()."
        )
        return plan

    bpy.context.scene.vrm_shapekey_transfer_source = source
    _select_active_mesh(face)
    op_result = bpy.ops.vrm.transfer_shapekeys()

    plan["operator_result"] = list(op_result) if op_result is not None else None
    plan["applied"] = op_result == {"FINISHED"}
    plan["shape_key_count_after"] = (
        len(face.data.shape_keys.key_blocks) if face.data.shape_keys else 0
    )

    if not plan["applied"]:
        plan["message"] = "bpy.ops.vrm.transfer_shapekeys did not finish successfully."
    else:
        plan["message"] = "ARKit shape keys transferred."

    return plan


if __name__ == "__main__":
    result = run_phase_d(body_type=None, face_mesh_name=DEFAULT_FACE_MESH_NAME, dry_run=True)
