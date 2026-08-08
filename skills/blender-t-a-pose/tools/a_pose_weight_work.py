"""
A-pose weight-work round-trip: temporary A rest for pelvic weight transfer,
then bake clothing back to T and rebind to the original VRM armature.

Original armature rest stays T. Only the work copy gets Apply Pose as Rest.

    result = setup_a_work_rest("Armature", leg_spread_deg=30)
    result = status_a_work_rest()
    result = finish_a_work_rest(["Skirt", "Pants"], cleanup=True)
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Sequence, Tuple

import bpy

import toggle_t_a_pose as ta

SCENE_SESSION_KEY = "a_work_session"
WORK_SUFFIX = ".AWork"

DEFAULT_WORK_ARM_ANGLE_DEG = ta.DEFAULT_A_POSE_ANGLE_DEG
DEFAULT_WORK_LEG_SPREAD_DEG = ta.DEFAULT_WORK_LEG_SPREAD_DEG

WEIGHT_MODIFIER_TYPES = {
    "DATA_TRANSFER",
    "VERTEX_WEIGHT_EDIT",
    "VERTEX_WEIGHT_MIX",
    "VERTEX_WEIGHT_PROXIMITY",
}


def _session_get() -> Optional[dict]:
    raw = bpy.context.scene.get(SCENE_SESSION_KEY)
    if raw is None:
        return None
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None
    # IDProperty group / dict-like
    try:
        return json.loads(json.dumps(dict(raw)))
    except Exception:
        return None


def _session_set(data: Optional[dict]) -> None:
    scene = bpy.context.scene
    if data is None:
        if SCENE_SESSION_KEY in scene:
            del scene[SCENE_SESSION_KEY]
        return
    scene[SCENE_SESSION_KEY] = json.dumps(data)


def _ensure_object_mode() -> str:
    prev = bpy.context.mode
    if prev != "OBJECT":
        try:
            bpy.ops.object.mode_set(mode="OBJECT")
        except Exception:
            pass
    return prev


def _link_like(source: bpy.types.Object, new_obj: bpy.types.Object) -> None:
    cols = list(source.users_collection)
    if not cols and bpy.context.collection:
        cols = [bpy.context.collection]
    for col in cols:
        if new_obj.name not in col.objects:
            col.objects.link(new_obj)


def _duplicate_object(obj: bpy.types.Object, name: str) -> bpy.types.Object:
    new_obj = obj.copy()
    if obj.data is not None:
        new_obj.data = obj.data.copy()
    new_obj.name = name
    if new_obj.data is not None:
        new_obj.data.name = name
    _link_like(obj, new_obj)
    return new_obj


def _meshes_skinned_to(arm: bpy.types.Object) -> List[bpy.types.Object]:
    out: List[bpy.types.Object] = []
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        for mod in obj.modifiers:
            if mod.type == "ARMATURE" and mod.object == arm:
                out.append(obj)
                break
    return out


def _retarget_armature_mods(obj: bpy.types.Object, src: bpy.types.Object, dst: bpy.types.Object) -> int:
    n = 0
    for mod in obj.modifiers:
        if mod.type == "ARMATURE" and mod.object == src:
            mod.object = dst
            n += 1
    return n


def _armature_mod_target(obj: bpy.types.Object) -> Optional[bpy.types.Object]:
    for mod in obj.modifiers:
        if mod.type == "ARMATURE" and mod.object is not None:
            return mod.object
    return None


def _find_armature_mod(obj: bpy.types.Object) -> Optional[bpy.types.Modifier]:
    for mod in obj.modifiers:
        if mod.type == "ARMATURE":
            return mod
    return None


def _has_shape_keys(obj: bpy.types.Object) -> bool:
    data = getattr(obj, "data", None)
    keys = getattr(data, "shape_keys", None)
    return keys is not None and len(keys.key_blocks) > 0


def _shape_key_names(obj: bpy.types.Object) -> List[str]:
    data = getattr(obj, "data", None)
    keys = getattr(data, "shape_keys", None)
    if keys is None:
        return []
    return [kb.name for kb in keys.key_blocks]


def _pose_a_on_armature(
    arm: bpy.types.Object,
    *,
    angle_deg: float,
    leg_spread_deg: float,
    include_arms: bool,
    include_legs: bool,
) -> Tuple[List[str], Optional[str]]:
    """Pose work armature toward A (from T rest). Returns (bone names, error)."""
    bones: List[str] = []
    left = ta._resolve_bone(arm, ta.UPPER_ARM_L)
    right = ta._resolve_bone(arm, ta.UPPER_ARM_R)
    leg_l = ta._resolve_bone(arm, ta.UPPER_LEG_L)
    leg_r = ta._resolve_bone(arm, ta.UPPER_LEG_R)

    if include_arms and (not left or not right):
        return [], "upper arm bones not found"
    if include_legs and (not leg_l or not leg_r):
        return [], "upper leg bones not found"
    if not include_arms and not include_legs:
        return [], "include_arms and include_legs both False"

    # REST pose_position ignores pose channels — Apply Pose as Rest would no-op.
    arm.data.pose_position = "POSE"

    prev = ta._ensure_pose_mode(arm)
    try:
        if include_arms and left and right:
            ta._set_upper_arm_a_pose(left, side="l", angle_deg=angle_deg)
            ta._set_upper_arm_a_pose(right, side="r", angle_deg=angle_deg)
            bones.extend([left.name, right.name])
        if include_legs and leg_l and leg_r and leg_spread_deg:
            ta._set_upper_leg_spread(leg_l, side="l", angle_deg=leg_spread_deg)
            ta._set_upper_leg_spread(leg_r, side="r", angle_deg=leg_spread_deg)
            bones.extend([leg_l.name, leg_r.name])
        bpy.context.view_layer.update()
    finally:
        ta._restore_mode(prev)
    return bones, None


def _pose_toward_t_from_a_rest(
    arm: bpy.types.Object,
    *,
    angle_deg: float,
    leg_spread_deg: float,
    include_arms: bool,
    include_legs: bool,
) -> Tuple[List[str], Optional[str]]:
    """Negated A offsets: A rest → T visual."""
    return _pose_a_on_armature(
        arm,
        angle_deg=-float(angle_deg),
        leg_spread_deg=-float(leg_spread_deg),
        include_arms=include_arms,
        include_legs=include_legs,
    )


def _apply_pose_as_rest(arm: bpy.types.Object) -> Optional[str]:
    _ensure_object_mode()
    # Must evaluate pose channels, not rest-only display.
    arm.data.pose_position = "POSE"
    bpy.ops.object.select_all(action="DESELECT")
    arm.hide_set(False)
    arm.hide_viewport = False
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    prev = ta._ensure_pose_mode(arm)
    try:
        bpy.ops.pose.select_all(action="SELECT")
        # Prefer context override — bare ops can CANCEL depending on area/mode.
        op_result = {"CANCELLED"}
        win = bpy.context.window
        scr = win.screen if win else None
        area = next((a for a in (scr.areas if scr else []) if a.type == "VIEW_3D"), None)
        region = next((r for r in (area.regions if area else []) if r.type == "WINDOW"), None)
        if area and region:
            with bpy.context.temp_override(
                window=win,
                screen=scr,
                area=area,
                region=region,
                active_object=arm,
                object=arm,
                selected_objects=[arm],
            ):
                if arm.mode != "POSE":
                    bpy.ops.object.mode_set(mode="POSE")
                bpy.ops.pose.select_all(action="SELECT")
                op_result = bpy.ops.pose.armature_apply(selected=False)
        else:
            op_result = bpy.ops.pose.armature_apply(selected=False)
        if op_result != {"FINISHED"}:
            return f"pose.armature_apply did not finish: {op_result}"
        # Clear residual pose channels after rest bake.
        for pb in arm.pose.bones:
            ta._clear_bone_rotation(pb)
        bpy.context.view_layer.update()
    except Exception as exc:
        return f"pose.armature_apply failed: {exc}"
    finally:
        ta._restore_mode(prev)
        _ensure_object_mode()
    return None


def _strip_shape_keys(obj: bpy.types.Object) -> bool:
    """Remove shape keys from a mesh object. Returns True if any were removed."""
    data = getattr(obj, "data", None)
    if data is None or data.shape_keys is None:
        return False
    obj.shape_key_clear()
    return True


def _bake_armature_to_mesh(obj: bpy.types.Object, work_arm: bpy.types.Object) -> Optional[str]:
    """
    While armature is posed A: apply Armature modifier into mesh verts, then
    re-add Armature mod targeting work_arm. Required because Apply Pose as Rest
    only changes bones — undeformed mesh would stay T.
    """
    mod = _find_armature_mod(obj)
    if mod is None:
        mod = obj.modifiers.new(name="Armature", type="ARMATURE")
        mod.object = work_arm
    else:
        mod.object = work_arm

    _strip_shape_keys(obj)
    mod_name = mod.name
    err = _apply_modifier(obj, mod_name)
    if err:
        return err

    new_mod = obj.modifiers.new(name="Armature", type="ARMATURE")
    new_mod.object = work_arm
    return None


def _apply_modifier(obj: bpy.types.Object, mod_name: str) -> Optional[str]:
    _ensure_object_mode()
    bpy.ops.object.select_all(action="DESELECT")
    obj.hide_set(False)
    obj.hide_viewport = False
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    try:
        bpy.ops.object.modifier_apply(modifier=mod_name)
    except Exception as exc:
        return f"{obj.name}: apply '{mod_name}' failed: {exc}"
    return None


def _apply_weight_modifiers(obj: bpy.types.Object) -> Tuple[List[str], List[str]]:
    applied: List[str] = []
    errors: List[str] = []
    # Apply top-to-bottom; re-scan each time because apply mutates the stack.
    while True:
        target = None
        for mod in obj.modifiers:
            if mod.type in WEIGHT_MODIFIER_TYPES:
                target = mod
                break
        if target is None:
            break
        name = target.name
        err = _apply_modifier(obj, name)
        if err:
            errors.append(err)
            break
        applied.append(name)
    return applied, errors


def _delete_object_and_data(obj: bpy.types.Object) -> None:
    data = obj.data
    data_type = obj.type
    bpy.data.objects.remove(obj, do_unlink=True)
    if data is not None and data.users == 0:
        if data_type == "ARMATURE":
            bpy.data.armatures.remove(data)
        elif data_type == "MESH":
            bpy.data.meshes.remove(data)


def status_a_work_rest() -> dict:
    """Inspect active A-work session (if any)."""
    session = _session_get()
    if not session:
        return {
            "phase": "a-work-status",
            "active": False,
            "session": None,
        }

    work_arm_name = session.get("work_armature")
    work_arm = bpy.data.objects.get(work_arm_name) if work_arm_name else None
    work_meshes = []
    for name in session.get("work_meshes") or []:
        obj = bpy.data.objects.get(name)
        work_meshes.append({"name": name, "exists": obj is not None})

    clothing = []
    for name in session.get("clothing") or []:
        obj = bpy.data.objects.get(name)
        clothing.append({"name": name, "exists": obj is not None})

    return {
        "phase": "a-work-status",
        "active": True,
        "session": session,
        "work_armature_exists": work_arm is not None,
        "work_meshes": work_meshes,
        "clothing": clothing,
        "source_armature_exists": bpy.data.objects.get(session.get("source_armature", "")) is not None,
    }


def _resolve_mesh_list(
    names: Optional[Sequence[str]],
    *,
    label: str,
) -> Tuple[List[bpy.types.Object], Optional[str]]:
    if not names:
        return [], None
    objs: List[bpy.types.Object] = []
    missing: List[str] = []
    for name in names:
        obj = bpy.data.objects.get(name)
        if not obj or obj.type != "MESH":
            missing.append(name)
        else:
            objs.append(obj)
    if missing:
        return [], f"{label} meshes not found: {missing}"
    return objs, None


def _bind_mesh_to_work(
    mesh: bpy.types.Object,
    src: bpy.types.Object,
    work_arm: bpy.types.Object,
) -> None:
    _retarget_armature_mods(mesh, src, work_arm)
    # Also catch mods already pointing nowhere / wrong if object uses Armature parent.
    for mod in mesh.modifiers:
        if mod.type == "ARMATURE" and mod.object is None:
            mod.object = work_arm
    if mesh.parent == src:
        mw = mesh.matrix_world.copy()
        mesh.parent = work_arm
        mesh.matrix_world = mw


def setup_a_work_rest(
    armature_object_name: str = "Armature",
    body_object_names: Optional[Sequence[str]] = None,
    angle_deg: float = DEFAULT_WORK_ARM_ANGLE_DEG,
    *,
    clothing_object_names: Optional[Sequence[str]] = None,
    leg_spread_deg: float = DEFAULT_WORK_LEG_SPREAD_DEG,
    include_arms: bool = True,
    include_legs: bool = True,
    dry_run: bool = False,
) -> dict:
    """
    Duplicate armature + body meshes, Apply Pose as Rest on the work copy (A).
    Optional clothing meshes are retargeted to the work armature *before* apply rest
    (not duplicated) so they bind correctly to A rest for weight work.
    Bakes Armature into work/clothing mesh verts while posed (required for A mesh).
    Warns if body sources have shape keys (expected none for this workflow).
    """
    existing = _session_get()
    if existing:
        return {
            "error": "a_work_session already active — finish_a_work_rest() or clear session first",
            "session": existing,
        }

    src = bpy.data.objects.get(armature_object_name)
    if not src or src.type != "ARMATURE":
        return {"error": f"armature not found: {armature_object_name}"}

    if body_object_names is None:
        bodies = _meshes_skinned_to(src)
        if clothing_object_names:
            skip = set(clothing_object_names)
            bodies = [b for b in bodies if b.name not in skip]
    else:
        bodies, err = _resolve_mesh_list(body_object_names, label="body")
        if err:
            return {"error": err}

    clothes, err = _resolve_mesh_list(clothing_object_names, label="clothing")
    if err:
        return {"error": err}

    if not bodies:
        return {"error": "no body meshes found with Armature modifier targeting source"}

    body_names = [b.name for b in bodies]
    clothing_names = [c.name for c in clothes]
    overlap = sorted(set(body_names) & set(clothing_names))
    if overlap:
        return {"error": f"meshes listed as both body and clothing: {overlap}"}

    # Body for this workflow should have no shape keys (work copy must bake A).
    warnings: List[str] = []
    body_shape_keys: Dict[str, List[str]] = {}
    for body in bodies:
        sk = _shape_key_names(body)
        if sk:
            body_shape_keys[body.name] = sk
            warnings.append(
                f"WARNING: body '{body.name}' has {len(sk)} shape key(s) — "
                "expected none. Work copy will strip keys to bake A bind; "
                "fix Body (remove shape keys) for clean weight-work source."
            )

    plan = {
        "phase": "a-work-setup",
        "dry_run": dry_run,
        "source_armature": src.name,
        "work_armature": f"{src.name}{WORK_SUFFIX}",
        "body_sources": body_names,
        "work_meshes": [f"{b.name}{WORK_SUFFIX}" for b in bodies],
        "clothing": clothing_names,
        "angle_deg": float(angle_deg),
        "leg_spread_deg": float(leg_spread_deg),
        "include_arms": bool(include_arms),
        "include_legs": bool(include_legs),
        "warnings": warnings,
        "body_shape_keys": body_shape_keys,
        "checklist": [
            (
                f"Clothing already on {src.name}{WORK_SUFFIX}"
                if clothing_names
                else f"Point clothing Armature modifier → {src.name}{WORK_SUFFIX}"
            ),
            "Data Transfer / weight paint from work body meshes",
            (
                f"Call finish_a_work_rest({clothing_names}) when done"
                if clothing_names
                else "Call finish_a_work_rest([clothing names]) when done"
            ),
        ],
    }

    if dry_run:
        return plan

    _ensure_object_mode()
    work_arm = _duplicate_object(src, f"{src.name}{WORK_SUFFIX}")
    # Clear animation on work copy so rest bake is not fighting actions.
    if work_arm.animation_data:
        work_arm.animation_data_clear()

    work_meshes: List[bpy.types.Object] = []
    source_to_work: Dict[str, str] = {}
    for body in bodies:
        work_mesh = _duplicate_object(body, f"{body.name}{WORK_SUFFIX}")
        if work_mesh.animation_data:
            work_mesh.animation_data_clear()
        _bind_mesh_to_work(work_mesh, src, work_arm)
        work_meshes.append(work_mesh)
        source_to_work[body.name] = work_mesh.name

    # Bind clothing to work armature BEFORE apply rest so A rest bind is correct.
    clothing_parents: Dict[str, Optional[str]] = {}
    for cloth in clothes:
        clothing_parents[cloth.name] = cloth.parent.name if cloth.parent else None
        _bind_mesh_to_work(cloth, src, work_arm)

    def _rollback_clothing() -> None:
        for cloth in clothes:
            _retarget_armature_mods(cloth, work_arm, src)
            prev_parent = clothing_parents.get(cloth.name)
            if prev_parent == src.name and cloth.parent == work_arm:
                mw = cloth.matrix_world.copy()
                cloth.parent = src
                cloth.matrix_world = mw
            # Restore mesh targets Body.AWork → Body if we remapped them.
            for mod in cloth.modifiers:
                if mod.type == "SHRINKWRAP" and mod.target and mod.target.name.endswith(WORK_SUFFIX):
                    src_name = mod.target.name[: -len(WORK_SUFFIX)]
                    src_obj = bpy.data.objects.get(src_name)
                    if src_obj:
                        mod.target = src_obj
                if mod.type == "DATA_TRANSFER" and getattr(mod, "object", None):
                    if mod.object.name.endswith(WORK_SUFFIX):
                        src_name = mod.object.name[: -len(WORK_SUFFIX)]
                        src_obj = bpy.data.objects.get(src_name)
                        if src_obj:
                            mod.object = src_obj

    # Point clothing Shrinkwrap / Data Transfer from source body → work body.
    mesh_retargets: List[str] = []
    for cloth in clothes:
        for mod in cloth.modifiers:
            if mod.type == "SHRINKWRAP" and mod.target and mod.target.name in source_to_work:
                work_name = source_to_work[mod.target.name]
                work_obj = bpy.data.objects.get(work_name)
                if work_obj:
                    mod.target = work_obj
                    mesh_retargets.append(f"{cloth.name}.{mod.name}->{work_name}")
            if mod.type == "DATA_TRANSFER" and getattr(mod, "object", None):
                if mod.object.name in source_to_work:
                    work_name = source_to_work[mod.object.name]
                    work_obj = bpy.data.objects.get(work_name)
                    if work_obj:
                        mod.object = work_obj
                        mesh_retargets.append(f"{cloth.name}.{mod.name}->{work_name}")

    bones, pose_err = _pose_a_on_armature(
        work_arm,
        angle_deg=angle_deg,
        leg_spread_deg=leg_spread_deg,
        include_arms=include_arms,
        include_legs=include_legs,
    )
    if pose_err:
        _rollback_clothing()
        for m in work_meshes:
            _delete_object_and_data(m)
        _delete_object_and_data(work_arm)
        return {"error": pose_err}

    # Bake posed A into mesh verts BEFORE Apply Pose as Rest (else mesh stays T).
    # Work-body shape keys stripped (copy only). Refuse clothing with shape keys.
    baked: List[str] = []
    for cloth in clothes:
        if _has_shape_keys(cloth):
            _rollback_clothing()
            for m in work_meshes:
                _delete_object_and_data(m)
            _delete_object_and_data(work_arm)
            return {
                "error": f"clothing '{cloth.name}' has shape keys — cannot bake A bind. Remove keys or duplicate clothing first.",
            }
    for mesh_obj in list(work_meshes) + list(clothes):
        bake_err = _bake_armature_to_mesh(mesh_obj, work_arm)
        if bake_err:
            _rollback_clothing()
            for m in work_meshes:
                if m.name in bpy.data.objects:
                    _delete_object_and_data(m)
            if work_arm.name in bpy.data.objects:
                _delete_object_and_data(work_arm)
            return {"error": bake_err}
        baked.append(mesh_obj.name)

    apply_err = _apply_pose_as_rest(work_arm)
    if apply_err:
        _rollback_clothing()
        for m in work_meshes:
            if m.name in bpy.data.objects:
                _delete_object_and_data(m)
        if work_arm.name in bpy.data.objects:
            _delete_object_and_data(work_arm)
        return {"error": apply_err}

    # Confirm rest actually became A (armature_apply can CANCEL silently).
    detect = ta.detect_pose(work_arm.name)
    if detect.get("pose") != "A" and include_arms:
        _rollback_clothing()
        for m in work_meshes:
            if m.name in bpy.data.objects:
                _delete_object_and_data(m)
        if work_arm.name in bpy.data.objects:
            _delete_object_and_data(work_arm)
        return {
            "error": "work armature still not A after apply rest",
            "detect": detect,
        }

    # Rest display = A bind (pose channels cleared).
    work_arm.data.pose_position = "REST"

    session = {
        "source_armature": src.name,
        "work_armature": work_arm.name,
        "work_meshes": [m.name for m in work_meshes],
        "source_meshes": body_names,
        "source_to_work": source_to_work,
        "clothing": clothing_names,
        "angle_deg": float(angle_deg),
        "leg_spread_deg": float(leg_spread_deg),
        "include_arms": bool(include_arms),
        "include_legs": bool(include_legs),
        "bones": bones,
        "baked_meshes": baked,
    }
    _session_set(session)

    plan.update(
        {
            "ok": True,
            "session": session,
            "bones": bones,
            "baked_meshes": baked,
            "mesh_retargets": mesh_retargets,
            "warnings": warnings,
            "body_shape_keys": body_shape_keys,
            "note": "A pose baked into work/clothing mesh verts; work-body shape keys stripped on copy only if present.",
        }
    )
    return plan


def finish_a_work_rest(
    clothing_object_names: Sequence[str],
    *,
    apply_weight_modifiers: bool = True,
    cleanup: bool = True,
    dry_run: bool = False,
) -> dict:
    """
    Pose work armature A→T visual, apply Armature on clothing, rebind to source T armature.
    """
    session = _session_get()
    if not session:
        return {"error": "no active a_work_session — run setup_a_work_rest() first"}

    if not clothing_object_names:
        return {"error": "clothing_object_names required"}

    work_arm_name = session["work_armature"]
    source_arm_name = session["source_armature"]
    work_arm = bpy.data.objects.get(work_arm_name)
    source_arm = bpy.data.objects.get(source_arm_name)
    if not work_arm or work_arm.type != "ARMATURE":
        return {"error": f"work armature missing: {work_arm_name}"}
    if not source_arm or source_arm.type != "ARMATURE":
        return {"error": f"source armature missing: {source_arm_name}"}

    clothes: List[bpy.types.Object] = []
    missing: List[str] = []
    bad_target: List[str] = []
    shape_key_blocks: List[str] = []
    for name in clothing_object_names:
        obj = bpy.data.objects.get(name)
        if not obj or obj.type != "MESH":
            missing.append(name)
            continue
        target = _armature_mod_target(obj)
        if target != work_arm:
            bad_target.append(
                f"{name} → {target.name if target else None} (expected {work_arm_name})"
            )
        if _has_shape_keys(obj):
            shape_key_blocks.append(name)
        clothes.append(obj)

    if missing:
        return {"error": f"clothing meshes not found: {missing}"}
    if bad_target:
        return {
            "error": "clothing Armature modifier must target work armature",
            "details": bad_target,
        }
    if shape_key_blocks:
        return {
            "error": "clothing has shape keys — Apply Armature blocked. Remove/apply shape keys first, or finish manually.",
            "meshes": shape_key_blocks,
        }

    angle_deg = float(session.get("angle_deg", DEFAULT_WORK_ARM_ANGLE_DEG))
    leg_spread_deg = float(session.get("leg_spread_deg", DEFAULT_WORK_LEG_SPREAD_DEG))
    include_arms = bool(session.get("include_arms", True))
    include_legs = bool(session.get("include_legs", True))

    plan: Dict[str, Any] = {
        "phase": "a-work-finish",
        "dry_run": dry_run,
        "clothing": [c.name for c in clothes],
        "work_armature": work_arm_name,
        "source_armature": source_arm_name,
        "apply_weight_modifiers": apply_weight_modifiers,
        "cleanup": cleanup,
        "angle_deg": angle_deg,
        "leg_spread_deg": leg_spread_deg,
        "steps": [
            "optional: apply Data Transfer / vertex weight modifiers",
            "pose work armature with negated A offsets (A rest → T visual)",
            "Apply Armature modifier on clothing (bake T mesh)",
            f"re-add Armature modifier → {source_arm_name}",
            "cleanup work copies" if cleanup else "leave work copies",
        ],
    }

    if dry_run:
        return plan

    weight_applied: Dict[str, List[str]] = {}
    weight_errors: List[str] = []
    if apply_weight_modifiers:
        for obj in clothes:
            applied, errors = _apply_weight_modifiers(obj)
            weight_applied[obj.name] = applied
            weight_errors.extend(errors)
        if weight_errors:
            return {
                "error": "failed applying weight modifiers",
                "details": weight_errors,
                "weight_applied": weight_applied,
            }

    bones, pose_err = _pose_toward_t_from_a_rest(
        work_arm,
        angle_deg=angle_deg,
        leg_spread_deg=leg_spread_deg,
        include_arms=include_arms,
        include_legs=include_legs,
    )
    if pose_err:
        return {"error": pose_err}

    bpy.context.view_layer.update()

    rebaked: List[str] = []
    for obj in clothes:
        mod = _find_armature_mod(obj)
        if mod is None:
            return {"error": f"no Armature modifier on {obj.name}"}
        mod_name = mod.name
        err = _apply_modifier(obj, mod_name)
        if err:
            return {"error": err, "rebaked": rebaked}

        new_mod = obj.modifiers.new(name="Armature", type="ARMATURE")
        new_mod.object = source_arm
        # Prefer same parenting as typical VRM: keep object parent if already source/work.
        if obj.parent == work_arm:
            mw = obj.matrix_world.copy()
            obj.parent = source_arm
            obj.matrix_world = mw
        rebaked.append(obj.name)

    deleted: List[str] = []
    if cleanup:
        for name in list(session.get("work_meshes") or []):
            obj = bpy.data.objects.get(name)
            if obj:
                deleted.append(obj.name)
                _delete_object_and_data(obj)
        if work_arm:
            deleted.append(work_arm.name)
            _delete_object_and_data(work_arm)

    _session_set(None)

    plan.update(
        {
            "ok": True,
            "bones": bones,
            "weight_applied": weight_applied,
            "rebaked": rebaked,
            "deleted": deleted,
            "session_cleared": True,
            "next": f"Verify {source_arm_name} still T rest, then export VRM",
        }
    )
    return plan


if __name__ == "__main__":
    result = status_a_work_rest()
