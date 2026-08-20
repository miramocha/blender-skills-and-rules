"""Convert a .vrm GLB between VRM 0.x and VRM 1.0. Stdlib only. No Blender/Unity."""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from typing import Any, Dict, Optional

try:
    from .coords import rewrite_bin_vrm0_vrm1
    from .detect import detect_vrm_version
    from .glb_io import GlbError, read_glb, write_glb
    from .migrate_0_to_1 import migrate_vrm0_to_vrm1
    from .migrate_1_to_0 import migrate_vrm1_to_vrm0
except ImportError:
    from coords import rewrite_bin_vrm0_vrm1
    from detect import detect_vrm_version
    from glb_io import GlbError, read_glb, write_glb
    from migrate_0_to_1 import migrate_vrm0_to_vrm1
    from migrate_1_to_0 import migrate_vrm1_to_vrm0


def convert_vrm(
    src: str,
    dst: Optional[str] = None,
    direction: str = "auto",
    dry_run: bool = True,
) -> Dict[str, Any]:
    """
    direction: 'auto' | '0to1' | '1to0'
    dry_run: if True, do not write dst.
    """
    src = os.path.abspath(src)
    with open(src, "rb") as f:
        raw = f.read()
    try:
        gltf, bin_chunk = read_glb(raw)
    except GlbError as e:
        return {"ok": False, "error": str(e), "src": src}

    ver, detail = detect_vrm_version(gltf)
    if ver is None:
        return {"ok": False, "error": "not a VRM file (no VRM / VRMC_vrm)", "src": src, "detect": detail}
    if direction == "auto":
        if ver == "0.x":
            direction = "0to1"
        elif ver == "1.0":
            direction = "1to0"
        else:
            return {
                "ok": False,
                "error": "file has both VRM and VRMC_vrm; pass direction=0to1 or 1to0",
                "src": src,
                "detect": detail,
            }

    if direction == "0to1" and ver == "1.0":
        return {"ok": False, "error": "already VRM 1.0", "src": src, "from": "1.0", "to": "1.0"}
    if direction == "1to0" and ver == "0.x":
        return {"ok": False, "error": "already VRM 0.x", "src": src, "from": "0.x", "to": "0.x"}

    work = copy.deepcopy(gltf)
    blob = bytearray(bin_chunk)
    rewrite_bin_vrm0_vrm1(work, blob)

    if direction == "0to1":
        notes = migrate_vrm0_to_vrm1(work)
        from_v, to_v = "0.x", "1.0"
    elif direction == "1to0":
        notes = migrate_vrm1_to_vrm0(work)
        from_v, to_v = "1.0", "0.x"
    else:
        return {"ok": False, "error": f"unknown direction {direction!r}"}

    counts = _counts(work, to_v)
    report: Dict[str, Any] = {
        "ok": True,
        "src": src,
        "from": from_v,
        "to": to_v,
        "direction": direction,
        "dry_run": dry_run,
        "dropped": notes.get("dropped") or [],
        "approximated": notes.get("approximated") or [],
        "extensionsUsed": list(work.get("extensionsUsed") or []),
        "counts": counts,
        "output_path": None,
    }

    if dry_run:
        return report

    if not dst:
        return {**report, "ok": False, "error": "dst required when dry_run=False"}
    dst = os.path.abspath(dst)
    asset = work.setdefault("asset", {})
    gen = asset.get("generator") or ""
    tag = "vrm0-vrm1-convert"
    if tag not in gen:
        asset["generator"] = (gen + " " if gen else "") + tag
    out = write_glb(work, bytes(blob))
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    with open(dst, "wb") as f:
        f.write(out)
    report["output_path"] = dst
    report["output_bytes"] = len(out)
    return report


def _counts(gltf: Dict[str, Any], version: str) -> Dict[str, Any]:
    ext = gltf.get("extensions") or {}
    if version == "1.0":
        vrm = ext.get("VRMC_vrm") or {}
        bones = ((vrm.get("humanoid") or {}).get("humanBones") or {})
        preset = ((vrm.get("expressions") or {}).get("preset") or {})
        custom = ((vrm.get("expressions") or {}).get("custom") or {})
        spring = ext.get("VRMC_springBone") or {}
        mtoon = 0
        for mat in gltf.get("materials") or []:
            if (mat.get("extensions") or {}).get("VRMC_materials_mtoon"):
                mtoon += 1
        return {
            "humanoid_bones": len(bones),
            "expression_presets": len(preset),
            "expression_custom": len(custom),
            "spring_colliders": len(spring.get("colliders") or []),
            "springs": len(spring.get("springs") or []),
            "mtoon_materials": mtoon,
        }
    vrm = ext.get("VRM") or {}
    return {
        "humanoid_bones": len((vrm.get("humanoid") or {}).get("humanBones") or []),
        "blendShapeGroups": len((vrm.get("blendShapeMaster") or {}).get("blendShapeGroups") or []),
        "colliderGroups": len((vrm.get("secondaryAnimation") or {}).get("colliderGroups") or []),
        "boneGroups": len((vrm.get("secondaryAnimation") or {}).get("boneGroups") or []),
        "materialProperties": len(vrm.get("materialProperties") or []),
    }


def main(argv: Optional[list] = None) -> int:
    p = argparse.ArgumentParser(description="Convert VRM 0.x <-> VRM 1.0 GLB (no Blender).")
    p.add_argument("--src", required=True)
    p.add_argument("--dst", default=None)
    p.add_argument("--direction", choices=("auto", "0to1", "1to0"), default="auto")
    p.add_argument("--dry-run", action="store_true", default=False)
    p.add_argument("--apply", action="store_true", help="write dst (overrides --dry-run)")
    args = p.parse_args(argv)
    dry = not args.apply
    if args.dry_run:
        dry = True
    if not dry and not args.dst:
        print(json.dumps({"ok": False, "error": "--dst required with --apply"}))
        return 1
    report = convert_vrm(args.src, args.dst, direction=args.direction, dry_run=dry)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
