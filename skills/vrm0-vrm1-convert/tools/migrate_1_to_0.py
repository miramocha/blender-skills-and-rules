"""VRM 1.0 VRMC_* → VRM 0.x extension (lossy reverse of UniVRM maps)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    from .coords import migrate_vector3_ext
    from .maps_loader import invert_str_map, load_map
except ImportError:
    from coords import migrate_vector3_ext
    from maps_loader import invert_str_map, load_map


def _xyz_obj(vec: Any) -> Dict[str, float]:
    if isinstance(vec, dict):
        return {
            "x": float(vec.get("x", 0)),
            "y": float(vec.get("y", 0)),
            "z": float(vec.get("z", 0)),
        }
    if isinstance(vec, (list, tuple)) and len(vec) >= 3:
        return {"x": float(vec[0]), "y": float(vec[1]), "z": float(vec[2])}
    return {"x": 0.0, "y": 0.0, "z": 0.0}


def _rev_ext_vec(vec: Any) -> Dict[str, float]:
    """Inverse of MigrateVector3: negate X."""
    x, y, z = migrate_vector3_ext(vec)
    return {"x": x, "y": y, "z": z}


def _node_to_mesh(gltf: Dict[str, Any], node_index: int) -> int:
    nodes = gltf.get("nodes") or []
    if 0 <= node_index < len(nodes):
        mesh = nodes[node_index].get("mesh")
        if mesh is not None:
            return int(mesh)
    return -1


def _image_to_texture(gltf: Dict[str, Any], image_index: int) -> int:
    for i, tex in enumerate(gltf.get("textures") or []):
        if tex.get("source") == image_index:
            return i
    return image_index


def migrate_meta_1_to_0(vrm1_meta: Dict[str, Any], dropped: List[str], approximated: List[str]) -> Dict[str, Any]:
    tables = load_map("meta.json")
    meta: Dict[str, Any] = {}
    m = vrm1_meta or {}
    if "name" in m:
        meta["title"] = m["name"]
    if "version" in m:
        meta["version"] = m["version"]
    authors = m.get("authors") or []
    if authors:
        meta["author"] = authors[0]
        if len(authors) > 1:
            approximated.append("meta.authors extra entries dropped after first")
    if m.get("contactInformation"):
        meta["contactInformation"] = m["contactInformation"]
    refs = m.get("references") or []
    if refs:
        meta["reference"] = refs[0]
        if len(refs) > 1:
            approximated.append("meta.references extra entries dropped after first")
    if "thumbnailImage" in m:
        # filled later with gltf in caller — store image; convert in migrate_vrm1_to_vrm0
        meta["_thumbnailImage"] = m["thumbnailImage"]

    inv_user = invert_str_map(tables["allowed_user"])
    perm = m.get("avatarPermission", "onlyAuthor")
    meta["allowedUserName"] = inv_user.get(perm, "OnlyAuthor")

    meta["violentUssageName"] = "Allow" if m.get("allowExcessivelyViolentUsage") else "Disallow"
    meta["sexualUssageName"] = "Allow" if m.get("allowExcessivelySexualUsage") else "Disallow"

    cu = m.get("commercialUsage", "personalNonProfit")
    if cu == "personalProfit":
        meta["commercialUssageName"] = "Allow"
        approximated.append("commercialUsage personalProfit → Allow")
    elif cu == "corporation":
        meta["commercialUssageName"] = "Allow"
        approximated.append("commercialUsage corporation → Allow (lossy)")
    else:
        meta["commercialUssageName"] = "Disallow"

    if m.get("otherLicenseUrl"):
        meta["otherLicenseUrl"] = m["otherLicenseUrl"]

    meta["licenseName"] = "Other"

    for key in (
        "allowAntisocialOrHateUsage",
        "allowPoliticalOrReligiousUsage",
        "allowRedistribution",
        "creditNotation",
        "modification",
        "copyrightInformation",
        "thirdPartyLicenses",
        "licenseUrl",
    ):
        if key in m:
            dropped.append(f"VRMC_vrm.meta.{key}")
    return meta


def migrate_humanoid_1_to_0(humanoid: Dict[str, Any]) -> Dict[str, Any]:
    inv = invert_str_map(load_map("humanoid_bones.json")["vrm0_to_vrm1"])
    bones = []
    for v1_name, hb in ((humanoid or {}).get("humanBones") or {}).items():
        v0 = inv.get(v1_name, v1_name)
        if isinstance(hb, dict) and "node" in hb:
            bones.append({"bone": v0, "node": int(hb["node"]), "useDefaultValues": True})
    return {"humanBones": bones}


def _preset_1_to_0(v1_key: str) -> str:
    inv = invert_str_map(load_map("presets.json")["vrm0_to_vrm1"])
    return inv.get(v1_key, "unknown")


def _expr_to_clip(gltf: Dict[str, Any], name: str, preset: str, expr: Dict[str, Any]) -> Dict[str, Any]:
    clip: Dict[str, Any] = {
        "name": name,
        "presetName": preset,
        "isBinary": bool(expr.get("isBinary", False)),
        "binds": [],
        "materialValues": [],
    }
    color_inv = invert_str_map(load_map("mtoon.json")["material_color_property"])
    for bind in expr.get("morphTargetBinds") or []:
        node_i = int(bind.get("node", -1))
        mesh_i = _node_to_mesh(gltf, node_i)
        if mesh_i < 0:
            continue
        weight = float(bind.get("weight", 0)) * 100.0
        clip["binds"].append({"mesh": mesh_i, "index": int(bind.get("index", 0)), "weight": weight})
    mats = gltf.get("materials") or []
    for cb in expr.get("materialColorBinds") or []:
        mi = int(cb.get("material", -1))
        if not (0 <= mi < len(mats)):
            continue
        prop = color_inv.get(cb.get("type") or "", "_Color")
        clip["materialValues"].append(
            {
                "materialName": mats[mi].get("name") or "",
                "propertyName": prop,
                "targetValue": list(cb.get("targetValue") or []),
            }
        )
    for tb in expr.get("textureTransformBinds") or []:
        mi = int(tb.get("material", -1))
        if not (0 <= mi < len(mats)):
            continue
        scale = tb.get("scale") or [1, 1]
        offset = tb.get("offset") or [0, 0]
        sx, sy = float(scale[0]), float(scale[1])
        ox, oy = float(offset[0]), float(offset[1])
        # inverse vertical flip: oy_unity = 1 - oy_gltf - sy
        oy_u = 1.0 - oy - sy
        clip["materialValues"].append(
            {
                "materialName": mats[mi].get("name") or "",
                "propertyName": "_MainTex_ST",
                "targetValue": [sx, sy, ox, oy_u],
            }
        )
    return clip


def migrate_expressions_1_to_0(gltf: Dict[str, Any], expressions: Dict[str, Any]) -> Dict[str, Any]:
    groups = []
    preset = (expressions or {}).get("preset") or {}
    for v1_key, expr in preset.items():
        if not expr:
            continue
        v0 = _preset_1_to_0(v1_key)
        groups.append(_expr_to_clip(gltf, v1_key, v0, expr))
    for name, expr in ((expressions or {}).get("custom") or {}).items():
        groups.append(_expr_to_clip(gltf, name, "unknown", expr or {}))
    return {"blendShapeGroups": groups}


def migrate_lookat_fp_1_to_0(
    gltf: Dict[str, Any], look_at: Dict[str, Any], first_person: Dict[str, Any], dropped: List[str]
) -> Dict[str, Any]:
    fp: Dict[str, Any] = {}
    ltype = (look_at or {}).get("type") or "bone"
    fp["lookAtTypeName"] = "BlendShape" if ltype == "expression" else "Bone"

    def curve(key: str, default_y: float) -> Dict[str, Any]:
        rm = (look_at or {}).get(key) or {}
        return {
            "xRange": float(rm.get("inputMaxValue", 90)),
            "yRange": float(rm.get("outputScale", default_y)),
        }

    default_y = 1.0 if ltype == "expression" else 10.0
    fp["lookAtHorizontalInner"] = curve("rangeMapHorizontalInner", default_y)
    fp["lookAtHorizontalOuter"] = curve("rangeMapHorizontalOuter", default_y)
    fp["lookAtVerticalDown"] = curve("rangeMapVerticalDown", default_y)
    fp["lookAtVerticalUp"] = curve("rangeMapVerticalUp", default_y)
    if look_at and look_at.get("offsetFromHeadBone") is not None:
        fp["firstPersonBoneOffset"] = _rev_ext_vec(look_at["offsetFromHeadBone"])
    fp["firstPersonBone"] = -1

    inv_flag = {
        "auto": "Auto",
        "both": "Both",
        "thirdPersonOnly": "ThirdPersonOnly",
        "firstPersonOnly": "FirstPersonOnly",
    }
    anns = []
    for ann in (first_person or {}).get("meshAnnotations") or []:
        node_i = int(ann.get("node", -1))
        mesh_i = _node_to_mesh(gltf, node_i)
        if mesh_i < 0:
            continue
        anns.append(
            {
                "mesh": mesh_i,
                "firstPersonFlag": inv_flag.get(ann.get("type") or "auto", "Auto"),
            }
        )
    if anns:
        fp["meshAnnotations"] = anns
    return fp


def migrate_spring_1_to_0(
    gltf: Dict[str, Any], spring: Dict[str, Any], dropped: List[str]
) -> Dict[str, Any]:
    vrm0_groups = []
    colliders = spring.get("colliders") or []
    for gi, cg in enumerate(spring.get("colliderGroups") or []):
        node_i: Optional[int] = None
        v0_cols = []
        for ci in cg.get("colliders") or []:
            if ci < 0 or ci >= len(colliders):
                continue
            col = colliders[ci]
            shape = col.get("shape") or {}
            if shape.get("capsule"):
                dropped.append(f"VRMC_springBone.colliders[{ci}] capsule")
                continue
            sphere = shape.get("sphere") or {}
            node_i = int(col.get("node", -1)) if node_i is None else node_i
            v0_cols.append(
                {
                    "offset": _rev_ext_vec(sphere.get("offset")),
                    "radius": float(sphere.get("radius", 0)),
                }
            )
        if node_i is None:
            continue
        vrm0_groups.append({"node": node_i, "colliders": v0_cols})

    bone_groups = []
    for sp in spring.get("springs") or []:
        joints = [j for j in (sp.get("joints") or []) if j.get("node") is not None]
        if not joints:
            continue
        roots = []
        if joints:
            roots.append(int(joints[0]["node"]))
        head = joints[0]
        gd = head.get("gravityDir")
        bone_groups.append(
            {
                "comment": sp.get("name") or "",
                "stiffiness": float(head.get("stiffness", 1)),
                "gravityPower": float(head.get("gravityPower", 0)),
                "gravityDir": _rev_ext_vec(gd) if gd is not None else {"x": 0, "y": -1, "z": 0},
                "dragForce": float(head.get("dragForce", 0.5)),
                "center": int(sp["center"]) if sp.get("center") is not None else -1,
                "hitRadius": float(head.get("hitRadius", 0)),
                "bones": roots,
                "colliderGroups": [int(x) for x in (sp.get("colliderGroups") or [])],
            }
        )
        approximated_note = len(joints) > 1
        if approximated_note:
            dropped.append(
                f"spring {sp.get('name')!r}: VRM0 boneGroups store root only; "
                "chain joints flattened to first node"
            )
    return {"colliderGroups": vrm0_groups, "boneGroups": bone_groups}


def _st_from_texinfo(tex: Dict[str, Any]) -> Optional[List[float]]:
    khr = ((tex.get("extensions") or {}).get("KHR_texture_transform")) or {}
    if not khr:
        return None
    scale = khr.get("scale") or [1, 1]
    offset = khr.get("offset") or [0, 0]
    sx, sy = float(scale[0]), float(scale[1])
    ox, oy = float(offset[0]), float(offset[1])
    oy_u = 1.0 - oy - sy
    return [sx, sy, ox, oy_u]


def migrate_mtoon_1_to_0(
    gltf: Dict[str, Any], mat: Dict[str, Any], dropped: List[str]
) -> Dict[str, Any]:
    tables = load_map("mtoon.json")
    mtoon = ((mat.get("extensions") or {}).get("VRMC_materials_mtoon")) or {}
    floats: Dict[str, float] = {}
    vecs: Dict[str, List[float]] = {}
    texs: Dict[str, int] = {}

    pbr = mat.get("pbrMetallicRoughness") or {}
    bc = pbr.get("baseColorFactor")
    if bc:
        vecs["_Color"] = list(bc) if len(bc) >= 4 else list(bc) + [1.0]
    shade = mtoon.get("shadeColorFactor")
    if shade:
        vecs["_ShadeColor"] = list(shade) + ([1.0] if len(shade) == 3 else [])
    rim = mtoon.get("parametricRimColorFactor")
    if rim:
        vecs["_RimColor"] = list(rim) + ([1.0] if len(rim) == 3 else [])
    oc = mtoon.get("outlineColorFactor")
    if oc:
        vecs["_OutlineColor"] = list(oc) + ([1.0] if len(oc) == 3 else [])
    ef = mat.get("emissiveFactor")
    if ef:
        vecs["_EmissionColor"] = list(ef) + ([1.0] if len(ef) == 3 else [])

    bct = pbr.get("baseColorTexture")
    if bct and "index" in bct:
        texs["_MainTex"] = int(bct["index"])
        st = _st_from_texinfo(bct)
        if st:
            vecs["_MainTex"] = st
    smt = mtoon.get("shadeMultiplyTexture")
    if smt and "index" in smt:
        texs["_ShadeTexture"] = int(smt["index"])
    nt = mat.get("normalTexture")
    if nt and "index" in nt:
        texs["_BumpMap"] = int(nt["index"])
        if "scale" in nt:
            floats["_BumpScale"] = float(nt["scale"])
    et = mat.get("emissiveTexture")
    if et and "index" in et:
        texs["_EmissionMap"] = int(et["index"])
    mc = mtoon.get("matcapTexture")
    if mc and "index" in mc:
        texs["_SphereAdd"] = int(mc["index"])
    rt = mtoon.get("rimMultiplyTexture")
    if rt and "index" in rt:
        texs["_RimTexture"] = int(rt["index"])
    ot = mtoon.get("outlineWidthMultiplyTexture")
    if ot and "index" in ot:
        texs["_OutlineWidthTexture"] = int(ot["index"])
    uv = mtoon.get("uvAnimationMaskTexture")
    if uv and "index" in uv:
        texs["_UvAnimMaskTexture"] = int(uv["index"])

    if "shadingShiftFactor" in mtoon:
        floats["_ShadeShift"] = float(mtoon["shadingShiftFactor"])
    if "shadingToonyFactor" in mtoon:
        floats["_ShadeToony"] = float(mtoon["shadingToonyFactor"])
    if "giEqualizationFactor" in mtoon:
        floats["_IndirectLightIntensity"] = max(
            0.0, min(1.0, 1.0 - float(mtoon["giEqualizationFactor"]))
        )
    if "parametricRimFresnelPowerFactor" in mtoon:
        floats["_RimFresnelPower"] = float(mtoon["parametricRimFresnelPowerFactor"])
    if "parametricRimLiftFactor" in mtoon:
        floats["_RimLift"] = float(mtoon["parametricRimLiftFactor"])
    if "rimLightingMixFactor" in mtoon:
        floats["_RimLightingMix"] = float(mtoon["rimLightingMixFactor"])
    if "outlineLightingMixFactor" in mtoon:
        floats["_OutlineLightingMix"] = float(mtoon["outlineLightingMixFactor"])
    if "uvAnimationScrollXSpeedFactor" in mtoon:
        floats["_UvAnimScrollX"] = float(mtoon["uvAnimationScrollXSpeedFactor"])
    if "uvAnimationScrollYSpeedFactor" in mtoon:
        floats["_UvAnimScrollY"] = float(mtoon["uvAnimationScrollYSpeedFactor"])
    if "uvAnimationRotationSpeedFactor" in mtoon:
        floats["_UvAnimRotation"] = float(mtoon["uvAnimationRotationSpeedFactor"])

    inv_ow = invert_str_map(tables["outline_width_mode"])
    mode = mtoon.get("outlineWidthMode", "none")
    floats["_OutlineWidthMode"] = float(int(inv_ow.get(mode, "0")))
    if "outlineWidthFactor" in mtoon:
        w = float(mtoon["outlineWidthFactor"])
        if mode == "worldCoordinates":
            floats["_OutlineWidth"] = w * 100.0
        else:
            floats["_OutlineWidth"] = w

    alpha = mat.get("alphaMode") or "OPAQUE"
    zwrite = bool(mtoon.get("transparentWithZWrite"))
    if alpha == "MASK":
        floats["_BlendMode"] = 1.0
        if "alphaCutoff" in mat:
            floats["_Cutoff"] = float(mat["alphaCutoff"])
    elif alpha == "BLEND" and zwrite:
        floats["_BlendMode"] = 3.0
    elif alpha == "BLEND":
        floats["_BlendMode"] = 2.0
    else:
        floats["_BlendMode"] = 0.0
    floats["_CullMode"] = 0.0 if mat.get("doubleSided") else 2.0

    if mtoon.get("shadingShiftTexture"):
        dropped.append(f"material {mat.get('name')!r} shadingShiftTexture")

    rq = 2000
    if floats["_BlendMode"] == 3.0:
        rq = 2501 + int(mtoon.get("renderQueueOffsetNumber") or 0)
    elif floats["_BlendMode"] == 2.0:
        rq = 3000 + int(mtoon.get("renderQueueOffsetNumber") or 0)
    elif floats["_BlendMode"] == 1.0:
        rq = 2450

    return {
        "name": mat.get("name") or "",
        "shader": "VRM/MToon",
        "renderQueue": rq,
        "floatProperties": floats,
        "vectorProperties": vecs,
        "textureProperties": texs,
        "keywordMap": {},
        "tagMap": {},
    }


def migrate_vrm1_to_vrm0(gltf: Dict[str, Any]) -> Dict[str, List[str]]:
    dropped: List[str] = []
    approximated: List[str] = []
    ext = gltf.setdefault("extensions", {})

    if ext.get("VRMC_node_constraint"):
        dropped.append("VRMC_node_constraint")
        ext.pop("VRMC_node_constraint", None)

    vrm1 = ext.pop("VRMC_vrm", None)
    if not vrm1:
        raise ValueError("no extensions.VRMC_vrm")

    vrm0: Dict[str, Any] = {
        "specVersion": "0.0",
        "exporterVersion": "vrm0-vrm1-convert",
        "meta": migrate_meta_1_to_0(vrm1.get("meta") or {}, dropped, approximated),
        "humanoid": migrate_humanoid_1_to_0(vrm1.get("humanoid") or {}),
        "firstPerson": migrate_lookat_fp_1_to_0(
            gltf, vrm1.get("lookAt") or {}, vrm1.get("firstPerson") or {}, dropped
        ),
        "blendShapeMaster": migrate_expressions_1_to_0(gltf, vrm1.get("expressions") or {}),
        "materialProperties": [],
    }
    thumb = vrm0["meta"].pop("_thumbnailImage", None)
    if thumb is not None:
        vrm0["meta"]["texture"] = _image_to_texture(gltf, int(thumb))

    spring = ext.pop("VRMC_springBone", None)
    if spring:
        vrm0["secondaryAnimation"] = migrate_spring_1_to_0(gltf, spring, dropped)

    for mat in gltf.get("materials") or []:
        vrm0["materialProperties"].append(migrate_mtoon_1_to_0(gltf, mat, dropped))
        mex = mat.get("extensions") or {}
        mex.pop("VRMC_materials_mtoon", None)
        if mex:
            mat["extensions"] = mex
        elif "extensions" in mat:
            del mat["extensions"]

    ext["VRM"] = vrm0
    used = [
        u
        for u in (gltf.get("extensionsUsed") or [])
        if u
        not in (
            "VRMC_vrm",
            "VRMC_springBone",
            "VRMC_materials_mtoon",
            "VRMC_node_constraint",
        )
    ]
    if "VRM" not in used:
        used.append("VRM")
    gltf["extensionsUsed"] = used
    if not ext:
        gltf.pop("extensions", None)
    else:
        # keep remaining extensions plus VRM
        gltf["extensions"] = ext

    req = gltf.get("extensionsRequired")
    if isinstance(req, list):
        gltf["extensionsRequired"] = [
            x
            for x in req
            if x
            not in ("VRMC_vrm", "VRMC_springBone", "VRMC_materials_mtoon", "VRMC_node_constraint")
        ]
        if "VRM" not in gltf["extensionsRequired"]:
            gltf["extensionsRequired"].append("VRM")

    return {"dropped": dropped, "approximated": approximated}
