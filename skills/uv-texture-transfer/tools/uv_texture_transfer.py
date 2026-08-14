"""Transfer a texture (including tangent normals) from one UV map to another.

Cycles bake on the same mesh: sample ``source_uv``, write into ``dest_uv``.
``kind="normal"`` re-encodes tangent space (island rotation-safe).
``kind="color"`` is an Emit copy (albedo / masks — do not use for normals).

MCP / Scripting:
  import uv_texture_transfer as uvt
  uvt.audit_uv_transfer("Hair")
  uvt.transfer_uv_texture("Hair", source_uv="UVMap", dest_uv="UVMap.Unwrapped",
                          kind="normal", size=4096, dry_run=True)
"""

from __future__ import annotations

import math
import os
import time
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence, Union

try:
    import bpy
except ImportError:  # pragma: no cover
    bpy = None  # type: ignore

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None  # type: ignore

SKILL_ROOT = Path(__file__).resolve().parents[1]
_SKILL_LOG_NAME = "uv-texture-transfer"
_SKILL_LOG_FN: Any = None
_PERF_ELAPSED_MS: Any = None
_SKILL_LOG_MISSING = object()

BAKE_MAT_NAME = "_UVTransferBake"
SizeArg = Union[int, Sequence[int], None]


def _load_skill_log_helpers() -> None:
    global _SKILL_LOG_FN, _PERF_ELAPSED_MS
    if _SKILL_LOG_FN is _SKILL_LOG_MISSING:
        return
    if _SKILL_LOG_FN is not None:
        return

    candidates = [
        SKILL_ROOT.parent / "blender-skill-log" / "tools" / "blender_skill_log.py",
        Path.home() / ".cursor" / "skills" / "blender-skill-log" / "tools" / "blender_skill_log.py",
    ]
    script = next((path for path in candidates if path.is_file()), None)
    if script is None:
        _SKILL_LOG_FN = _SKILL_LOG_MISSING
        return

    import importlib.util

    spec = importlib.util.spec_from_file_location("blender_skill_log", script)
    if spec is None or spec.loader is None:
        _SKILL_LOG_FN = _SKILL_LOG_MISSING
        return
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    fn = getattr(mod, "skill_log", None)
    if not callable(fn):
        _SKILL_LOG_FN = _SKILL_LOG_MISSING
        return
    _SKILL_LOG_FN = fn
    perf = getattr(mod, "perf_elapsed_ms", None)
    _PERF_ELAPSED_MS = perf if callable(perf) else None


def _elapsed_ms(start: float) -> float:
    _load_skill_log_helpers()
    if callable(_PERF_ELAPSED_MS):
        return _PERF_ELAPSED_MS(start)
    return round((time.perf_counter() - start) * 1000, 2)


def _maybe_skill_log(event: str, **data: Any) -> None:
    _load_skill_log_helpers()
    if not callable(_SKILL_LOG_FN):
        return
    try:
        _SKILL_LOG_FN(event, skill=_SKILL_LOG_NAME, **data)
    except Exception:
        pass


def _mesh_object(name: str) -> Any:
    obj = bpy.data.objects.get(name)
    if obj is None:
        raise ValueError(f"object not found: {name}")
    if obj.type != "MESH":
        raise ValueError(f"object '{name}' is {obj.type}, need MESH")
    return obj


def _uv_layer(mesh: Any, name: str) -> Any:
    layer = mesh.uv_layers.get(name)
    if layer is None:
        have = [uv.name for uv in mesh.uv_layers]
        raise ValueError(f"UV layer '{name}' missing on {mesh.name}; have {have}")
    return layer


def _uv_stats(mesh: Any, layer: Any) -> dict[str, Any]:
    data = layer.data
    n = len(data)
    if n == 0:
        return {
            "name": layer.name,
            "loop_count": 0,
            "unique_uv_4dp": 0,
            "u_min": None,
            "u_max": None,
            "v_min": None,
            "v_max": None,
            "active": layer.active,
            "active_render": layer.active_render,
        }
    keys: set[tuple[float, float]] = set()
    umin = vmin = 1e9
    umax = vmax = -1e9
    for i in range(n):
        u, v = data[i].uv
        umin = min(umin, u)
        umax = max(umax, u)
        vmin = min(vmin, v)
        vmax = max(vmax, v)
        keys.add((round(u, 4), round(v, 4)))
    return {
        "name": layer.name,
        "loop_count": n,
        "unique_uv_4dp": len(keys),
        "u_min": umin,
        "u_max": umax,
        "v_min": vmin,
        "v_max": vmax,
        "active": layer.active,
        "active_render": layer.active_render,
    }


