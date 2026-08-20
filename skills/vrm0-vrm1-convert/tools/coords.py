"""Coordinate rewrite matching UniVRM Model.ConvertCoordinate Vrm0→Unity→Vrm1.

Vrm0↔Unity: reverse Z + UV V-flip + triangle flip.
Vrm1↔Unity: reverse X + UV V-flip + triangle flip.

Net Vrm0 file → Vrm1 file:
- VEC3 / node translation: (x, y, z) → (-x, y, -z)
- UV and indices: two flips cancel (unchanged)
- MAT4 / node matrix: R * M * R with R = diag(-1, 1, -1, 1)
- node rotation: sandwich with 180° around Y

Extension JSON vectors (spring offset, gravityDir, lookAt) use
MigrateVector3: (x, y, z) → (-x, y, z) — applied in migrate_*.py, not here.
"""

from __future__ import annotations

import struct
from typing import Any, Dict, List, Optional, Set, Tuple

# glTF accessor.componentType
CT_BYTE = 5120
CT_UBYTE = 5121
CT_SHORT = 5122
CT_USHORT = 5123
CT_UINT = 5125
CT_FLOAT = 5126

_COMP_SIZE = {
    CT_BYTE: 1,
    CT_UBYTE: 1,
    CT_SHORT: 2,
    CT_USHORT: 2,
    CT_UINT: 4,
    CT_FLOAT: 4,
}

_NCOMP = {
    "SCALAR": 1,
    "VEC2": 2,
    "VEC3": 3,
    "VEC4": 4,
    "MAT2": 4,
    "MAT3": 9,
    "MAT4": 16,
}


def qmul(a: Tuple[float, float, float, float], b: Tuple[float, float, float, float]):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    )


# 180° around +Y (xyzw)
_QY180 = (0.0, 1.0, 0.0, 0.0)


def rotate_quat_vrm0_vrm1(q: List[float]) -> List[float]:
    """Change-of-basis for net ReverseZ then ReverseX (180° Y)."""
    qq = (float(q[0]), float(q[1]), float(q[2]), float(q[3]))
    out = qmul(qmul(_QY180, qq), _QY180)
    return [out[0], out[1], out[2], out[3]]


def vec3_mesh(x: float, y: float, z: float) -> Tuple[float, float, float]:
    return (-x, y, -z)


def mat4_similarity(m: List[float]) -> List[float]:
    """R * M * R, R = diag(-1, 1, -1, 1), column-major glTF 4x4."""
    r = [-1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, -1.0, 0, 0, 0, 0, 1.0]
    return _matmul4(r, _matmul4(m, r))


def _matmul4(a: List[float], b: List[float]) -> List[float]:
    out = [0.0] * 16
    for col in range(4):
        for row in range(4):
            s = 0.0
            for k in range(4):
                s += a[k * 4 + row] * b[col * 4 + k]
            out[col * 4 + row] = s
    return out


def _accessor_elem_size(acc: Dict[str, Any]) -> int:
    ct = acc.get("componentType", CT_FLOAT)
    n = _NCOMP.get(acc.get("type", "SCALAR"), 1)
    return _COMP_SIZE[ct] * n


