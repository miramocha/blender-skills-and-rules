"""
Sync MToon 1.0 look attributes (rim + shading) across materials from a reference.

Run via MCP execute_blender_code or Blender Scripting workspace:

    result = audit_mtoon_sync(reference_material="Face_00_SKIN (Instance)")
    result = apply_mtoon_sync(reference_material="Face_00_SKIN (Instance)", dry_run=False)
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple, Union

import bpy

MTOON_OUTPUT_NODE = "Mtoon1Material.Mtoon1Output"
DEFAULT_REFERENCE_MATERIAL = "Face_00_SKIN (Instance)"
SHADING_TOONY_TARGET = 0.95
GI_EQUALIZATION_TARGET = 1.0
EMISSIVE_FACTOR_TARGET: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)

Scalar = Union[int, float]
Value = Union[Scalar, Sequence[Scalar]]

# Project rule: fixed targets (not copied from reference).
FIXED_INPUT_DEFAULTS: Dict[str, Value] = {
    "Shading Toony": SHADING_TOONY_TARGET,
    "GI Equalization Factor": GI_EQUALIZATION_TARGET,
    "Emissive Factor": EMISSIVE_FACTOR_TARGET,
}

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
    "GI Equalization Factor",
    "Shading Toony",
    "Shading Shift Texture Scale",
    "Expression Shade Color Bind",
)

EMISSION_INPUTS: Tuple[str, ...] = (
    "Emissive Factor",
)

SYNC_GROUPS: Dict[str, Tuple[str, ...]] = {
    "rim": RIM_INPUTS,
    "shading": SHADING_INPUTS,
    "emission": EMISSION_INPUTS,
}

def _apply_fixed_input_defaults(values: Dict[str, dict]) -> Dict[str, dict]:
    patched = {name: dict(entry) for name, entry in values.items()}
    for name, target in FIXED_INPUT_DEFAULTS.items():
        entry = patched.get(name)
        if not entry or entry.get("missing"):
            continue
        entry["linked"] = False
        entry["default"] = target
        patched[name] = entry
    return patched


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
        return ["rim", "shading", "emission"]
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


def _iter_target_materials(
    *,
    reference_material: str,
    only_in_use: bool = True,
    include_outline: bool = False,
) -> List[bpy.types.Material]:
    targets: List[bpy.types.Material] = []
    for mat in bpy.data.materials:
        if mat.name == reference_material:
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
    mat = bpy.data.materials.get(material_name)
    node = _mtoon_output_node(mat) if mat else None
    if not node:
        return None

    values: Dict[str, dict] = {}
    for name in input_names:
        inp = node.inputs.get(name)
        if inp is None:
            values[name] = {"missing": True}
            continue
        values[name] = _read_input_value(inp)
    return {
        "material": material_name,
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
            "error": f"reference material not found or has no {MTOON_OUTPUT_NODE}: {reference_material}",
        }

    ref_values = _apply_fixed_input_defaults(ref_extract["values"])
    rows: List[dict] = []
    for mat in _iter_target_materials(
        reference_material=reference_material,
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
        "reference_material": reference_material,
        "groups": group_list,
        "input_names": input_names,
        "reference_values": ref_values,
        "materials_needing_sync": len(rows),
        "rows": rows,
        "target_count": len(
            _iter_target_materials(
                reference_material=reference_material,
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
    updated: List[dict] = []
    skipped: List[dict] = []

    ref_mat = bpy.data.materials.get(reference_material)
    if ref_mat:
        ref_node = _mtoon_output_node(ref_mat)
        if ref_node:
            changed_inputs: List[str] = []
            for name, target in FIXED_INPUT_DEFAULTS.items():
                if name not in ref_values:
                    continue
                inp = ref_node.inputs.get(name)
                if inp is None:
                    continue
                if _apply_input_value(inp, ref_values[name]):
                    changed_inputs.append(name)
            if changed_inputs:
                updated.append(
                    {"material": ref_mat.name, "changed": changed_inputs, "reference": True}
                )

    for mat in _iter_target_materials(
        reference_material=reference_material,
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
