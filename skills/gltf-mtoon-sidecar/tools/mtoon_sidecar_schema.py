"""Sidecar JSON helpers (no Blender)."""

from __future__ import annotations

from typing import Any, Dict, Optional
import os

SPEC_VERSION = "1.0"
KIND = "mtoon-sidecar"

OUTLINE_MODE_FROM_INT = {
    0: "none",
    1: "worldCoordinates",
    2: "screenCoordinates",
}
OUTLINE_MODE_TO_INT = {v: k for k, v in OUTLINE_MODE_FROM_INT.items()}

ALPHA_MODE_FROM_INT = {0: "OPAQUE", 1: "MASK", 2: "BLEND"}


def outline_mode_from_int(value: Any) -> str:
    try:
        key = int(round(float(value)))
    except (TypeError, ValueError):
        return "none"
    return OUTLINE_MODE_FROM_INT.get(key, "none")


def rgb(value: Any, default: Optional[list] = None) -> list:
    if default is None:
        default = [0.0, 0.0, 0.0]
    if value is None:
        return list(default)
    if hasattr(value, "__len__") and not isinstance(value, (str, bytes)):
        seq = list(value)
        return [float(seq[0]), float(seq[1]), float(seq[2])]
    return list(default)


def rgba(value: Any, default: Optional[list] = None) -> list:
    if default is None:
        default = [1.0, 1.0, 1.0, 1.0]
    if value is None:
        return list(default)
    if hasattr(value, "__len__") and not isinstance(value, (str, bytes)):
        seq = list(value)
        r, g, b = float(seq[0]), float(seq[1]), float(seq[2])
        a = float(seq[3]) if len(seq) > 3 else 1.0
        return [r, g, b, a]
    return list(default)


def with_alpha(rgb_list: Any, alpha: float = 1.0) -> Optional[list]:
    if not rgb_list:
        return None
    seq = list(rgb_list)
    if len(seq) >= 4:
        return [float(seq[0]), float(seq[1]), float(seq[2]), float(seq[3])]
    if len(seq) >= 3:
        return [float(seq[0]), float(seq[1]), float(seq[2]), alpha]
    return None


def portable_basename(path: str) -> str:
    """Strip drive, dirs, and Blender `//` prefix. Datablock name or path → file name only."""
    text = (path or "").replace("\\", "/").strip()
    if text.startswith("//"):
        text = text[2:]
    return os.path.basename(text)


def wrap_document(materials: Dict[str, Any], *, blend: str = "") -> Dict[str, Any]:
    return {
        "specVersion": SPEC_VERSION,
        "kind": KIND,
        "blend": portable_basename(blend),
        "materials": materials,
    }