def _island_rotation_hint(mesh: Any, src_name: str, dst_name: str, max_faces: int = 4000) -> dict[str, Any]:
    src = mesh.uv_layers[src_name].data
    dst = mesh.uv_layers[dst_name].data
    n_rot_gt15 = 0
    n_flip = 0
    n = 0
    for p in mesh.polygons:
        if p.loop_total < 3:
            continue
        if n >= max_faces:
            break
        lis = p.loop_indices
        s0 = src[lis[0]].uv
        s1 = src[lis[1]].uv
        s2 = src[lis[2]].uv
        d0 = dst[lis[0]].uv
        d1 = dst[lis[1]].uv
        d2 = dst[lis[2]].uv
        sex, sey = s1.x - s0.x, s1.y - s0.y
        dex, dey = d1.x - d0.x, d1.y - d0.y
        sl = math.hypot(sex, sey)
        dl = math.hypot(dex, dey)
        if sl < 1e-8 or dl < 1e-8:
            continue
        ang = abs(math.degrees(math.atan2(sex * dey - sey * dex, sex * dex + sey * dey)))
        sc = sex * (s2.y - s0.y) - sey * (s2.x - s0.x)
        dc = dex * (d2.y - d0.y) - dey * (d2.x - d0.x)
        if sc * dc < 0:
            n_flip += 1
        if ang > 15:
            n_rot_gt15 += 1
        n += 1
    return {
        "faces_sampled": n,
        "rot_gt15_deg": n_rot_gt15,
        "flipped": n_flip,
        "needs_tangent_reencode": n > 0 and (n_rot_gt15 / n) > 0.05,
    }


def _image_by_name(name: str) -> Any:
    img = bpy.data.images.get(name)
    if img is None:
        raise ValueError(f"image not found: {name}")
    return img


def _vrm_textures(mat: Any) -> list[Any]:
    try:
        return list(mat.vrm_addon_extension.mtoon1.all_textures(downgrade_to_mtoon0=False))
    except Exception:
        return []


def _vrm_normal_image(mat: Any) -> Any:
    try:
        return mat.vrm_addon_extension.mtoon1.normal_texture.index.source
    except Exception:
        return None


def _iter_tex_nodes(mat: Any) -> Iterable[Any]:
    if not mat or not mat.use_nodes or not mat.node_tree:
        return
    for node in mat.node_tree.nodes:
        if node.type == "TEX_IMAGE":
            yield node


def _materials_on_object(obj: Any) -> list[Any]:
    out: list[Any] = []
    seen: set[str] = set()
    for slot in obj.material_slots:
        mat = slot.material
        if mat is None or mat.name in seen:
            continue
        seen.add(mat.name)
        out.append(mat)
    return out


def _materials_using_image(mats: Sequence[Any], img: Any) -> list[str]:
    names: list[str] = []
    for mat in mats:
        hit = False
        for node in _iter_tex_nodes(mat):
            if node.image == img:
                hit = True
                break
        if not hit:
            for tex in _vrm_textures(mat):
                if getattr(tex, "source", None) == img:
                    hit = True
                    break
        if hit:
            names.append(mat.name)
    return names


def _guess_kind(img: Any, mats: Sequence[Any]) -> str:
    name = (img.name if img else "").lower()
    if "normal" in name or name.endswith("_nrm") or name.endswith("_n"):
        return "normal"
    for mat in mats:
        if _vrm_normal_image(mat) == img:
            return "normal"
        for node in _iter_tex_nodes(mat):
            if node.image == img and "normal" in (node.name + node.label).lower():
                return "normal"
    return "color"


def _dest_slug(dest_uv: str) -> str:
    slug = dest_uv.strip().replace(" ", "_")
    lower = slug.lower()
    if lower.startswith("uvmap."):
        slug = slug.split(".", 1)[1]
    elif lower == "uvmap":
        slug = "uv"
    return slug.replace(".", "_").lower()


