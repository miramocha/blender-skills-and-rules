"""
Phase I — Clean VRoid mesh datablock names (merged / baked suffixes).
Run via MCP execute_blender_code or Blender Scripting workspace.

    audit = audit_mesh_datablock_names()
    result = clean_mesh_datablock_names(dry_run=False)
"""

from __future__ import annotations

import re
from typing import List, Optional

import bpy

PAT = re.compile(r"\s*\(merged\)|\.baked", re.I)
DRY_RUN = True


def _clean_name(name: str) -> str:
    n = PAT.sub("", name).strip()
    n = re.sub(r"\s+", " ", n).strip(" .")
    return n


def _unique_mesh_name(desired: str, mesh: bpy.types.Mesh) -> str:
    if desired == mesh.name:
        return desired
    existing = bpy.data.meshes.get(desired)
    if existing is None or existing == mesh:
        return desired
    index = 1
    while True:
        candidate = f"{desired}.{index:03d}"
        other = bpy.data.meshes.get(candidate)
        if other is None or other == mesh:
            return candidate
        index += 1


def audit_mesh_datablock_names() -> dict:
    rows: List[dict] = []
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        mesh = obj.data
        if not PAT.search(mesh.name):
            continue
        desired = _clean_name(mesh.name)
        if obj.name != mesh.name and obj.name == _clean_name(obj.name):
            alt = obj.name
            if bpy.data.meshes.get(alt) is None or bpy.data.meshes.get(alt) == mesh:
                desired = alt
        rows.append(
            {
                "object": obj.name,
                "mesh_data": mesh.name,
                "proposed": desired,
                "users": mesh.users,
            }
        )

    orphans: List[dict] = []
    for mesh in bpy.data.meshes:
        if mesh.users != 0 or not PAT.search(mesh.name):
            continue
        orphans.append(
            {
                "mesh_data": mesh.name,
                "proposed": _clean_name(mesh.name),
                "users": mesh.users,
            }
        )

    return {
        "phase": "I",
        "dry_run": True,
        "mesh_objects": rows,
        "orphan_mesh_data": orphans,
        "count": len(rows) + len(orphans),
    }


def clean_mesh_datablock_names(
    align_to_object: bool = True,
    dry_run: bool = DRY_RUN,
) -> dict:
    audit = audit_mesh_datablock_names()
    if dry_run:
        return audit

    renamed: List[dict] = []

    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        mesh = obj.data
        if not PAT.search(mesh.name):
            continue
        desired = _clean_name(mesh.name)
        if align_to_object and obj.name != mesh.name and obj.name == _clean_name(obj.name):
            alt = obj.name
            if bpy.data.meshes.get(alt) is None or bpy.data.meshes.get(alt) == mesh:
                desired = alt
        new_name = _unique_mesh_name(desired, mesh)
        if new_name != mesh.name:
            old = mesh.name
            mesh.name = new_name
            renamed.append(
                {
                    "type": "mesh_data",
                    "object": obj.name,
                    "old": old,
                    "new": new_name,
                }
            )

    for mesh in list(bpy.data.meshes):
        if mesh.users != 0 or not PAT.search(mesh.name):
            continue
        desired = _clean_name(mesh.name)
        new_name = _unique_mesh_name(desired, mesh)
        if new_name != mesh.name:
            old = mesh.name
            mesh.name = new_name
            renamed.append({"type": "orphan_mesh_data", "old": old, "new": new_name})

    verify = audit_mesh_datablock_names()
    return {
        "phase": "I",
        "dry_run": False,
        "applied": True,
        "renamed": renamed,
        "renamed_count": len(renamed),
        "remaining_count": verify.get("count", 0),
    }


def run_phase_i(align_to_object: bool = True, dry_run: bool = DRY_RUN) -> dict:
    if dry_run:
        return audit_mesh_datablock_names()
    return clean_mesh_datablock_names(align_to_object=align_to_object, dry_run=False)


if __name__ == "__main__":
    result = run_phase_i(dry_run=True)
