"""UV-keyed tri→quad topology replay for Blender meshes.

Portable across mesh imports that share the same UV layout (VRoid face, body, etc.).
Uses dissolve on matched UV edge pairs — not tris_convert_to_quads.

When extracting a mesh by material slot, profiles may set `material_token` (e.g. Face.Skin).
`apply_profile` resolves it via Phase B `resolve_material_by_token()` and only dissolves
edges on that material slot. Returns `{skipped: True, reason: ...}` when the map CSV is
missing/empty or the material is not on the target object.

MCP / Scripting:
  import tri_to_quad_uv_map as tq
  tq.export_reference("face", src_obj="Face.only", dst_obj="Face.only.quad")
  result = tq.apply_profile("face", target_obj="Face", dry_run=True)
  if result.get("skipped"):
      print(result["reason"])
  tq.apply_profile("face", target_obj="Face", dry_run=False)
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional, Set

import bmesh

try:
    import bpy
except ImportError:  # pragma: no cover
    bpy = None  # type: ignore

SKILL_ROOT = Path(__file__).resolve().parents[1]
PROFILES_DIR = SKILL_ROOT / "profiles"
MAPS_DIR = SKILL_ROOT / "maps"
CLEANUP_TOOLS = SKILL_ROOT.parent / "vroid-vrm-blender-cleanup" / "tools"

DEFAULT_UV_PREC = 4
DEFAULT_CO_PREC = 6
CSV_HEADER = ("u1", "v1", "u2", "v2")


@dataclass
class Profile:
    """Per mesh-region config (face, body, hair, …)."""

    profile: str
    label: str = ""
    uv_layer: str = "UVMap"
    uv_precision: int = DEFAULT_UV_PREC
    co_precision: int = DEFAULT_CO_PREC
    map_file: str = ""
    notes: str = ""
    material_token: str = ""
    reference: dict[str, str] = field(default_factory=dict)

    @property
    def map_path(self) -> Path:
        if self.map_file:
            p = Path(self.map_file)
            return p if p.is_absolute() else SKILL_ROOT / p
        return MAPS_DIR / f"{self.profile}-quad-dissolve.csv"

    @classmethod
    def load(cls, profile: str, profiles_dir: Path | None = None) -> Profile:
        root = profiles_dir or PROFILES_DIR
        path = root / f"{profile}.json"
        if not path.is_file():
            raise FileNotFoundError(f"Profile not found: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            profile=data["profile"],
            label=data.get("label", ""),
            uv_layer=data.get("uv_layer", "UVMap"),
            uv_precision=int(data.get("uv_precision", DEFAULT_UV_PREC)),
            co_precision=int(data.get("co_precision", DEFAULT_CO_PREC)),
            map_file=data.get("map_file", ""),
            notes=data.get("notes", ""),
            material_token=data.get("material_token", ""),
            reference=data.get("reference", {}),
        )


_resolve_material_fn: Optional[Callable[..., Any]] = None


def _resolve_material_by_token(token: str) -> Any:
    """Delegate to vroid-vrm-blender-cleanup Phase B material resolver."""
    global _resolve_material_fn
    if _resolve_material_fn is None:
        import importlib.util

        path = CLEANUP_TOOLS / "clean_vroid_material_names.py"
        if not path.is_file():
            raise FileNotFoundError(f"Phase B material tools not found: {path}")
        spec = importlib.util.spec_from_file_location("clean_vroid_material_names", path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load {path}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _resolve_material_fn = mod.resolve_material_by_token
    return _resolve_material_fn(token)


def material_slot_indices(obj: Any, material: Any) -> Set[int]:
    """Slot indices on mesh object that use this material datablock."""
    if material is None or obj.type != "MESH":
        return set()
    return {i for i, slot in enumerate(obj.material_slots) if slot.material == material}


def audit_material_on_object(
    obj_name: str,
    material_token: str,
) -> dict[str, Any]:
    """Check map token resolves and which slots on the object use it."""
    obj = bpy.data.objects.get(obj_name)
    if not obj or obj.type != "MESH":
        return {
            "object": obj_name,
            "material_token": material_token,
            "found": False,
            "error": "mesh_object_not_found",
        }
    mat = _resolve_material_by_token(material_token)
    if mat is None:
        return {
            "object": obj_name,
            "material_token": material_token,
            "found": False,
            "error": "material_not_found",
        }
    slots = sorted(material_slot_indices(obj, mat))
    face_count = sum(1 for p in obj.data.polygons if p.material_index in slots) if slots else 0
    return {
        "object": obj_name,
        "material_token": material_token,
        "material_name": mat.name,
        "found": bool(slots),
        "slot_indices": slots,
        "face_count": face_count,
    }


def audit_profile_ready(
    profile_name: str,
    target_obj: str,
    *,
    profiles_dir: Path | None = None,
) -> dict[str, Any]:
    """Dry readiness check: profile, map file, optional material on object."""
    try:
        prof = Profile.load(profile_name, profiles_dir)
    except FileNotFoundError as exc:
        return {"ready": False, "reason": "profile_not_found", "error": str(exc)}

    path = prof.map_path
    if not path.is_file():
        return {
            "ready": False,
            "reason": "map_not_found",
            "profile": profile_name,
            "object": target_obj,
            "map": str(path),
        }

    data = load_map(path)
    targets = _iter_target_edges(data)
    if not targets:
        return {
            "ready": False,
            "reason": "empty_map",
            "profile": profile_name,
            "object": target_obj,
            "map": str(path),
        }

    out: dict[str, Any] = {
        "ready": True,
        "profile": profile_name,
        "object": target_obj,
        "map": str(path),
        "join_count": len(targets),
    }
    if prof.material_token:
        out["material"] = audit_material_on_object(target_obj, prof.material_token)
        if not out["material"].get("found"):
            out["ready"] = False
            out["reason"] = out["material"].get("error", "material_not_ready")
    return out


def _skip_result(
    *,
    reason: str,
    profile: str = "",
    target_obj: str = "",
    map_path: str = "",
    material_token: str = "",
    **extra: Any,
) -> dict[str, Any]:
    return {
        "skipped": True,
        "reason": reason,
        "profile": profile,
        "object": target_obj,
        "map": map_path,
        "material_token": material_token,
        **extra,
    }


def _uv_key(uv, prec: int) -> tuple[float, float]:
    return (round(uv.x, prec), round(uv.y, prec))


def _co_key(v, prec: int) -> tuple[float, float, float]:
    return (round(v.co.x, prec), round(v.co.y, prec), round(v.co.z, prec))


def _load_bm(obj_name: str) -> bmesh.types.BMesh:
    obj = bpy.data.objects[obj_name]
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.verts.ensure_lookup_table()
    return bm


def _get_bmesh(obj_name: str) -> tuple[Any, bmesh.types.BMesh, bool]:
    obj = bpy.data.objects[obj_name]
    if obj.mode == "EDIT":
        return obj, bmesh.from_edit_mesh(obj.data), True
    return obj, _load_bm(obj_name), False


def _write_bmesh(obj, bm: bmesh.types.BMesh, in_edit_mode: bool) -> None:
    if in_edit_mode:
        bmesh.update_edit_mesh(obj.data, destructive=True)
    else:
        bm.to_mesh(obj.data)
        obj.data.update()
        bm.free()


def _edge_uv_keys(edge, uv_layer, prec: int) -> frozenset[tuple[float, float]]:
    return frozenset(_uv_key(loop[uv_layer].uv, prec) for loop in edge.link_loops)


def extract_dissolve_edges(
    src_name: str,
    dst_name: str,
    *,
    uv_layer: str = "UVMap",
    uv_precision: int = DEFAULT_UV_PREC,
    co_precision: int = DEFAULT_CO_PREC,
    include_quad_uv: bool = False,
) -> list[dict[str, Any]]:
    """Pair each result quad with the dissolved UV edge from the tri source mesh."""
    src = _load_bm(src_name)
    dst = _load_bm(dst_name)
    suv = src.loops.layers.uv.get(uv_layer) or src.loops.layers.uv.active
    duv = dst.loops.layers.uv.get(uv_layer) or dst.loops.layers.uv.active
    if suv is None or duv is None:
        src.free()
        dst.free()
        raise ValueError(f"UV layer {uv_layer!r} missing on source or result mesh")

    joins: list[dict[str, Any]] = []
    for q in dst.faces:
        if len(q.verts) != 4:
            continue
        q_cos = frozenset(_co_key(v, co_precision) for v in q.verts)
        src_tris = [
            f
            for f in src.faces
            if len(f.verts) == 3 and frozenset(_co_key(v, co_precision) for v in f.verts) <= q_cos
        ]
        if len(src_tris) != 2:
            continue
        a, b = src_tris
        shared = set(a.edges) & set(b.edges)
        if not shared:
            continue
        e = next(iter(shared))
        ev = {_co_key(v, co_precision) for v in e.verts}
        edge_uv = sorted(
            {
                _uv_key(l[suv].uv, uv_precision)
                for f in (a, b)
                for l in f.loops
                if _co_key(l.vert, co_precision) in ev
            }
        )
        if len(edge_uv) != 2:
            continue
        row: dict[str, Any] = {"dissolve_edge_uv": edge_uv}
        if include_quad_uv:
            row["quad_uv"] = sorted(_uv_key(l[duv].uv, uv_precision) for l in q.loops)
        joins.append(row)

    src.free()
    dst.free()
    return joins


def write_csv(
    joins: list[dict[str, Any]],
    out_path: Path,
    *,
    profile: str = "",
    uv_layer: str = "UVMap",
    uv_precision: int = DEFAULT_UV_PREC,
    source_object: str = "",
    result_object: str = "",
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        f.write(
            f"# tri-to-quad-uv-map v1 profile={profile} uv_layer={uv_layer} "
            f"uv_precision={uv_precision} joins={len(joins)}"
        )
        if source_object or result_object:
            f.write(f" source={source_object} result={result_object}")
        f.write("\n")
        writer = csv.writer(f)
        writer.writerow(CSV_HEADER)
        for row in joins:
            (u1, v1), (u2, v2) = row["dissolve_edge_uv"]
            writer.writerow([u1, v1, u2, v2])


def read_csv(path: Path) -> dict[str, Any]:
    meta: dict[str, Any] = {"format": "csv", "uv_precision": DEFAULT_UV_PREC, "uv_layer": "UVMap"}
    rows: list[list[tuple[float, float]]] = []
    with path.open(encoding="utf-8", newline="") as f:
        for line in f:
            if line.startswith("# tri-to-quad-uv-map"):
                for token in line[1:].strip().split():
                    if "=" in token:
                        k, v = token.split("=", 1)
                        if k == "profile":
                            meta["profile"] = v
                        elif k == "uv_layer":
                            meta["uv_layer"] = v
                        elif k == "uv_precision":
                            meta["uv_precision"] = int(v)
                        elif k == "joins":
                            meta["join_count"] = int(v)
                continue
            if line.startswith("#"):
                continue
            reader = csv.reader([line])
            for r in reader:
                if not r or r[0] in CSV_HEADER:
                    continue
                if len(r) < 4:
                    continue
                rows.append([(float(r[0]), float(r[1])), (float(r[2]), float(r[3]))])
    meta["joins"] = rows
    meta["join_count"] = len(rows)
    return meta


def read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    data["format"] = "json"
    return data


def load_map(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if path.suffix.lower() == ".csv":
        return read_csv(path)
    return read_json(path)


def _iter_target_edges(data: dict[str, Any]) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    prec = int(data.get("uv_precision", DEFAULT_UV_PREC))
    out: list[tuple[tuple[float, float], tuple[float, float]]] = []
    if data.get("format") == "csv":
        for pair in data["joins"]:
            a, b = pair
            out.append(
                (
                    (round(a[0], prec), round(a[1], prec)),
                    (round(b[0], prec), round(b[1], prec)),
                )
            )
    else:
        for entry in data.get("joins", []):
            pair = tuple(tuple(round(c, prec) for c in pt) for pt in entry["dissolve_edge_uv"])
            if len(pair) == 2:
                out.append(pair)  # type: ignore[arg-type]
    return out


def export_map(
    src_name: str,
    dst_name: str,
    out_path: str | Path,
    *,
    profile: str = "",
    uv_layer: str = "UVMap",
    uv_precision: int = DEFAULT_UV_PREC,
    co_precision: int = DEFAULT_CO_PREC,
    include_quad_uv: bool = False,
) -> dict[str, Any]:
    """Export dissolve map. Extension .csv (default) or .json."""
    joins = extract_dissolve_edges(
        src_name,
        dst_name,
        uv_layer=uv_layer,
        uv_precision=uv_precision,
        co_precision=co_precision,
        include_quad_uv=include_quad_uv,
    )
    out_path = Path(out_path)
    if out_path.suffix.lower() == ".json":
        payload = {
            "version": 1,
            "profile": profile,
            "uv_layer": uv_layer,
            "uv_precision": uv_precision,
            "source_object": src_name,
            "result_object": dst_name,
            "join_count": len(joins),
            "joins": joins if include_quad_uv else [{"dissolve_edge_uv": j["dissolve_edge_uv"]} for j in joins],
        }
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    else:
        write_csv(
            joins,
            out_path,
            profile=profile,
            uv_layer=uv_layer,
            uv_precision=uv_precision,
            source_object=src_name,
            result_object=dst_name,
        )
    return {"join_count": len(joins), "path": str(out_path), "format": out_path.suffix.lower().lstrip(".")}


def export_reference(
    profile_name: str,
    *,
    src_obj: str | None = None,
    dst_obj: str | None = None,
    out_path: str | Path | None = None,
    profiles_dir: Path | None = None,
) -> dict[str, Any]:
    """Export map using a profile JSON (face, body, …)."""
    prof = Profile.load(profile_name, profiles_dir)
    src = src_obj or prof.reference.get("source_object")
    dst = dst_obj or prof.reference.get("result_object")
    if not src or not dst:
        raise ValueError(f"Profile {profile_name!r} needs src_obj/dst_obj or reference.source_object/result_object")
    path = Path(out_path) if out_path else prof.map_path
    return export_map(
        src,
        dst,
        path,
        profile=prof.profile,
        uv_layer=prof.uv_layer,
        uv_precision=prof.uv_precision,
        co_precision=prof.co_precision,
    )


def apply_map(
    obj_name: str,
    map_path: str | Path,
    *,
    uv_layer: str | None = None,
    material_slot_indices: Set[int] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Dissolve UV-matched internal edges on target mesh."""
    path = Path(map_path)
    if not path.is_file():
        return _skip_result(
            reason="map_not_found",
            target_obj=obj_name,
            map_path=str(path),
        )

    data = load_map(path)
    targets = _iter_target_edges(data)
    if not targets:
        return _skip_result(
            reason="empty_map",
            target_obj=obj_name,
            map_path=str(path),
            profile=data.get("profile", ""),
        )

    prec = int(data.get("uv_precision", DEFAULT_UV_PREC))
    layer_name = uv_layer or data.get("uv_layer", "UVMap")

    obj, bm, in_edit = _get_bmesh(obj_name)
    uv = bm.loops.layers.uv.get(layer_name) or bm.loops.layers.uv.active
    if uv is None:
        raise ValueError(f"UV layer {layer_name!r} not found on {obj_name!r}")

    allowed = material_slot_indices
    applied = 0
    skipped = 0
    skipped_wrong_material = 0
    for edge_uv_a, edge_uv_b in targets:
        want = frozenset({edge_uv_a, edge_uv_b})
        found = None
        for e in bm.edges:
            if _edge_uv_keys(e, uv, prec) != want:
                continue
            tris = [f for f in e.link_faces if len(f.verts) == 3]
            if len(tris) != 2:
                continue
            if allowed is not None and not all(f.material_index in allowed for f in tris):
                skipped_wrong_material += 1
                continue
            found = e
            break
        if not found:
            skipped += 1
            continue
        if not dry_run:
            bmesh.ops.dissolve_edges(bm, edges=[found], use_verts=False)
            bm.edges.ensure_lookup_table()
            bm.faces.ensure_lookup_table()
        applied += 1

    if not dry_run:
        _write_bmesh(obj, bm, in_edit)

    return {
        "object": obj_name,
        "profile": data.get("profile", ""),
        "map": str(path),
        "dry_run": dry_run,
        "skipped": False,
        "targets": len(targets),
        "applied": applied,
        "skipped_edges": skipped,
        "skipped_wrong_material": skipped_wrong_material,
        "material_slot_indices": sorted(allowed) if allowed is not None else None,
    }


