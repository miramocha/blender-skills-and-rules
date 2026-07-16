"""UV topology symmetry audit and TriQuad vertex groups for Blender.

Mirrors faces/edges across a U axis (default: UV bbox center, usually 0.5 on VRoid
atlases). Assigns side + quad/tri groups and highlights faces without a mirror partner.

MCP / Scripting:
  import uv_topology_symmetry as uvs
  report = uvs.audit_uv_symmetry("Body.Torso")
  uvs.assign_triquad_vertex_groups("Body.Torso")
  uvs.audit_and_assign("Body.Torso")
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
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
DEFAULT_U_CENTER: float | None = None

VG_LEFT_QUAD = "TriQuad.Left.Quad"
VG_LEFT_TRI = "TriQuad.Left.Tri"
VG_RIGHT_QUAD = "TriQuad.Right.Quad"
VG_RIGHT_TRI = "TriQuad.Right.Tri"
VG_LEFT = "TriQuad.Left"
VG_RIGHT = "TriQuad.Right"
VG_CENTER = "TriQuad.Center"
VG_MISMATCH = "TriQuad.Mismatch"
VG_MISMATCH_LEFT = "TriQuad.Mismatch.Left"
VG_MISMATCH_RIGHT = "TriQuad.Mismatch.Right"


@dataclass
class SymmetryProfile:
    profile: str = "default"
    uv_layer: str = "UVMap"
    uv_precision: int = DEFAULT_UV_PREC
    u_center: float | None = DEFAULT_U_CENTER
    vertex_groups: dict[str, str] = field(default_factory=dict)
    assign_vertex_groups: bool = True

    @classmethod
    def load(cls, profile: str = "default", profiles_dir: Path | None = None) -> SymmetryProfile:
        root = profiles_dir or PROFILES_DIR
        path = root / f"{profile}.json"
        if not path.is_file():
            return cls(profile=profile)
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            profile=data.get("profile", profile),
            uv_layer=data.get("uv_layer", "UVMap"),
            uv_precision=int(data.get("uv_precision", DEFAULT_UV_PREC)),
            u_center=data.get("u_center"),
            vertex_groups=data.get("vertex_groups", {}),
            assign_vertex_groups=bool(data.get("assign_vertex_groups", True)),
        )

    def vg_name(self, key: str, default: str) -> str:
        return self.vertex_groups.get(key, default)


def _uv_key(uv, prec: int) -> tuple[float, float]:
    return (round(uv.x, prec), round(uv.y, prec))


def _mirror_u(uv: tuple[float, float], center: float, prec: int) -> tuple[float, float]:
    return (round(2 * center - uv[0], prec), uv[1])


def _face_side(centroid_u: float, u_center: float, tol: float) -> str:
    if abs(centroid_u - u_center) <= tol:
        return "center"
    return "left" if centroid_u < u_center - tol else "right"


def _face_sig(uvs: list[tuple[float, float]], prec: int) -> tuple[int, tuple[float, ...]]:
    n = len(uvs)
    elens = tuple(
        sorted(
            round(((uvs[i][0] - uvs[(i + 1) % n][0]) ** 2 + (uvs[i][1] - uvs[(i + 1) % n][1]) ** 2) ** 0.5, prec)
            for i in range(n)
        )
    )
    return (n, elens)


def _edge_key(a: tuple[float, float], b: tuple[float, float]) -> tuple[tuple[float, float], tuple[float, float]]:
    return tuple(sorted((a, b)))


def _mirror_edge(
    edge: tuple[tuple[float, float], tuple[float, float]], center: float, prec: int
) -> tuple[tuple[float, float], tuple[float, float]]:
    return _edge_key(_mirror_u(edge[0], center, prec), _mirror_u(edge[1], center, prec))


def _get_mesh_obj(obj_name: str):
    if bpy is None:
        raise RuntimeError("bpy not available")
    obj = bpy.data.objects.get(obj_name)
    if obj is None or obj.type != "MESH":
        return None
    return obj


def _ensure_object_mode() -> str:
    prev = bpy.context.mode
    if prev != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    return prev


def _restore_mode(prev: str) -> None:
    if prev == "OBJECT":
        return
    mode = "EDIT" if "EDIT" in prev else prev
    try:
        bpy.ops.object.mode_set(mode=mode)
    except TypeError:
        pass


def _collect_uv_geometry(
    bm: bmesh.types.BMesh,
    uv_lay,
    *,
    u_center: float,
    prec: int,
    tol: float,
) -> dict[str, Any]:
    faces_by_side: dict[str, list[tuple[bmesh.types.BMFace, list[tuple[float, float]]]]] = {
        "left": [],
        "right": [],
        "center": [],
    }
    edges: set[tuple[tuple[float, float], tuple[float, float]]] = set()
    u_values: list[float] = []

    for face in bm.faces:
        uvs = [_uv_key(lp[uv_lay].uv, prec) for lp in face.loops]
        for u, _ in uvs:
            u_values.append(u)
        cu = sum(u for u, _ in uvs) / len(uvs)
        side = _face_side(cu, u_center, tol)
        faces_by_side[side].append((face, uvs))
        n = len(uvs)
        for i in range(n):
            edges.add(_edge_key(uvs[i], uvs[(i + 1) % n]))

    left_edges: set[tuple[tuple[float, float], tuple[float, float]]] = set()
    right_edges: set[tuple[tuple[float, float], tuple[float, float]]] = set()
    center_edge_count = 0
    for edge in edges:
        on_center = abs(edge[0][0] - u_center) <= tol and abs(edge[1][0] - u_center) <= tol
        if on_center:
            center_edge_count += 1
            continue
        mid_u = (edge[0][0] + edge[1][0]) / 2.0
        if mid_u < u_center - tol:
            left_edges.add(edge)
        elif mid_u > u_center + tol:
            right_edges.add(edge)
        else:
            center_edge_count += 1

    mirrored_left = {_mirror_edge(e, u_center, prec) for e in left_edges}
    mirrored_right = {_mirror_edge(e, u_center, prec) for e in right_edges}
    unmatched_left_edges = mirrored_left - right_edges
    unmatched_right_edges = mirrored_right - left_edges

    right_sigs = Counter(_face_sig(uvs, prec) for _, uvs in faces_by_side["right"])
    unmatched_left_faces: list[tuple[bmesh.types.BMFace, list[tuple[float, float]]]] = []
    for face, uvs in faces_by_side["left"]:
        mirrored_uvs = [_mirror_u(uv, u_center, prec) for uv in uvs]
        sig = _face_sig(mirrored_uvs, prec)
        if right_sigs[sig] > 0:
            right_sigs[sig] -= 1
        else:
            unmatched_left_faces.append((face, uvs))

    unmatched_right_faces: list[tuple[bmesh.types.BMFace, list[tuple[float, float]]]] = []
    for face, uvs in faces_by_side["right"]:
        sig = _face_sig(uvs, prec)
        if right_sigs[sig] > 0:
            right_sigs[sig] -= 1
            unmatched_right_faces.append((face, uvs))

    side_face_types = {side: Counter(len(face.verts) for face, _ in items) for side, items in faces_by_side.items()}

    return {
        "u_min": min(u_values) if u_values else 0.0,
        "u_max": max(u_values) if u_values else 0.0,
        "faces_by_side": faces_by_side,
        "side_face_types": side_face_types,
        "left_edge_count": len(left_edges),
        "right_edge_count": len(right_edges),
        "center_edge_count": center_edge_count,
        "unmatched_left_edge_count": len(unmatched_left_edges),
        "unmatched_right_edge_count": len(unmatched_right_edges),
        "unmatched_left_faces": unmatched_left_faces,
        "unmatched_right_faces": unmatched_right_faces,
        "unmatched_left_face_count": len(unmatched_left_faces),
        "unmatched_right_face_count": len(unmatched_right_faces),
    }


def audit_uv_symmetry(
    obj_name: str,
    *,
    uv_layer: str = "UVMap",
    u_center: float | None = None,
    uv_precision: int = DEFAULT_UV_PREC,
) -> dict[str, Any]:
    """Return UV mirror symmetry stats without writing vertex groups."""
    obj = _get_mesh_obj(obj_name)
    if obj is None:
        return {"error": "mesh_object_not_found", "object": obj_name}

    bm = bmesh.new()
    bm.from_mesh(obj.data)
    uv_lay = bm.loops.layers.uv.get(uv_layer) or bm.loops.layers.uv.active
    if uv_lay is None:
        bm.free()
        return {"error": "uv_layer_not_found", "object": obj_name, "uv_layer": uv_layer}

    prec = uv_precision
    tol = 10 ** (-prec)

    probe_us: list[float] = []
    for face in bm.faces:
        for lp in face.loops:
            probe_us.append(round(lp[uv_lay].uv.x, prec))
    resolved_center = u_center if u_center is not None else ((min(probe_us) + max(probe_us)) / 2.0 if probe_us else 0.5)

    geo = _collect_uv_geometry(bm, uv_lay, u_center=resolved_center, prec=prec, tol=tol)

    xs = [v.co.x for v in bm.verts]
    x_center = (min(xs) + max(xs)) / 2.0 if xs else 0.0
    left_v = sum(1 for x in xs if x < x_center - tol)
    right_v = sum(1 for x in xs if x > x_center + tol)
    center_v = len(xs) - left_v - right_v

    edge_sym = geo["unmatched_left_edge_count"] == 0 and geo["unmatched_right_edge_count"] == 0
    face_sym = geo["unmatched_left_face_count"] == 0 and geo["unmatched_right_face_count"] == 0

    bm.free()

    return {
        "object": obj_name,
        "mesh": obj.data.name,
        "uv_layer": uv_layer,
        "u_range": [round(geo["u_min"], prec), round(geo["u_max"], prec)],
        "u_center": round(resolved_center, prec),
        "symmetric": edge_sym and face_sym,
        "edge_symmetric": edge_sym,
        "face_symmetric": face_sym,
        "unmatched_left_edge_mirrors": geo["unmatched_left_edge_count"],
        "unmatched_right_edge_mirrors": geo["unmatched_right_edge_count"],
        "unmatched_left_faces": geo["unmatched_left_face_count"],
        "unmatched_right_faces": geo["unmatched_right_face_count"],
        "left_uv_edges": geo["left_edge_count"],
        "right_uv_edges": geo["right_edge_count"],
        "centerline_uv_edges": geo["center_edge_count"],
        "left_faces": sum(geo["side_face_types"]["left"].values()),
        "right_faces": sum(geo["side_face_types"]["right"].values()),
        "center_faces": sum(geo["side_face_types"]["center"].values()),
        "uv_face_types_by_side": {k: dict(v) for k, v in geo["side_face_types"].items()},
        "mesh_3d_bilateral_balanced": abs(left_v - right_v) <= max(5, int(0.02 * len(xs))),
        "verts_left_3d": left_v,
        "verts_right_3d": right_v,
        "verts_centerline_3d": center_v,
    }


def assign_triquad_vertex_groups(
    obj_name: str,
    *,
    profile: str = "default",
    uv_layer: str | None = None,
    u_center: float | None = None,
    uv_precision: int | None = None,
) -> dict[str, Any]:
    """Assign TriQuad side/quad/tri groups plus mismatch highlight groups."""
    cfg = SymmetryProfile.load(profile)
    obj = _get_mesh_obj(obj_name)
    if obj is None:
        return {"error": "mesh_object_not_found", "object": obj_name}

    layer = uv_layer or cfg.uv_layer
    prec = uv_precision if uv_precision is not None else cfg.uv_precision
    tol = 10 ** (-prec)
    center_override = u_center if u_center is not None else cfg.u_center

    names = {
        "left_quad": cfg.vg_name("left_quad", VG_LEFT_QUAD),
        "left_tri": cfg.vg_name("left_tri", VG_LEFT_TRI),
        "right_quad": cfg.vg_name("right_quad", VG_RIGHT_QUAD),
        "right_tri": cfg.vg_name("right_tri", VG_RIGHT_TRI),
        "left": cfg.vg_name("left", VG_LEFT),
        "right": cfg.vg_name("right", VG_RIGHT),
        "center": cfg.vg_name("center", VG_CENTER),
        "mismatch": cfg.vg_name("mismatch", VG_MISMATCH),
        "mismatch_left": cfg.vg_name("mismatch_left", VG_MISMATCH_LEFT),
        "mismatch_right": cfg.vg_name("mismatch_right", VG_MISMATCH_RIGHT),
    }

    prev_mode = _ensure_object_mode()

    bm = bmesh.new()
    bm.from_mesh(obj.data)
    uv_lay = bm.loops.layers.uv.get(layer) or bm.loops.layers.uv.active
    if uv_lay is None:
        bm.free()
        _restore_mode(prev_mode)
        return {"error": "uv_layer_not_found", "object": obj_name, "uv_layer": layer}

    probe_us = [round(lp[uv_lay].uv.x, prec) for face in bm.faces for lp in face.loops]
    resolved_center = center_override if center_override is not None else (
        (min(probe_us) + max(probe_us)) / 2.0 if probe_us else 0.5
    )

    geo = _collect_uv_geometry(bm, uv_lay, u_center=resolved_center, prec=prec, tol=tol)

    buckets: dict[str, set[int]] = {name: set() for name in names.values()}

    for side, items in geo["faces_by_side"].items():
        for face, uvs in items:
            n = len(face.verts)
            if side == "center":
                key = "center"
            elif side == "left":
                key = "left_quad" if n == 4 else "left_tri"
            else:
                key = "right_quad" if n == 4 else "right_tri"
            for v in face.verts:
                buckets[names[key]].add(v.index)

    for face, _ in geo["unmatched_left_faces"]:
        for v in face.verts:
            buckets[names["mismatch"]].add(v.index)
            buckets[names["mismatch_left"]].add(v.index)

    for face, _ in geo["unmatched_right_faces"]:
        for v in face.verts:
            buckets[names["mismatch"]].add(v.index)
            buckets[names["mismatch_right"]].add(v.index)

    buckets[names["left"]] = buckets[names["left_quad"]] | buckets[names["left_tri"]]
    buckets[names["right"]] = buckets[names["right_quad"]] | buckets[names["right_tri"]]

    def ensure_vg(name: str):
        vg = obj.vertex_groups.get(name)
        return vg if vg else obj.vertex_groups.new(name=name)

    def clear_vg(vg) -> None:
        for v in obj.data.vertices:
            for g in v.groups:
                if g.group == vg.index:
                    vg.remove([v.index])
                    break

    assigned: dict[str, int] = {}
    for vg_name, vert_ids in buckets.items():
        vg = ensure_vg(vg_name)
        clear_vg(vg)
        if vert_ids:
            vg.add(list(vert_ids), 1.0, "REPLACE")
        assigned[vg_name] = len(vert_ids)

    bm.free()
    _restore_mode(prev_mode)

    return {
        "object": obj_name,
        "mesh": obj.data.name,
        "uv_layer": layer,
        "u_center": round(resolved_center, prec),
        "vertex_groups": assigned,
        "unmatched_faces": geo["unmatched_left_face_count"] + geo["unmatched_right_face_count"],
        "unmatched_left_faces": geo["unmatched_left_face_count"],
        "unmatched_right_faces": geo["unmatched_right_face_count"],
        "how_to_check": [
            "Edit mode: Ctrl+G > Select by Vertex Group",
            "Select TriQuad.Mismatch to highlight non-mirrored UV topology",
            "Compare TriQuad.Left.Quad vs TriQuad.Right.Quad after tri-to-quad",
        ],
    }


def audit_and_assign(
    obj_name: str,
    *,
    profile: str = "default",
    uv_layer: str | None = None,
    u_center: float | None = None,
    uv_precision: int | None = None,
) -> dict[str, Any]:
    """Audit UV symmetry and write TriQuad vertex groups."""
    layer = uv_layer or SymmetryProfile.load(profile).uv_layer
    prec = uv_precision if uv_precision is not None else SymmetryProfile.load(profile).uv_precision
    audit = audit_uv_symmetry(obj_name, uv_layer=layer, u_center=u_center, uv_precision=prec)
    if audit.get("error"):
        return audit
    groups = assign_triquad_vertex_groups(
        obj_name,
        profile=profile,
        uv_layer=layer,
        u_center=u_center,
        uv_precision=prec,
    )
    if groups.get("error"):
        return groups
    return {"audit": audit, "vertex_groups": groups}
