"""Read/write MikuMikuDance .vmd (Vocaloid Motion Data). Stdlib only."""

from __future__ import annotations

import os
import struct
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

SIG_0002 = b"Vocaloid Motion Data 0002"
SIG_OLD = b"Vocaloid Motion Data file"

BONE_NAME_LEN = 15
MORPH_NAME_LEN = 15
MODEL_NAME_LEN_0002 = 20
MODEL_NAME_LEN_OLD = 10
IK_NAME_LEN = 20
HEADER_SIG_LEN = 30
BONE_FRAME_SIZE = 111
MORPH_FRAME_SIZE = 23
CAMERA_FRAME_SIZE = 61
LIGHT_FRAME_SIZE = 28
SHADOW_FRAME_SIZE = 9

# Common facial control bones (JP). Used by take=face_bones.
FACE_BONE_NAMES = frozenset(
    {
        "目",
        "両目",
        "左目",
        "右目",
        "あご",
        "顎",
        "歯",
        "舌",
        "Eyeball_L",
        "Eyeball_R",
        "Eye_L",
        "Eye_R",
    }
)

ALL_CHANNELS = ("bones", "morphs", "camera", "light", "shadow", "ik")


class VmdError(ValueError):
    pass


def _decode_sjis(raw: bytes) -> str:
    cut = raw.split(b"\x00", 1)[0]
    return cut.decode("cp932", errors="replace")


def _encode_sjis(text: str, width: int) -> bytes:
    encoded = text.encode("cp932", errors="replace")[:width]
    return encoded + b"\x00" * (width - len(encoded))


def sjis_slot(text: str, width: int) -> str:
    """Name as stored in a VMD fixed-width Shift-JIS field (truncated)."""
    return _decode_sjis(_encode_sjis(text, width))


def _need(buf: bytes, offset: int, size: int, what: str) -> None:
    if offset + size > len(buf):
        raise VmdError(f"truncated VMD while reading {what} at offset {offset}")


@dataclass
class BoneKey:
    name: str
    frame: int
    pos: Tuple[float, float, float]
    rot: Tuple[float, float, float, float]  # xyzw
    interpolation: bytes

    def key(self) -> Tuple[str, int]:
        return (self.name, self.frame)


@dataclass
class MorphKey:
    name: str
    frame: int
    weight: float

    def key(self) -> Tuple[str, int]:
        return (self.name, self.frame)


@dataclass
class CameraKey:
    frame: int
    distance: float
    pos: Tuple[float, float, float]
    rot: Tuple[float, float, float]
    interpolation: bytes
    fov: int
    perspective: int

    def key(self) -> Tuple[int]:
        return (self.frame,)


@dataclass
class LightKey:
    frame: int
    color: Tuple[float, float, float]
    direction: Tuple[float, float, float]

    def key(self) -> Tuple[int]:
        return (self.frame,)


@dataclass
class ShadowKey:
    frame: int
    type: int
    distance: float

    def key(self) -> Tuple[int]:
        return (self.frame,)


@dataclass
class IkEnable:
    name: str
    enable: int


@dataclass
class IkKey:
    frame: int
    show: int
    iks: List[IkEnable] = field(default_factory=list)

    def key(self) -> Tuple[int]:
        return (self.frame,)


@dataclass
class VmdMotion:
    signature: str
    model_name: str
    bones: List[BoneKey] = field(default_factory=list)
    morphs: List[MorphKey] = field(default_factory=list)
    camera: List[CameraKey] = field(default_factory=list)
    light: List[LightKey] = field(default_factory=list)
    shadow: List[ShadowKey] = field(default_factory=list)
    ik: List[IkKey] = field(default_factory=list)
    extra: bytes = b""


def read_vmd(path: str) -> VmdMotion:
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        raise VmdError(f"not a file: {path}")
    with open(path, "rb") as f:
        buf = f.read()
    return parse_vmd(buf)


def parse_vmd(buf: bytes) -> VmdMotion:
    if len(buf) < HEADER_SIG_LEN + MODEL_NAME_LEN_OLD:
        raise VmdError("file too small to be VMD")
    sig_raw = buf[:HEADER_SIG_LEN]
    sig = _decode_sjis(sig_raw).rstrip("\x00")
    offset = HEADER_SIG_LEN
    if sig_raw.startswith(SIG_0002):
        _need(buf, offset, MODEL_NAME_LEN_0002, "model name")
        model = _decode_sjis(buf[offset : offset + MODEL_NAME_LEN_0002])
        offset += MODEL_NAME_LEN_0002
    elif sig_raw.startswith(SIG_OLD):
        _need(buf, offset, MODEL_NAME_LEN_OLD, "legacy model name")
        model = _decode_sjis(buf[offset : offset + MODEL_NAME_LEN_OLD])
        offset += MODEL_NAME_LEN_OLD
    else:
        raise VmdError(f"not a VMD file (signature {sig_raw[:30]!r})")

    motion = VmdMotion(signature=sig, model_name=model)
    offset = _read_bones(buf, offset, motion)
    offset = _read_morphs(buf, offset, motion)
    offset = _read_camera(buf, offset, motion)
    offset = _read_light(buf, offset, motion)
    offset = _read_shadow(buf, offset, motion)
    offset = _read_ik(buf, offset, motion)
    motion.extra = buf[offset:]
    return motion


