"""VRoid hair tri→quad — stock Blender operator, not UV CSV maps.

Hair UV atlas packing varies per hairstyle. Use ``tris_convert_to_quads`` at 90° face
and shape angles on the full ``Hair`` mesh. Cap detection helpers are for audits only.

MCP / Scripting:
  import hair_tris_to_quad as hq
  hq.apply_tris_to_quads("Hair", dry_run=False)  # also assigns Hair.Cap / Hair.Strip
  caps = hq.find_cap_faces_bmesh(bm, uv_layer)
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import bmesh

try:
    import bpy
except ImportError:  # pragma: no cover
    bpy = None  # type: ignore

SKILL_ROOT = Path(__file__).resolve().parents[1]
PROFILES_DIR = SKILL_ROOT / "profiles"

DEFAULT_UV_PREC = 4
CAP_UV_EPS = 1e-4
AXIS_ANGLE_TOL = 8.0
FACE_ANGLE_DEG = 90.0
SHAPE_ANGLE_DEG = 90.0
VG_CAP = "Hair.Cap"
VG_STRIP = "Hair.Strip"


def _uv_key(uv, prec: int) -> tuple[float, float]:
    return (round(uv.x, prec), round(uv.y, prec))


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


def audit_topology(obj_name: str) -> dict[str, int]:
    obj = bpy.data.objects[obj_name]
    if obj.mode == "EDIT":
        bm = bmesh.from_edit_mesh(obj.data)
    else:
        bm = _load_bm(obj_name)
    counts = Counter(len(f.verts) for f in bm.faces)
    if obj.mode != "EDIT":
        bm.free()
    return dict(sorted(counts.items()))


def find_cap_faces_bmesh(
    bm: bmesh.types.BMesh,
    uv_layer: Any,
    *,
    uv_eps: float = CAP_UV_EPS,
) -> set[bmesh.types.BMFace]:
    """VRoid hair cap: 2 tris, 4 mesh verts, UV on one horizontal line (constant V)."""
    cap_faces: set[bmesh.types.BMFace] = set()
    seen_pairs: set[tuple[int, int]] = set()

    for face in bm.faces:
        if len(face.verts) != 3:
            continue
        for edge in face.edges:
            for other in edge.link_faces:
                if other is face or len(other.verts) != 3:
                    continue
                pair_key = tuple(sorted((face.index, other.index)))
                if pair_key in seen_pairs:
                    continue
                if len(set(face.verts) | set(other.verts)) != 4:
                    continue

                us: list[float] = []
                vs: list[float] = []
                for tri in (face, other):
                    for loop in tri.loops:
                        uv_coord = loop[uv_layer].uv
                        us.append(uv_coord.x)
                        vs.append(uv_coord.y)

                if max(vs) - min(vs) > uv_eps or max(us) - min(us) < uv_eps:
                    continue

                seen_pairs.add(pair_key)
                cap_faces.add(face)
                cap_faces.add(other)

    return cap_faces


def is_cap_face(
    face: bmesh.types.BMFace,
    uv_layer: Any,
    *,
    cap_faces: set[bmesh.types.BMFace] | None = None,
    bm: bmesh.types.BMesh | None = None,
    uv_eps: float = CAP_UV_EPS,
) -> bool:
    if cap_faces is not None:
        return face in cap_faces
    if bm is None:
        raise ValueError("is_cap_face requires cap_faces or bm")
    return face in find_cap_faces_bmesh(bm, uv_layer, uv_eps=uv_eps)


def assign_cap_strip_vertex_groups(
    obj_name: str,
    *,
    vg_cap: str = VG_CAP,
    vg_strip: str = VG_STRIP,
    uv_layer: str = "UVMap",
) -> dict[str, Any]:
    """Assign cap vs strip verts to vertex groups (audit / weight paint check)."""
    obj = bpy.data.objects.get(obj_name)
    if obj is None or obj.type != "MESH":
        return {"error": "mesh_object_not_found", "object": obj_name}

    if bpy.context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")

    bm = bmesh.new()
    bm.from_mesh(obj.data)
    uv = bm.loops.layers.uv.get(uv_layer) or bm.loops.layers.uv.active
    if uv is None:
        bm.free()
        return {"error": "uv_layer_not_found", "object": obj_name}

    cap_faces = find_cap_faces_bmesh(bm, uv)
    cap_verts: set[int] = set()
    strip_verts: set[int] = set()
    cap_face_count = 0
    strip_face_count = 0

    for face in bm.faces:
        if len(face.verts) != 3:
            continue
        if face in cap_faces:
            cap_face_count += 1
            for v in face.verts:
                cap_verts.add(v.index)
        else:
            strip_face_count += 1
            for v in face.verts:
                strip_verts.add(v.index)

    bm.free()
    strip_only = strip_verts - cap_verts

    def ensure_vg(name: str):
        vg = obj.vertex_groups.get(name)
        return vg if vg else obj.vertex_groups.new(name=name)

    def clear_vg(vg) -> None:
        for v in obj.data.vertices:
            for g in v.groups:
                if g.group == vg.index:
                    vg.remove([v.index])
                    break

    vg_c = ensure_vg(vg_cap)
    vg_s = ensure_vg(vg_strip)
    clear_vg(vg_c)
    clear_vg(vg_s)
    if cap_verts:
        vg_c.add(list(cap_verts), 1.0, "REPLACE")
    if strip_only:
        vg_s.add(list(strip_only), 1.0, "REPLACE")

    return {
        "object": obj_name,
        "vertex_groups": [vg_cap, vg_strip],
        "cap_faces": cap_face_count,
        "strip_faces": strip_face_count,
        "cap_verts": len(cap_verts),
        "strip_verts": len(strip_only),
    }


def _uv_edge_is_diagonal(
    a: tuple[float, float],
    b: tuple[float, float],
    *,
    angle_tol: float = AXIS_ANGLE_TOL,
) -> bool:
    du = abs(b[0] - a[0])
    dv = abs(b[1] - a[1])
    if du + dv < 1e-8:
        return False
    ang = math.degrees(math.atan2(dv, du))
    return angle_tol < ang < 90.0 - angle_tol


def extract_strip_dissolve_targets(
    bm: bmesh.types.BMesh,
    uv_layer: Any,
    *,
    uv_precision: int = DEFAULT_UV_PREC,
    skip_caps: bool = True,
    cap_faces: set[bmesh.types.BMFace] | None = None,
) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """Experimental: diagonal shared UV edges on isolated strand meshes (e.g. ``Strand``)."""
    if skip_caps and cap_faces is None:
        cap_faces = find_cap_faces_bmesh(bm, uv_layer)
    elif not skip_caps:
        cap_faces = set()

    tri_uv: dict[int, list[tuple[float, float]]] = {}
    uv_edge_faces: defaultdict[tuple[tuple[float, float], tuple[float, float]], list[int]] = defaultdict(list)

    for face in bm.faces:
        if len(face.verts) != 3 or face in cap_faces:
            continue
        corners = [_uv_key(l[uv_layer].uv, uv_precision) for l in face.loops]
        tri_uv[face.index] = corners
        for i in range(3):
            a, b = corners[i], corners[(i + 1) % 3]
            uv_edge_faces[tuple(sorted((a, b)))].append(face.index)

    targets: list[tuple[tuple[float, float], tuple[float, float]]] = []
    seen: set[tuple[tuple[float, float], tuple[float, float]]] = set()

    for edge, face_ids in uv_edge_faces.items():
        if len(face_ids) != 2 or not _uv_edge_is_diagonal(edge[0], edge[1]):
            continue
        a_id, b_id = face_ids
        corners = set(tri_uv[a_id]) | set(tri_uv[b_id])
        uvals = sorted({c[0] for c in corners})
        vvals = sorted({c[1] for c in corners})
        if len(corners) != 4 or len(uvals) != 2 or len(vvals) != 2:
            continue
        key = tuple(sorted(edge))
        if key in seen:
            continue
        seen.add(key)
        targets.append((edge[0], edge[1]))

    return targets


def apply_strand_pattern(
    obj_name: str,
    *,
    uv_layer: str = "UVMap",
    uv_precision: int = DEFAULT_UV_PREC,
    skip_caps: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Experimental UV-pattern dissolve for single ``Strand`` objects — not full ``Hair``."""
    obj, bm, in_edit = _get_bmesh(obj_name)
    uv = bm.loops.layers.uv.get(uv_layer) or bm.loops.layers.uv.active
    if uv is None:
        raise ValueError(f"UV layer {uv_layer!r} not found on {obj_name!r}")

    cap_faces = find_cap_faces_bmesh(bm, uv) if skip_caps else set()
    targets = extract_strip_dissolve_targets(
        bm, uv, uv_precision=uv_precision, skip_caps=skip_caps, cap_faces=cap_faces
    )

    applied = 0
    skipped = 0
    for edge_uv_a, edge_uv_b in targets:
        want = frozenset({edge_uv_a, edge_uv_b})
        found = None
        for e in bm.edges:
            if _edge_uv_keys(e, uv, uv_precision) != want:
                continue
            tris = [f for f in e.link_faces if len(f.verts) == 3]
            if len(tris) != 2:
                continue
            if skip_caps and any(f in cap_faces for f in tris):
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

    topo = Counter(len(f.verts) for f in bm.faces) if in_edit else audit_topology(obj_name)

    return {
        "object": obj_name,
        "mode": "strand_pattern",
        "dry_run": dry_run,
        "cap_faces_skipped": len(cap_faces),
        "targets": len(targets),
        "applied": applied,
        "skipped_edges": skipped,
        "topology_after": dict(sorted(topo.items())),
    }


