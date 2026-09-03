"""Dump VRM Add-on MToon 1.0 node/RNA state to sidecar JSON for three-vrm apply."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from mtoon_sidecar_schema import (
    ALPHA_MODE_FROM_INT,
    KIND,
    outline_mode_from_int,
    portable_basename,
    rgb,
    rgba,
    with_alpha,
    wrap_document,
)

try:
    import bpy
except ImportError:  # pragma: no cover
    bpy = None  # type: ignore

MTOON_OUTPUT = "Mtoon1Material.Mtoon1Output"

IMAGE_NODES = {
    "base": "Mtoon1BaseColorTexture.Image",
    "shade": "Mtoon1ShadeMultiplyTexture.Image",
    "matcap": "Mtoon1MatcapTexture.Image",
    "normal": "Mtoon1NormalTexture.Image",
    "emissive": "Mtoon1EmissiveTexture.Image",
    "rim": "Mtoon1RimMultiplyTexture.Image",
    "outlineWidth": "Mtoon1OutlineWidthMultiplyTexture.Image",
    "uvAnimMask": "Mtoon1UvAnimationMaskTexture.Image",
}

SOCK = {
    "lit": "Lit Color",
    "shade": "Shade Color",
    "emissive": "Emissive Factor",
    "emissiveStrength": "Emissive Strength",
    "rim": "Parametric Rim Color",
    "rimFresnel": "Parametric Rim Fresnel Power",
    "rimLift": "Parametric Rim Lift",
    "rimMix": "Rim LightingMix",
    "outlineMode": "Outline Width Mode",
    "outlineWidth": "Outline Width",
    "outlineColor": "Outline Color",
    "outlineMix": "Outline LightingMix",
    "toony": "Shading Toony",
    "shift": "Shading Shift",
    "gi": "GI Equalization Factor",
    "matcapFactor": "MatCap Factor",
    "alphaMode": "Alpha Mode",
    "alphaCutoff": "Alpha Cutoff",
    "doubleSided": "Double Sided",
}


def _sock(node, name: str) -> Any:
    inp = node.inputs.get(name)
    if inp is None or not hasattr(inp, "default_value"):
        return None
    return inp.default_value


def _image_ref(tree, node_name: str) -> Optional[Dict[str, Any]]:
    n = tree.nodes.get(node_name)
    if n is None or n.type != "TEX_IMAGE" or n.image is None:
        return None
    img = n.image
    name = portable_basename(img.name) or portable_basename(img.filepath)
    if not name:
        return None
    return {"name": name}


def dump_material(mat) -> Optional[Dict[str, Any]]:
    if mat is None or not mat.use_nodes or mat.node_tree is None:
        return None
    if mat.name.startswith("MToon Outline"):
        return None
    tree = mat.node_tree
    out = tree.nodes.get(MTOON_OUTPUT)
    if out is None:
        return None
    textures = {key: _image_ref(tree, node) for key, node in IMAGE_NODES.items()}
    textures = {k: v for k, v in textures.items() if v}
    alpha_i = _sock(out, SOCK["alphaMode"])
    try:
        alpha_mode = ALPHA_MODE_FROM_INT.get(int(round(float(alpha_i or 0))), "OPAQUE")
    except (TypeError, ValueError):
        alpha_mode = "OPAQUE"
    try:
        ext = mat.vrm_addon_extension.mtoon1
        enabled = bool(ext.enabled)
        if ext.alpha_mode:
            alpha_mode = str(ext.alpha_mode)
        double_sided = bool(ext.double_sided)
    except Exception:
        enabled = False
        ds = _sock(out, SOCK["doubleSided"])
        double_sided = bool(ds) if ds is not None else True
    return {
        "enabled": enabled,
        "alphaMode": alpha_mode,
        "doubleSided": double_sided,
        "color": rgba(_sock(out, SOCK["lit"])),
        "emissiveFactor": rgb(_sock(out, SOCK["emissive"])),
        "emissiveStrength": float(_sock(out, SOCK["emissiveStrength"]) or 0.0),
        "mtoon": {
            "shadeColorFactor": rgb(_sock(out, SOCK["shade"]), [1.0, 1.0, 1.0]),
            "shadingToonyFactor": float(_sock(out, SOCK["toony"]) or 0.9),
            "shadingShiftFactor": float(_sock(out, SOCK["shift"]) or 0.0),
            "giEqualizationFactor": float(_sock(out, SOCK["gi"]) or 1.0),
            "matcapFactor": rgb(_sock(out, SOCK["matcapFactor"]), [1.0, 1.0, 1.0]),
            "parametricRimColorFactor": rgb(_sock(out, SOCK["rim"])),
            "parametricRimFresnelPowerFactor": float(_sock(out, SOCK["rimFresnel"]) or 1.0),
            "parametricRimLiftFactor": float(_sock(out, SOCK["rimLift"]) or 0.0),
            "rimLightingMixFactor": float(_sock(out, SOCK["rimMix"]) or 0.0),
            "outlineWidthMode": outline_mode_from_int(_sock(out, SOCK["outlineMode"])),
            "outlineWidthFactor": float(_sock(out, SOCK["outlineWidth"]) or 0.0),
            "outlineColorFactor": rgb(_sock(out, SOCK["outlineColor"])),
            "outlineLightingMixFactor": float(_sock(out, SOCK["outlineMix"]) or 1.0),
            "textures": textures,
        },
    }


def dump_scene(*, only_in_use: bool = True, include_outline: bool = False) -> Dict[str, Any]:
    if bpy is None:
        raise RuntimeError("bpy required")
    materials: Dict[str, Any] = {}
    skipped: List[str] = []
    for mat in bpy.data.materials:
        if only_in_use and not mat.users:
            continue
        if not include_outline and mat.name.startswith("MToon Outline"):
            continue
        row = dump_material(mat)
        if row is None:
            skipped.append(mat.name)
            continue
        materials[mat.name] = row
    return wrap_document(materials, blend=bpy.data.filepath or "")


def dump_mtoon_sidecar(
    out_path: str,
    *,
    dry_run: bool = True,
    only_in_use: bool = True,
) -> Dict[str, Any]:
    doc = dump_scene(only_in_use=only_in_use)
    report: Dict[str, Any] = {
        "phase": "dump-mtoon-sidecar",
        "dry_run": dry_run,
        "out_path": os.path.abspath(out_path),
        "kind": KIND,
        "material_count": len(doc["materials"]),
        "materials": list(doc["materials"].keys()),
        "blend": doc.get("blend"),
    }
    if dry_run:
        report["document"] = doc
        return report
    path = os.path.abspath(out_path)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(doc, handle, indent=2)
        handle.write("\n")
    report["wrote"] = True
    return report


def restore_material_from_entry(mat, entry: Dict[str, Any]) -> List[str]:
    """Write sidecar entry back onto Mtoon1Output + image nodes (after enable wipe)."""
    if bpy is None:
        raise RuntimeError("bpy required")
    tree = mat.node_tree
    out = tree.nodes.get(MTOON_OUTPUT)
    if out is None:
        return ["missing-output"]
    changed: List[str] = []
    mtoon = entry.get("mtoon") or {}
    mapping = [
        (SOCK["lit"], entry.get("color")),
        (SOCK["shade"], with_alpha(mtoon.get("shadeColorFactor"))),
        (SOCK["emissive"], with_alpha(entry.get("emissiveFactor"))),
        (SOCK["emissiveStrength"], entry.get("emissiveStrength")),
        (SOCK["rim"], with_alpha(mtoon.get("parametricRimColorFactor"))),
        (SOCK["rimFresnel"], mtoon.get("parametricRimFresnelPowerFactor")),
        (SOCK["rimLift"], mtoon.get("parametricRimLiftFactor")),
        (SOCK["rimMix"], mtoon.get("rimLightingMixFactor")),
        (SOCK["outlineWidth"], mtoon.get("outlineWidthFactor")),
        (SOCK["outlineColor"], with_alpha(mtoon.get("outlineColorFactor"))),
        (SOCK["outlineMix"], mtoon.get("outlineLightingMixFactor")),
        (SOCK["toony"], mtoon.get("shadingToonyFactor")),
        (SOCK["shift"], mtoon.get("shadingShiftFactor")),
        (SOCK["gi"], mtoon.get("giEqualizationFactor")),
        (SOCK["matcapFactor"], with_alpha(mtoon.get("matcapFactor"))),
    ]
    from mtoon_sidecar_schema import OUTLINE_MODE_TO_INT

    mode = mtoon.get("outlineWidthMode")
    if mode in OUTLINE_MODE_TO_INT:
        mapping.append((SOCK["outlineMode"], OUTLINE_MODE_TO_INT[mode]))
    for sock_name, val in mapping:
        inp = out.inputs.get(sock_name)
        if inp is None or val is None or not hasattr(inp, "default_value"):
            continue
        try:
            if isinstance(val, list):
                inp.default_value = val[:4] if len(val) >= 3 else val
            else:
                inp.default_value = val
            changed.append(sock_name)
        except Exception:
            continue
    textures = mtoon.get("textures") or {}
    for key, node_name in IMAGE_NODES.items():
        ref = textures.get(key)
        node = tree.nodes.get(node_name)
        if node is None or node.type != "TEX_IMAGE" or not ref:
            continue
        name = ref.get("name") if isinstance(ref, dict) else None
        if not name:
            continue
        img = bpy.data.images.get(name)
        if img is not None:
            node.image = img
            changed.append(node_name)
    return changed