def _resolve_size(size: SizeArg, src: Any) -> tuple[int, int]:
    if size is None:
        w, h = int(src.size[0]), int(src.size[1])
        if w < 1 or h < 1:
            raise ValueError(f"source image '{src.name}' has invalid size {list(src.size)}")
        return w, h
    if isinstance(size, int):
        if size < 1:
            raise ValueError(f"size must be >= 1, got {size}")
        return size, size
    if len(size) != 2:
        raise ValueError(f"size must be int or (w, h), got {size!r}")
    w, h = int(size[0]), int(size[1])
    if w < 1 or h < 1:
        raise ValueError(f"size must be >= 1, got {(w, h)}")
    return w, h


def _fill_image(img: Any, rgba: tuple[float, float, float, float]) -> None:
    w, h = img.size
    n = int(w) * int(h)
    if np is not None:
        px = np.empty(n * 4, dtype=np.float32)
        px[0::4] = rgba[0]
        px[1::4] = rgba[1]
        px[2::4] = rgba[2]
        px[3::4] = rgba[3]
        img.pixels.foreach_set(px)
    else:
        img.pixels.foreach_set([rgba[0], rgba[1], rgba[2], rgba[3]] * n)
    img.update()


def _nonflat_count(img: Any, flat: tuple[float, float, float], step: int = 16, eps: float = 0.02) -> dict[str, Any]:
    w, h = img.size
    n = int(w) * int(h)
    if np is not None:
        buf = np.empty(n * 4, dtype=np.float32)
        img.pixels.foreach_get(buf)
        sample = buf.reshape(n, 4)[::step, :3]
        dist = np.abs(sample - np.array(flat, dtype=np.float32))
        changed = int(np.any(dist > eps, axis=1).sum())
        return {
            "nonflat": changed,
            "sampled": int(sample.shape[0]),
            "r": [float(sample[:, 0].min()), float(sample[:, 0].max())],
            "g": [float(sample[:, 1].min()), float(sample[:, 1].max())],
            "b": [float(sample[:, 2].min()), float(sample[:, 2].max())],
        }
    import array

    buf = array.array("f", [0.0]) * (n * 4)
    img.pixels.foreach_get(buf)
    changed = 0
    sampled = 0
    rmin = gmin = bmin = 1e9
    rmax = gmax = bmax = -1e9
    for i in range(0, n, step):
        r, g, b = buf[i * 4], buf[i * 4 + 1], buf[i * 4 + 2]
        rmin = min(rmin, r)
        rmax = max(rmax, r)
        gmin = min(gmin, g)
        gmax = max(gmax, g)
        bmin = min(bmin, b)
        bmax = max(bmax, b)
        sampled += 1
        if abs(r - flat[0]) > eps or abs(g - flat[1]) > eps or abs(b - flat[2]) > eps:
            changed += 1
    return {
        "nonflat": changed,
        "sampled": sampled,
        "r": [rmin, rmax],
        "g": [gmin, gmax],
        "b": [bmin, bmax],
    }


def _default_save_path(src: Any, dest_name: str) -> Optional[str]:
    fp = src.filepath or ""
    abs_fp = bpy.path.abspath(fp) if fp else ""
    parent = os.path.dirname(abs_fp) if abs_fp else ""
    if parent and os.path.isdir(parent):
        return os.path.join(parent, f"{dest_name}.png")
    blend = bpy.data.filepath
    if blend:
        tex_dir = os.path.join(os.path.dirname(blend), "textures")
        return os.path.join(tex_dir, f"{dest_name}.png")
    return None


def _setup_cycles(samples: int) -> dict[str, Any]:
    scene = bpy.context.scene
    orig = {
        "engine": scene.render.engine,
        "samples": scene.cycles.samples,
        "device": scene.cycles.device,
        "denoise": getattr(scene.cycles, "use_denoising", None),
        "adaptive": getattr(scene.cycles, "use_adaptive_sampling", None),
    }
    scene.render.engine = "CYCLES"
    gpu_type = None
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.get_devices()
        present = {d.type for d in prefs.devices}
        for cand in ("OPTIX", "CUDA", "HIP", "ONEAPI", "METAL"):
            if cand in present:
                gpu_type = cand
                break
        if gpu_type:
            prefs.compute_device_type = gpu_type
            prefs.get_devices()
            for d in prefs.devices:
                d.use = d.type == gpu_type
            scene.cycles.device = "GPU"
        else:
            scene.cycles.device = "CPU"
    except Exception:
        scene.cycles.device = "CPU"
        gpu_type = None
    scene.cycles.samples = samples
    if hasattr(scene.cycles, "use_denoising"):
        scene.cycles.use_denoising = False
    if hasattr(scene.cycles, "use_adaptive_sampling"):
        scene.cycles.use_adaptive_sampling = False
    orig["gpu_type"] = gpu_type
    return orig


