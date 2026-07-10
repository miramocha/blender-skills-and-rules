"""
Import a .vrm file (or pick from a directory) and audit the scene for cleanup.

Run via MCP execute_blender_code or Blender Scripting workspace.

    files = list_vrm_files(r"D:\\path\\to\\folder")
    result = run_phase_import(filepath=files[0], new_file=True, dry_run=False)
    audit = audit_after_import()
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import bpy

# Default VRM import profile (VRM Add-on for Blender).
DEFAULT_IMPORT_KWARGS: Dict[str, Any] = {
    "use_addon_preferences": True,
    "extract_textures_into_folder": False,
    "make_new_texture_folder": True,
    "set_shading_type_to_material_on_import": True,
    "set_view_transform_to_standard_on_import": True,
    "set_armature_display_to_wire": True,
    "set_armature_display_to_show_in_front": True,
    "set_armature_bone_shape_to_default": True,
    "enable_mtoon_outline_preview": True,
}

DRY_RUN = True


def list_vrm_files(directory: str) -> dict:
    root = Path(directory).expanduser()
    if not root.is_dir():
        return {
            "phase": "import",
            "error": f"Not a directory: {directory}",
            "files": [],
        }

    files = sorted(
        str(p.resolve())
        for p in root.iterdir()
        if p.is_file() and p.suffix.lower() == ".vrm"
    )
    return {
        "phase": "import",
        "directory": str(root.resolve()),
        "count": len(files),
        "files": files,
        "file_names": [Path(f).name for f in files],
    }


def resolve_vrm_path(
    filepath: Optional[str] = None,
    directory: Optional[str] = None,
    filename: Optional[str] = None,
) -> dict:
    if filepath:
        path = Path(filepath).expanduser().resolve()
        if path.suffix.lower() != ".vrm":
            return {"error": f"Not a .vrm file: {filepath}", "filepath": None}
        if not path.is_file():
            return {"error": f"File not found: {filepath}", "filepath": None}
        return {"filepath": str(path), "file_name": path.name}

    if directory:
        listing = list_vrm_files(directory)
        if listing.get("error"):
            return listing
        files = listing["files"]
        if not files:
            return {"error": f"No .vrm files in {directory}", "filepath": None}
        if filename:
            matches = [f for f in files if Path(f).name == filename]
            if not matches:
                return {
                    "error": f"{filename!r} not found in directory",
                    "filepath": None,
                    "available": listing["file_names"],
                }
            return {"filepath": matches[0], "file_name": filename}
        if len(files) == 1:
            return {"filepath": files[0], "file_name": Path(files[0]).name}
        return {
            "error": "multiple_vrm_files",
            "message": "Multiple .vrm files; user must pick one.",
            "filepath": None,
            "files": files,
            "file_names": listing["file_names"],
        }

    return {"error": "Provide filepath or directory", "filepath": None}


def _new_empty_blend() -> None:
    bpy.ops.wm.read_homefile(use_empty=True)


def _objects_snapshot() -> set[str]:
    return {obj.name for obj in bpy.data.objects}


def _find_face_child(armature: bpy.types.Object) -> Optional[str]:
    for child in armature.children:
        if child.type == "MESH" and child.name.lower().startswith("face"):
            return child.name
    for child in armature.children:
        if child.type == "MESH" and "face" in child.name.lower():
            return child.name
    return None


def audit_after_import(armature_name: Optional[str] = None) -> dict:
    armatures = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]
    armature_infos: List[dict] = []

    for arm in armatures:
        if armature_name and arm.name != armature_name:
            continue
        face_name = _find_face_child(arm)
        vrm_meta_title = None
        if hasattr(arm.data, "vrm_addon_extension"):
            try:
                vrm_meta_title = arm.data.vrm_addon_extension.vrm0.meta.title
            except Exception:
                pass
        armature_infos.append(
            {
                "armature_object": arm.name,
                "bone_count": len(arm.data.bones),
                "face_mesh_object": face_name,
                "child_meshes": [c.name for c in arm.children if c.type == "MESH"],
                "vrm0_meta_title": vrm_meta_title,
            }
        )

    vrm_texts = [t.name for t in bpy.data.texts if "vrm" in t.name.lower()]

    primary = None
    if armature_name:
        primary = next((a for a in armature_infos if a["armature_object"] == armature_name), None)
    elif len(armature_infos) == 1:
        primary = armature_infos[0]

    return {
        "phase": "import-audit",
        "blend_filepath": bpy.data.filepath or None,
        "armatures": armature_infos,
        "armature_count": len(armature_infos),
        "primary_armature": primary["armature_object"] if primary else None,
        "primary_face_mesh": primary["face_mesh_object"] if primary else None,
        "vrm_json_text_blocks": vrm_texts,
        "needs_armature_pick": len(armature_infos) > 1 and armature_name is None,
    }


def import_vrm(
    filepath: str,
    new_file: bool = False,
    dry_run: bool = DRY_RUN,
    import_kwargs: Optional[Dict[str, Any]] = None,
) -> dict:
    resolved = resolve_vrm_path(filepath=filepath)
    if resolved.get("error"):
        return {"phase": "import", "skipped": True, **resolved}

    vrm_path = resolved["filepath"]
    kwargs = {**DEFAULT_IMPORT_KWARGS, **(import_kwargs or {})}

    if dry_run:
        return {
            "phase": "import",
            "dry_run": True,
            "skipped": False,
            "filepath": vrm_path,
            "file_name": resolved["file_name"],
            "new_file": new_file,
            "import_kwargs": kwargs,
            "message": f"Would import {resolved['file_name']!r} then run cleanup phases.",
        }

    if not hasattr(bpy.ops.import_scene, "vrm"):
        return {
            "phase": "import",
            "error": "bpy.ops.import_scene.vrm not available — enable VRM Add-on for Blender.",
            "applied": False,
        }

    before = _objects_snapshot()
    if new_file:
        _new_empty_blend()
        before = _objects_snapshot()

    op_result = bpy.ops.import_scene.vrm(filepath=vrm_path, **kwargs)
    applied = op_result == {"FINISHED"}

    after = _objects_snapshot()
    new_object_names = sorted(after - before)
    new_armatures = [
        name
        for name in new_object_names
        if bpy.data.objects.get(name) and bpy.data.objects[name].type == "ARMATURE"
    ]

    audit = audit_after_import(
        armature_name=new_armatures[0] if len(new_armatures) == 1 else None
    )

    return {
        "phase": "import",
        "dry_run": False,
        "applied": applied,
        "operator_result": list(op_result) if op_result is not None else None,
        "filepath": vrm_path,
        "file_name": resolved["file_name"],
        "new_file": new_file,
        "new_object_names": new_object_names,
        "imported_armatures": new_armatures,
        "audit": audit,
        "armature_object_name": audit.get("primary_armature"),
        "face_mesh_object_name": audit.get("primary_face_mesh"),
    }


def run_phase_import(
    filepath: Optional[str] = None,
    directory: Optional[str] = None,
    filename: Optional[str] = None,
    new_file: bool = True,
    dry_run: bool = DRY_RUN,
    import_kwargs: Optional[Dict[str, Any]] = None,
) -> dict:
    resolved = resolve_vrm_path(filepath=filepath, directory=directory, filename=filename)
    if resolved.get("error") == "multiple_vrm_files":
        return {
            "phase": "import",
            "skipped": True,
            "reason": "multiple_vrm_files",
            **resolved,
        }
    if resolved.get("error"):
        return {"phase": "import", "skipped": True, **resolved}

    return import_vrm(
        filepath=resolved["filepath"],
        new_file=new_file,
        dry_run=dry_run,
        import_kwargs=import_kwargs,
    )


if __name__ == "__main__":
    result = run_phase_import(dry_run=True)
