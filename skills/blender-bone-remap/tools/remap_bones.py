"""
Blender bone / vertex-group / F-Curve remap utilities.
Run inside Blender (bpy) via MCP execute_blender_code or Scripting workspace.

Usage:
    mapping = {}
    mapping.update(build_vroid_hair_mapping(armature_data))
    mapping.update(build_body_mapping(armature_data))
  # optional: side at end, then mirror pairs
    mapping = {o: side_suffix_at_end(n) or n for o, n in mapping.items() if side_suffix_at_end(n)}
    mapping.update(build_hair_mirror_mapping(arm))
    report = dry_run_mapping(mapping, armature_data)
    apply_mapping(mapping, armature_object_name="Armature")
"""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Tuple

import bpy

# --- Parsers: VRoid hair ---

RE_HAIR_END_SIDE = re.compile(r"^Hair(\d+)_(\d+)_end_(L|R)$", re.I)
RE_HAIR_END = re.compile(r"^Hair(\d+)_(.+)_end$", re.I)
RE_HAIR = re.compile(r"^Hair(\d+)_(.+)$", re.I)


def norm_hair_strand(s: str) -> str:
    if s.endswith("_L"):
        base = s[:-2]
        return f"{base.zfill(2) if base.isdigit() else base.lower()}l"
    if s.endswith("_R"):
        base = s[:-2]
        return f"{base.zfill(2) if base.isdigit() else base.lower()}r"
    if s.isdigit():
        return s.zfill(2)
    return s.lower()


def convert_vroid_hair_name(old: str) -> Optional[str]:
    m = RE_HAIR_END_SIDE.match(old)
    if m:
        seg, strand_num, side = int(m.group(1)), m.group(2).zfill(2), m.group(3).lower()
        return f"hair{strand_num}{side}.{seg}.end"
    m = RE_HAIR_END.match(old)
    if m:
        seg, strand = int(m.group(1)), norm_hair_strand(m.group(2))
        return f"hair{strand}.{seg}.end"
    m = RE_HAIR.match(old)
    if not m:
        return None
    return f"hair{norm_hair_strand(m.group(2))}.{int(m.group(1))}"


def build_vroid_hair_mapping(armature_data) -> Dict[str, str]:
    out = {}
    for bone in armature_data.bones:
        if not re.match(r"^Hair", bone.name, re.I):
            continue
        new = convert_vroid_hair_name(bone.name)
        if new and new != bone.name:
            out[bone.name] = new
    return out


# --- Side at end: hair07l.7 -> hair07.7.l ---

RE_HAIR_SIDED = re.compile(r"^hair(\d+)([lr])\.(\d+)(\.end)?$", re.I)


def side_suffix_at_end(name: str) -> Optional[str]:
    m = RE_HAIR_SIDED.match(name)
    if not m:
        return None
    strand, side, link, end = m.group(1), m.group(2).lower(), m.group(3), m.group(4) or ""
    return f"hair{strand}.{link}{end}.{side}"


# --- Mirror strand pairs: 03 -> 01.r, 04 -> 02.r ---

def _hair_link_suffix(name: str) -> Optional[str]:
    m = re.match(r"^hair\d+\.(.+)$", name, re.I)
    return m.group(1) if m else None


def build_hair_mirror_mapping(
    armature_data,
    pairs: Iterable[Tuple[str, str]] = (("01", "03"), ("02", "04")),
) -> Dict[str, str]:
    """
    Map physical strands to logical mirror pairs.
    Left strand (e.g. 01) -> hair01.{link}.l ; right strand (e.g. 03) -> hair01.{link}.r
    """
    mapping: Dict[str, str] = {}
    for bone in armature_data.bones:
        n = bone.name
        m = re.match(r"^hair(\d+)\.(.+)$", n, re.I)
        if not m:
            continue
        strand, rest = m.group(1), m.group(2)
        for left, right in pairs:
            if strand == right:
                base = rest
                if base.endswith(".l"):
                    base = base[:-2]
                elif base.endswith(".r"):
                    base = base[:-2]
                mapping[n] = f"hair{left}.{base}.r"
            elif strand == left:
                if rest.endswith(".l") or rest.endswith(".r"):
                    continue
                mapping[n] = f"hair{left}.{rest}.l"
    return mapping


# --- Body (PascalCase + _L/_R) ---

