"""VRM 0.x JSON extensions → VRMC_* (UniVRM MigrationVrm port)."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

try:
    from .coords import migrate_vector3_ext
    from .maps_loader import load_map, outline_width_0_to_1
except ImportError:
    from coords import migrate_vector3_ext
    from maps_loader import load_map, outline_width_0_to_1


def _mesh_to_node(gltf: Dict[str, Any], mesh_index: int) -> int:
    for i, node in enumerate(gltf.get("nodes") or []):
        if node.get("mesh") == mesh_index:
            return i
    return -1


def _tex_index_to_image(gltf: Dict[str, Any], texture_index: int) -> int:
    if texture_index < 0:
        return -1
    textures = gltf.get("textures") or []
    if texture_index >= len(textures):
        return texture_index
    src = textures[texture_index].get("source")
    return src if src is not None else texture_index


def _vertical_flip_st(sx: float, sy: float, ox: float, oy: float) -> Tuple[float, float, float, float]:
    """Unity UV ST → glTF (V = 1 - V)."""
    return sx, sy, ox, 1.0 - oy - sy


def migrate_meta(gltf: Dict[str, Any], vrm0_meta: Dict[str, Any], approximated: List[str]) -> Dict[str, Any]:
    tables = load_map("meta.json")
    meta = dict(tables["vrm1_defaults"])
    meta["licenseUrl"] = tables["license_url"]
    other_license = ""
    other_perm = ""

    if not vrm0_meta:
        approximated.append("meta: empty VRM0 meta; VRM1 defaults applied")
        meta["name"] = ""
        meta["authors"] = [""]
        return meta

    if "title" in vrm0_meta:
        meta["name"] = str(vrm0_meta["title"])
    if "version" in vrm0_meta:
        meta["version"] = str(vrm0_meta["version"])
    if "author" in vrm0_meta:
        meta["authors"] = [str(vrm0_meta["author"])]
    if "contactInformation" in vrm0_meta:
        meta["contactInformation"] = str(vrm0_meta["contactInformation"])
    if "reference" in vrm0_meta:
        ref = str(vrm0_meta["reference"])
        if ref:
            meta["references"] = [ref]

    if "texture" in vrm0_meta:
        tex = int(vrm0_meta["texture"])
        img = _tex_index_to_image(gltf, tex)
        if img >= 0:
            meta["thumbnailImage"] = img

    allowed = tables["allowed_user"]
    if "allowedUserName" in vrm0_meta:
        raw = str(vrm0_meta["allowedUserName"])
        if raw in allowed:
            meta["avatarPermission"] = allowed[raw]
        else:
            approximated.append(f"meta.allowedUserName unknown {raw!r}; kept onlyAuthor")

    ad = tables["allow_disallow_to_bool"]
    for src, dst in (
        ("violentUssageName", "allowExcessivelyViolentUsage"),
        ("sexualUssageName", "allowExcessivelySexualUsage"),
    ):
        if src in vrm0_meta:
            raw = str(vrm0_meta[src])
            if raw in ad:
                meta[dst] = ad[raw]
            else:
                approximated.append(f"meta.{src} unknown {raw!r}")

    if "commercialUssageName" in vrm0_meta:
        raw = str(vrm0_meta["commercialUssageName"])
        cmap = tables["commercial"]
        if raw in cmap:
            meta["commercialUsage"] = cmap[raw]
            if raw == "Allow":
                approximated.append(
                    "meta.commercialUssageName Allow → commercialUsage personalProfit "
                    "(not corporation)"
                )
        else:
            approximated.append(f"meta.commercialUssageName unknown {raw!r}")

    if "otherLicenseUrl" in vrm0_meta:
        other_license = str(vrm0_meta["otherLicenseUrl"] or "")
    if "otherPermissionUrl" in vrm0_meta:
        other_perm = str(vrm0_meta["otherPermissionUrl"] or "")
    if other_license and other_perm:
        if other_license == other_perm:
            meta["otherLicenseUrl"] = other_license
        else:
            meta["otherLicenseUrl"] = f"'{other_license}', '{other_perm}'"
            approximated.append("meta otherLicenseUrl+otherPermissionUrl concatenated")
    elif other_license:
        meta["otherLicenseUrl"] = other_license
    elif other_perm:
        meta["otherLicenseUrl"] = other_perm
        approximated.append("meta.otherPermissionUrl folded into otherLicenseUrl")

    if vrm0_meta.get("licenseName"):
        approximated.append(
            f"meta.licenseName {vrm0_meta['licenseName']!r} not a VRM1 field; "
            "modification=prohibited default"
        )
    return meta


def migrate_humanoid(vrm0_humanoid: Dict[str, Any]) -> Dict[str, Any]:
    bone_map = load_map("humanoid_bones.json")["vrm0_to_vrm1"]
    bones: Dict[str, Any] = {}
    for hb in (vrm0_humanoid or {}).get("humanBones") or []:
        src = hb.get("bone")
        if src is None or "node" not in hb:
            continue
        dst = bone_map.get(src)
        if dst is None:
            continue
        bones[dst] = {"node": int(hb["node"])}
    return {"humanBones": bones}


def _preset_key(preset_name: str, clip_name: str) -> Tuple[str, Optional[str]]:
    """Return ('preset', vrm1_key) or ('custom', name)."""
    tables = load_map("presets.json")["vrm0_to_vrm1"]
    src = (preset_name or "").lower()
    if src == "unknown":
        src = (clip_name or "").lower()
    if src in tables:
        return "preset", tables[src]
    return "custom", clip_name or preset_name or "custom"


def _material_index_by_name(gltf: Dict[str, Any], name: str) -> int:
    for i, mat in enumerate(gltf.get("materials") or []):
        if mat.get("name") == name:
            return i
    return -1


def migrate_expressions(gltf: Dict[str, Any], blend_master: Dict[str, Any]) -> Dict[str, Any]:
    preset: Dict[str, Any] = {}
    custom: Dict[str, Any] = {}
    for clip in (blend_master or {}).get("blendShapeGroups") or []:
        name = clip.get("name") or ""
        kind, key = _preset_key(clip.get("presetName") or "", name)
        expr: Dict[str, Any] = {
            "isBinary": bool(clip.get("isBinary", False)),
            "morphTargetBinds": [],
            "materialColorBinds": [],
            "textureTransformBinds": [],
        }
        for bind in clip.get("binds") or []:
            mesh_i = int(bind.get("mesh", -1))
            node_i = _mesh_to_node(gltf, mesh_i)
            if node_i < 0:
                continue
            weight = float(bind.get("weight", 0)) * 0.01
            expr["morphTargetBinds"].append(
                {"node": node_i, "index": int(bind.get("index", 0)), "weight": weight}
            )
        seen_tt = set()
        for mv in clip.get("materialValues") or []:
            mat_i = _material_index_by_name(gltf, mv.get("materialName") or "")
            if mat_i < 0:
                continue
            prop = mv.get("propertyName") or ""
            tv = [float(x) for x in (mv.get("targetValue") or [])]
            if prop in ("_MainTex_ST", "_MainTex_ST_S", "_MainTex_ST_T"):
                if mat_i in seen_tt:
                    continue
                seen_tt.add(mat_i)
                if prop == "_MainTex_ST" and len(tv) >= 4:
                    sx, sy, ox, oy = _vertical_flip_st(tv[0], tv[1], tv[2], tv[3])
                elif prop == "_MainTex_ST_S" and len(tv) >= 3:
                    sx, sy, ox, oy = _vertical_flip_st(tv[0], 1.0, tv[2], 0.0)
                elif prop == "_MainTex_ST_T" and len(tv) >= 4:
                    sx, sy, ox, oy = _vertical_flip_st(1.0, tv[1], 0.0, tv[3])
                else:
                    continue
                expr["textureTransformBinds"].append(
                    {"material": mat_i, "scale": [sx, sy], "offset": [ox, oy]}
                )
            else:
                color_map = load_map("mtoon.json")["material_color_property"]
                ctype = color_map.get(prop)
                if ctype:
                    expr["materialColorBinds"].append(
                        {"material": mat_i, "type": ctype, "targetValue": tv}
                    )
        slot = {"preset": preset, "custom": custom}[kind]
        if kind == "custom":
            if key not in slot:
                slot[key] = expr
        else:
            slot.setdefault(key, expr)
    out: Dict[str, Any] = {}
    if preset:
        out["preset"] = preset
    if custom:
        out["custom"] = custom
    return out


def migrate_lookat_firstperson(
    gltf: Dict[str, Any], fp: Dict[str, Any]
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    look_type_raw = str(fp.get("lookAtTypeName") or "Bone").lower()
    look_type = "expression" if look_type_raw == "blendshape" else "bone"
    default_y = 10.0 if look_type == "bone" else 1.0

    def range_map(key: str) -> Dict[str, float]:
        node = fp.get(key) or {}
        return {
            "inputMaxValue": float(node.get("xRange", 90)),
            "outputScale": float(node.get("yRange", default_y)),
        }

    look_at = {
        "type": look_type,
        "rangeMapHorizontalInner": range_map("lookAtHorizontalInner"),
        "rangeMapHorizontalOuter": range_map("lookAtHorizontalOuter"),
        "rangeMapVerticalDown": range_map("lookAtVerticalDown"),
        "rangeMapVerticalUp": range_map("lookAtVerticalUp"),
        "offsetFromHeadBone": migrate_vector3_ext(fp.get("firstPersonBoneOffset")),
    }
    annotations = []
    fp_type_map = {
        "auto": "auto",
        "both": "both",
        "thirdpersononly": "thirdPersonOnly",
        "firstpersononly": "firstPersonOnly",
    }
    for ann in fp.get("meshAnnotations") or []:
        mesh_i = int(ann.get("mesh", -1))
        node_i = _mesh_to_node(gltf, mesh_i)
        if node_i < 0:
            continue
        flag = str(ann.get("firstPersonFlag") or "Auto").lower()
        annotations.append({"node": node_i, "type": fp_type_map.get(flag, "auto")})
    first_person = {"meshAnnotations": annotations} if annotations else {}
    return look_at, first_person


def _add_tail_7cm(gltf: Dict[str, Any], last_index: int) -> int:
    nodes = gltf.setdefault("nodes", [])
    last = nodes[last_index]
    t = last.get("translation") or [0.0, 0.0, 0.0]
    vx, vy, vz = float(t[0]), float(t[1]), float(t[2])
    length = math.sqrt(vx * vx + vy * vy + vz * vz) or 1.0
    scale = 0.07 / length
    tail = {
        "name": (last.get("name") or "") + "_end",
        "translation": [vx * scale, vy * scale, vz * scale],
    }
    tail_i = len(nodes)
    nodes.append(tail)
    last["children"] = [tail_i]
    return tail_i


def _create_joints_recursive(
    gltf: Dict[str, Any],
    node_index: int,
    level: int,
    spring: Optional[Dict[str, Any]],
    springs: List[Dict[str, Any]],
    joint_template: Dict[str, Any],
    comment: str,
) -> None:
    nodes = gltf["nodes"]
    node = nodes[node_index]
    if spring is None and level > 0:
        spring = {
            "name": comment,
            "colliderGroups": list(joint_template["colliderGroups"]),
            "joints": [],
            **({"center": joint_template["center"]} if joint_template.get("center") is not None else {}),
        }
        springs.append(spring)
    if spring is not None:
        joint = {"node": node_index}
        joint.update({k: v for k, v in joint_template.items() if k not in ("colliderGroups", "center")})
        spring["joints"].append(joint)

    children = list(node.get("children") or [])
    if not children:
        if spring is not None and spring["joints"]:
            last = spring["joints"][-1]["node"]
            tail_i = _add_tail_7cm(gltf, last)
            spring["joints"].append({"node": tail_i})
        return
    for i, child in enumerate(children):
        if child < 0 or child >= len(nodes):
            continue
        if i == 0:
            _create_joints_recursive(
                gltf, child, level + 1, spring, springs, joint_template, comment
            )
        else:
            _create_joints_recursive(
                gltf, child, 0, None, springs, joint_template, comment
            )


def migrate_spring(gltf: Dict[str, Any], secondary: Dict[str, Any]) -> Dict[str, Any]:
    colliders: List[Dict[str, Any]] = []
    collider_groups: List[Dict[str, Any]] = []
    for cg in secondary.get("colliderGroups") or []:
        indices = []
        node_i = int(cg.get("node", -1))
        for col in cg.get("colliders") or []:
            if "offset" not in col or "radius" not in col:
                continue
            indices.append(len(colliders))
            colliders.append(
                {
                    "node": node_i,
                    "shape": {
                        "sphere": {
                            "offset": migrate_vector3_ext(col["offset"]),
                            "radius": float(col["radius"]),
                        }
                    },
                }
            )
        group: Dict[str, Any] = {"colliders": indices}
        if indices and 0 <= node_i < len(gltf.get("nodes") or []):
            group["name"] = gltf["nodes"][node_i].get("name")
        collider_groups.append(group)

    springs: List[Dict[str, Any]] = []
    for bg in secondary.get("boneGroups") or []:
        comment = bg.get("comment") or ""
        center = int(bg.get("center", -1))
        template = {
            "dragForce": float(bg.get("dragForce", 0.5)),
            "gravityDir": migrate_vector3_ext(bg.get("gravityDir")),
            "gravityPower": float(bg.get("gravityPower", 0)),
            "hitRadius": float(bg.get("hitRadius", 0)),
            "stiffness": float(bg.get("stiffiness", bg.get("stiffness", 1))),
            "colliderGroups": [int(x) for x in (bg.get("colliderGroups") or [])],
            "center": center if center >= 0 else None,
        }
        start = len(springs)
        for root in bg.get("bones") or []:
            ri = int(root)
            if 0 <= ri < len(gltf.get("nodes") or []):
                _create_joints_recursive(gltf, ri, 1, None, springs, template, comment)
        for sp in springs[start:]:
            if not sp.get("name") and sp.get("joints"):
                ni = sp["joints"][0]["node"]
                if 0 <= ni < len(gltf["nodes"]):
                    sp["name"] = gltf["nodes"][ni].get("name")
    return {
        "specVersion": "1.0",
        "colliders": colliders,
        "colliderGroups": collider_groups,
        "springs": springs,
    }


def _tex_info(index: int) -> Dict[str, Any]:
    return {"index": int(index)}


def migrate_mtoon_material(
    gltf: Dict[str, Any], mat: Dict[str, Any], prop: Dict[str, Any], approximated: List[str]
) -> None:
    tables = load_map("mtoon.json")
    floats = prop.get("floatProperties") or {}
    vecs = prop.get("vectorProperties") or {}
    texs = prop.get("textureProperties") or {}
    shader = str(prop.get("shader") or "")
    if "MToon" not in shader and shader not in ("VRM/MToon", "VRM/UnlitTexture"):
        approximated.append(f"material {mat.get('name')!r} shader {shader!r} not MToon; skip")
        return

    mtoon: Dict[str, Any] = {"specVersion": "1.0"}
    pbr = mat.setdefault("pbrMetallicRoughness", {})

    color = vecs.get("_Color")
    if color and len(color) >= 3:
        pbr["baseColorFactor"] = [float(c) for c in color[:4]]
        if len(pbr["baseColorFactor"]) == 3:
            pbr["baseColorFactor"].append(1.0)
    shade = vecs.get("_ShadeColor")
    if shade:
        mtoon["shadeColorFactor"] = [float(c) for c in shade[:3]]
    rim = vecs.get("_RimColor")
    if rim:
        mtoon["parametricRimColorFactor"] = [float(c) for c in rim[:3]]
    outline_c = vecs.get("_OutlineColor")
    if outline_c:
        mtoon["outlineColorFactor"] = [float(c) for c in outline_c[:3]]
    emis = vecs.get("_EmissionColor")
    if emis:
        mat["emissiveFactor"] = [float(c) for c in emis[:3]]

    if "_MainTex" in texs:
        pbr["baseColorTexture"] = _tex_info(texs["_MainTex"])
        st = vecs.get("_MainTex")
        if st and len(st) >= 4:
            sx, sy, ox, oy = _vertical_flip_st(float(st[0]), float(st[1]), float(st[2]), float(st[3]))
            pbr["baseColorTexture"].setdefault("extensions", {}).setdefault(
                "KHR_texture_transform", {}
            ).update({"scale": [sx, sy], "offset": [ox, oy]})
    if "_ShadeTexture" in texs:
        mtoon["shadeMultiplyTexture"] = _tex_info(texs["_ShadeTexture"])
    if "_BumpMap" in texs:
        mat["normalTexture"] = _tex_info(texs["_BumpMap"])
        if "_BumpScale" in floats:
            mat["normalTexture"]["scale"] = float(floats["_BumpScale"])
    if "_EmissionMap" in texs:
        mat["emissiveTexture"] = _tex_info(texs["_EmissionMap"])
    if "_SphereAdd" in texs:
        mtoon["matcapTexture"] = _tex_info(texs["_SphereAdd"])
        mtoon["matcapFactor"] = [1.0, 1.0, 1.0]
    if "_RimTexture" in texs:
        mtoon["rimMultiplyTexture"] = _tex_info(texs["_RimTexture"])
    if "_OutlineWidthTexture" in texs:
        mtoon["outlineWidthMultiplyTexture"] = _tex_info(texs["_OutlineWidthTexture"])
    if "_UvAnimMaskTexture" in texs:
        mtoon["uvAnimationMaskTexture"] = _tex_info(texs["_UvAnimMaskTexture"])

    if "_ShadeShift" in floats:
        mtoon["shadingShiftFactor"] = float(floats["_ShadeShift"])
    if "_ShadeToony" in floats:
        mtoon["shadingToonyFactor"] = float(floats["_ShadeToony"])
    if "_IndirectLightIntensity" in floats:
        mtoon["giEqualizationFactor"] = max(
            0.0, min(1.0, 1.0 - float(floats["_IndirectLightIntensity"]))
        )
    if "_RimFresnelPower" in floats:
        mtoon["parametricRimFresnelPowerFactor"] = float(floats["_RimFresnelPower"])
    if "_RimLift" in floats:
        mtoon["parametricRimLiftFactor"] = float(floats["_RimLift"])
    if "_RimLightingMix" in floats:
        mtoon["rimLightingMixFactor"] = float(floats["_RimLightingMix"])
    if "_OutlineLightingMix" in floats:
        mtoon["outlineLightingMixFactor"] = float(floats["_OutlineLightingMix"])
    if "_UvAnimScrollX" in floats:
        mtoon["uvAnimationScrollXSpeedFactor"] = float(floats["_UvAnimScrollX"])
    if "_UvAnimScrollY" in floats:
        mtoon["uvAnimationScrollYSpeedFactor"] = float(floats["_UvAnimScrollY"])
    if "_UvAnimRotation" in floats:
        mtoon["uvAnimationRotationSpeedFactor"] = float(floats["_UvAnimRotation"])

    ow_mode = str(int(floats.get("_OutlineWidthMode", 0)))
    mtoon["outlineWidthMode"] = tables["outline_width_mode"].get(ow_mode, "none")
    if "_OutlineWidth" in floats:
        mtoon["outlineWidthFactor"] = outline_width_0_to_1(
            mtoon["outlineWidthMode"], float(floats["_OutlineWidth"])
        )

    blend = str(int(floats.get("_BlendMode", 0)))
    kind = tables["blend_mode"].get(blend, "opaque")
    if kind == "opaque":
        mat["alphaMode"] = "OPAQUE"
        mtoon["transparentWithZWrite"] = False
    elif kind == "mask":
        mat["alphaMode"] = "MASK"
        if "_Cutoff" in floats:
            mat["alphaCutoff"] = float(floats["_Cutoff"])
        mtoon["transparentWithZWrite"] = False
    elif kind == "blend_zwrite":
        mat["alphaMode"] = "BLEND"
        mtoon["transparentWithZWrite"] = True
    else:
        mat["alphaMode"] = "BLEND"
        mtoon["transparentWithZWrite"] = False

    cull = int(floats.get("_CullMode", 2))
    mat["doubleSided"] = cull == 0

    rq = int(prop.get("renderQueue", 2000))
    if kind in ("blend", "blend_zwrite"):
        base = 2501 if kind == "blend_zwrite" else 3000
        mtoon["renderQueueOffsetNumber"] = max(-9, min(9, rq - base))
    else:
        mtoon["renderQueueOffsetNumber"] = 0

    mat.setdefault("extensions", {})["VRMC_materials_mtoon"] = mtoon
    used = gltf.setdefault("extensionsUsed", [])
    if "VRMC_materials_mtoon" not in used:
        used.append("VRMC_materials_mtoon")
    if "KHR_materials_unlit" not in used:
        used.append("KHR_materials_unlit")
    mat.setdefault("extensions", {}).setdefault("KHR_materials_unlit", {})


def migrate_vrm0_to_vrm1(gltf: Dict[str, Any]) -> Dict[str, List[str]]:
    dropped: List[str] = []
    approximated: List[str] = []
    ext = gltf.setdefault("extensions", {})
    vrm0 = ext.pop("VRM", None)
    if not vrm0:
        raise ValueError("no extensions.VRM")

    vrm1: Dict[str, Any] = {"specVersion": "1.0"}
    vrm1["meta"] = migrate_meta(gltf, vrm0.get("meta") or {}, approximated)
    vrm1["humanoid"] = migrate_humanoid(vrm0.get("humanoid") or {})
    exprs = migrate_expressions(gltf, vrm0.get("blendShapeMaster") or {})
    if exprs:
        vrm1["expressions"] = exprs
    if vrm0.get("firstPerson"):
        look, fp = migrate_lookat_firstperson(gltf, vrm0["firstPerson"])
        vrm1["lookAt"] = look
        if fp:
            vrm1["firstPerson"] = fp

    ext["VRMC_vrm"] = vrm1
    if vrm0.get("secondaryAnimation"):
        ext["VRMC_springBone"] = migrate_spring(gltf, vrm0["secondaryAnimation"])

    props = vrm0.get("materialProperties") or []
    mats = gltf.get("materials") or []
    for i, prop in enumerate(props):
        if i < len(mats):
            migrate_mtoon_material(gltf, mats[i], prop, approximated)

    used = [u for u in (gltf.get("extensionsUsed") or []) if u != "VRM"]
    if "VRMC_vrm" not in used:
        used.append("VRMC_vrm")
    if "VRMC_springBone" in ext and "VRMC_springBone" not in used:
        used.append("VRMC_springBone")
    gltf["extensionsUsed"] = used
    req = gltf.get("extensionsRequired")
    if isinstance(req, list) and "VRM" in req:
        gltf["extensionsRequired"] = [x for x in req if x != "VRM"]
        if "VRMC_vrm" not in gltf["extensionsRequired"]:
            gltf["extensionsRequired"].append("VRMC_vrm")

    return {"dropped": dropped, "approximated": approximated}
