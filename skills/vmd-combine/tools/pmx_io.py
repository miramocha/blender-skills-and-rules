"""Read PMX 2.0/2.1 bone/morph/IK names. Stdlib only. No Blender."""

from __future__ import annotations

import json
import os
import struct
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    from .vmd_io import BONE_NAME_LEN, IK_NAME_LEN, MORPH_NAME_LEN, sjis_slot
except ImportError:
    from vmd_io import BONE_NAME_LEN, IK_NAME_LEN, MORPH_NAME_LEN, sjis_slot

FLAG_TAIL_IS_BONE = 0x0001
FLAG_IK = 0x0020
FLAG_INHERIT_ROT = 0x0100
FLAG_INHERIT_TRANS = 0x0200
FLAG_FIXED_AXIS = 0x0400
FLAG_LOCAL_AXIS = 0x0800
FLAG_EXT_PARENT = 0x2000


class PmxError(ValueError):
    pass


@dataclass
class PmxBone:
    name_jp: str
    name_en: str
    is_ik: bool
    index: int


@dataclass
class PmxMorph:
    name_jp: str
    name_en: str
    index: int


@dataclass
class PmxModel:
    path: str
    version: float
    name_jp: str
    name_en: str
    bones: List[PmxBone] = field(default_factory=list)
    morphs: List[PmxMorph] = field(default_factory=list)

    @property
    def ik_bones(self) -> List[PmxBone]:
        return [b for b in self.bones if b.is_ik]


class _R:
    def __init__(self, buf: bytes):
        self.buf = buf
        self.o = 0

    def left(self) -> int:
        return len(self.buf) - self.o

    def need(self, n: int, what: str) -> None:
        if self.o + n > len(self.buf):
            raise PmxError(f"truncated PMX while reading {what} at {self.o}")

    def skip(self, n: int, what: str) -> None:
        self.need(n, what)
        self.o += n

    def u8(self) -> int:
        self.need(1, "u8")
        v = self.buf[self.o]
        self.o += 1
        return v

    def u16(self) -> int:
        self.need(2, "u16")
        v = struct.unpack_from("<H", self.buf, self.o)[0]
        self.o += 2
        return v

    def i32(self) -> int:
        self.need(4, "i32")
        v = struct.unpack_from("<i", self.buf, self.o)[0]
        self.o += 4
        return v

    def f32(self) -> float:
        self.need(4, "f32")
        v = struct.unpack_from("<f", self.buf, self.o)[0]
        self.o += 4
        return v

    def vec3(self) -> Tuple[float, float, float]:
        self.need(12, "vec3")
        v = struct.unpack_from("<3f", self.buf, self.o)
        self.o += 12
        return v

    def vec4(self) -> Tuple[float, float, float, float]:
        self.need(16, "vec4")
        v = struct.unpack_from("<4f", self.buf, self.o)
        self.o += 16
        return v

    def text(self, utf8: bool) -> str:
        n = self.i32()
        if n < 0:
            raise PmxError("negative PMX string length")
        self.need(n, "text")
        raw = self.buf[self.o : self.o + n]
        self.o += n
        enc = "utf-8" if utf8 else "utf-16-le"
        return raw.decode(enc, errors="replace")

    def index(self, size: int) -> int:
        if size == 1:
            v = self.u8()
            return -1 if v == 0xFF else v
        if size == 2:
            self.need(2, "index2")
            v = struct.unpack_from("<H", self.buf, self.o)[0]
            self.o += 2
            return -1 if v == 0xFFFF else v
        if size == 4:
            return self.i32()
        raise PmxError(f"bad index size {size}")


def read_pmx(path: str) -> PmxModel:
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        raise PmxError(f"not a file: {path}")
    with open(path, "rb") as f:
        buf = f.read()
    return parse_pmx(buf, path=path)