def _read_u32(buf: bytes, offset: int) -> Tuple[Optional[int], int]:
    if offset + 4 > len(buf):
        return None, offset
    return struct.unpack_from("<I", buf, offset)[0], offset + 4


def _read_bones(buf: bytes, offset: int, motion: VmdMotion) -> int:
    n, offset = _read_u32(buf, offset)
    if n is None:
        return offset
    need = n * BONE_FRAME_SIZE
    if offset + need > len(buf):
        raise VmdError(f"bone section claims {n} frames, not enough bytes")
    for _ in range(n):
        name = _decode_sjis(buf[offset : offset + BONE_NAME_LEN])
        offset += BONE_NAME_LEN
        frame = struct.unpack_from("<I", buf, offset)[0]
        offset += 4
        pos = struct.unpack_from("<3f", buf, offset)
        offset += 12
        rot = struct.unpack_from("<4f", buf, offset)
        offset += 16
        interp = bytes(buf[offset : offset + 64])
        offset += 64
        motion.bones.append(
            BoneKey(name=name, frame=frame, pos=pos, rot=rot, interpolation=interp)
        )
    return offset


def _read_morphs(buf: bytes, offset: int, motion: VmdMotion) -> int:
    n, offset = _read_u32(buf, offset)
    if n is None:
        return offset
    need = n * MORPH_FRAME_SIZE
    if offset + need > len(buf):
        raise VmdError(f"morph section claims {n} frames, not enough bytes")
    for _ in range(n):
        name = _decode_sjis(buf[offset : offset + MORPH_NAME_LEN])
        offset += MORPH_NAME_LEN
        frame = struct.unpack_from("<I", buf, offset)[0]
        offset += 4
        weight = struct.unpack_from("<f", buf, offset)[0]
        offset += 4
        motion.morphs.append(MorphKey(name=name, frame=frame, weight=weight))
    return offset


def _read_camera(buf: bytes, offset: int, motion: VmdMotion) -> int:
    n, offset = _read_u32(buf, offset)
    if n is None:
        return offset
    need = n * CAMERA_FRAME_SIZE
    if offset + need > len(buf):
        raise VmdError(f"camera section claims {n} frames, not enough bytes")
    for _ in range(n):
        frame = struct.unpack_from("<I", buf, offset)[0]
        offset += 4
        distance = struct.unpack_from("<f", buf, offset)[0]
        offset += 4
        pos = struct.unpack_from("<3f", buf, offset)
        offset += 12
        rot = struct.unpack_from("<3f", buf, offset)
        offset += 12
        interp = bytes(buf[offset : offset + 24])
        offset += 24
        fov = struct.unpack_from("<I", buf, offset)[0]
        offset += 4
        perspective = buf[offset]
        offset += 1
        motion.camera.append(
            CameraKey(
                frame=frame,
                distance=distance,
                pos=pos,
                rot=rot,
                interpolation=interp,
                fov=fov,
                perspective=perspective,
            )
        )
    return offset


def _read_light(buf: bytes, offset: int, motion: VmdMotion) -> int:
    n, offset = _read_u32(buf, offset)
    if n is None:
        return offset
    need = n * LIGHT_FRAME_SIZE
    if offset + need > len(buf):
        raise VmdError(f"light section claims {n} frames, not enough bytes")
    for _ in range(n):
        frame = struct.unpack_from("<I", buf, offset)[0]
        offset += 4
        color = struct.unpack_from("<3f", buf, offset)
        offset += 12
        direction = struct.unpack_from("<3f", buf, offset)
        offset += 12
        motion.light.append(LightKey(frame=frame, color=color, direction=direction))
    return offset


def _read_shadow(buf: bytes, offset: int, motion: VmdMotion) -> int:
    n, offset = _read_u32(buf, offset)
    if n is None:
        return offset
    need = n * SHADOW_FRAME_SIZE
    if offset + need > len(buf):
        raise VmdError(f"shadow section claims {n} frames, not enough bytes")
    for _ in range(n):
        frame = struct.unpack_from("<I", buf, offset)[0]
        offset += 4
        typ = buf[offset]
        offset += 1
        distance = struct.unpack_from("<f", buf, offset)[0]
        offset += 4
        motion.shadow.append(ShadowKey(frame=frame, type=typ, distance=distance))
    return offset


def _read_ik(buf: bytes, offset: int, motion: VmdMotion) -> int:
    n, offset = _read_u32(buf, offset)
    if n is None:
        return offset
    for i in range(n):
        if offset + 4 + 1 + 4 > len(buf):
            raise VmdError(f"truncated IK frame {i}")
        frame = struct.unpack_from("<I", buf, offset)[0]
        offset += 4
        show = buf[offset]
        offset += 1
        ik_count = struct.unpack_from("<I", buf, offset)[0]
        offset += 4
        iks: List[IkEnable] = []
        for _ in range(ik_count):
            _need(buf, offset, IK_NAME_LEN + 1, "IK enable")
            name = _decode_sjis(buf[offset : offset + IK_NAME_LEN])
            offset += IK_NAME_LEN
            enable = buf[offset]
            offset += 1
            iks.append(IkEnable(name=name, enable=enable))
        motion.ik.append(IkKey(frame=frame, show=show, iks=iks))
    return offset


