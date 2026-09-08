"""Export skinned prop GLB (no VRM humanoid). MToon does not survive; pair with sidecar dump."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from dump_mtoon_sidecar import IMAGE_NODES, MTOON_OUTPUT

try:
    import bpy
except ImportError:  # pragma: no cover
    bpy = None  # type: ignore

PACK_PREFIX = "MToonSidecarPack"


def collect_mtoon_images() -> List[Any]:
    if bpy is None:
        raise RuntimeError("bpy required")
    found: Dict[str, Any] = {}
    for mat in bpy.data.materials:
        if not mat.use_nodes or mat.node_tree is None:
            continue
        tree = mat.node_tree
        if tree.nodes.get(MTOON_OUTPUT) is None:
            continue
        for node_name in IMAGE_NODES.values():
            node = tree.nodes.get(node_name)
            if node is None or node.type != "TEX_IMAGE" or node.image is None:
                continue
            found[node.image.name] = node.image
    return list(found.values())


def _safe_id(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in name)
    return (cleaned or "img")[:40]


def install_mtoon_pack_dummies(images: List[Any]) -> List[str]:
    """Temp planes with Principled baseColor = each MToon image so glTF packs unused maps."""
    if bpy is None:
        raise RuntimeError("bpy required")
    remove_mtoon_pack_dummies()
    scene = bpy.context.scene
    coll = bpy.data.collections.get(PACK_PREFIX)
    if coll is None:
        coll = bpy.data.collections.new(PACK_PREFIX)
        scene.collection.children.link(coll)
    created: List[str] = []
    for image in images:
        tag = _safe_id(image.name)
        obj_name = f"{PACK_PREFIX}.{tag}"
        mat_name = f"{PACK_PREFIX}.{tag}"
        mesh = bpy.data.meshes.new(obj_name)
        mesh.from_pydata([(0.0, 0.0, 0.0), (0.001, 0.0, 0.0), (0.0, 0.001, 0.0)], [], [(0, 1, 2)])
        obj = bpy.data.objects.new(obj_name, mesh)
        obj.scale = (0.0001, 0.0001, 0.0001)
        obj.location = (0.0, 0.0, -50.0)
        coll.objects.link(obj)
        mat = bpy.data.materials.new(mat_name)
        mat.use_nodes = True
        tree = mat.node_tree
        assert tree is not None
        tree.nodes.clear()
        bsdf = tree.nodes.new("ShaderNodeBsdfPrincipled")
        out = tree.nodes.new("ShaderNodeOutputMaterial")
        tex = tree.nodes.new("ShaderNodeTexImage")
        tex.image = image
        tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        tree.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
        mesh.materials.append(mat)
        created.append(obj_name)
    return created


def remove_mtoon_pack_dummies() -> None:
    if bpy is None:
        return
    names = [obj.name for obj in list(bpy.data.objects) if obj.name.startswith(PACK_PREFIX)]
    for name in names:
        obj = bpy.data.objects.get(name)
        if obj is None:
            continue
        mesh = obj.data
        mats = list(getattr(obj.data, "materials", []) or [])
        bpy.data.objects.remove(obj, do_unlink=True)
        if mesh is not None and mesh.users == 0:
            bpy.data.meshes.remove(mesh)
        for mat in mats:
            if mat is not None and mat.users == 0:
                bpy.data.materials.remove(mat)
    coll = bpy.data.collections.get(PACK_PREFIX)
    if coll is not None:
        bpy.data.collections.remove(coll)


def _rename_nla_tracks_from_strips() -> List[tuple]:
    """glTF NLA mode uses track names. Stash tracks become Activate* if we copy strip names."""
    restored: List[tuple] = []
    if bpy is None:
        return restored
    for obj in bpy.data.objects:
        ad = obj.animation_data
        if ad is None:
            continue
        for track in ad.nla_tracks:
            if not track.strips:
                continue
            strip_name = track.strips[0].name
            if track.name == strip_name:
                continue
            restored.append((obj, track, track.name))
            track.name = strip_name
    return restored


def _restore_nla_track_names(restored: List[tuple]) -> None:
    for _obj, track, name in restored:
        try:
            track.name = name
        except Exception:
            continue


def export_prop_gltf(
    filepath: str,
    *,
    dry_run: bool = True,
    animation_mode: str = "NLA_TRACKS",
    use_selection: bool = False,
    pack_mtoon_images: bool = True,
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
        "export_apply": True,
        "export_extras": False,
        "use_selection": use_selection,
        "use_visible": True,
        "export_animations": True,
        "export_nla_strips": True,
        "export_anim_single_armature": True,
        # True bakes every bone into every NLA clip. Strip unused channels after write
        # or layered mixer actions freeze each other with sampled rest.
        "export_force_sampling": True,
        "export_reset_pose_bones": True,
    }
    images = collect_mtoon_images() if pack_mtoon_images else []
    report: Dict[str, Any] = {
        "phase": "export-prop-gltf",
        "dry_run": dry_run,
        "out_path": path,
        "animation_mode": animation_mode,
        "use_selection": use_selection,
        "use_visible": True,
        "pack_mtoon_images": pack_mtoon_images,
        "pack_image_names": [img.name for img in images],
        "note": "glTF bakes PBR. Load MToon from sidecar via applyMtoonSidecar.",
    }
    if dry_run:
        return report
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    last_err: Optional[str] = None
    packed: List[str] = []
    nla_restore: List[tuple] = []
    try:
        if pack_mtoon_images and images:
            packed = install_mtoon_pack_dummies(images)
            report["pack_objects"] = packed
        nla_restore = _rename_nla_tracks_from_strips()
        if nla_restore:
            report["nla_track_names"] = [track.strips[0].name for _o, track, _n in nla_restore]
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
    finally:
        _restore_nla_track_names(nla_restore)
        if packed:
            remove_mtoon_pack_dummies()
