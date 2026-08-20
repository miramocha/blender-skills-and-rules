"""Stdlib GLB (glTF 2.0 binary) read/write. No bpy, no pip."""

from __future__ import annotations

import json
import struct
from typing import Any, Dict, Tuple

GLB_MAGIC = 0x46546C67
CHUNK_JSON = 0x4E4F534A
CHUNK_BIN = 0x004E4942


class GlbError(ValueError):
    pass


def _pad4(n: int) -> int:
    return (4 - (n % 4)) % 4


def read_glb(data: bytes) -> Tuple[Dict[str, Any], bytes]:
    if len(data) < 12:
        raise GlbError("file too small for GLB header")
    magic, version, length = struct.unpack_from("<III", data, 0)
    if magic != GLB_MAGIC:
        raise GlbError("not a GLB (magic mismatch)")
    if version != 2:
        raise GlbError(f"unsupported GLB version {version}")
    if length > len(data):
        raise GlbError("GLB length exceeds file")

    offset = 12
    json_dict: Dict[str, Any] | None = None
    bin_chunk = b""
    while offset + 8 <= length:
        chunk_len, chunk_type = struct.unpack_from("<II", data, offset)
        offset += 8
        chunk = data[offset : offset + chunk_len]
        offset += chunk_len
        if chunk_type == CHUNK_JSON:
            json_dict = json.loads(chunk.decode("utf-8"))
        elif chunk_type == CHUNK_BIN:
            bin_chunk = chunk
    if json_dict is None:
        raise GlbError("GLB missing JSON chunk")
    return json_dict, bin_chunk


def write_glb(gltf: Dict[str, Any], bin_chunk: bytes) -> bytes:
    json_bytes = json.dumps(gltf, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    json_pad = _pad4(len(json_bytes))
    json_bytes += b" " * json_pad
    bin_pad = _pad4(len(bin_chunk))
    bin_out = bin_chunk + (b"\x00" * bin_pad)

    total = 12 + 8 + len(json_bytes) + 8 + len(bin_out)
    header = struct.pack("<III", GLB_MAGIC, 2, total)
    json_header = struct.pack("<II", len(json_bytes), CHUNK_JSON)
    bin_header = struct.pack("<II", len(bin_out), CHUNK_BIN)
    return header + json_header + json_bytes + bin_header + bin_out
