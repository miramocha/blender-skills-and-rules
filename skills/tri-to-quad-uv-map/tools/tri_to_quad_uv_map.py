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
from collections import defaultdict
from dataclasses import dataclass, field
from itertools import combinations
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
    map_variants: list[dict[str, str]] = field(default_factory=list)

    @property
    def map_path(self) -> Path:
        return self.resolve_map_path(self.map_file, self.profile)

    @staticmethod
    def resolve_map_path(map_file: str, profile: str = "") -> Path:
        if map_file:
            p = Path(map_file)
            return p if p.is_absolute() else SKILL_ROOT / p
        if profile:
            return MAPS_DIR / f"{profile}-quad-dissolve.csv"
        return MAPS_DIR / "quad-dissolve.csv"

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
            map_variants=list(data.get("map_variants", [])),
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


@dataclass(frozen=True)
class _UVIsland:
    faces: frozenset[Any]
    uv_keys: frozenset[tuple[float, float]]
    bounds: tuple[float, float, float, float]


def _collect_uv_islands(
    faces,
    uv_layer,
    uv_precision: int,
) -> list[_UVIsland]:
    """Flood-fill faces connected through shared UV edges."""
    uv_edge_to_faces: dict[tuple[tuple[float, float], tuple[float, float]], set[Any]] = defaultdict(set)
    face_uv_edges: dict[Any, list[tuple[tuple[float, float], tuple[float, float]]]] = {}

    for face in faces:
        uvs = [_uv_key(loop[uv_layer].uv, uv_precision) for loop in face.loops]
        edges: list[tuple[tuple[float, float], tuple[float, float]]] = []
        n = len(uvs)
        for i in range(n):
            edge = tuple(sorted((uvs[i], uvs[(i + 1) % n])))
            edges.append(edge)
            uv_edge_to_faces[edge].add(face)
        face_uv_edges[face] = edges

    visited: set[Any] = set()
    islands: list[_UVIsland] = []
    for seed in faces:
        if seed in visited:
            continue
        stack = [seed]
        island_faces: set[Any] = set()
        uv_keys: set[tuple[float, float]] = set()
        while stack:
            face = stack.pop()
            if face in visited:
                continue
            visited.add(face)
            island_faces.add(face)
            for loop in face.loops:
                uv_keys.add(_uv_key(loop[uv_layer].uv, uv_precision))
            for edge in face_uv_edges[face]:
                for neighbor in uv_edge_to_faces[edge]:
                    if neighbor not in visited:
                        stack.append(neighbor)

        us = [u for u, _ in uv_keys]
        vs = [v for _, v in uv_keys]
        islands.append(
            _UVIsland(
                faces=frozenset(island_faces),
                uv_keys=frozenset(uv_keys),
                bounds=(min(us), max(us), min(vs), max(vs)),
            )
        )
    return islands


def _match_uv_islands(
    src_islands: list[_UVIsland],
    dst_islands: list[_UVIsland],
) -> tuple[list[tuple[_UVIsland, _UVIsland]], list[_UVIsland], list[_UVIsland]]:
    """Pair source/result islands by identical UV-key sets, then best overlap."""
    by_uv_keys = {island.uv_keys: island for island in src_islands}
    used_src: set[frozenset[tuple[float, float]]] = set()
    pairs: list[tuple[_UVIsland, _UVIsland]] = []
    unmatched_dst: list[_UVIsland] = []

    for dst_island in dst_islands:
        src_island = by_uv_keys.get(dst_island.uv_keys)
        if src_island is not None and src_island.uv_keys not in used_src:
            used_src.add(src_island.uv_keys)
            pairs.append((src_island, dst_island))
            continue

        best: _UVIsland | None = None
        best_overlap = 0
        for candidate in src_islands:
            if candidate.uv_keys in used_src:
                continue
            overlap = len(candidate.uv_keys & dst_island.uv_keys)
            if overlap > best_overlap:
                best_overlap = overlap
                best = candidate
        if best is not None and best_overlap >= max(3, int(len(dst_island.uv_keys) * 0.9)):
            used_src.add(best.uv_keys)
            pairs.append((best, dst_island))
        else:
            unmatched_dst.append(dst_island)

    unmatched_src = [island for island in src_islands if island.uv_keys not in used_src]
    return pairs, unmatched_src, unmatched_dst