def rewrite_bin_vrm0_vrm1(gltf: Dict[str, Any], blob: bytearray) -> None:
    """In-place BIN rewrite for VRM0↔VRM1 (involution). Mutates blob."""
    accessors = gltf.get("accessors") or []
    views = gltf.get("bufferViews") or []
    seen: Set[Tuple[int, int, int, str]] = set()

    def transform_accessor(index: Optional[int], kind: str) -> None:
        if index is None:
            return
        acc = accessors[index]
        if acc.get("sparse"):
            return
        bv_i = acc.get("bufferView")
        if bv_i is None:
            return
        bv = views[bv_i]
        if bv.get("buffer", 0) != 0:
            return
        ct = acc.get("componentType")
        if ct != CT_FLOAT:
            return
        atype = acc.get("type")
        count = int(acc.get("count", 0))
        base = int(bv.get("byteOffset", 0)) + int(acc.get("byteOffset", 0))
        elem = _accessor_elem_size(acc)
        stride = int(bv.get("byteStride") or elem)
        key = (base, count, stride, kind)
        if key in seen:
            return
        seen.add(key)

        if kind == "vec3" and atype == "VEC3":
            for i in range(count):
                off = base + i * stride
                x, y, z = struct.unpack_from("<fff", blob, off)
                nx, ny, nz = vec3_mesh(x, y, z)
                struct.pack_into("<fff", blob, off, nx, ny, nz)
        elif kind == "vec4xyz" and atype == "VEC4":
            for i in range(count):
                off = base + i * stride
                x, y, z, w = struct.unpack_from("<ffff", blob, off)
                nx, ny, nz = vec3_mesh(x, y, z)
                struct.pack_into("<ffff", blob, off, nx, ny, nz, w)
        elif kind == "mat4" and atype == "MAT4":
            for i in range(count):
                off = base + i * stride
                m = list(struct.unpack_from("<16f", blob, off))
                m2 = mat4_similarity(m)
                struct.pack_into("<16f", blob, off, *m2)

    for mesh in gltf.get("meshes") or []:
        for prim in mesh.get("primitives") or []:
            attrs = prim.get("attributes") or {}
            transform_accessor(attrs.get("POSITION"), "vec3")
            transform_accessor(attrs.get("NORMAL"), "vec3")
            transform_accessor(attrs.get("TANGENT"), "vec4xyz")
            for target in prim.get("targets") or []:
                transform_accessor(target.get("POSITION"), "vec3")
                transform_accessor(target.get("NORMAL"), "vec3")
                transform_accessor(target.get("TANGENT"), "vec4xyz")

    for skin in gltf.get("skins") or []:
        transform_accessor(skin.get("inverseBindMatrices"), "mat4")

    for node in gltf.get("nodes") or []:
        if "translation" in node and len(node["translation"]) >= 3:
            t = node["translation"]
            nx, ny, nz = vec3_mesh(float(t[0]), float(t[1]), float(t[2]))
            node["translation"] = [nx, ny, nz]
        if "rotation" in node and len(node["rotation"]) >= 4:
            node["rotation"] = rotate_quat_vrm0_vrm1(list(node["rotation"]))
        if "matrix" in node and len(node["matrix"]) == 16:
            node["matrix"] = mat4_similarity([float(x) for x in node["matrix"]])

    for anim in gltf.get("animations") or []:
        samplers = anim.get("samplers") or []
        accs = gltf.get("accessors") or []
        for ch in anim.get("channels") or []:
            path = (ch.get("target") or {}).get("path")
            si = ch.get("sampler")
            if si is None or si >= len(samplers):
                continue
            out_i = samplers[si].get("output")
            if path == "translation":
                transform_accessor(out_i, "vec3")
            elif path == "rotation" and out_i is not None:
                acc = accs[out_i]
                if acc.get("type") == "VEC4" and acc.get("componentType") == CT_FLOAT:
                    bv_i = acc.get("bufferView")
                    if bv_i is None:
                        continue
                    bv = views[bv_i]
                    base = int(bv.get("byteOffset", 0)) + int(acc.get("byteOffset", 0))
                    count = int(acc.get("count", 0))
                    elem = _accessor_elem_size(acc)
                    stride = int(bv.get("byteStride") or elem)
                    key = (base, count, stride, "quat")
                    if key in seen:
                        continue
                    seen.add(key)
                    for i in range(count):
                        off = base + i * stride
                        q = list(struct.unpack_from("<ffff", blob, off))
                        q2 = rotate_quat_vrm0_vrm1(q)
                        struct.pack_into("<ffff", blob, off, *q2)


def migrate_vector3_ext(vec: Any) -> List[float]:
    """UniVRM MigrateVector3: VRM0 JSON vec → VRM1 (-x, y, z)."""
    x, y, z = _as_xyz(vec)
    return [-x, y, z]


def _as_xyz(vec: Any) -> Tuple[float, float, float]:
    if vec is None:
        return (0.0, 0.0, 0.0)
    if isinstance(vec, dict):
        return (float(vec.get("x", 0)), float(vec.get("y", 0)), float(vec.get("z", 0)))
    if isinstance(vec, (list, tuple)) and len(vec) >= 3:
        return (float(vec[0]), float(vec[1]), float(vec[2]))
    return (0.0, 0.0, 0.0)
