"""Detect VRM 0.x vs 1.0 from glTF JSON extensions."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple


def detect_vrm_version(gltf: Dict[str, Any]) -> Tuple[Optional[str], Dict[str, Any]]:
    """
    Return ('0.x'|'1.0'|None, detail).
    Both extensions present → 'both'.
    """
    ext = gltf.get("extensions") or {}
    used = list(gltf.get("extensionsUsed") or [])
    has_vrm0 = "VRM" in ext or "VRM" in used
    has_vrm1 = "VRMC_vrm" in ext or "VRMC_vrm" in used
    detail = {
        "has_vrm0_extension": "VRM" in ext,
        "has_vrm1_extension": "VRMC_vrm" in ext,
        "extensionsUsed": used,
        "vrm0_spec": None,
        "vrm1_spec": None,
    }
    if "VRM" in ext:
        detail["vrm0_spec"] = (ext["VRM"] or {}).get("specVersion") or (ext["VRM"] or {}).get(
            "exporterVersion"
        )
    if "VRMC_vrm" in ext:
        detail["vrm1_spec"] = (ext["VRMC_vrm"] or {}).get("specVersion")
    if has_vrm0 and has_vrm1:
        return "both", detail
    if has_vrm1:
        return "1.0", detail
    if has_vrm0:
        return "0.x", detail
    return None, detail
