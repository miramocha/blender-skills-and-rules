"""Rewrite the leading JSON chunk of a GLB 2.0 file. Preserve the binary tail."""

from __future__ import annotations

import json
import struct
from typing import Any, Dict, Tuple

GLB_MAGIC = b"glTF"
CHUNK_JSON = 0x4E4F534A


class GlbError(ValueError):
    pass


def split_glb(data: bytes) -> Tuple[Dict[str, Any], bytes, int]:
    if len(data) < 20:
        raise GlbError("file too small for GLB header")
    magic, version, length = struct.unpack_from("<4sII", data, 0)
    if magic != GLB_MAGIC:
        raise GlbError("not a GLB (magic mismatch)")
    if version != 2:
        raise GlbError(f"unsupported GLB version {version}")
    if length != len(data):
        raise GlbError("GLB length does not match file size")
    chunk_len, chunk_type = struct.unpack_from("<II", data, 12)
    if chunk_type != CHUNK_JSON or 20 + chunk_len > len(data):
        raise GlbError("expected a valid leading JSON chunk")
    document = json.loads(data[20 : 20 + chunk_len])
    tail = data[20 + chunk_len :]
    return document, tail, chunk_type


def join_glb(document: Dict[str, Any], tail: bytes, json_chunk_type: int = CHUNK_JSON) -> bytes:
    chunk = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    chunk += b" " * (-len(chunk) % 4)
    return (
        struct.pack("<4sII", GLB_MAGIC, 2, 20 + len(chunk) + len(tail))
        + struct.pack("<II", len(chunk), json_chunk_type)
        + chunk
        + tail
    )
