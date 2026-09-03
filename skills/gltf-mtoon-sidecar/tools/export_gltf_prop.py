"""Export skinned prop GLB (no VRM humanoid). MToon does not survive; pair with sidecar dump."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

try:
    import bpy
except ImportError:  # pragma: no cover
    bpy = None  # type: ignore


def export_prop_gltf(
    filepath: str,
    *,
    dry_run: bool = True,
    animation_mode: str = "NLA_TRACKS",
    use_selection: bool = False,
) -> Dict[str, Any]:
    if bpy is None:
        raise RuntimeError("bpy required")
    path = os.path.abspath(filepath)
    kwargs: Dict[str, Any] = {
        "filepath": path,
        "export_format": "GLB",
        "export_yup": True,
        "export_texcoords": True,
        "export_normals": True,
        "export_materials": "EXPORT",
        "export_image_format": "AUTO",
        "export_skins": True,
        "export_morph": True,
        "export_lights": False,
        "export_apply": False,
        "export_extras": False,
        "use_selection": use_selection,
        "export_animations": True,
        "export_nla_strips": True,
        "export_anim_single_armature": True,
        "export_force_sampling": True,
        "export_reset_pose_bones": True,
    }
    report: Dict[str, Any] = {
        "phase": "export-prop-gltf",
        "dry_run": dry_run,
        "out_path": path,
        "animation_mode": animation_mode,
        "use_selection": use_selection,
        "note": "glTF bakes PBR. Load MToon from sidecar via applyMtoonSidecar.",
    }
    if dry_run:
        return report
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    last_err: Optional[str] = None
    for mode in (animation_mode, "ACTIONS"):
        try:
            kwargs["export_animation_mode"] = mode
            bpy.ops.export_scene.gltf(**kwargs)
            report["wrote"] = True
            report["animation_mode_used"] = mode
            return report
        except TypeError as exc:
            last_err = str(exc)
            kwargs.pop("export_animation_mode", None)
            continue
        except Exception as exc:
            last_err = str(exc)
            break
    report["error"] = last_err or "gltf export failed"
    return report