def _build_tri_co_index(tris, co_precision: int) -> dict[frozenset[tuple[float, float, float]], Any]:
    index: dict[frozenset[tuple[float, float, float]], Any] = {}
    for face in tris:
        if len(face.verts) != 3:
            continue
        index[frozenset(_co_key(v, co_precision) for v in face.verts)] = face
    return index


def _build_tri_uv_index(tris, suv, uv_precision: int) -> dict[frozenset[tuple[float, float]], Any]:
    index: dict[frozenset[tuple[float, float]], Any] = {}
    for face in tris:
        if len(face.verts) != 3:
            continue
        index[frozenset(_uv_key(loop[suv].uv, uv_precision) for loop in face.loops)] = face
    return index


def _tris_from_corner_index(
    corner_keys: frozenset,
    tri_index: dict[frozenset, Any],
) -> list[Any]:
    found: list[Any] = []
    seen: set[Any] = set()
    for combo in combinations(corner_keys, 3):
        face = tri_index.get(frozenset(combo))
        if face is not None and face not in seen:
            found.append(face)
            seen.add(face)
    return found


def _src_tris_for_quad(
    quad,
    src_faces,
    *,
    suv,
    duv,
    co_precision: int,
    uv_precision: int,
    co_index: dict[frozenset[tuple[float, float, float]], Any] | None = None,
    uv_index: dict[frozenset[tuple[float, float]], Any] | None = None,
) -> list[Any] | None:
    """Find the two source tris that were joined into ``quad`` (indexed, then island scan)."""
    q_cos = frozenset(_co_key(v, co_precision) for v in quad.verts)
    if co_index is not None:
        src_tris = _tris_from_corner_index(q_cos, co_index)
    else:
        src_tris = [
            f
            for f in src_faces
            if len(f.verts) == 3 and frozenset(_co_key(v, co_precision) for v in f.verts) <= q_cos
        ]
    if len(src_tris) == 2:
        return src_tris

    q_uv = frozenset(_uv_key(loop[duv].uv, uv_precision) for loop in quad.loops)
    if uv_index is not None:
        uv_tris = _tris_from_corner_index(q_uv, uv_index)
    else:
        uv_tris = []
        for f in src_faces:
            if len(f.verts) != 3:
                continue
            f_uv = frozenset(_uv_key(loop[suv].uv, uv_precision) for loop in f.loops)
            if f_uv <= q_uv:
                uv_tris.append(f)
    if len(uv_tris) == 2:
        return uv_tris

    # Rare duplicate-UV cases: small island-local fallback only.
    if co_index is not None or uv_index is not None:
        island_tris = list({*(co_index or {}).values(), *(uv_index or {}).values()})
        for f in island_tris:
            if len(f.verts) != 3:
                continue
            f_uv = frozenset(_uv_key(loop[suv].uv, uv_precision) for loop in f.loops)
            if f_uv <= q_uv:
                uv_tris.append(f)
        uv_tris = list(dict.fromkeys(uv_tris))
        if len(uv_tris) == 2:
            return uv_tris
    return None


def _dissolve_edge_uv(
    tri_a,
    tri_b,
    *,
    suv,
    co_precision: int,
    uv_precision: int,
) -> list[tuple[float, float]] | None:
    shared = set(tri_a.edges) & set(tri_b.edges)
    if not shared:
        return None
    e = next(iter(shared))
    ev = {_co_key(v, co_precision) for v in e.verts}
    edge_uv = sorted(
        {
            _uv_key(l[suv].uv, uv_precision)
            for f in (tri_a, tri_b)
            for l in f.loops
            if _co_key(l.vert, co_precision) in ev
        }
    )
    return edge_uv if len(edge_uv) == 2 else None