def _restore_cycles(orig: dict[str, Any]) -> None:
    scene = bpy.context.scene
    scene.render.engine = orig["engine"]
    scene.cycles.samples = orig["samples"]
    scene.cycles.device = orig["device"]
    if orig.get("denoise") is not None and hasattr(scene.cycles, "use_denoising"):
        scene.cycles.use_denoising = orig["denoise"]
    if orig.get("adaptive") is not None and hasattr(scene.cycles, "use_adaptive_sampling"):
        scene.cycles.use_adaptive_sampling = orig["adaptive"]


def _ensure_object_mode() -> str:
    prev = bpy.context.mode
    if prev != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    return prev


def _build_bake_material(
    *,
    kind: str,
    source_img: Any,
    target_img: Any,
    source_uv: str,
) -> Any:
    old = bpy.data.materials.get(BAKE_MAT_NAME)
    if old:
        bpy.data.materials.remove(old)
    mat = bpy.data.materials.new(BAKE_MAT_NAME)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()

    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (600, 0)
    uv = nt.nodes.new("ShaderNodeUVMap")
    uv.location = (-440, -80)
    uv.uv_map = source_uv
    tex_src = nt.nodes.new("ShaderNodeTexImage")
    tex_src.name = "SourceTex"
    tex_src.location = (-220, -80)
    tex_src.image = source_img
    tex_src.interpolation = "Linear"
    tex_src.extension = "REPEAT"
    tex_tgt = nt.nodes.new("ShaderNodeTexImage")
    tex_tgt.name = "BakeTarget"
    tex_tgt.location = (-220, 180)
    tex_tgt.image = target_img
    tex_tgt.interpolation = "Linear"

    if kind == "normal":
        nrm = nt.nodes.new("ShaderNodeNormalMap")
        nrm.location = (80, -80)
        nrm.uv_map = source_uv
        nrm.space = "TANGENT"
        bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
        bsdf.location = (300, 0)
        nt.links.new(uv.outputs["UV"], tex_src.inputs["Vector"])
        nt.links.new(tex_src.outputs["Color"], nrm.inputs["Color"])
        nt.links.new(nrm.outputs["Normal"], bsdf.inputs["Normal"])
        nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    else:
        emit = nt.nodes.new("ShaderNodeEmission")
        emit.location = (300, 0)
        nt.links.new(uv.outputs["UV"], tex_src.inputs["Vector"])
        nt.links.new(tex_src.outputs["Color"], emit.inputs["Color"])
        nt.links.new(emit.outputs["Emission"], out.inputs["Surface"])

    for node in nt.nodes:
        node.select = False
    tex_tgt.select = True
    nt.nodes.active = tex_tgt
    return mat


def _replace_image_refs(mats: Sequence[Any], source_img: Any, dest_img: Any) -> list[dict[str, str]]:
    changed: list[dict[str, str]] = []
    for mat in mats:
        for tex in _vrm_textures(mat):
            if getattr(tex, "source", None) == source_img:
                tex.source = dest_img
                changed.append({"material": mat.name, "via": "vrm", "label": getattr(tex, "label", "") or tex.bl_rna.identifier})
        for node in _iter_tex_nodes(mat):
            if node.image == source_img:
                node.image = dest_img
                changed.append({"material": mat.name, "via": "node", "label": node.name})
    return changed


def _other_mapped_images(obj: Any, source_img: Any) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for mat in _materials_on_object(obj):
        for node in _iter_tex_nodes(mat):
            img = node.image
            if img is None or img == source_img:
                continue
            if img.name in seen:
                continue
            w, h = int(img.size[0]), int(img.size[1])
            if w <= 16 and h <= 16:
                continue
            seen.add(img.name)
            names.append(img.name)
    return names


