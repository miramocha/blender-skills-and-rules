"""
Full VRoid avatar pipeline orchestrator (phases A–K).
Run via MCP execute_blender_code or Blender Scripting workspace.

    result = run_full_pipeline(body_type="female", dry_run=True)
    result = run_full_pipeline(body_type="female", dry_run=False)
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, Optional, Set

import bpy

DRY_RUN = True
DEFAULT_PHASES = frozenset({"A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K"})

_NS: Dict[str, Any] = {}
_LOADED = False
SKILL_TOOLS_DIR: Optional[str] = None


def _cleanup_tools_dir() -> str:
    if SKILL_TOOLS_DIR and os.path.isdir(SKILL_TOOLS_DIR):
        return SKILL_TOOLS_DIR
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except NameError:
        pass
    home = os.path.join(
        os.path.expanduser("~"), ".cursor", "skills", "vroid-vrm-blender-cleanup", "tools"
    )
    if os.path.isdir(home):
        return home
    raise FileNotFoundError(
        "Set run_full_pipeline.SKILL_TOOLS_DIR to the skill tools folder before exec via MCP."
    )


def _skill_paths() -> dict:
    cleanup_tools = _cleanup_tools_dir()
    skills_root = os.path.dirname(os.path.dirname(cleanup_tools))
    home_skills = os.path.join(os.path.expanduser("~"), ".cursor", "skills")

    def pick(*parts: str) -> str:
        repo = os.path.join(skills_root, *parts)
        if os.path.isdir(repo):
            return repo
        alt = os.path.join(home_skills, *parts)
        return alt if os.path.isdir(alt) else repo

    return {
        "cleanup": cleanup_tools,
        "shapekey": pick("vroid-shapekey-remap", "tools"),
        "bone": pick("blender-bone-remap", "tools"),
        "mtoon": pick("mtoon-material-sync", "tools"),
        "bone_collections": pick("blender-bone-collections", "tools"),
    }


def _exec_script(script_path: str) -> Dict[str, Any]:
    namespace: Dict[str, Any] = {}
    with open(script_path, encoding="utf-8") as handle:
        exec(compile(handle.read(), script_path, "exec"), namespace)
    return namespace


def _merge_exports(namespace: Dict[str, Any], names: Optional[Set[str]] = None) -> None:
    for key, value in namespace.items():
        if key.startswith("__"):
            continue
        if names is not None and key not in names:
            continue
        _NS[key] = value


def _load_tools() -> None:
    global _LOADED
    paths = _skill_paths()
    if not _LOADED:
        local = [
            "import_vrm.py",
            "vrm_bones_rename.py",
            "clean_vroid_material_names.py",
            "rename_mtoon_textures.py",
            "check_beyond_expressions.py",
            "transfer_arkit_shapekeys.py",
            "reset_shape_keys.py",
            "clean_mesh_datablocks.py",
        ]
        for name in local:
            script = os.path.join(paths["cleanup"], name)
            if not os.path.isfile(script):
                raise FileNotFoundError(f"Pipeline script not found: {script}")
            _merge_exports(_exec_script(script))

        bone_script = os.path.join(paths["bone"], "remap_bones.py")
        collider_script = os.path.join(paths["bone"], "rename_vrm_colliders.py")
        shapekey_script = os.path.join(paths["shapekey"], "remap_shapekeys.py")
        for script in (bone_script, collider_script, shapekey_script):
            if not os.path.isfile(script):
                raise FileNotFoundError(f"Pipeline script not found: {script}")

        _merge_exports(_exec_script(bone_script))
        _merge_exports(_exec_script(collider_script))
        # Shapekey module shares dry_run_mapping / apply_mapping names with bones — export entrypoint only.
        _merge_exports(_exec_script(shapekey_script), {"remap_object_fcl_keys"})
        _LOADED = True

    mtoon_script = os.path.join(paths["mtoon"], "sync_mtoon_attributes.py")
    if os.path.isfile(mtoon_script) and "run_phase_j" not in _NS:
        _merge_exports(
            _exec_script(mtoon_script),
            {"audit_mtoon_sync", "apply_mtoon_sync", "run_phase_j"},
        )

    bc_script = os.path.join(paths["bone_collections"], "assign_bone_collections.py")
    if os.path.isfile(bc_script) and "run_phase_k" not in _NS:
        _merge_exports(
            _exec_script(bc_script),
            {"audit_bone_collections", "apply_bone_collections", "run_phase_k"},
        )


def _fn(name: str):
    _load_tools()
    return _NS[name]


def _has_j_prefixed_bones(armature_object_name: str) -> bool:
    arm = bpy.data.objects.get(armature_object_name)
    if not arm or arm.type != "ARMATURE":
        return False
    return any(b.name.startswith("J_") for b in arm.data.bones)


def _normalize_phases(phases: Optional[Set[str]]) -> Set[str]:
    chosen = {p.upper() for p in (phases or DEFAULT_PHASES)}
    if "A" not in chosen:
        raise ValueError("Phase A (VRM bones_rename) is mandatory; cannot omit from phases.")
    return chosen


def _skip_result(phase: str, reason: str) -> dict:
    return {"phase": phase, "skipped": True, "reason": reason}


def _run_b_rescan(dry_run: bool, label: str) -> dict:
    run_phase_b = _fn("run_phase_b")
    b2 = run_phase_b(dry_run=dry_run)
    b2["phase_letter"] = "B"
    b2["rescan"] = label
    return b2


def _run_c_arkit_cleanup(dry_run: bool) -> dict:
    cleanup = _fn("cleanup_arkit_texture_duplicates")
    result = cleanup(dry_run=dry_run)
    result["phase_letter"] = "C"
    result["rescan"] = "after_arkit"
    return result


def run_full_pipeline(
    *,
    armature_object_name: str = "Armature",
    face_mesh_object_name: str = "Face",
    body_type: Optional[str] = None,
    dry_run: bool = DRY_RUN,
    phases: Optional[Set[str]] = None,
    import_filepath: Optional[str] = None,
    import_directory: Optional[str] = None,
    import_filename: Optional[str] = None,
    skip_arkit: bool = False,
    reference_material: str = "Face_Skin",
    mtoon_include_outline: bool = False,
) -> dict:
    chosen = _normalize_phases(phases)
    results: Dict[str, Any] = {
        "pipeline": "full",
        "dry_run": dry_run,
        "phases_requested": sorted(chosen),
        "armature_object_name": armature_object_name,
        "face_mesh_object_name": face_mesh_object_name,
        "phases": {},
        "errors": [],
    }

    rename_map_c: Optional[dict] = None
    phase_d_result: Optional[dict] = None

    # --- Optional Import ---
    if import_filepath or import_directory:
        run_import = _fn("run_phase_import")
        imp = run_import(
            filepath=import_filepath,
            directory=import_directory,
            filename=import_filename,
            new_file=True,
            dry_run=dry_run,
        )
        results["phases"]["Import"] = imp
        if imp.get("error") or imp.get("skipped"):
            results["errors"].append(imp.get("error") or imp.get("reason"))
        else:
            armature_object_name = imp.get("armature_object_name") or armature_object_name
            face_mesh_object_name = imp.get("face_mesh_object_name") or face_mesh_object_name
            results["armature_object_name"] = armature_object_name
            results["face_mesh_object_name"] = face_mesh_object_name

    # --- A: VRM bones_rename ---
    if "A" in chosen:
        run_phase_a = _fn("run_phase_a")
        a_result = run_phase_a(armature_object_name=armature_object_name, dry_run=dry_run)
        a_result["phase_letter"] = "A"
        results["phases"]["A"] = a_result
        if not dry_run and not a_result.get("applied"):
            results["errors"].append(a_result.get("error") or "Phase A failed")

    # --- B: materials ---
    if "B" in chosen:
        run_phase_b = _fn("run_phase_b")
        b_result = run_phase_b(dry_run=dry_run)
        b_result["phase_letter"] = "B"
        results["phases"]["B"] = b_result

    # --- C: textures ---
    if "C" in chosen:
        run_phase_c = _fn("run_phase_c")
        if dry_run:
            c_result = run_phase_c(step="audit")
        else:
            audit = run_phase_c(step="audit")
            rename_map_c = audit.get("rename_map", {})
            c_result = run_phase_c(step="apply", rename_map=rename_map_c)
            verify = run_phase_c(step="verify")
            c_result["verify"] = verify
        c_result["phase_letter"] = "C"
        results["phases"]["C"] = c_result

        if "B" in chosen:
            results["phases"]["B_rescan_after_c"] = _run_b_rescan(dry_run, "after_c")

    # --- D/E: ARKit + reset ---
    run_arkit = "D" in chosen and not skip_arkit
    if run_arkit:
        if not body_type:
            results["phases"]["D"] = _skip_result("D", "body_type_not_specified")
            results["phases"]["E"] = _skip_result("E", "phase_d_skipped")
        else:
            beyond_ready = _fn("beyond_expressions_ready")()
            if not beyond_ready.get("ready"):
                results["phases"]["D"] = {
                    "phase": "D",
                    "skipped": True,
                    "reason": "beyond_expressions_not_ready",
                    "messages": beyond_ready.get("messages", []),
                }
                results["phases"]["E"] = _skip_result("E", "phase_d_skipped")
            else:
                run_phase_d = _fn("run_phase_d")
                d_result = run_phase_d(
                    body_type=body_type,
                    face_mesh_name=face_mesh_object_name,
                    dry_run=dry_run,
                )
                d_result["phase_letter"] = "D"
                results["phases"]["D"] = d_result
                phase_d_result = d_result

                if "E" in chosen:
                    run_phase_e = _fn("run_phase_e")
                    if dry_run and not d_result.get("skipped"):
                        e_result = run_phase_e(
                            mesh_name=face_mesh_object_name,
                            dry_run=True,
                            phase_d_result={"applied": True},
                        )
                    else:
                        e_result = run_phase_e(
                            mesh_name=face_mesh_object_name,
                            dry_run=dry_run,
                            phase_d_result=d_result,
                        )
                    e_result["phase_letter"] = "E"
                    results["phases"]["E"] = e_result

                    if "B" in chosen and d_result.get("applied"):
                        results["phases"]["B_rescan_after_d"] = _run_b_rescan(
                            dry_run, "after_arkit"
                        )
                    if "C" in chosen and d_result.get("applied"):
                        results["phases"]["C_cleanup_after_arkit"] = _run_c_arkit_cleanup(
                            dry_run
                        )
    elif skip_arkit and ("D" in chosen or "E" in chosen):
        results["phases"]["D"] = _skip_result("D", "skip_arkit")
        results["phases"]["E"] = _skip_result("E", "skip_arkit")

    # --- J: MToon rim + shading sync (after material/texture + ARKit mat rescans) ---
    if "J" in chosen:
        _load_tools()
        if "run_phase_j" not in _NS:
            results["phases"]["J"] = _skip_result("J", "mtoon_sync_script_not_found")
        else:
            j_result = _NS["run_phase_j"](
                reference_material=reference_material,
                include_outline=mtoon_include_outline,
                dry_run=dry_run,
            )
            results["phases"]["J"] = j_result

    # --- F: shape keys ---
    if "F" in chosen:
        remap_object_fcl_keys = _fn("remap_object_fcl_keys")
        f_result = remap_object_fcl_keys(
            face_mesh_object_name,
            dry_run_only=dry_run,
            fix_vrm_expression_binds=not dry_run,
            armature_object_name=armature_object_name,
        )
        f_result["phase_letter"] = "F"
        results["phases"]["F"] = f_result

    # --- G: custom bone remap ---
    if "G" in chosen:
        if _has_j_prefixed_bones(armature_object_name) and not dry_run:
            results["phases"]["G"] = {
                "phase": "G",
                "skipped": True,
                "reason": "j_bones_present_run_phase_a_first",
            }
        else:
            build_vroid_hair_mapping = _fn("build_vroid_hair_mapping")
            build_body_mapping = _fn("build_body_mapping")
            side_suffix_at_end = _fn("side_suffix_at_end")
            build_hair_mirror_mapping = _fn("build_hair_mirror_mapping")
            dry_run_mapping = _fn("dry_run_mapping")
            apply_mapping = _fn("apply_mapping")

            arm = bpy.data.objects.get(armature_object_name)
            if not arm or arm.type != "ARMATURE":
                results["phases"]["G"] = {
                    "phase": "G",
                    "error": f"armature not found: {armature_object_name}",
                }
            else:
                mapping: Dict[str, str] = {}
                mapping.update(build_vroid_hair_mapping(arm.data))
                mapping.update(build_body_mapping(arm.data))
                mapping = {
                    old: side_suffix_at_end(new) or new for old, new in mapping.items()
                }
                audit_g = dry_run_mapping(mapping, arm.data)
                if dry_run:
                    mirror = build_hair_mirror_mapping(arm.data)
                    results["phases"]["G"] = {
                        "phase": "G",
                        "dry_run": True,
                        "pass1_count": audit_g.get("count", 0),
                        "pass1": audit_g,
                        "pass2_mirror_count": len(mirror),
                        "pass2_mirror_preview": sorted(mirror.items())[:20],
                    }
                else:
                    apply1 = apply_mapping(mapping, armature_object_name=armature_object_name)
                    arm = bpy.data.objects[armature_object_name]
                    mirror = build_hair_mirror_mapping(arm.data)
                    apply2 = apply_mapping(mirror, armature_object_name=armature_object_name)
                    results["phases"]["G"] = {
                        "phase": "G",
                        "applied": True,
                        "pass1": apply1,
                        "pass2": apply2,
                        "mirror_count": len(mirror),
                    }

    # --- K: bone collections (Hair / Body / Clothing) ---
    if "K" in chosen:
        _load_tools()
        if "run_phase_k" not in _NS:
            results["phases"]["K"] = _skip_result("K", "bone_collections_script_not_found")
        else:
            k_result = _NS["run_phase_k"](
                armature_object_name=armature_object_name,
                dry_run=dry_run,
            )
            results["phases"]["K"] = k_result

    # --- H: colliders ---
    if "H" in chosen:
        audit_vrm_colliders = _fn("audit_vrm_colliders")
        apply_vrm_collider_renames = _fn("apply_vrm_collider_renames")
        if dry_run:
            h_result = audit_vrm_colliders(armature_object_name=armature_object_name)
        else:
            h_result = apply_vrm_collider_renames(
                armature_object_name=armature_object_name,
                dry_run=False,
            )
        h_result["phase_letter"] = "H"
        results["phases"]["H"] = h_result

    # --- I: mesh datablocks ---
    if "I" in chosen:
        run_phase_i = _fn("run_phase_i")
        i_result = run_phase_i(dry_run=dry_run)
        i_result["phase_letter"] = "I"
        results["phases"]["I"] = i_result

    # --- summary checks ---
    if not dry_run:
        results["summary"] = _pipeline_summary(
            armature_object_name=armature_object_name,
            face_mesh_object_name=face_mesh_object_name,
        )

    results["approval_needed"] = dry_run
    results["ok"] = len(results["errors"]) == 0
    return results


def _pipeline_summary(
    armature_object_name: str,
    face_mesh_object_name: str,
) -> dict:
    face = bpy.data.objects.get(face_mesh_object_name)
    fcl_left = 0
    if face and face.data.shape_keys:
        fcl_left = sum(1 for kb in face.data.shape_keys.key_blocks if kb.name.startswith("Fcl_"))

    n00_mats = sum(
        1 for m in bpy.data.materials if m.name and re.search(r"N\d{2}_", m.name)
    )
    j_colliders = sum(
        1 for o in bpy.data.objects if "_collider_" in o.name and "J_Bip" in o.name
    )
    merged_meshes = sum(
        1 for m in bpy.data.meshes if re.search(r"\(merged\)|\.baked", m.name, re.I)
    )
    legacy_textures = 0
    try:
        legacy_textures = _fn("verify_mtoon_textures")().get("legacy_name_count", 0)
    except Exception:
        pass

    mtoon_materials_needing_sync = 0
    try:
        if "audit_mtoon_sync" in _NS:
            mtoon_materials_needing_sync = _NS["audit_mtoon_sync"]().get(
                "materials_needing_sync", 0
            )
    except Exception:
        pass

    bone_collection_unassigned = 0
    bone_collection_mismatches = 0
    try:
        if "audit_bone_collections" in _NS:
            bc_audit = _NS["audit_bone_collections"](armature_object_name=armature_object_name)
            bone_collection_unassigned = bc_audit.get("unassigned_bone_count", 0)
            bone_collection_mismatches = len(bc_audit.get("mismatches", []))
    except Exception:
        pass

    return {
        "fcl_shape_keys_remaining": fcl_left,
        "n00_materials_remaining": n00_mats,
        "j_bip_collider_objects_remaining": j_colliders,
        "merged_baked_mesh_data_remaining": merged_meshes,
        "legacy_texture_names_remaining": legacy_textures,
        "mtoon_materials_needing_sync": mtoon_materials_needing_sync,
        "bone_collection_unassigned": bone_collection_unassigned,
        "bone_collection_mismatches": bone_collection_mismatches,
    }


if __name__ == "__main__":
    result = run_full_pipeline(dry_run=True)