CENTER = {
    "Root": "root",
    "Hips": "hips",
    "Spine": "spine",
    "Chest": "chest",
    "UpperChest": "upperChest",
    "Neck": "neck",
    "Head": "head",
}


def pascal_to_camel(s: str) -> str:
    return s[0].lower() + s[1:] if s else s


def convert_body_bone_name(old: str) -> Optional[str]:
    if old in CENTER:
        return CENTER[old]
    m = re.match(r"^Bust(\d+)_end_(L|R)$", old)
    if m:
        return f"bust.{m.group(1)}.end.{m.group(2).lower()}"
    m = re.match(r"^Bust(\d+)_(L|R)$", old)
    if m:
        return f"bust.{m.group(1)}.{m.group(2).lower()}"
    m = re.match(r"^FaceEye_(L|R)$", old)
    if m:
        return f"faceEye.{m.group(1).lower()}"
    m = re.match(r"^HoodString(\d+)_end_01_(L|R)$", old)
    if m:
        return f"hoodString.{m.group(1)}.end.{m.group(2).lower()}"
    m = re.match(r"^HoodString(\d+)_01_(L|R)$", old)
    if m:
        return f"hoodString.{m.group(1)}.{m.group(2).lower()}"
    if old == "Hood_01":
        return "hood.1"
    if old == "Hood_end_01":
        return "hood.1.end"
    if old == "Hood_end_01_end":
        return "hood.1.end.end"
    m = re.match(r"^(Index|Middle|Ring|Little|Thumb)(\d+)_(L|R)$", old)
    if m:
        return f"{m.group(1).lower()}.{m.group(2)}.{m.group(3).lower()}"
    m = re.match(r"^(.+?)_(L|R)$", old)
    if m:
        return f"{pascal_to_camel(m.group(1))}.{m.group(2).lower()}"
    return None


def build_body_mapping(armature_data, skip_hair_prefix: str = "hair") -> Dict[str, str]:
    out = {}
    for bone in armature_data.bones:
        if bone.name.lower().startswith(skip_hair_prefix):
            continue
        new = convert_body_bone_name(bone.name)
        if new and new != bone.name:
            out[bone.name] = new
    return out


# --- Apply / verify ---

def dry_run_mapping(mapping: Dict[str, str], armature_data) -> dict:
    inv: Dict[str, List[str]] = {}
    for old, new in mapping.items():
        inv.setdefault(new, []).append(old)
    dups = {k: v for k, v in inv.items() if len(v) > 1}
    missing = [b.name for b in armature_data.bones if b.name not in mapping and not b.name.startswith("__tmp__")]
    return {"count": len(mapping), "duplicates": dups, "bones_not_in_map": missing}


def apply_mapping(
    mapping: Dict[str, str],
    armature_object_name: str = "Armature",
    mesh_names: Optional[List[str]] = None,
    rename_all_meshes: bool = True,
) -> dict:
    arm_obj = bpy.data.objects[armature_object_name]
    arm = arm_obj.data

    for old in mapping:
        if old in arm.bones:
            arm.bones[old].name = f"__tmp__{old}"
    for old, new in mapping.items():
        tmp = f"__tmp__{old}"
        if tmp in arm.bones:
            arm.bones[tmp].name = new

    vg_count = 0
    meshes = []
    if rename_all_meshes:
        meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    elif mesh_names:
        meshes = [bpy.data.objects[n] for n in mesh_names if n in bpy.data.objects]

    for obj in meshes:
        for old, new in mapping.items():
            vg = obj.vertex_groups.get(old)
            if vg:
                vg.name = new
                vg_count += 1

    cons_count = 0
    for pb in arm_obj.pose.bones:
        for c in pb.constraints:
            st = getattr(c, "subtarget", None)
            if st and st in mapping:
                c.subtarget = mapping[st]
                cons_count += 1

    fc_count = 0
    for action in bpy.data.actions:
        for fc in action.fcurves:
            path = fc.data_path
            new_path = path
            for old, new in mapping.items():
                ref = f'pose.bones["{old}"]'
                if ref in new_path:
                    new_path = new_path.replace(ref, f'pose.bones["{new}"]')
            if new_path != path:
                fc.data_path = new_path
                fc_count += 1

    return {
        "bones": len(mapping),
        "vertex_group_renames": vg_count,
        "constraints": cons_count,
        "fcurves": fc_count,
    }
