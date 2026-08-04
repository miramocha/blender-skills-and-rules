"""
Toggle VRoid/VRM armature between T-pose and A-pose (arms + optional leg spread).

Run via MCP execute_blender_code or Blender Scripting:

    result = toggle_t_a_pose(armature_object_name=\"Armature\")
    result = apply_a_pose(armature_object_name=\"Armature\", angle_deg=35, leg_spread_deg=8)
    result = apply_t_pose(armature_object_name=\"Armature\")
    result = detect_pose(armature_object_name=\"Armature\")
"""

from __future__ import annotations

import math
from typing import List, Optional, Tuple

import bpy
from mathutils import Euler, Quaternion

# Remapped (Phase G) then VRM humanoid (Phase A) aliases.
UPPER_ARM_L = ("upperArm.l", "UpperArm_L", "J_Bip_L_UpperArm")
UPPER_ARM_R = ("upperArm.r", "UpperArm_R", "J_Bip_R_UpperArm")
UPPER_LEG_L = ("upperLeg.l", "UpperLeg_L", "J_Bip_L_UpperLeg")
UPPER_LEG_R = ("upperLeg.r", "UpperLeg_R", "J_Bip_R_UpperLeg")

DEFAULT_A_POSE_ANGLE_DEG = 35.0
DEFAULT_LEG_SPREAD_DEG = 8.0
# World-space arm direction Z: T ≈ 0, A ≈ -sin(angle)
T_POSE_Z_ABS_MAX = 0.15
A_POSE_Z_ABS_MIN = 0.25

SCENE_STATE_KEY = "ta_pose_state"


def _resolve_bone(arm_obj: bpy.types.Object, aliases: Tuple[str, ...]) -> Optional[bpy.types.PoseBone]:
    for name in aliases:
        pb = arm_obj.pose.bones.get(name)
        if pb is not None:
            return pb
    return None


def _bone_world_dir(arm_obj: bpy.types.Object, pb: bpy.types.PoseBone):
    head = arm_obj.matrix_world @ pb.head
    tail = arm_obj.matrix_world @ pb.tail
    return (tail - head).normalized()


def _arm_world_dir_z(arm_obj: bpy.types.Object, pb: bpy.types.PoseBone) -> float:
    return float(_bone_world_dir(arm_obj, pb).z)


def _ensure_pose_mode(arm_obj: bpy.types.Object) -> str:
    prev = bpy.context.mode
    bpy.context.view_layer.objects.active = arm_obj
    if arm_obj.mode != "POSE":
        bpy.ops.object.mode_set(mode="POSE")
    return prev


def _restore_mode(prev: str) -> None:
    try:
        if prev == "EDIT_ARMATURE":
            bpy.ops.object.mode_set(mode="EDIT")
        elif prev == "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        elif prev == "POSE":
            bpy.ops.object.mode_set(mode="POSE")
    except Exception:
        pass


def _clear_bone_rotation(pb: bpy.types.PoseBone) -> None:
    pb.rotation_mode = "QUATERNION"
    pb.rotation_quaternion = Quaternion((1.0, 0.0, 0.0, 0.0))
    pb.rotation_euler = Euler((0.0, 0.0, 0.0), "XYZ")


def _set_upper_arm_a_pose(pb: bpy.types.PoseBone, *, side: str, angle_deg: float) -> None:
    """A-pose: pitch arms down via local Z (VRoid/VRM rest bones along ±X)."""
    angle = math.radians(angle_deg)
    z = -angle if side == "l" else angle
    pb.rotation_mode = "XYZ"
    pb.rotation_euler = Euler((0.0, 0.0, z), "XYZ")


def _set_upper_leg_spread(pb: bpy.types.PoseBone, *, side: str, angle_deg: float) -> None:
    """Slight outward hip spread via local Z (left +, right −)."""
    angle = math.radians(angle_deg)
    z = angle if side == "l" else -angle
    pb.rotation_mode = "XYZ"
    pb.rotation_euler = Euler((0.0, 0.0, z), "XYZ")


def detect_pose(armature_object_name: str = "Armature") -> dict:
    arm = bpy.data.objects.get(armature_object_name)
    if not arm or arm.type != "ARMATURE":
        return {"error": f"armature not found: {armature_object_name}"}

    left = _resolve_bone(arm, UPPER_ARM_L)
    right = _resolve_bone(arm, UPPER_ARM_R)
    if not left or not right:
        return {
            "error": "upper arm bones not found",
            "looked_for_l": list(UPPER_ARM_L),
            "looked_for_r": list(UPPER_ARM_R),
        }

    leg_l = _resolve_bone(arm, UPPER_LEG_L)
    leg_r = _resolve_bone(arm, UPPER_LEG_R)

    bpy.context.view_layer.update()
    z_l = _arm_world_dir_z(arm, left)
    z_r = _arm_world_dir_z(arm, right)
    mean_down = (-z_l + -z_r) / 2.0
    if abs(z_l) <= T_POSE_Z_ABS_MAX and abs(z_r) <= T_POSE_Z_ABS_MAX:
        pose = "T"
    elif z_l <= -A_POSE_Z_ABS_MIN and z_r <= -A_POSE_Z_ABS_MIN:
        pose = "A"
    else:
        pose = "other"

    out = {
        "phase": "ta-pose-detect",
        "armature": armature_object_name,
        "pose": pose,
        "upper_arm_l": left.name,
        "upper_arm_r": right.name,
        "world_dir_z_l": z_l,
        "world_dir_z_r": z_r,
        "mean_down": mean_down,
        "stored_state": bpy.context.scene.get(SCENE_STATE_KEY),
    }
    if leg_l and leg_r:
        out["upper_leg_l"] = leg_l.name
        out["upper_leg_r"] = leg_r.name
        out["leg_dir_x_l"] = float(_bone_world_dir(arm, leg_l).x)
        out["leg_dir_x_r"] = float(_bone_world_dir(arm, leg_r).x)
    return out


