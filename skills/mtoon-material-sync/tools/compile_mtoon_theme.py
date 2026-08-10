"""
Compile workspace mtoon_theme.json onto in-use MToon materials.

    result = audit_mtoon_theme(theme_path=r"D:\\...\\mtoon_theme.json")
    result = apply_mtoon_theme(theme_path=..., dry_run=False)
    result = stamp_mtoon_classes(theme_path=..., dry_run=True)
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import bpy

try:
    SKILL_ROOT = Path(__file__).resolve().parents[1]
except NameError:
    SKILL_ROOT = Path.home() / ".cursor" / "skills" / "mtoon-material-sync"
MTOON_OUTPUT = "Mtoon1Material.Mtoon1Output"
MATCAP_IMAGE_NODE = "Mtoon1MatcapTexture.Image"
SCENE_PALETTE_KEY = "mtoon_palette"
EXPR_NAME = "invertAccent"
EXPR_LEGACY_NAME = "rimPink"
COLOR_EPS = 1e-3
NONE_WHITE = "mtoon_none_white"
NONE_BLACK = "mtoon_none_black"
HIGHLIGHT_ALIASES = ("mtoon_matcap_highlight", "light_matcap")

_naming_mod = None


def _cleanup_tools_dir() -> Path:
    candidates = [
        SKILL_ROOT.parent / "vroid-vrm-blender-cleanup" / "tools",
        Path.home() / ".cursor" / "skills" / "vroid-vrm-blender-cleanup" / "tools",
    ]
    for path in candidates:
        script = path / "clean_vroid_material_names.py"
        if script.is_file():
            return path
    return candidates[0]


def _naming():
    global _naming_mod
    if _naming_mod is not None:
        return _naming_mod
    path = _cleanup_tools_dir() / "clean_vroid_material_names.py"
    import importlib.util

    spec = importlib.util.spec_from_file_location("clean_vroid_material_names", path)
    if spec is None or spec.loader is None:
        raise FileNotFoundError(str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _naming_mod = mod
    return mod


def _mtoon_node(mat: bpy.types.Material):
    if not mat or not mat.use_nodes or not mat.node_tree:
        return None
    return mat.node_tree.nodes.get(MTOON_OUTPUT)


def _iter_mtoon(only_in_use: bool = True, include_outline: bool = True) -> List[bpy.types.Material]:
    out: List[bpy.types.Material] = []
    for mat in bpy.data.materials:
        if only_in_use and not mat.users:
            continue
        if not include_outline and mat.name.startswith("MToon Outline"):
            continue
        if _mtoon_node(mat) is None:
            continue
        out.append(mat)
    return out


def _as_rgb(val: Any) -> Tuple[float, float, float]:
    try:
        seq = list(val)
        return (float(seq[0]), float(seq[1]), float(seq[2]))
    except TypeError:
        f = float(val)
        return (f, f, f)


def _as_rgba(val: Any, alpha: Optional[float] = None) -> Tuple[float, float, float, float]:
    try:
        seq = list(val)
        if len(seq) >= 3:
            if alpha is not None:
                a = float(alpha)
            elif len(seq) >= 4:
                a = float(seq[3])
            else:
                a = 1.0
            return (float(seq[0]), float(seq[1]), float(seq[2]), a)
    except TypeError:
        pass
    f = float(val)
    return (f, f, f, 1.0 if alpha is None else float(alpha))


def _rgb_close(a: Any, b: Any, eps: float = COLOR_EPS) -> bool:
    ar, ag, ab = _as_rgb(a)
    br, bg, bb = _as_rgb(b)
    return abs(ar - br) <= eps and abs(ag - bg) <= eps and abs(ab - bb) <= eps


def _is_black_rgb(val: Any) -> bool:
    r, g, b = _as_rgb(val)
    return r <= COLOR_EPS and g <= COLOR_EPS and b <= COLOR_EPS


def load_mtoon_theme(theme_path: str) -> Dict[str, Any]:
    path = Path(theme_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "groups" not in data:
        raise ValueError(f"Invalid theme JSON: {theme_path}")
    return data


def theme_hash(theme: Dict[str, Any]) -> str:
    blob = json.dumps(theme, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _socket_value(node, name: str) -> Optional[Any]:
    inp = node.inputs.get(name)
    if inp is None:
        return None
    return inp.default_value


def _set_socket(node, name: str, value: Any, *, unlink: bool = True) -> Optional[str]:
    inp = node.inputs.get(name)
    if inp is None:
        return None
    changed = False
    if unlink and inp.is_linked:
        tree = inp.id_data
        for link in list(inp.links):
            tree.links.remove(link)
        changed = True
    try:
        old = inp.default_value
        if hasattr(old, "__len__") and not isinstance(old, str):
            new = _as_rgba(value, alpha=float(old[3]) if len(old) > 3 else 1.0)
            if name in ("Outline Width Mode",) or inp.type == "INT":
                inp.default_value = int(value)
            elif inp.type == "VALUE":
                inp.default_value = float(value if not hasattr(value, "__len__") else value[0])
            else:
                inp.default_value = new
        else:
            if inp.type == "INT":
                inp.default_value = int(value)
            elif inp.type == "BOOLEAN":
                inp.default_value = bool(value)
            else:
                inp.default_value = float(value)
        if not _values_equal(old, inp.default_value):
            changed = True
    except Exception:
        try:
            inp.default_value = value
            changed = True
        except Exception:
            return None
    return name if changed else None


def _values_equal(a: Any, b: Any) -> bool:
    try:
        return tuple(a) == tuple(b)
    except TypeError:
        return a == b


def _matcap_image(mat: bpy.types.Material) -> Optional[bpy.types.Image]:
    if not mat.node_tree:
        return None
    node = mat.node_tree.nodes.get(MATCAP_IMAGE_NODE)
    if node is None or node.type != "TEX_IMAGE":
        return None
    return node.image


def _set_matcap_image(mat: bpy.types.Material, image_name: str) -> Optional[str]:
    img = bpy.data.images.get(image_name)
    if img is None:
        return f"missing_image:{image_name}"
    if not mat.node_tree:
        return "no_node_tree"
    node = mat.node_tree.nodes.get(MATCAP_IMAGE_NODE)
    if node is None or node.type != "TEX_IMAGE":
        return "no_matcap_node"
    if node.image != img:
        node.image = img
        return image_name
    return None


def _ensure_images_exist(theme: Dict[str, Any]) -> List[str]:
    missing: List[str] = []
    highlight = theme.get("groups", {}).get("highlight", {}).get("image", "mtoon_matcap_highlight")
    for name in (NONE_WHITE, highlight):
        if bpy.data.images.get(name) is None:
            missing.append(name)
    return missing


def desired_socket_plan(mat: bpy.types.Material, theme: Dict[str, Any]) -> Dict[str, Any]:
    n = _naming()
    parsed = n.parse_material_name(mat.name)
    classes = set(parsed["classes"])
    outline = bool(parsed["outline"])
    groups = theme["groups"]
    accent = theme["accent"]
    invert = theme["invertAccent"]
    rim = groups["rim"]
    outline_g = groups["outline"]
    shading = groups["shading"]
    emission = groups["emission"]
    highlight = groups.get("highlight", {})

    if "EmissionAccent" in classes and "InvertEmissionAccent" in classes:
        raise ValueError(f"{mat.name}: both EmissionAccent and InvertEmissionAccent")

    sockets: Dict[str, Any] = {
        "Parametric Rim Color": accent,
        "Parametric Rim Fresnel Power": 1000.0
        if "NoRim" in classes
        else rim.get("Parametric Rim Fresnel Power", 100),
        "Parametric Rim Lift": 0.0 if "NoRim" in classes else rim.get("Parametric Rim Lift", 0.25),
        "Rim LightingMix": rim.get("Rim LightingMix", 0.0),
        "Outline Width": outline_g.get("Outline Width", 0.001),
        "Outline Color": outline_g.get("Outline Color", [0.0392, 0.0353, 0.0745, 1.0]),
        "Emissive Factor": emission.get("Emissive Factor", [0, 0, 0, 1]),
    }
    if "NoOutline" not in classes and not outline:
        sockets["Outline Width Mode"] = int(outline_g.get("Outline Width Mode", 2))
    if not outline:
        sockets["Shading Toony"] = shading.get("Shading Toony", 0.95)
        sockets["GI Equalization Factor"] = shading.get("GI Equalization Factor", 1.0)
    if "EmissionAccent" in classes:
        sockets["Lit Color"] = accent
        sockets["Shade Color"] = accent
        sockets["Emissive Factor"] = accent
    elif "InvertEmissionAccent" in classes:
        sockets["Lit Color"] = invert
        sockets["Shade Color"] = invert
        sockets["Emissive Factor"] = invert

    hide = "Highlight" not in classes
    matcap_image = NONE_WHITE if hide else highlight.get("image", "mtoon_matcap_highlight")
    matcap_factor = [0.0, 0.0, 0.0, 1.0] if hide else highlight.get("MatCap Factor", [1, 1, 1, 1])
    sockets["MatCap Factor"] = matcap_factor

    skipped = []
    if "NoOutline" in classes or outline:
        skipped.append("Outline Width Mode")
    if outline:
        skipped.extend(["Shading Toony", "GI Equalization Factor"])

    return {
        "identity": n.dotted_workflow_to_underscore(str(parsed["identity"])),
        "classes": sorted(classes),
        "unknown_classes": list(parsed["unknown_classes"]),
        "invalid_class_dots": bool(parsed.get("invalid_class_dots")),
        "outline": outline,
        "sockets": sockets,
        "matcap_image": matcap_image,
        "skipped": skipped,
    }


def _diff_mat(mat: bpy.types.Material, plan: Dict[str, Any]) -> List[str]:
    node = _mtoon_node(mat)
    if node is None:
        return ["no_mtoon_output"]
    diffs: List[str] = []
    if plan.get("invalid_class_dots"):
        diffs.append("invalid_class_dots")
    if plan.get("unknown_classes"):
        diffs.append(f"unknown_classes:{plan['unknown_classes']}")
    for name, want in plan["sockets"].items():
        inp = node.inputs.get(name)
        if inp is None:
            continue
        cur = inp.default_value
        if name == "Outline Width Mode" or getattr(inp, "type", "") == "INT":
            if int(cur) != int(want):
                diffs.append(name)
        elif name in (
            "Parametric Rim Fresnel Power",
            "Parametric Rim Lift",
            "Rim LightingMix",
            "Outline Width",
            "Shading Toony",
            "GI Equalization Factor",
        ):
            if abs(float(cur) - float(want if not hasattr(want, "__len__") else want)) > COLOR_EPS:
                diffs.append(name)
        else:
            if not _rgb_close(cur, want):
                diffs.append(name)
    img = _matcap_image(mat)
    want_img = plan["matcap_image"]
    if img is None or img.name != want_img:
        diffs.append(f"MatCap Texture:{want_img}")
    return diffs


def audit_mtoon_theme(
    theme_path: str,
    *,
    only_in_use: bool = True,
) -> dict:
    theme = load_mtoon_theme(theme_path)
    missing_images = _ensure_images_exist(theme)
    rows: List[dict] = []
    errors: List[str] = []
    for mat in _iter_mtoon(only_in_use=only_in_use, include_outline=True):
        try:
            plan = desired_socket_plan(mat, theme)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        diffs = _diff_mat(mat, plan)
        rows.append(
            {
                "material": mat.name,
                "identity": plan["identity"],
                "classes": plan["classes"],
                "unknown_classes": plan["unknown_classes"],
                "skipped_groups": plan["skipped"],
                "diffs": diffs,
                "diff_count": len(diffs),
            }
        )
    needing = [r for r in rows if r["diff_count"]]
    return {
        "phase": "mtoon-theme-audit",
        "dry_run": True,
        "theme_path": theme_path,
        "theme_name": theme.get("name"),
        "theme_hash": theme_hash(theme),
        "missing_images": missing_images,
        "errors": errors,
        "materials_needing_sync": len(needing),
        "rows": needing,
        "all_rows": rows,
        "target_count": len(rows),
    }


def _apply_plan(mat: bpy.types.Material, plan: Dict[str, Any]) -> List[str]:
    node = _mtoon_node(mat)
    if node is None:
        return []
    changed: List[str] = []
    for name, want in plan["sockets"].items():
        unlink = name not in ("MatCap Factor",)
        hit = _set_socket(node, name, want, unlink=unlink)
        if hit:
            changed.append(hit)
    img_err = _set_matcap_image(mat, plan["matcap_image"])
    if img_err and not img_err.startswith("missing") and not img_err.startswith("no_"):
        changed.append(f"MatCap Texture:{img_err}")
    elif img_err and (img_err.startswith("missing") or img_err.startswith("no_")):
        changed.append(img_err)
    return changed


def _find_invert_expression():
    for arm in bpy.data.armatures:
        ext = getattr(arm, "vrm_addon_extension", None)
        if ext is None:
            continue
        is_vrm1 = getattr(ext, "is_vrm1", None)
        try:
            ok = is_vrm1() if callable(is_vrm1) else bool(getattr(ext, "vrm1", None))
        except Exception:
            ok = bool(getattr(ext, "vrm1", None))
        if not ok:
            continue
        exprs = ext.vrm1.expressions
        mapping = exprs.all_name_to_expression_dict()
        for key in (EXPR_NAME, EXPR_LEGACY_NAME):
            if key in mapping:
                return mapping[key], key
    return None, None


def sync_invert_accent_expression(theme: Dict[str, Any], *, dry_run: bool = True) -> dict:
    expr, found_name = _find_invert_expression()
    if expr is None:
        return {"error": "invertAccent/rimPink expression not found", "binds": []}
    accent = theme["accent"]
    invert = theme["invertAccent"]
    bind_map = (
        ("rimColor", "Parametric Rim Color", 0.0),
        ("color", "Lit Color", 1.0),
        ("shadeColor", "Shade Color", 1.0),
        ("emissionColor", "Emissive Factor", 1.0),
    )
    planned: List[dict] = []
    for mat in _iter_mtoon(only_in_use=True, include_outline=False):
        node = _mtoon_node(mat)
        if node is None:
            continue
        for bind_type, socket, alpha in bind_map:
            inp = node.inputs.get(socket)
            if inp is None:
                continue
            rest = inp.default_value
            if _rgb_close(rest, accent):
                target = _as_rgba(invert, alpha=alpha)
            elif _rgb_close(rest, invert):
                target = _as_rgba(accent, alpha=alpha)
            else:
                continue
            planned.append(
                {
                    "material": mat.name,
                    "type": bind_type,
                    "target_value": list(target),
                }
            )

    report = {
        "expression_found_as": found_name,
        "expression_name": EXPR_NAME,
        "bind_count": len(planned),
        "binds": planned,
        "renamed": found_name != EXPR_NAME,
    }
    if dry_run:
        return report

    if getattr(expr, "custom_name", None) != EXPR_NAME:
        expr.custom_name = EXPR_NAME
    binds = expr.material_color_binds
    while len(binds):
        binds.remove(0)
    for item in planned:
        mat = bpy.data.materials.get(item["material"])
        if mat is None:
            continue
        b = binds.add()
        b.material = mat
        b.type = item["type"]
        b.target_value = item["target_value"]
    report["applied"] = True
    return report


def apply_mtoon_theme(
    theme_path: str,
    *,
    dry_run: bool = True,
    only_in_use: bool = True,
    sync_expression: bool = True,
) -> dict:
    audit = audit_mtoon_theme(theme_path, only_in_use=only_in_use)
    theme = load_mtoon_theme(theme_path)
    expr_report = (
        sync_invert_accent_expression(theme, dry_run=True) if sync_expression else {}
    )
    audit["expression"] = expr_report
    if dry_run:
        return audit

    updated: List[dict] = []
    errors: List[str] = list(audit.get("errors") or [])
    for mat in _iter_mtoon(only_in_use=only_in_use, include_outline=True):
        try:
            plan = desired_socket_plan(mat, theme)
        except ValueError as exc:
            msg = str(exc)
            if msg not in errors:
                errors.append(msg)
            continue
        changed = _apply_plan(mat, plan)
        if changed:
            updated.append({"material": mat.name, "changed": changed})

    if sync_expression:
        expr_report = sync_invert_accent_expression(theme, dry_run=False)

    scene = bpy.context.scene
    if scene is not None:
        scene[SCENE_PALETTE_KEY] = json.dumps(
            {
                "theme_path": os.path.basename(theme_path),
                "theme_name": theme.get("name"),
                "applied_hash": theme_hash(theme),
            },
            sort_keys=True,
        )

    verify = audit_mtoon_theme(theme_path, only_in_use=only_in_use)
    return {
        **audit,
        "phase": "mtoon-theme-apply",
        "dry_run": False,
        "errors": errors,
        "updated_count": len(updated),
        "updated": updated,
        "expression": expr_report,
        "remaining_materials_needing_sync": verify.get("materials_needing_sync", 0),
        "remaining_rows": verify.get("rows", []),
    }


def extract_mtoon_theme(
    reference_material: str = "Face_Skin",
    out_path: Optional[str] = None,
) -> dict:
    n = _naming()
    mat = n.resolve_material_by_token(reference_material)
    node = _mtoon_node(mat) if mat else None
    if mat is None or node is None:
        return {"error": f"reference not found: {reference_material}"}
    rim_c = list(_as_rgba(_socket_value(node, "Parametric Rim Color") or (1, 1, 1, 1)))
    theme = {
        "name": "extracted",
        "accent": rim_c,
        "invertAccent": [0.7991, 0.006, 0.4072, 1.0],
        "groups": {
            "rim": {
                "Parametric Rim Color": rim_c,
                "Parametric Rim Fresnel Power": float(
                    _socket_value(node, "Parametric Rim Fresnel Power") or 100
                ),
                "Parametric Rim Lift": float(_socket_value(node, "Parametric Rim Lift") or 0.25),
                "Rim LightingMix": float(_socket_value(node, "Rim LightingMix") or 0.0),
            },
            "outline": {
                "Outline Width Mode": int(_socket_value(node, "Outline Width Mode") or 2),
                "Outline Width": float(_socket_value(node, "Outline Width") or 0.001),
                "Outline Color": list(
                    _as_rgba(_socket_value(node, "Outline Color") or (0.0392, 0.0353, 0.0745, 1))
                ),
            },
            "shading": {
                "Shading Toony": float(_socket_value(node, "Shading Toony") or 0.95),
                "GI Equalization Factor": float(
                    _socket_value(node, "GI Equalization Factor") or 1.0
                ),
            },
            "emission": {"Emissive Factor": [0, 0, 0, 1]},
            "highlight": {
                "image": "mtoon_matcap_highlight",
                "MatCap Factor": [1, 1, 1, 1],
            },
        },
    }
    if out_path:
        Path(out_path).write_text(json.dumps(theme, indent=2) + "\n", encoding="utf-8")
    return {"theme": theme, "out_path": out_path, "reference": mat.name}


def _read_outline_mode(mat: bpy.types.Material) -> Optional[int]:
    node = _mtoon_node(mat)
    if node is None:
        return None
    inp = node.inputs.get("Outline Width Mode")
    if inp is None:
        return None
    return int(inp.default_value)


def stamp_mtoon_classes(
    theme_path: Optional[str] = None,
    *,
    dry_run: bool = True,
    only_in_use: bool = True,
) -> dict:
    n = _naming()
    theme = load_mtoon_theme(theme_path) if theme_path else None
    accent = theme["accent"] if theme else (0.0168, 0.7157, 0.7991, 1.0)
    invert = theme["invertAccent"] if theme else (0.7991, 0.006, 0.4072, 1.0)

    rows: List[dict] = []
    mapping: Dict[str, str] = {}
    base_new_by_old: Dict[str, str] = {}
    base_new_by_ident: Dict[str, str] = {}
    outline_mats: List[bpy.types.Material] = []

    for mat in _iter_mtoon(only_in_use=only_in_use, include_outline=True):
        parsed = n.parse_material_name(mat.name)
        if parsed["outline"]:
            outline_mats.append(mat)
            continue

        ident = n.dotted_workflow_to_underscore(str(parsed["identity"]))
        classes = list(parsed["classes"])

        if ident.endswith("_Matcap"):
            ident = ident[: -len("_Matcap")]
            if "Highlight" not in classes:
                classes.append("Highlight")

        node = _mtoon_node(mat)
        if node is None:
            continue

        mode = _read_outline_mode(mat)
        width = node.inputs.get("Outline Width")
        width_v = float(width.default_value) if width else 1.0
        if mode == 0 or width_v == 0.0:
            if "NoOutline" not in classes:
                classes.append("NoOutline")

        rim = node.inputs.get("Parametric Rim Color")
        lift = node.inputs.get("Parametric Rim Lift")
        if rim is not None and _is_black_rgb(rim.default_value):
            if "NoRim" not in classes:
                classes.append("NoRim")
        elif lift is not None and abs(float(lift.default_value)) <= COLOR_EPS:
            if "NoRim" not in classes:
                classes.append("NoRim")

        img = _matcap_image(mat)
        if img is not None and img.name in HIGHLIGHT_ALIASES:
            if "Highlight" not in classes:
                classes.append("Highlight")

        lit = node.inputs.get("Lit Color")
        shade = node.inputs.get("Shade Color")
        emis = node.inputs.get("Emissive Factor")
        if lit and shade and emis:
            if (
                _rgb_close(lit.default_value, accent)
                and _rgb_close(shade.default_value, accent)
                and _rgb_close(emis.default_value, accent)
            ):
                if "InvertEmissionAccent" not in classes and "EmissionAccent" not in classes:
                    classes.append("EmissionAccent")
            elif (
                _rgb_close(lit.default_value, invert)
                and _rgb_close(shade.default_value, invert)
                and _rgb_close(emis.default_value, invert)
            ):
                if "EmissionAccent" not in classes and "InvertEmissionAccent" not in classes:
                    classes.append("InvertEmissionAccent")

        new_name = n.rebuild_material_name(
            ident,
            classes,
            outline=False,
            dup=str(parsed["dup"]),
        )
        base_new_by_old[mat.name] = new_name
        base_new_by_ident[ident] = new_name
        if new_name != mat.name:
            mapping[mat.name] = new_name
        rows.append({"old": mat.name, "new": new_name, "classes": classes, "identity": ident})

    for mat in outline_mats:
        parsed = n.parse_material_name(mat.name)
        inner_old = mat.name[len(n.OUTLINE_PREFIX) : -1] if mat.name.startswith(n.OUTLINE_PREFIX) else mat.name
        ident = n.dotted_workflow_to_underscore(str(parsed["identity"]))
        if inner_old in base_new_by_old:
            new_inner = base_new_by_old[inner_old]
        elif ident in base_new_by_ident:
            new_inner = base_new_by_ident[ident]
        else:
            new_inner = n.rebuild_material_name(
                ident,
                list(parsed["classes"]),
                outline=False,
                dup=str(parsed["dup"]),
            )
        new_name = f"{n.OUTLINE_PREFIX}{new_inner})"
        wrap_parsed = n.parse_material_name(new_name)
        if new_name != mat.name:
            mapping[mat.name] = new_name
        rows.append(
            {
                "old": mat.name,
                "new": new_name,
                "classes": list(wrap_parsed["classes"]),
                "identity": wrap_parsed["identity"],
            }
        )

    if dry_run:
        return {
            "phase": "mtoon-stamp-audit",
            "dry_run": True,
            "count": len(mapping),
            "mapping": mapping,
            "rows": rows,
        }

    renamed: List[Tuple[str, str]] = []
    for mat in list(bpy.data.materials):
        new_name = mapping.get(mat.name)
        if not new_name or new_name == mat.name:
            continue
        new_name = n.unique_material_name(new_name, mat)
        old = mat.name
        mat.name = new_name
        renamed.append((old, new_name))

    return {
        "phase": "mtoon-stamp-apply",
        "dry_run": False,
        "renamed_count": len(renamed),
        "renamed": renamed,
        "rows": rows,
    }


def run_phase_j_theme(
    theme_path: str,
    *,
    dry_run: bool = True,
) -> dict:
    result = apply_mtoon_theme(theme_path, dry_run=dry_run)
    result["phase"] = "J"
    result["phase_letter"] = "J"
    result["mode"] = "theme"
    return result
