"""
VRoid Fcl_* shape key rename utilities for Blender (bpy).
Run via MCP execute_blender_code or Blender Scripting workspace.

    mapping = build_fcl_mapping(obj.data.shape_keys.key_blocks)
    report = dry_run_mapping(mapping, existing_names=[kb.name for kb in ...])
    apply_shape_key_mapping(obj, mapping)
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Tuple

import bpy

CATEGORY_MAP = {
    "ALL": "All",
    "BRW": "Brow",
    "EYE": "Eye",
    "MTH": "Mouth",
    "HA": "Teeth",
}


def cap_first(s: str) -> str:
    return s[0].upper() + s[1:] if s else s


def convert_fcl_shape_key(
    name: str,
    prefix_out: str = "vroid",
    category_map: Optional[Dict[str, str]] = None,
    fix_fung: bool = True,
) -> Optional[str]:
    if not name.startswith("Fcl_"):
        return None
    parts = name.split("_")
    if len(parts) < 2:
        return None
    cmap = category_map or CATEGORY_MAP
    out = [prefix_out]
    cat = parts[1]
    out.append(cmap.get(cat, cap_first(cat.lower())))
    for part in parts[2:]:
        if part:
            out.append(cap_first(part))
    result = "".join(out)
    if fix_fung:
        result = result.replace("Fung", "Fang")
    return result


def build_fcl_mapping(
    key_blocks: Iterable,
    only_if_changed: bool = True,
    **convert_kwargs,
) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for kb in key_blocks:
        new = convert_fcl_shape_key(kb.name, **convert_kwargs)
        if not new:
            continue
        if only_if_changed and new == kb.name:
            continue
        mapping[kb.name] = new
    return mapping


def dry_run_mapping(
    mapping: Dict[str, str],
    existing_names: Optional[Iterable[str]] = None,
) -> dict:
    inv: Dict[str, List[str]] = {}
    for old, new in mapping.items():
        inv.setdefault(new, []).append(old)
    duplicates = {k: v for k, v in inv.items() if len(v) > 1}
    conflicts: List[str] = []
    if existing_names is not None:
        existing = set(existing_names)
        for old, new in mapping.items():
            if new in existing and new != old:
                conflicts.append(new)
    return {
        "count": len(mapping),
        "duplicates": duplicates,
        "conflicts": sorted(set(conflicts)),
        "preview": sorted(mapping.items(), key=lambda x: x[1]),
    }


def apply_shape_key_mapping(
    obj: bpy.types.Object,
    mapping: Dict[str, str],
) -> dict:
    if not obj.data or not obj.data.shape_keys:
        return {"error": "no shape keys on object"}
    renamed: List[Tuple[str, str]] = []
    for kb in obj.data.shape_keys.key_blocks:
        new = mapping.get(kb.name)
        if new:
            old = kb.name
            kb.name = new
            renamed.append((old, new))
    return {"object": obj.name, "renamed": renamed, "count": len(renamed)}


def scan_fcl_driver_refs(object_names: Optional[List[str]] = None) -> dict:
    """Find animation drivers referencing shape key blocks (often stale Fcl_* names)."""
    hits: List[dict] = []
    targets = object_names
    if targets is None:
        targets = [o.name for o in bpy.data.objects if o.type == "MESH"]

    for obj_name in targets:
        obj = bpy.data.objects.get(obj_name)
        if not obj or not obj.animation_data:
            continue
        for driver in obj.animation_data.drivers:
            path = driver.data_path
            if "key_blocks" not in path:
                continue
            stale = "Fcl_" in path
            hits.append(
                {
                    "object": obj_name,
                    "data_path": path,
                    "possibly_stale_fcl": stale,
                }
            )

    return {
        "driver_count": len(hits),
        "stale_fcl_count": sum(1 for h in hits if h["possibly_stale_fcl"]),
        "drivers": hits,
    }


def _armature_vrm_extension(armature_object_name: str) -> tuple:
    arm = bpy.data.objects.get(armature_object_name)
    if not arm or arm.type != "ARMATURE":
        return None, {"error": f"armature not found: {armature_object_name}"}
    ext = getattr(arm.data, "vrm_addon_extension", None)
    if not ext:
        return None, {"error": "no vrm_addon_extension on armature"}
    return ext, None


BIND_SHAPE_KEY_FIELDS = ("index", "shape_key_name")


def _remap_bind_shape_key_ref(value: Optional[str], mapping: Dict[str, str]) -> Optional[str]:
    if not value or not isinstance(value, str):
        return None
    return mapping.get(value)


def _resolve_bind_shape_key_name(
    old: Optional[str],
    mapping: Optional[Dict[str, str]],
) -> Optional[str]:
    if not isinstance(old, str) or not old:
        return None
    if mapping and old in mapping:
        return mapping[old]
    if old.startswith("Fcl_"):
        return convert_fcl_shape_key(old)
    return None


def _iter_bind_shape_key_fields(bind) -> List[Tuple[str, str]]:
    refs: List[Tuple[str, str]] = []
    for field in BIND_SHAPE_KEY_FIELDS:
        if not hasattr(bind, field):
            continue
        old = getattr(bind, field, None)
        if isinstance(old, str) and old:
            refs.append((field, old))
    return refs


def _bind_mesh_object_name(bind) -> Optional[str]:
    node = getattr(bind, "node", None)
    if node is not None:
        return getattr(node, "mesh_object_name", None) or getattr(node, "name", None) or None
    mesh = getattr(bind, "mesh", None)
    if mesh is not None:
        return getattr(mesh, "mesh_object_name", None) or getattr(mesh, "name", None) or None
    mesh_name = getattr(bind, "mesh_name", None)
    return mesh_name if isinstance(mesh_name, str) and mesh_name else None


def _sync_bind_mesh_object(bind, mesh_object_name: str) -> bool:
    if not mesh_object_name:
        return False
    node = getattr(bind, "node", None)
    if node is not None and hasattr(node, "mesh_object_name"):
        if node.mesh_object_name == mesh_object_name:
            return False
        node.mesh_object_name = mesh_object_name
        return True
    mesh = getattr(bind, "mesh", None)
    if mesh is not None and hasattr(mesh, "mesh_object_name"):
        if mesh.mesh_object_name == mesh_object_name:
            return False
        mesh.mesh_object_name = mesh_object_name
        return True
    if hasattr(bind, "mesh_name"):
        if bind.mesh_name == mesh_object_name:
            return False
        bind.mesh_name = mesh_object_name
        return True
    return False


def _shape_key_exists_on_mesh(mesh_object_name: Optional[str], key_name: Optional[str]) -> bool:
    if not mesh_object_name or not key_name:
        return False
    obj = bpy.data.objects.get(mesh_object_name)
    if not obj or not obj.data or not obj.data.shape_keys:
        return False
    return key_name in obj.data.shape_keys.key_blocks


def audit_vrm_expression_binds(
    armature_object_name: str = "Armature",
    mapping: Optional[Dict[str, str]] = None,
    face_mesh_object_name: Optional[str] = None,
) -> dict:
    """Dry-run: find VRM0/VRM1 expression binds with stale shape key names or mesh refs."""
    ext, err = _armature_vrm_extension(armature_object_name)
    if err:
        return err

    stale: List[dict] = []
    planned: List[dict] = []
    mesh_mismatches: List[dict] = []

    def _audit_bind(
        *,
        vrm: str,
        expression: str,
        bind,
    ) -> None:
        mesh_name = _bind_mesh_object_name(bind)
        target_mesh = face_mesh_object_name or mesh_name
        if face_mesh_object_name and mesh_name != face_mesh_object_name:
            mesh_row = {
                "vrm": vrm,
                "expression": expression,
                "field": "mesh_object_name",
                "old": mesh_name,
                "new": face_mesh_object_name,
            }
            mesh_mismatches.append(mesh_row)
            planned.append(mesh_row)

        for field, old in _iter_bind_shape_key_fields(bind):
            new = _resolve_bind_shape_key_name(old, mapping)
            key_missing = target_mesh and not _shape_key_exists_on_mesh(target_mesh, old)
            if not new and not key_missing:
                continue
            row = {
                "vrm": vrm,
                "expression": expression,
                "field": field,
                "old": old,
                "new": new,
                "mesh_object_name": mesh_name,
                "key_missing_on_mesh": key_missing,
            }
            stale.append(row)
            if new and new != old:
                planned.append(row)

    vrm0 = getattr(ext, "vrm0", None)
    if vrm0 and getattr(vrm0, "blend_shape_master", None):
        for group in vrm0.blend_shape_master.blend_shape_groups:
            for bind in group.binds:
                _audit_bind(vrm="vrm0", expression=group.name, bind=bind)

    vrm1_exprs = getattr(getattr(ext, "vrm1", None), "expressions", None)
    if vrm1_exprs and hasattr(vrm1_exprs, "all_name_to_expression_dict"):
        for expr_name, expr in vrm1_exprs.all_name_to_expression_dict().items():
            for bind in getattr(expr, "morph_target_binds", []):
                _audit_bind(vrm="vrm1", expression=expr_name, bind=bind)

    return {
        "phase": "vrm-expression-audit",
        "armature": armature_object_name,
        "face_mesh_object_name": face_mesh_object_name,
        "stale_count": len(stale),
        "planned_count": len(planned),
        "mesh_mismatch_count": len(mesh_mismatches),
        "stale": stale,
        "planned": planned,
        "mesh_mismatches": mesh_mismatches,
    }


def apply_vrm_expression_bind_renames(
    mapping: Dict[str, str],
    armature_object_name: str = "Armature",
    face_mesh_object_name: Optional[str] = None,
) -> dict:
    """Rewrite VRM expression morph binds from Fcl_* to vroid* and sync mesh object refs."""
    ext, err = _armature_vrm_extension(armature_object_name)
    if err:
        return err

    renamed: List[dict] = []
    mesh_synced: List[dict] = []

    def _apply_bind(*, vrm: str, expression: str, bind) -> None:
        if face_mesh_object_name:
            old_mesh = _bind_mesh_object_name(bind)
            if _sync_bind_mesh_object(bind, face_mesh_object_name):
                mesh_synced.append(
                    {
                        "vrm": vrm,
                        "expression": expression,
                        "field": "mesh_object_name",
                        "old": old_mesh,
                        "new": face_mesh_object_name,
                    }
                )
        for field, old in _iter_bind_shape_key_fields(bind):
            new = _remap_bind_shape_key_ref(old, mapping)
            if not new:
                continue
            setattr(bind, field, new)
            renamed.append(
                {
                    "vrm": vrm,
                    "expression": expression,
                    "field": field,
                    "old": old,
                    "new": new,
                }
            )

    vrm0 = getattr(ext, "vrm0", None)
    if vrm0 and getattr(vrm0, "blend_shape_master", None):
        for group in vrm0.blend_shape_master.blend_shape_groups:
            for bind in group.binds:
                _apply_bind(vrm="vrm0", expression=group.name, bind=bind)

    vrm1_exprs = getattr(getattr(ext, "vrm1", None), "expressions", None)
    if vrm1_exprs and hasattr(vrm1_exprs, "all_name_to_expression_dict"):
        for expr_name, expr in vrm1_exprs.all_name_to_expression_dict().items():
            for bind in getattr(expr, "morph_target_binds", []):
                _apply_bind(vrm="vrm1", expression=expr_name, bind=bind)

    return {
        "phase": "vrm-expression-apply",
        "armature": armature_object_name,
        "face_mesh_object_name": face_mesh_object_name,
        "renamed_count": len(renamed),
        "mesh_synced_count": len(mesh_synced),
        "renamed": renamed,
        "mesh_synced": mesh_synced,
    }


def fix_vrm_expression_binds_after_fcl_rename(
    armature_object_name: str = "Armature",
    mapping: Optional[Dict[str, str]] = None,
    face_mesh_object_name: Optional[str] = None,
    dry_run: bool = True,
) -> dict:
    """
    After Fcl_* shape key rename, sync VRM0 blend_shape_master and VRM1 morph binds.
    Pass the same mapping used for apply_shape_key_mapping, or omit to derive from convert_fcl_shape_key.
    """
    audit = audit_vrm_expression_binds(
        armature_object_name=armature_object_name,
        mapping=mapping,
        face_mesh_object_name=face_mesh_object_name,
    )
    if audit.get("error"):
        return audit
    if dry_run:
        return audit

    effective_mapping = mapping or {row["old"]: row["new"] for row in audit["planned"] if row.get("new")}
    apply_result = apply_vrm_expression_bind_renames(
        mapping=effective_mapping,
        armature_object_name=armature_object_name,
        face_mesh_object_name=face_mesh_object_name,
    )
    verify = audit_vrm_expression_binds(
        armature_object_name=armature_object_name,
        mapping=effective_mapping,
        face_mesh_object_name=face_mesh_object_name,
    )
    return {
        **audit,
        **apply_result,
        "verify_stale_count": verify.get("stale_count", 0),
        "verify_mesh_mismatch_count": verify.get("mesh_mismatch_count", 0),
    }


def remap_object_fcl_keys(
    object_name: str,
    dry_run_only: bool = False,
    fix_vrm_expression_binds: bool = False,
    armature_object_name: str = "Armature",
    **convert_kwargs,
) -> dict:
    obj = bpy.data.objects.get(object_name)
    if not obj:
        return {"error": f"object not found: {object_name}"}
    if not obj.data.shape_keys:
        return {"error": f"no shape keys on {object_name}"}
    names = [kb.name for kb in obj.data.shape_keys.key_blocks]
    mapping = build_fcl_mapping(obj.data.shape_keys.key_blocks, **convert_kwargs)
    report = dry_run_mapping(mapping, existing_names=names)
    if dry_run_only:
        vrm_audit = audit_vrm_expression_binds(
            armature_object_name=armature_object_name,
            mapping=mapping,
            face_mesh_object_name=object_name,
        )
        return {**report, "vrm_expression_audit": vrm_audit}
    apply_result = apply_shape_key_mapping(obj, mapping)
    result = {**report, **apply_result}
    if fix_vrm_expression_binds:
        result["vrm_expression_fix"] = fix_vrm_expression_binds_after_fcl_rename(
            armature_object_name=armature_object_name,
            mapping=mapping,
            face_mesh_object_name=object_name,
            dry_run=False,
        )
    return result