def apply_profile(
    profile_name: str,
    target_obj: str,
    *,
    map_path: str | Path | None = None,
    uv_layer: str | None = None,
    material_token: str | None = None,
    dry_run: bool = False,
    profiles_dir: Path | None = None,
) -> dict[str, Any]:
    prof = Profile.load(profile_name, profiles_dir)
    path = Path(map_path) if map_path else prof.map_path
    token = material_token if material_token is not None else prof.material_token

    if not path.is_file():
        return _skip_result(
            reason="map_not_found",
            profile=profile_name,
            target_obj=target_obj,
            map_path=str(path),
            material_token=token,
        )

    allowed_slots: Set[int] | None = None
    resolved_material = None
    if token:
        try:
            resolved_material = _resolve_material_by_token(token)
        except (FileNotFoundError, ImportError) as exc:
            return _skip_result(
                reason="material_resolver_unavailable",
                profile=profile_name,
                target_obj=target_obj,
                map_path=str(path),
                material_token=token,
                error=str(exc),
            )
        if resolved_material is None:
            return _skip_result(
                reason="material_not_found",
                profile=profile_name,
                target_obj=target_obj,
                map_path=str(path),
                material_token=token,
            )
        obj = bpy.data.objects.get(target_obj)
        if obj is None or obj.type != "MESH":
            return _skip_result(
                reason="mesh_object_not_found",
                profile=profile_name,
                target_obj=target_obj,
                map_path=str(path),
                material_token=token,
            )
        allowed_slots = material_slot_indices(obj, resolved_material)
        if not allowed_slots:
            return _skip_result(
                reason="material_not_on_object",
                profile=profile_name,
                target_obj=target_obj,
                map_path=str(path),
                material_token=token,
                material_name=resolved_material.name,
            )

    result = apply_map(
        target_obj,
        path,
        uv_layer=uv_layer or prof.uv_layer,
        material_slot_indices=allowed_slots,
        dry_run=dry_run,
    )
    if result.get("skipped"):
        result.setdefault("profile", profile_name)
        result.setdefault("material_token", token)
        return result

    result["profile"] = profile_name
    if token:
        result["material_token"] = token
        result["material_name"] = resolved_material.name if resolved_material else None
    return result


def audit_topology(obj_name: str) -> dict[str, int]:
    obj = bpy.data.objects[obj_name]
    from collections import Counter

    if obj.mode == "EDIT":
        bm = bmesh.from_edit_mesh(obj.data)
    else:
        bm = _load_bm(obj_name)
    counts = Counter(len(f.verts) for f in bm.faces)
    if obj.mode != "EDIT":
        bm.free()
    return dict(sorted(counts.items()))