def extract_dissolve_edges(
    src_name: str,
    dst_name: str,
    *,
    uv_layer: str = "UVMap",
    uv_precision: int = DEFAULT_UV_PREC,
    co_precision: int = DEFAULT_CO_PREC,
    include_quad_uv: bool = False,
    use_uv_islands: bool = True,
    island_stats: dict[str, Any] | None = None,
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
    seen_edges: set[frozenset[tuple[float, float]]] = set()

    def process_quads(dst_quads, src_scope, co_index=None, uv_index=None) -> None:
        for q in dst_quads:
            if len(q.verts) != 4:
                continue
            src_tris = _src_tris_for_quad(
                q,
                src_scope,
                suv=suv,
                duv=duv,
                co_precision=co_precision,
                uv_precision=uv_precision,
                co_index=co_index,
                uv_index=uv_index,
            )
            if src_tris is None:
                continue
            edge_uv = _dissolve_edge_uv(
                src_tris[0],
                src_tris[1],
                suv=suv,
                co_precision=co_precision,
                uv_precision=uv_precision,
            )
            if edge_uv is None:
                continue
            edge_key = frozenset(edge_uv)
            if edge_key in seen_edges:
                continue
            seen_edges.add(edge_key)
            row: dict[str, Any] = {"dissolve_edge_uv": edge_uv}
            if include_quad_uv:
                row["quad_uv"] = sorted(_uv_key(loop[duv].uv, uv_precision) for loop in q.loops)
            joins.append(row)

    if use_uv_islands:
        src_islands = _collect_uv_islands(src.faces, suv, uv_precision)
        dst_islands = _collect_uv_islands(dst.faces, duv, uv_precision)
        pairs, unmatched_src, unmatched_dst = _match_uv_islands(src_islands, dst_islands)

        for src_island, dst_island in pairs:
            island_src_tris = [face for face in src_island.faces if len(face.verts) == 3]
            dst_quads = [face for face in dst_island.faces if len(face.verts) == 4]
            co_index = _build_tri_co_index(island_src_tris, co_precision)
            uv_index = _build_tri_uv_index(island_src_tris, suv, uv_precision)
            process_quads(dst_quads, island_src_tris, co_index=co_index, uv_index=uv_index)

        # Unmatched islands still run, but only against their local source faces.
        for dst_island in unmatched_dst:
            dst_quads = [face for face in dst_island.faces if len(face.verts) == 4]
            if not dst_quads:
                continue
            overlap_keys = dst_island.uv_keys
            island_src_tris = [
                face
                for face in src.faces
                if len(face.verts) == 3
                and frozenset(_uv_key(loop[suv].uv, uv_precision) for loop in face.loops) <= overlap_keys
            ]
            co_index = _build_tri_co_index(island_src_tris, co_precision)
            uv_index = _build_tri_uv_index(island_src_tris, suv, uv_precision)
            process_quads(dst_quads, island_src_tris, co_index=co_index, uv_index=uv_index)

        if island_stats is not None:
            island_stats.update(
                {
                    "src_islands": len(src_islands),
                    "dst_islands": len(dst_islands),
                    "matched_pairs": len(pairs),
                    "unmatched_src_islands": len(unmatched_src),
                    "unmatched_dst_islands": len(unmatched_dst),
                }
            )
    else:
        process_quads(dst.faces, src.faces)
        if island_stats is not None:
            island_stats.clear()

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
    island_stats: dict[str, Any] = {}
    joins = extract_dissolve_edges(
        src_name,
        dst_name,
        uv_layer=uv_layer,
        uv_precision=uv_precision,
        co_precision=co_precision,
        include_quad_uv=include_quad_uv,
        island_stats=island_stats,
    )
    out_path = Path(out_path)
    result: dict[str, Any] = {
        "join_count": len(joins),
        "path": str(out_path),
        "format": out_path.suffix.lower().lstrip("."),
    }
    if island_stats:
        result["island_stats"] = island_stats
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
    return result


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


def _build_uv_edge_index(
    bm: bmesh.types.BMesh,
    uv_layer,
    prec: int,
) -> dict[frozenset[tuple[float, float]], list[Any]]:
    """Map rounded UV edge keys to mesh edges (bmesh edge iteration order)."""
    index: dict[frozenset[tuple[float, float]], list[Any]] = defaultdict(list)
    for edge in bm.edges:
        index[_edge_uv_keys(edge, uv_layer, prec)].append(edge)
    return index


def _find_dissolve_edge(
    want: frozenset[tuple[float, float]],
    index: dict[frozenset[tuple[float, float]], list[Any]],
    *,
    allowed: Set[int] | None,
) -> tuple[Any | None, int]:
    """First index hit that borders two tris and passes material filter."""
    skipped_wrong_material = 0
    for edge in index.get(want, ()):
        if not edge.is_valid:
            continue
        tris = [face for face in edge.link_faces if len(face.verts) == 3]
        if len(tris) != 2:
            continue
        if allowed is not None and not all(face.material_index in allowed for face in tris):
            skipped_wrong_material += 1
            continue
        return edge, skipped_wrong_material
    return None, skipped_wrong_material


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
    uv_index = _build_uv_edge_index(bm, uv, prec)
    applied = 0
    skipped = 0
    skipped_wrong_material = 0
    for edge_uv_a, edge_uv_b in targets:
        want = frozenset({edge_uv_a, edge_uv_b})
        found, wrong_mat = _find_dissolve_edge(want, uv_index, allowed=allowed)
        skipped_wrong_material += wrong_mat
        if found is None:
            skipped += 1
            continue
        if not dry_run:
            bmesh.ops.dissolve_edges(bm, edges=[found], use_verts=False)
            bm.edges.ensure_lookup_table()
            bm.faces.ensure_lookup_table()
            # Dissolved edge gone — drop stale bucket (UV keys unchanged on remaining edges).
            bucket = uv_index.get(want)
            if bucket is not None:
                uv_index[want] = [edge for edge in bucket if edge.is_valid]
                if not uv_index[want]:
                    del uv_index[want]
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
        "fit_ratio": round(applied / len(targets), 4) if targets else 0.0,
    }


