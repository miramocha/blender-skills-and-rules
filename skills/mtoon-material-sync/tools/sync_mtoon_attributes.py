"""
Sync MToon 1.0 look attributes (rim + shading) across materials from a reference.

Run via MCP execute_blender_code or Blender Scripting workspace:

    result = audit_mtoon_sync(reference_material="Face.Skin")
    result = apply_mtoon_sync(reference_material="Face.Skin", dry_run=False)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple, Union

import bpy

SKILL_ROOT = Path(__file__).resolve().parents[1]
_phase_b_resolve_fn: Optional[Callable[..., Any]] = None


def _cleanup_tools_dir() -> Path:
    """Prefer repo sibling cleanup tools with workflow resolver over stale home copy."""
    candidates = [
        SKILL_ROOT.parent / "vroid-vrm-blender-cleanup" / "tools",
        Path.home() / ".cursor" / "skills" / "vroid-vrm-blender-cleanup" / "tools",
    ]
    for path in candidates:
        script = path / "clean_vroid_material_names.py"
        if not script.is_file():
            continue
        text = script.read_text(encoding="utf-8")
        if "standardize_workflow_tail" in text and "resolve_material_by_token" in text:
            return path
    for path in candidates:
        if (path / "clean_vroid_material_names.py").is_file():
            return path
    return candidates[0]


def _phase_b_resolve_material(token: str) -> Optional[bpy.types.Material]:
    """Delegate to vroid-vrm-blender-cleanup Phase B material resolver."""
    global _phase_b_resolve_fn
    path = _cleanup_tools_dir() / "clean_vroid_material_names.py"
    if _phase_b_resolve_fn is None or getattr(_phase_b_resolve_fn, "__file__", "") != str(path):
        import importlib.util

        if not path.is_file():
            return None
        spec = importlib.util.spec_from_file_location("clean_vroid_material_names", path)
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        fn = getattr(mod, "resolve_material_by_token", None)
        if not callable(fn):
            return None
        _phase_b_resolve_fn = fn
        setattr(_phase_b_resolve_fn, "__file__", str(path))
    return _phase_b_resolve_fn(token)

MTOON_OUTPUT_NODE = "Mtoon1Material.Mtoon1Output"
DEFAULT_REFERENCE_MATERIAL = "Face.Skin"

# Inputs copied for a consistent rim look (parametric values only; not texture links).
RIM_INPUTS: Tuple[str, ...] = (
    "Parametric Rim Color",
    "Parametric Rim Fresnel Power",
    "Parametric Rim Lift",
    "Rim LightingMix",
    "Rim Color Texture",
    "Expression Rim Color Bind",
)

# Toon shading params synced from reference. Shading Shift is intentionally excluded —
# face skin usually uses a different shift than body/hair/cloth; keep per-material.
SHADING_INPUTS: Tuple[str, ...] = (
    "Shading Toony",
    "Shading Shift Texture Scale",
    "Expression Shade Color Bind",
)

SYNC_GROUPS: Dict[str, Tuple[str, ...]] = {
    "rim": RIM_INPUTS,
    "shading": SHADING_INPUTS,
}

Scalar = Union[int, float]
Value = Union[Scalar, Sequence[Scalar]]


def _copy_value(val: Value) -> Value:
    try:
        return val[:]  # type: ignore[index]
    except TypeError:
        return val


def _as_tuple(val: Value) -> Tuple[Scalar, ...]:
    try:
        return tuple(val)  # type: ignore[arg-type]
    except TypeError:
        return (val,)  # type: ignore[return-value]


def _values_equal(a: Value, b: Value) -> bool:
    return _as_tuple(a) == _as_tuple(b)


def _resolve_groups(groups: Optional[Iterable[str]] = None) -> List[str]:
    if groups is None:
        return ["rim", "shading"]
    chosen = [g.lower() for g in groups]
    unknown = [g for g in chosen if g not in SYNC_GROUPS]
    if unknown:
        raise ValueError(f"Unknown sync group(s): {unknown}. Use: {sorted(SYNC_GROUPS)}")
    return chosen


def _input_names_for_groups(groups: Sequence[str]) -> List[str]:
    names: List[str] = []
    seen: Set[str] = set()
    for group in groups:
        for name in SYNC_GROUPS[group]:
            if name not in seen:
                names.append(name)
                seen.add(name)
    return names


def _mtoon_output_node(mat: bpy.types.Material) -> Optional[bpy.types.Node]:
    if not mat or not mat.use_nodes or not mat.node_tree:
        return None
    node = mat.node_tree.nodes.get(MTOON_OUTPUT_NODE)
    return node


def resolve_material_by_token(token: str) -> Optional[bpy.types.Material]:
    """Phase B workflow/VRoid resolver first, then MToon substring fallback."""
    if not token:
        return None

    mat = _phase_b_resolve_material(token)
    if mat is not None:
        return mat if _mtoon_output_node(mat) else None

    candidates = [
        m
        for m in bpy.data.materials
        if token in m.name
        and _mtoon_output_node(m)
        and not m.name.startswith("MToon Outline")
    ]
    if not candidates:
        candidates = [
            m for m in bpy.data.materials if token in m.name and _mtoon_output_node(m)
        ]
    if not candidates:
        return None
    return min(candidates, key=lambda m: (m.name != token, len(m.name), m.name))


def _iter_target_materials(
    *,
    reference_material: str,
    resolved_reference_name: Optional[str] = None,
    only_in_use: bool = True,
    include_outline: bool = False,
) -> List[bpy.types.Material]:
    skip_name = resolved_reference_name or reference_material
    targets: List[bpy.types.Material] = []
    for mat in bpy.data.materials:
        if mat.name == skip_name:
            continue
        if only_in_use and not mat.users:
            continue
        if not include_outline and mat.name.startswith("MToon Outline"):
            continue
        if _mtoon_output_node(mat) is None:
            continue
        targets.append(mat)
    return targets


def _read_input_value(inp: bpy.types.NodeSocket) -> dict:
    if inp.is_linked:
        link = inp.links[0]
        from_node = link.from_node
        payload: dict = {
            "linked": True,
            "from_node": from_node.name,
            "from_socket": link.from_socket.name,
        }
        if from_node.type == "TEX_IMAGE" and from_node.image:
            payload["image"] = from_node.image.name
        return payload
    return {"linked": False, "default": _copy_value(inp.default_value)}


def extract_mtoon_values(
    material_name: str,
    input_names: Sequence[str],
) -> Optional[dict]:
    mat = resolve_material_by_token(material_name)
    node = _mtoon_output_node(mat) if mat else None
    if not node or not mat:
        return None

    values: Dict[str, dict] = {}
    for name in input_names:
        inp = node.inputs.get(name)
        if inp is None:
            values[name] = {"missing": True}
            continue
        values[name] = _read_input_value(inp)
    return {
        "material": mat.name,
        "values": values,
    }


def _diff_values(reference: dict, current: dict) -> List[str]:
    diffs: List[str] = []
    for name, ref_entry in reference.items():
        cur = current.get(name)
        if not cur:
            diffs.append(f"missing:{name}")
            continue
        if cur.get("missing"):
            diffs.append(f"missing:{name}")
            continue
        if ref_entry.get("linked") != cur.get("linked"):
            diffs.append(name)
            continue
        if ref_entry.get("linked"):
            if ref_entry.get("image") != cur.get("image"):
                diffs.append(f"{name}:texture")
            continue
        if not _values_equal(ref_entry.get("default"), cur.get("default")):
            diffs.append(name)
    return diffs


def audit_mtoon_sync(
    reference_material: str = DEFAULT_REFERENCE_MATERIAL,
    *,
    groups: Optional[Iterable[str]] = None,
    only_in_use: bool = True,
    include_outline: bool = False,
) -> dict:
    group_list = _resolve_groups(groups)
    input_names = _input_names_for_groups(group_list)

    ref_extract = extract_mtoon_values(reference_material, input_names)
    if not ref_extract:
        return {
            "phase": "mtoon-sync-audit",
            "error": f"reference material not found or has no {MTOON_OUTPUT_NODE} (token: {reference_material})",
        }

    ref_values = ref_extract["values"]
    resolved_reference = ref_extract["material"]
    rows: List[dict] = []
    for mat in _iter_target_materials(
        reference_material=reference_material,
        resolved_reference_name=resolved_reference,
        only_in_use=only_in_use,
        include_outline=include_outline,
    ):
        cur_extract = extract_mtoon_values(mat.name, input_names)
        if not cur_extract:
            continue
        diffs = _diff_values(ref_values, cur_extract["values"])
        if diffs:
            rows.append(
                {
                    "material": mat.name,
                    "diff_count": len(diffs),
                    "diffs": diffs,
                }
            )

    return {
        "phase": "mtoon-sync-audit",
        "dry_run": True,
        "reference_material": resolved_reference,
        "reference_token": reference_material,
        "groups": group_list,
        "input_names": input_names,
        "reference_values": ref_values,
        "materials_needing_sync": len(rows),
        "rows": rows,
        "target_count": len(
            _iter_target_materials(
                reference_material=reference_material,
                resolved_reference_name=resolved_reference,
                only_in_use=only_in_use,
                include_outline=include_outline,
            )
        ),
    }


def _apply_input_value(
    inp: bpy.types.NodeSocket,
    ref_entry: dict,
) -> bool:
    if ref_entry.get("missing"):
        return False

    changed = False
    if not ref_entry.get("linked"):
        if inp.is_linked:
            tree = inp.id_data
            for link in list(inp.links):
                tree.links.remove(link)
            changed = True
        old = _copy_value(inp.default_value)
        new = ref_entry["default"]
        inp.default_value = new
        if not _values_equal(old, new):
            changed = True
        return changed

    # Reference uses a linked socket — only mirror simple image links.
    if inp.is_linked:
        link = inp.links[0]
        from_node = link.from_node
        if (
            from_node.type == "TEX_IMAGE"
            and ref_entry.get("from_node") == from_node.name
            and ref_entry.get("image")
            and from_node.image
            and from_node.image.name == ref_entry.get("image")
        ):
            return False
    return False


def apply_mtoon_sync(
    reference_material: str = DEFAULT_REFERENCE_MATERIAL,
    *,
    groups: Optional[Iterable[str]] = None,
    only_in_use: bool = True,
    include_outline: bool = False,
    dry_run: bool = True,
) -> dict:
    audit = audit_mtoon_sync(
        reference_material=reference_material,
        groups=groups,
        only_in_use=only_in_use,
        include_outline=include_outline,
    )
    if audit.get("error"):
        return audit
    if dry_run:
        return audit

    ref_values = audit["reference_values"]
    resolved_reference = audit.get("reference_material", reference_material)
    updated: List[dict] = []
    skipped: List[dict] = []

    for mat in _iter_target_materials(
        reference_material=reference_material,
        resolved_reference_name=resolved_reference,
        only_in_use=only_in_use,
        include_outline=include_outline,
    ):
        node = _mtoon_output_node(mat)
        if not node:
            skipped.append({"material": mat.name, "reason": "no_mtoon_output"})
            continue

        changed_inputs: List[str] = []
        for name, ref_entry in ref_values.items():
            inp = node.inputs.get(name)
            if inp is None:
                continue
            if _apply_input_value(inp, ref_entry):
                changed_inputs.append(name)

        if changed_inputs:
            updated.append({"material": mat.name, "changed": changed_inputs})

    verify = audit_mtoon_sync(
        reference_material=reference_material,
        groups=groups,
        only_in_use=only_in_use,
        include_outline=include_outline,
    )

    return {
        **audit,
        "phase": "mtoon-sync-apply",
        "dry_run": False,
        "updated_count": len(updated),
        "updated": updated,
        "skipped": skipped,
        "remaining_materials_needing_sync": verify.get("materials_needing_sync", 0),
        "remaining_rows": verify.get("rows", []),
    }


def run_mtoon_sync(
    reference_material: str = DEFAULT_REFERENCE_MATERIAL,
    *,
    groups: Optional[Iterable[str]] = None,
    only_in_use: bool = True,
    include_outline: bool = False,
    dry_run: bool = True,
) -> dict:
    if dry_run:
        return audit_mtoon_sync(
            reference_material=reference_material,
            groups=groups,
            only_in_use=only_in_use,
            include_outline=include_outline,
        )
    return apply_mtoon_sync(
        reference_material=reference_material,
        groups=groups,
        only_in_use=only_in_use,
        include_outline=include_outline,
        dry_run=False,
    )


def run_phase_j(
    reference_material: str = DEFAULT_REFERENCE_MATERIAL,
    *,
    groups: Optional[Iterable[str]] = None,
    include_outline: bool = False,
    dry_run: bool = True,
) -> dict:
    """Pipeline Phase J — sync MToon rim + shading from reference material."""
    result = run_mtoon_sync(
        reference_material=reference_material,
        groups=groups,
        include_outline=include_outline,
        dry_run=dry_run,
    )
    result["phase"] = "J"
    result["phase_letter"] = "J"
    return result


if __name__ == "__main__":
    result = run_mtoon_sync(dry_run=True)