def parse_pmx(buf: bytes, path: str = "") -> PmxModel:
    if len(buf) < 8 or buf[:4] != b"PMX ":
        raise PmxError("not a PMX file")
    r = _R(buf)
    r.o = 4
    ver = r.f32()
    glob_n = r.u8()
    if glob_n < 8:
        raise PmxError(f"PMX globals too short ({glob_n})")
    g = [r.u8() for _ in range(glob_n)]
    utf8 = g[0] == 1
    add_uv = g[1]
    i_vtx, i_tex, i_mat, i_bone, i_morph, i_rb = g[2:8]
    name_jp = r.text(utf8)
    name_en = r.text(utf8)
    r.text(utf8)  # comment jp
    r.text(utf8)  # comment en

    n_vtx = r.i32()
    for _ in range(n_vtx):
        _skip_vertex(r, add_uv, i_bone)

    n_idx = r.i32()
    r.skip(n_idx * i_vtx, "faces")

    n_tex = r.i32()
    for _ in range(n_tex):
        r.text(utf8)

    n_mat = r.i32()
    for _ in range(n_mat):
        _skip_material(r, utf8, i_tex)

    n_bone = r.i32()
    bones: List[PmxBone] = []
    for i in range(n_bone):
        bones.append(_read_bone(r, utf8, i_bone, i))

    n_morph = r.i32()
    morphs: List[PmxMorph] = []
    for i in range(n_morph):
        morphs.append(_read_morph(r, utf8, i_vtx, i_bone, i_morph, i_mat, i_rb, i))

    return PmxModel(
        path=path, version=ver, name_jp=name_jp, name_en=name_en, bones=bones, morphs=morphs
    )


def _skip_vertex(r: _R, add_uv: int, i_bone: int) -> None:
    r.skip(12 + 12 + 8, "vertex header")
    r.skip(16 * add_uv, "add UV")
    wtype = r.u8()
    if wtype == 0:
        r.index(i_bone)
    elif wtype == 1:
        r.index(i_bone)
        r.index(i_bone)
        r.f32()
    elif wtype in (2, 4):
        for _ in range(4):
            r.index(i_bone)
        for _ in range(4):
            r.f32()
    elif wtype == 3:
        r.index(i_bone)
        r.index(i_bone)
        r.f32()
        r.skip(12 * 3, "SDEF")
    else:
        raise PmxError(f"unknown vertex weight type {wtype}")
    r.f32()  # edge scale


def _skip_material(r: _R, utf8: bool, i_tex: int) -> None:
    r.text(utf8)
    r.text(utf8)
    r.skip(16 + 12 + 4 + 12 + 1 + 16 + 4, "material colors")
    r.index(i_tex)
    r.index(i_tex)
    r.u8()  # sphere mode
    toon_flag = r.u8()
    if toon_flag == 0:
        r.index(i_tex)
    else:
        r.u8()
    r.text(utf8)
    r.i32()  # face count


def _read_bone(r: _R, utf8: bool, i_bone: int, index: int) -> PmxBone:
    name_jp = r.text(utf8)
    name_en = r.text(utf8)
    r.vec3()
    r.index(i_bone)
    r.i32()  # layer
    flags = r.u16()
    if flags & FLAG_TAIL_IS_BONE:
        r.index(i_bone)
    else:
        r.vec3()
    if flags & (FLAG_INHERIT_ROT | FLAG_INHERIT_TRANS):
        r.index(i_bone)
        r.f32()
    if flags & FLAG_FIXED_AXIS:
        r.vec3()
    if flags & FLAG_LOCAL_AXIS:
        r.vec3()
        r.vec3()
    if flags & FLAG_EXT_PARENT:
        r.i32()
    if flags & FLAG_IK:
        r.index(i_bone)
        r.i32()
        r.f32()
        n_link = r.i32()
        for _ in range(n_link):
            r.index(i_bone)
            limit = r.u8()
            if limit:
                r.vec3()
                r.vec3()
    return PmxBone(name_jp=name_jp, name_en=name_en, is_ik=bool(flags & FLAG_IK), index=index)


def _read_morph(
    r: _R,
    utf8: bool,
    i_vtx: int,
    i_bone: int,
    i_morph: int,
    i_mat: int,
    i_rb: int,
    index: int,
) -> PmxMorph:
    name_jp = r.text(utf8)
    name_en = r.text(utf8)
    r.u8()  # panel
    mtype = r.u8()
    n = r.i32()
    if mtype == 0 or mtype == 9:
        for _ in range(n):
            r.index(i_morph)
            r.f32()
    elif mtype == 1:
        for _ in range(n):
            r.index(i_vtx)
            r.vec3()
    elif mtype == 2:
        for _ in range(n):
            r.index(i_bone)
            r.vec3()
            r.vec4()
    elif mtype in (3, 4, 5, 6, 7):
        for _ in range(n):
            r.index(i_vtx)
            r.vec4()
    elif mtype == 8:
        for _ in range(n):
            r.index(i_mat)
            r.u8()
            r.skip(4 * 4 + 12 + 4 + 12 + 16 + 4 + 16 + 16 + 16, "mat morph")
    elif mtype == 10:
        for _ in range(n):
            r.index(i_rb)
            r.u8()
            r.vec3()
            r.vec3()
    else:
        raise PmxError(f"unknown morph type {mtype}")
    return PmxMorph(name_jp=name_jp, name_en=name_en, index=index)