def audit_map_fit(
    obj_name: str,
    map_path: str | Path,
    *,
    uv_layer: str | None = None,
    material_slot_indices: Set[int] | None = None,
) -> dict[str, Any]:
    """Dry-run dissolve map against mesh; report how many UV edges match."""
    return apply_map(
        obj_name,
        map_path,
        uv_layer=uv_layer,
        material_slot_indices=material_slot_indices,
        dry_run=True,
    )


def _resolve_material_slots(
    target_obj: str,
    token: str,
    *,
    profile_name: str,
    map_path: str,
) -> tuple[Set[int] | None, Any | None, dict[str, Any] | None]:
    """Resolve Body.Skin (etc.) slots or return a skip-result dict."""
    try:
        resolved_material = _resolve_material_by_token(token)
    except (FileNotFoundError, ImportError) as exc:
        return None, None, _skip_result(
            reason="material_resolver_unavailable",
            profile=profile_name,
            target_obj=target_obj,
            map_path=map_path,
            material_token=token,
            error=str(exc),
        )
    if resolved_material is None:
        return None, None, _skip_result(
            reason="material_not_found",
            profile=profile_name,
            target_obj=target_obj,
            map_path=map_path,
            material_token=token,
        )
    obj = bpy.data.objects.get(target_obj)
    if obj is None or obj.type != "MESH":
        return None, None, _skip_result(
            reason="mesh_object_not_found",
            profile=profile_name,
            target_obj=target_obj,
            map_path=map_path,
            material_token=token,
        )
    allowed_slots = material_slot_indices(obj, resolved_material)
    if not allowed_slots:
        return None, None, _skip_result(
            reason="material_not_on_object",
            profile=profile_name,
            target_obj=target_obj,
            map_path=map_path,
            material_token=token,
            material_name=resolved_material.name,
        )
    return allowed_slots, resolved_material, None