def audit_uv_transfer(
    object_name: str,
    source_uv: Optional[str] = None,
    dest_uv: Optional[str] = None,
    image: Optional[str] = None,
) -> dict[str, Any]:
    """Inspect mesh UVs, candidate images, and whether dest islands are rotated."""
    obj = _mesh_object(object_name)
    mesh = obj.data
    uv_layers = [_uv_stats(mesh, uv) for uv in mesh.uv_layers]
    mats = _materials_on_object(obj)

    images: list[dict[str, Any]] = []
    seen_img: set[str] = set()
    for mat in mats:
        nrm = _vrm_normal_image(mat)
        for node in _iter_tex_nodes(mat):
            img = node.image
            if img is None or img.name in seen_img:
                continue
            seen_img.add(img.name)
            images.append(
                {
                    "name": img.name,
                    "size": list(img.size),
                    "colorspace": img.colorspace_settings.name,
                    "filepath": img.filepath,
                    "guess_kind": _guess_kind(img, mats),
                    "used_by": _materials_using_image(mats, img),
                    "is_vrm_normal": nrm == img,
                }
            )

    src_name = source_uv or (uv_layers[0]["name"] if uv_layers else None)
    dst_name = dest_uv
    if dst_name is None:
        for uv in uv_layers:
            if uv["name"] != src_name:
                dst_name = uv["name"]
                break

    rot = None
    if src_name and dst_name and mesh.uv_layers.get(src_name) and mesh.uv_layers.get(dst_name):
        rot = _island_rotation_hint(mesh, src_name, dst_name)

    src_img = bpy.data.images.get(image) if image else None
    if src_img is None:
        for row in images:
            if row.get("is_vrm_normal"):
                src_img = bpy.data.images.get(row["name"])
                break
        if src_img is None and images:
            src_img = bpy.data.images.get(images[0]["name"])

    kind = _guess_kind(src_img, mats) if src_img else None
    other = _other_mapped_images(obj, src_img) if src_img else []
    warn: list[str] = []
    if rot and rot.get("needs_tangent_reencode") and kind == "color":
        warn.append("dest islands rotated vs source — kind='color' will break tangent normals; use kind='normal'")
    if other:
        warn.append(
            "other non-tiny textures on this object: "
            + ", ".join(other)
            + " — switch_render_uv=True will sample them with dest UV"
        )

    return {
        "object": obj.name,
        "uv_layers": uv_layers,
        "source_uv": src_name,
        "dest_uv": dst_name,
        "images": images,
        "image": src_img.name if src_img else None,
        "kind": kind,
        "rotation": rot,
        "other_mapped_images": other,
        "warnings": warn,
        "materials": [m.name for m in mats],
    }