def apply_tris_to_quads(
    obj_name: str,
    *,
    face_angle_deg: float = FACE_ANGLE_DEG,
    shape_angle_deg: float = SHAPE_ANGLE_DEG,
    assign_vertex_groups: bool = True,
    vg_cap: str = VG_CAP,
    vg_strip: str = VG_STRIP,
    uv_layer: str = "UVMap",
    dry_run: bool = False,
) -> dict[str, Any]:
    """VRoid hair tri→quad via ``mesh.tris_convert_to_quads`` (default 90° / 90°).

    When ``assign_vertex_groups`` is True (default), writes ``Hair.Cap`` and
    ``Hair.Strip`` from UV cap detection **before** convert (requires tri caps).
    """
    obj = bpy.data.objects.get(obj_name)
    if obj is None or obj.type != "MESH":
        return {"skipped": True, "reason": "mesh_object_not_found", "object": obj_name}

    before = audit_topology(obj_name)
    tri_before = before.get(3, 0)

    vertex_groups: dict[str, Any] | None = None
    if assign_vertex_groups and tri_before > 0:
        vertex_groups = assign_cap_strip_vertex_groups(
            obj_name, vg_cap=vg_cap, vg_strip=vg_strip, uv_layer=uv_layer
        )

    if tri_before == 0:
        return {
            "object": obj_name,
            "mode": "tris_convert_to_quads",
            "dry_run": dry_run,
            "skipped": True,
            "reason": "no_tris",
            "topology_before": before,
            "topology_after": before,
            "face_angle_deg": face_angle_deg,
            "shape_angle_deg": shape_angle_deg,
            "vertex_groups": vertex_groups,
        }

    if dry_run:
        return {
            "object": obj_name,
            "mode": "tris_convert_to_quads",
            "dry_run": True,
            "skipped": False,
            "topology_before": before,
            "tris_before": tri_before,
            "face_angle_deg": face_angle_deg,
            "shape_angle_deg": shape_angle_deg,
            "vertex_groups": vertex_groups,
        }

    view_layer = bpy.context.view_layer
    prev_active = view_layer.objects.active
    prev_mode = prev_active.mode if prev_active else "OBJECT"
    prev_selection = {o: o.select_get() for o in view_layer.objects}

    try:
        if bpy.context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        for o in view_layer.objects:
            o.select_set(False)
        obj.select_set(True)
        view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.tris_convert_to_quads(
            face_threshold=math.radians(face_angle_deg),
            shape_threshold=math.radians(shape_angle_deg),
        )
        bpy.ops.object.mode_set(mode="OBJECT")
    finally:
        for o, selected in prev_selection.items():
            o.select_set(selected)
        if prev_active is not None:
            view_layer.objects.active = prev_active
            if prev_mode == "EDIT" and prev_active.type == "MESH":
                bpy.ops.object.mode_set(mode="EDIT")

    after = audit_topology(obj_name)
    return {
        "object": obj_name,
        "mode": "tris_convert_to_quads",
        "dry_run": False,
        "skipped": False,
        "topology_before": before,
        "topology_after": after,
        "tris_before": tri_before,
        "tris_after": after.get(3, 0),
        "quads_after": after.get(4, 0),
        "face_angle_deg": face_angle_deg,
        "shape_angle_deg": shape_angle_deg,
        "vertex_groups": vertex_groups,
    }