def dumps_vmd(motion: VmdMotion) -> bytes:
    parts = [
        _encode_sjis("Vocaloid Motion Data 0002", HEADER_SIG_LEN),
        _encode_sjis(motion.model_name or "", MODEL_NAME_LEN_0002),
    ]
    parts.append(struct.pack("<I", len(motion.bones)))
    for k in motion.bones:
        parts.append(_encode_sjis(k.name, BONE_NAME_LEN))
        parts.append(struct.pack("<I", int(k.frame)))
        parts.append(struct.pack("<3f", *k.pos))
        parts.append(struct.pack("<4f", *k.rot))
        interp = k.interpolation if len(k.interpolation) == 64 else (k.interpolation + bytes(64))[:64]
        parts.append(interp)
    parts.append(struct.pack("<I", len(motion.morphs)))
    for k in motion.morphs:
        parts.append(_encode_sjis(k.name, MORPH_NAME_LEN))
        parts.append(struct.pack("<I", int(k.frame)))
        parts.append(struct.pack("<f", float(k.weight)))
    parts.append(struct.pack("<I", len(motion.camera)))
    for k in motion.camera:
        parts.append(struct.pack("<I", int(k.frame)))
        parts.append(struct.pack("<f", float(k.distance)))
        parts.append(struct.pack("<3f", *k.pos))
        parts.append(struct.pack("<3f", *k.rot))
        interp = k.interpolation if len(k.interpolation) == 24 else (k.interpolation + bytes(24))[:24]
        parts.append(interp)
        parts.append(struct.pack("<I", int(k.fov)))
        parts.append(struct.pack("B", int(k.perspective) & 0xFF))
    parts.append(struct.pack("<I", len(motion.light)))
    for k in motion.light:
        parts.append(struct.pack("<I", int(k.frame)))
        parts.append(struct.pack("<3f", *k.color))
        parts.append(struct.pack("<3f", *k.direction))
    parts.append(struct.pack("<I", len(motion.shadow)))
    for k in motion.shadow:
        parts.append(struct.pack("<I", int(k.frame)))
        parts.append(struct.pack("B", int(k.type) & 0xFF))
        parts.append(struct.pack("<f", float(k.distance)))
    parts.append(struct.pack("<I", len(motion.ik)))
    for k in motion.ik:
        parts.append(struct.pack("<I", int(k.frame)))
        parts.append(struct.pack("B", int(k.show) & 0xFF))
        parts.append(struct.pack("<I", len(k.iks)))
        for ik in k.iks:
            parts.append(_encode_sjis(ik.name, IK_NAME_LEN))
            parts.append(struct.pack("B", int(ik.enable) & 0xFF))
    return b"".join(parts)


def write_vmd(path: str, motion: VmdMotion) -> int:
    path = os.path.abspath(path)
    data = dumps_vmd(motion)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    return len(data)


def max_frame(motion: VmdMotion) -> int:
    frames = [0]
    frames.extend(k.frame for k in motion.bones)
    frames.extend(k.frame for k in motion.morphs)
    frames.extend(k.frame for k in motion.camera)
    frames.extend(k.frame for k in motion.light)
    frames.extend(k.frame for k in motion.shadow)
    frames.extend(k.frame for k in motion.ik)
    return max(frames)


def inspect_vmd(path: str) -> Dict[str, Any]:
    motion = read_vmd(path)
    bone_names = sorted({k.name for k in motion.bones})
    morph_names = sorted({k.name for k in motion.morphs})
    return {
        "ok": True,
        "path": os.path.abspath(path),
        "signature": motion.signature,
        "model_name": motion.model_name,
        "bytes": os.path.getsize(path),
        "max_frame": max_frame(motion),
        "counts": {
            "bones": len(motion.bones),
            "morphs": len(motion.morphs),
            "camera": len(motion.camera),
            "light": len(motion.light),
            "shadow": len(motion.shadow),
            "ik": len(motion.ik),
            "bone_names": len(bone_names),
            "morph_names": len(morph_names),
        },
        "bone_names": bone_names,
        "morph_names": morph_names,
        "face_bones_present": sorted(
            n for n in bone_names if n in FACE_BONE_NAMES
        ),
    }


# MMD default bezier (20/107). Rest-pose pads use this so keys match MMD save.
MMD_IDENTITY_INTERP = bytes.fromhex(
    "14140000141414146b6b6b6b6b6b6b6b"
    "141414141414146b6b6b6b6b6b6b6b00"
    "1414141414146b6b6b6b6b6b6b6b0000"
    "14141414146b6b6b6b6b6b6b6b000000"
)


def identity_interpolation() -> bytes:
    return MMD_IDENTITY_INTERP