def transfer_uv_texture(
    object_name: str,
    source_uv: str,
    dest_uv: str,
    image: Optional[str] = None,
    kind: Optional[str] = None,
    size: SizeArg = None,
    margin: int = 16,
    samples: int = 16,
    save_path: Optional[str] = None,
    dest_image_name: Optional[str] = None,
    assign: bool = True,
    switch_render_uv: bool = False,
    materials: Optional[Sequence[str]] = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Bake ``image`` from ``source_uv`` onto ``dest_uv``.

    ``kind="normal"``: Cycles tangent NORMAL bake (reorients for packed/rotated islands).
    ``kind="color"``: Cycles EMIT bake (albedo, masks, packed color). Never for normals
    when dest islands are rotated.

    Dry-run first. Does not overwrite the source image file.
    """
    start = time.perf_counter()
    obj = _mesh_object(object_name)
    mesh = obj.data
    _uv_layer(mesh, source_uv)
    _uv_layer(mesh, dest_uv)
    if source_uv == dest_uv:
        raise ValueError("source_uv and dest_uv must differ")

    obj_mats = _materials_on_object(obj)
    if image:
        src_img = _image_by_name(image)
    else:
        src_img = None
        for mat in obj_mats:
            src_img = _vrm_normal_image(mat)
            if src_img:
                break
        if src_img is None:
            raise ValueError("image not given and no VRM normal texture on object materials")

    resolved_kind = kind or _guess_kind(src_img, obj_mats)
    if resolved_kind not in ("normal", "color"):
        raise ValueError(f"kind must be 'normal' or 'color', got {resolved_kind!r}")

    width, height = _resolve_size(size, src_img)
    slug = _dest_slug(dest_uv)
    out_name = dest_image_name or f"{src_img.name}_{slug}"
    out_path = save_path or _default_save_path(src_img, out_name)
    src_abs = bpy.path.abspath(src_img.filepath) if src_img.filepath else ""
    if out_path and src_abs and os.path.normcase(os.path.normpath(out_path)) == os.path.normcase(os.path.normpath(src_abs)):
        stem, ext = os.path.splitext(out_path)
        out_path = f"{stem}_{slug}{ext or '.png'}"

    target_mats = obj_mats
    if materials:
        target_mats = []
        for name in materials:
            mat = bpy.data.materials.get(name)
            if mat is None:
                raise ValueError(f"material not found: {name}")
            target_mats.append(mat)
    assign_mats = [m for m in target_mats if m.name in _materials_using_image(target_mats, src_img)]
    if assign and not assign_mats:
        assign_mats = list(target_mats)

    other = _other_mapped_images(obj, src_img)
    rot = _island_rotation_hint(mesh, source_uv, dest_uv)
    warnings: list[str] = []
    if resolved_kind == "color" and rot.get("needs_tangent_reencode"):
        warnings.append("dest islands rotated — color/emit bake will not reorient tangent normals")
    if switch_render_uv and other:
        warnings.append("switch_render_uv will make other textures sample dest UV: " + ", ".join(other))

    plan = {
        "object": obj.name,
        "source_uv": source_uv,
        "dest_uv": dest_uv,
        "source_image": src_img.name,
        "source_size": list(src_img.size),
        "kind": resolved_kind,
        "dest_image": out_name,
        "dest_size": [width, height],
        "save_path": out_path,
        "margin": margin,
        "samples": samples,
        "assign": assign,
        "assign_materials": [m.name for m in assign_mats],
        "switch_render_uv": switch_render_uv,
        "rotation": rot,
        "other_mapped_images": other,
        "warnings": warnings,
        "dry_run": dry_run,
    }

    if dry_run:
        _maybe_skill_log(
            "phase_done",
            phase="audit",
            dry_run=True,
            status="ok",
            elapsed_ms=_elapsed_ms(start),
            object=obj.name,
            kind=resolved_kind,
        )
        plan["status"] = "dry_run"
        return plan

    _maybe_skill_log(
        "phase_start",
        phase="bake",
        dry_run=False,
        object=obj.name,
        kind=resolved_kind,
    )

    orig_slots = [s.material.name if s.material else None for s in obj.material_slots]
    orig_active_uv = mesh.uv_layers.active.name if mesh.uv_layers.active else None
    orig_render_uv = next((uv.name for uv in mesh.uv_layers if uv.active_render), None)
    orig_cycles: Optional[dict[str, Any]] = None
    bake_mat = None
    prev_mode = "OBJECT"
    uv_committed = False

    try:
        prev_mode = _ensure_object_mode()
        orig_cycles = _setup_cycles(samples)
        scene = bpy.context.scene
        scene.cycles.bake_type = "NORMAL" if resolved_kind == "normal" else "EMIT"

        old_img = bpy.data.images.get(out_name)
        if old_img:
            bpy.data.images.remove(old_img)
        tgt = bpy.data.images.new(
            name=out_name,
            width=width,
            height=height,
            alpha=True,
            float_buffer=False,
        )
        if resolved_kind == "normal":
            fill = (0.5, 0.5, 1.0, 1.0)
            tgt.colorspace_settings.name = "Non-Color"
            tgt.alpha_mode = "CHANNEL_PACKED"
        else:
            fill = (0.0, 0.0, 0.0, 1.0)
            tgt.colorspace_settings.name = src_img.colorspace_settings.name
        tgt.generated_color = fill
        tgt.generated_type = "BLANK"
        _fill_image(tgt, fill)

        bake_mat = _build_bake_material(
            kind=resolved_kind,
            source_img=src_img,
            target_img=tgt,
            source_uv=source_uv,
        )

        mesh.uv_layers[dest_uv].active = True
        mesh.uv_layers[source_uv].active_render = True

        bpy.ops.object.select_all(action="DESELECT")
        obj.hide_set(False)
        obj.hide_viewport = False
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        for i in range(len(obj.material_slots)):
            obj.material_slots[i].material = bake_mat
        if not obj.material_slots:
            obj.data.materials.append(bake_mat)

        bake = scene.render.bake
        bake.margin = margin
        bake.margin_type = "ADJACENT_FACES"
        bake.use_clear = True
        bake.use_selected_to_active = False
        bake.normal_space = "TANGENT"
        bake.target = "IMAGE_TEXTURES"

        bake_type = "NORMAL" if resolved_kind == "normal" else "EMIT"
        override = {
            "active_object": obj,
            "selected_objects": [obj],
            "object": obj,
            "scene": scene,
            "view_layer": bpy.context.view_layer,
        }
        with bpy.context.temp_override(**override):
            bake_op = bpy.ops.object.bake(
                type=bake_type,
                normal_space="TANGENT",
                margin=margin,
                margin_type="ADJACENT_FACES",
                use_clear=True,
                use_selected_to_active=False,
                target="IMAGE_TEXTURES",
                save_mode="INTERNAL",
                uv_layer=dest_uv,
            )
        tgt.update()

        flat = (0.5, 0.5, 1.0) if resolved_kind == "normal" else (0.0, 0.0, 0.0)
        stats = _nonflat_count(tgt, flat)
        if stats["nonflat"] == 0:
            raise RuntimeError("bake produced a flat image — check UVs, source image, and Cycles")

        tgt.pack()
        saved_how = None
        file_bytes = None
        if out_path:
            os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
            try:
                tgt.save(filepath=out_path)
                saved_how = "save(filepath=)"
            except TypeError:
                tgt.file_format = "PNG"
                tgt.filepath_raw = out_path
                tgt.save()
                saved_how = "filepath_raw+save"
            tgt.filepath = out_path
            if os.path.isfile(out_path):
                file_bytes = os.path.getsize(out_path)

        assigned: list[dict[str, str]] = []
        if assign:
            assigned = _replace_image_refs(assign_mats, src_img, tgt)

        if switch_render_uv:
            mesh.uv_layers[dest_uv].active_render = True
            mesh.uv_layers[dest_uv].active = True
        else:
            if orig_render_uv:
                mesh.uv_layers[orig_render_uv].active_render = True
            if orig_active_uv:
                mesh.uv_layers[orig_active_uv].active = True
        uv_committed = True

        plan.update(
            {
                "status": "ok",
                "bake_op": str(bake_op),
                "pixel_stats": stats,
                "saved_how": saved_how,
                "file_bytes": file_bytes,
                "packed": bool(tgt.packed_file),
                "assigned": assigned,
                "active_uv": mesh.uv_layers.active.name if mesh.uv_layers.active else None,
                "active_render_uv": next((uv.name for uv in mesh.uv_layers if uv.active_render), None),
                "gpu_type": orig_cycles.get("gpu_type") if orig_cycles else None,
                "elapsed_ms": _elapsed_ms(start),
            }
        )
        _maybe_skill_log(
            "phase_done",
            phase="bake",
            dry_run=False,
            status="ok",
            elapsed_ms=plan["elapsed_ms"],
            object=obj.name,
            kind=resolved_kind,
        )
        return plan
    except Exception as exc:
        _maybe_skill_log(
            "phase_error",
            phase="bake",
            dry_run=False,
            error=str(exc),
            elapsed_ms=_elapsed_ms(start),
        )
        raise
    finally:
        for i, name in enumerate(orig_slots):
            if i < len(obj.material_slots):
                obj.material_slots[i].material = bpy.data.materials.get(name) if name else None
        bake_left = bpy.data.materials.get(BAKE_MAT_NAME)
        if bake_left:
            bpy.data.materials.remove(bake_left)
        if orig_cycles is not None:
            _restore_cycles(orig_cycles)
        if not uv_committed:
            if orig_render_uv and mesh.uv_layers.get(orig_render_uv):
                mesh.uv_layers[orig_render_uv].active_render = True
            if orig_active_uv and mesh.uv_layers.get(orig_active_uv):
                mesh.uv_layers[orig_active_uv].active = True
        if prev_mode != "OBJECT":
            try:
                bpy.ops.object.mode_set(mode="EDIT" if "EDIT" in prev_mode else prev_mode)
            except TypeError:
                pass
