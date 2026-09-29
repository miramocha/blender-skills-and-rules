"""
Check whether Beyond VTuber Tools or Beyond VRM Tools is ready for
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


# Either product registers vrm.transfer_shapekeys. Prefer an enabled module,
# and Beyond VTuber Tools when both are enabled.
_BEYOND_MODULE_MARKERS = (
    "beyond_vtuber",
    "beyond_vrm",
)


def _beyond_addon_label(module_name: str) -> str:
    if "beyond_vtuber" in module_name.lower():
        return "Beyond VTuber Tools"
    return "Beyond VRM Tools"


def _find_beyond_module_name() -> Optional[str]:
    matches: list[tuple[int, int, str]] = []
    for mod in addon_utils.modules():
        low = mod.__name__.lower()
        rank = next(
            (index for index, marker in enumerate(_BEYOND_MODULE_MARKERS) if marker in low),
            None,
        )
        if rank is None:
            continue
        enabled = 0 if addon_utils.check(mod.__name__)[1] else 1
        matches.append((enabled, rank, mod.__name__))
    if not matches:
        return None
    matches.sort()
    return matches[0][2]


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
            "Beyond VTuber Tools or Beyond VRM Tools not found."
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
        result["messages"].append(f"{_beyond_addon_label(module_name)} is not enabled.")
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