def inspect_pmx(path: str) -> dict:
    m = load_model(path)
    return {
        "ok": True,
        "path": m.path,
        "version": m.version,
        "name_jp": m.name_jp,
        "name_en": m.name_en,
        "bone_count": len(m.bones),
        "morph_count": len(m.morphs),
        "ik_count": len(m.ik_bones),
        "ik_names": [b.name_jp for b in m.ik_bones],
    }


RIG_KIND = "vmd-combine-rig"
RIG_VERSION = 1


def pmx_to_rig(model: PmxModel) -> Dict[str, Any]:
    """Names + IK flags only. No mesh, vertices, textures, or rest pose."""
    return {
        "kind": RIG_KIND,
        "version": RIG_VERSION,
        "name_jp": model.name_jp,
        "name_en": model.name_en,
        "source": os.path.basename(model.path) if model.path else "",
        "bones": [
            {
                "index": b.index,
                "name_jp": b.name_jp,
                "name_en": b.name_en,
                "is_ik": b.is_ik,
            }
            for b in model.bones
        ],
        "morphs": [
            {
                "index": m.index,
                "name_jp": m.name_jp,
                "name_en": m.name_en,
            }
            for m in model.morphs
        ],
    }


def rig_to_model(data: Dict[str, Any], path: str = "") -> PmxModel:
    kind = data.get("kind")
    if kind not in (None, RIG_KIND):
        raise PmxError(f"unknown rig kind {kind!r}")
    if "bones" not in data or "morphs" not in data:
        raise PmxError("rig JSON missing bones/morphs")
    bones = []
    for i, raw in enumerate(data.get("bones") or []):
        if isinstance(raw, str):
            bones.append(PmxBone(name_jp=raw, name_en="", is_ik=False, index=i))
            continue
        bones.append(
            PmxBone(
                name_jp=str(raw.get("name_jp") or raw.get("name") or ""),
                name_en=str(raw.get("name_en") or ""),
                is_ik=bool(raw.get("is_ik")),
                index=int(raw["index"]) if "index" in raw else i,
            )
        )
    morphs = []
    for i, raw in enumerate(data.get("morphs") or []):
        if isinstance(raw, str):
            morphs.append(PmxMorph(name_jp=raw, name_en="", index=i))
            continue
        morphs.append(
            PmxMorph(
                name_jp=str(raw.get("name_jp") or raw.get("name") or ""),
                name_en=str(raw.get("name_en") or ""),
                index=int(raw["index"]) if "index" in raw else i,
            )
        )
    return PmxModel(
        path=path,
        version=float(data.get("version") or RIG_VERSION),
        name_jp=str(data.get("name_jp") or ""),
        name_en=str(data.get("name_en") or ""),
        bones=bones,
        morphs=morphs,
    )


def load_rig(path: str) -> PmxModel:
    path = os.path.abspath(path)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise PmxError("rig JSON must be an object")
    return rig_to_model(data, path=path)