def apply_t_pose(armature_object_name: str = "Armature") -> dict:
    arm = bpy.data.objects.get(armature_object_name)
    if not arm or arm.type != "ARMATURE":
        return {"error": f"armature not found: {armature_object_name}"}

    left = _resolve_bone(arm, UPPER_ARM_L)
    right = _resolve_bone(arm, UPPER_ARM_R)
    if not left or not right:
        return {"error": "upper arm bones not found"}

    leg_l = _resolve_bone(arm, UPPER_LEG_L)
    leg_r = _resolve_bone(arm, UPPER_LEG_R)

    bones: List[str] = [left.name, right.name]
    prev = _ensure_pose_mode(arm)
    try:
        _clear_bone_rotation(left)
        _clear_bone_rotation(right)
        if leg_l:
            _clear_bone_rotation(leg_l)
            bones.append(leg_l.name)
        if leg_r:
            _clear_bone_rotation(leg_r)
            bones.append(leg_r.name)
        bpy.context.view_layer.update()
        bpy.context.scene[SCENE_STATE_KEY] = "T"
    finally:
        _restore_mode(prev)

    return {
        "phase": "ta-pose-apply",
        "pose": "T",
        "bones": bones,
        "detect": detect_pose(armature_object_name),
    }


def apply_a_pose(
    armature_object_name: str = "Armature",
    angle_deg: float = DEFAULT_A_POSE_ANGLE_DEG,
    *,
    include_legs: bool = True,
    leg_spread_deg: float = DEFAULT_LEG_SPREAD_DEG,
) -> dict:
    arm = bpy.data.objects.get(armature_object_name)
    if not arm or arm.type != "ARMATURE":
        return {"error": f"armature not found: {armature_object_name}"}

    left = _resolve_bone(arm, UPPER_ARM_L)
    right = _resolve_bone(arm, UPPER_ARM_R)
    if not left or not right:
        return {"error": "upper arm bones not found"}

    leg_l = _resolve_bone(arm, UPPER_LEG_L) if include_legs else None
    leg_r = _resolve_bone(arm, UPPER_LEG_R) if include_legs else None

    bones: List[str] = [left.name, right.name]
    prev = _ensure_pose_mode(arm)
    try:
        _set_upper_arm_a_pose(left, side="l", angle_deg=angle_deg)
        _set_upper_arm_a_pose(right, side="r", angle_deg=angle_deg)
        if include_legs and leg_l and leg_r and leg_spread_deg:
            _set_upper_leg_spread(leg_l, side="l", angle_deg=leg_spread_deg)
            _set_upper_leg_spread(leg_r, side="r", angle_deg=leg_spread_deg)
            bones.extend([leg_l.name, leg_r.name])
        elif include_legs and (not leg_l or not leg_r):
            # Clear any stale leg pose if one side missing
            for pb in (leg_l, leg_r):
                if pb:
                    _clear_bone_rotation(pb)
        bpy.context.view_layer.update()
        bpy.context.scene[SCENE_STATE_KEY] = "A"
    finally:
        _restore_mode(prev)

    return {
        "phase": "ta-pose-apply",
        "pose": "A",
        "angle_deg": angle_deg,
        "include_legs": include_legs,
        "leg_spread_deg": leg_spread_deg if include_legs else 0.0,
        "bones": bones,
        "detect": detect_pose(armature_object_name),
    }


def toggle_t_a_pose(
    armature_object_name: str = "Armature",
    angle_deg: float = DEFAULT_A_POSE_ANGLE_DEG,
    *,
    include_legs: bool = True,
    leg_spread_deg: float = DEFAULT_LEG_SPREAD_DEG,
) -> dict:
    """If current looks like T (or unknown/stored T) → A; if A → T."""
    detect = detect_pose(armature_object_name)
    if detect.get("error"):
        return detect

    pose = detect.get("pose")
    stored = detect.get("stored_state")
    if pose == "A" or (pose == "other" and stored == "A"):
        result = apply_t_pose(armature_object_name)
    else:
        result = apply_a_pose(
            armature_object_name,
            angle_deg=angle_deg,
            include_legs=include_legs,
            leg_spread_deg=leg_spread_deg,
        )

    result["toggled_from"] = pose
    result["phase"] = "ta-pose-toggle"
    return result


if __name__ == "__main__":
    result = detect_pose()