def choose_map_variant(
    profile_name: str,
    target_obj: str,
    *,
    profiles_dir: Path | None = None,
    uv_layer: str | None = None,
    material_token: str | None = None,
) -> dict[str, Any]:
    """Pick best map for target mesh by dry-run UV edge fit across profile variants."""
    prof = Profile.load(profile_name, profiles_dir)
    token = material_token if material_token is not None else prof.material_token
    layer = uv_layer or prof.uv_layer

    variants: list[dict[str, str]] = list(prof.map_variants)
    if not variants:
        return {
            "profile": profile_name,
            "object": target_obj,
            "auto_select": False,
            "chosen_variant": "default",
            "chosen_map": str(prof.map_path),
            "audits": [],
        }

    allowed_slots: Set[int] | None = None
    if token:
        allowed_slots, _, skip = _resolve_material_slots(
            target_obj,
            token,
            profile_name=profile_name,
            map_path=str(prof.map_path),
        )
        if skip is not None:
            return skip

    audits: list[dict[str, Any]] = []
    for variant in variants:
        variant_id = variant.get("id", "")
        label = variant.get("label", variant_id)
        variant_path = Profile.resolve_map_path(variant.get("map_file", ""), profile_name)
        if not variant_path.is_file():
            audits.append(
                {
                    "variant_id": variant_id,
                    "label": label,
                    "map": str(variant_path),
                    "skipped": True,
                    "reason": "map_not_found",
                    "applied": 0,
                    "targets": 0,
                    "fit_ratio": 0.0,
                }
            )
            continue
        audit = audit_map_fit(
            target_obj,
            variant_path,
            uv_layer=layer,
            material_slot_indices=allowed_slots,
        )
        audit["variant_id"] = variant_id
        audit["label"] = label
        audits.append(audit)

    candidates = [
        audit
        for audit in audits
        if not audit.get("skipped") and int(audit.get("targets", 0)) > 0
    ]
    if not candidates:
        return {
            "profile": profile_name,
            "object": target_obj,
            "auto_select": True,
            "chosen_variant": None,
            "chosen_map": None,
            "audits": audits,
            "error": "no_usable_map_variant",
        }

    best = max(
        candidates,
        key=lambda audit: (int(audit.get("applied", 0)), float(audit.get("fit_ratio", 0.0))),
    )
    return {
        "profile": profile_name,
        "object": target_obj,
        "auto_select": True,
        "chosen_variant": best.get("variant_id"),
        "chosen_label": best.get("label"),
        "chosen_map": best.get("map"),
        "chosen_applied": best.get("applied"),
        "chosen_targets": best.get("targets"),
        "chosen_fit_ratio": best.get("fit_ratio"),
        "audits": audits,
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
    token = material_token if material_token is not None else prof.material_token
    map_choice: dict[str, Any] | None = None

    if map_path is None and prof.map_variants:
        map_choice = choose_map_variant(
            profile_name,
            target_obj,
            profiles_dir=profiles_dir,
            uv_layer=uv_layer,
            material_token=token,
        )
        if map_choice.get("error") == "no_usable_map_variant":
            return _skip_result(
                reason="no_usable_map_variant",
                profile=profile_name,
                target_obj=target_obj,
                material_token=token,
                audits=map_choice.get("audits", []),
            )
        if map_choice.get("skipped"):
            return map_choice
        chosen = map_choice.get("chosen_map")
        if not chosen:
            return _skip_result(
                reason="map_not_chosen",
                profile=profile_name,
                target_obj=target_obj,
                material_token=token,
            )
        path = Path(chosen)
    else:
        path = Path(map_path) if map_path else prof.map_path

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
        allowed_slots, resolved_material, skip = _resolve_material_slots(
            target_obj,
            token,
            profile_name=profile_name,
            map_path=str(path),
        )
        if skip is not None:
            return skip

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
    if map_choice and map_choice.get("auto_select"):
        result["map_variant"] = map_choice.get("chosen_variant")
        result["map_variant_label"] = map_choice.get("chosen_label")
        result["map_selection"] = map_choice
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