def write_rig(src_pmx: str, dst: str) -> Dict[str, Any]:
    model = read_pmx(src_pmx)
    dst = os.path.abspath(dst)
    parent = os.path.dirname(dst)
    if parent:
        os.makedirs(parent, exist_ok=True)
    payload = pmx_to_rig(model)
    with open(dst, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return {
        "ok": True,
        "pmx": os.path.abspath(src_pmx),
        "output_path": dst,
        "name_jp": model.name_jp,
        "bone_count": len(model.bones),
        "morph_count": len(model.morphs),
        "ik_count": len(model.ik_bones),
        "bytes": os.path.getsize(dst),
    }


def load_model(path: str) -> PmxModel:
    path = os.path.abspath(path)
    lower = path.lower()
    if lower.endswith(".json") or lower.endswith(".rig.json"):
        return load_rig(path)
    return read_pmx(path)


def vmd_name_set(names: List[str], width: int) -> Set[str]:
    out: Set[str] = set()
    for n in names:
        if not n:
            continue
        out.add(n)
        out.add(sjis_slot(n, width))
    return out


def bone_allowlist(model: PmxModel) -> Set[str]:
    names: List[str] = []
    for b in model.bones:
        names.append(b.name_jp)
        names.append(b.name_en)
    return vmd_name_set(names, BONE_NAME_LEN)


def morph_allowlist(model: PmxModel) -> Set[str]:
    names: List[str] = []
    for m in model.morphs:
        names.append(m.name_jp)
        names.append(m.name_en)
    return vmd_name_set(names, MORPH_NAME_LEN)


def bone_index_map(model: PmxModel) -> dict:
    """VMD slot name → first PMX bone index (JP preferred)."""
    out = {}
    for b in model.bones:
        for n in (b.name_en, b.name_jp):
            if n:
                out[n] = b.index
                out[sjis_slot(n, BONE_NAME_LEN)] = b.index
    return out


def morph_index_map(model: PmxModel) -> dict:
    out = {}
    for m in model.morphs:
        for n in (m.name_en, m.name_jp):
            if n:
                out[n] = m.index
                out[sjis_slot(n, MORPH_NAME_LEN)] = m.index
    return out


def ik_slot_names(model: PmxModel) -> List[str]:
    """PMX IK bones in model order, as VMD 20-byte names."""
    seen = set()
    out: List[str] = []
    for b in model.ik_bones:
        slot = sjis_slot(b.name_jp or b.name_en, IK_NAME_LEN)
        if slot and slot not in seen:
            seen.add(slot)
            out.append(slot)
    return out


def rest_bone_slots(model: PmxModel) -> List[str]:
    seen = set()
    out: List[str] = []
    for b in model.bones:
        slot = sjis_slot(b.name_jp or b.name_en, BONE_NAME_LEN)
        if slot and slot not in seen:
            seen.add(slot)
            out.append(slot)
    return out


def rest_morph_slots(model: PmxModel) -> List[str]:
    seen = set()
    out: List[str] = []
    for m in model.morphs:
        slot = sjis_slot(m.name_jp or m.name_en, MORPH_NAME_LEN)
        if slot and slot not in seen:
            seen.add(slot)
            out.append(slot)
    return out


# --- test helper: tiny PMX 2.0 (UTF-8, empty mesh) ---

def dumps_test_pmx(
    name_jp: str,
    bones: List[Tuple[str, bool]],
    morphs: List[str],
) -> bytes:
    """bones: (jp_name, is_ik). No geometry. For unit tests only."""

    def tx(s: str) -> bytes:
        raw = s.encode("utf-8")
        return struct.pack("<i", len(raw)) + raw

    parts = [b"PMX ", struct.pack("<f", 2.0), bytes([8, 1, 0, 1, 1, 1, 1, 1, 1])]
    parts.append(tx(name_jp))
    parts.append(tx("en"))
    parts.append(tx(""))
    parts.append(tx(""))
    parts.append(struct.pack("<i", 0))  # vtx
    parts.append(struct.pack("<i", 0))  # faces
    parts.append(struct.pack("<i", 0))  # tex
    parts.append(struct.pack("<i", 0))  # mat
    parts.append(struct.pack("<i", len(bones)))
    for name, is_ik in bones:
        flags = 0x001E | (FLAG_IK if is_ik else 0)
        parts.append(tx(name))
        parts.append(tx(""))
        parts.append(struct.pack("<3f", 0.0, 0.0, 0.0))
        parts.append(bytes([0xFF]))  # parent none
        parts.append(struct.pack("<i", 0))
        parts.append(struct.pack("<H", flags))
        parts.append(struct.pack("<3f", 0.0, 0.0, 0.0))  # tail offset
        if is_ik:
            parts.append(bytes([0xFF]))  # target
            parts.append(struct.pack("<i", 0))
            parts.append(struct.pack("<f", 0.0))
            parts.append(struct.pack("<i", 0))  # links
    parts.append(struct.pack("<i", len(morphs)))
    for name in morphs:
        parts.append(tx(name))
        parts.append(tx(""))
        parts.append(bytes([0, 1]))  # panel, vertex type
        parts.append(struct.pack("<i", 0))
    return b"".join(parts)
