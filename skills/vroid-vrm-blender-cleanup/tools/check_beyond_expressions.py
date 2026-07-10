"""
Check whether Beyond VRM Extension Suite (Beyond Expressions) is ready for
ARKit shape key transfer via bpy.ops.vrm.transfer_shapekeys.

Run via MCP execute_blender_code or Blender Scripting workspace.

    result = beyond_expressions_ready()
"""

from __future__ import annotations

import importlib
import os
from typing import Optional

import addon_utils
import bpy


def _find_beyond_module_name() -> Optional[str]:
    for mod in addon_utils.modules():
        name = mod.__name__.lower()
        if "beyond_vrm" in name or "beyond_vrm_extension" in name:
            return mod.__name__
    return None


def beyond_expressions_ready() -> dict:
    result = {
        "phase": "D-check",
        "addon_module": None,
        "addon_module_found": False,
        "addon_enabled": False,
        "operator_available": False,
        "transfer_source_enum_ok": False,
        "blend_file_path": None,
        "blend_file_exists": False,
        "ready": False,
        "messages": [],
    }

    module_name = _find_beyond_module_name()
    if module_name is None:
        result["messages"].append(
            "Beyond VRM Extension Suite not found (beyond_vrm_extension_suite)."
        )
        return result

    result["addon_module"] = module_name
    result["addon_module_found"] = True
    result["addon_enabled"] = addon_utils.check(module_name)[1]

    result["operator_available"] = hasattr(bpy.ops, "vrm") and hasattr(
        bpy.ops.vrm, "transfer_shapekeys"
    )
    result["transfer_source_enum_ok"] = hasattr(
        bpy.types.Scene, "vrm_shapekey_transfer_source"
    )

    try:
        mod = importlib.import_module(module_name)
        addon_dir = os.path.dirname(os.path.realpath(mod.__file__))
        blend_path = os.path.join(addon_dir, "Expression_Tools_Blender.blend")
        result["blend_file_path"] = blend_path
        result["blend_file_exists"] = os.path.exists(blend_path)
    except Exception as exc:
        result["messages"].append(f"Could not resolve addon path: {exc}")

    if not result["addon_enabled"]:
        result["messages"].append("Beyond VRM Extension Suite is not enabled.")
    if not result["operator_available"]:
        result["messages"].append("bpy.ops.vrm.transfer_shapekeys is not available.")
    if not result["transfer_source_enum_ok"]:
        result["messages"].append("Scene property vrm_shapekey_transfer_source is missing.")
    if not result["blend_file_exists"]:
        result["messages"].append("Expression_Tools_Blender.blend missing from addon folder.")

    result["ready"] = (
        result["addon_enabled"]
        and result["operator_available"]
        and result["transfer_source_enum_ok"]
        and result["blend_file_exists"]
    )
    return result


def run_check() -> dict:
    return beyond_expressions_ready()


if __name__ == "__main__":
    result = run_check()
