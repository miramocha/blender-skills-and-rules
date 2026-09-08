"""Overlay or concat multiple VMD motions (dance + facial). Stdlib only. No Blender."""

from __future__ import annotations

import argparse
import json
import os
import sys
from copy import deepcopy
from typing import Any, Dict, Iterable, List, Optional, Sequence, Union

try:
    from .pmx_io import (
        PmxError,
        inspect_pmx,
        load_model,
        write_rig,
        bone_allowlist,
        bone_index_map,
        ik_slot_names,
        morph_allowlist,
        morph_index_map,
        rest_bone_slots,
        rest_morph_slots,
    )
    from .vmd_io import (
        ALL_CHANNELS,
        FACE_BONE_NAMES,
        BoneKey,
        IkEnable,
        IkKey,
        MorphKey,
        VmdError,
        VmdMotion,
        identity_interpolation,
        inspect_vmd,
        max_frame,
        read_vmd,
        sjis_slot,
        write_vmd,
        MODEL_NAME_LEN_0002,
    )
except ImportError:
    from pmx_io import (
        PmxError,
        inspect_pmx,
        load_model,
        write_rig,
        bone_allowlist,
        bone_index_map,
        ik_slot_names,
        morph_allowlist,
        morph_index_map,
        rest_bone_slots,
        rest_morph_slots,
    )
    from vmd_io import (
        ALL_CHANNELS,
        FACE_BONE_NAMES,
        BoneKey,
        IkEnable,
        IkKey,
        MorphKey,
        VmdError,
        VmdMotion,
        identity_interpolation,
        inspect_vmd,
        max_frame,
        read_vmd,
        sjis_slot,
        write_vmd,
        MODEL_NAME_LEN_0002,
    )

DANCE_TAKE = ("bones", "morphs", "camera", "light", "shadow", "ik")
FACE_TAKE = ("morphs", "face_bones")
TAKE_ALIASES = {
    "all": ALL_CHANNELS,
    "bone": ("bones",),
    "bones": ("bones",),
    "morph": ("morphs",),
    "morphs": ("morphs",),
    "face": FACE_TAKE,
    "facial": FACE_TAKE,
    "face_bones": ("face_bones",),
    "face-bones": ("face_bones",),
    "camera": ("camera",),
    "cam": ("camera",),
    "light": ("light",),
    "shadow": ("shadow",),
    "ik": ("ik",),
}

SourceSpec = Union[str, Dict[str, Any]]


def _parse_take(take: Optional[Union[str, Sequence[str]]]) -> List[str]:
    if take is None:
        return list(ALL_CHANNELS)
    if isinstance(take, str):
        parts = [p.strip() for p in take.replace(";", ",").split(",") if p.strip()]
    else:
        parts = [str(p).strip() for p in take if str(p).strip()]
    out: List[str] = []
    for p in parts:
        key = p.lower().replace(" ", "_")
        if key not in TAKE_ALIASES:
            raise VmdError(
                f"unknown take {p!r}; expected one of {sorted(TAKE_ALIASES)}"
            )
        for ch in TAKE_ALIASES[key]:
            if ch not in out:
                out.append(ch)
    if not out:
        raise VmdError("empty take list")
    return out


def _norm_sources(sources: Sequence[SourceSpec]) -> List[Dict[str, Any]]:
    if not sources:
        raise VmdError("at least one source VMD required")
    out = []
    for i, spec in enumerate(sources):
        if isinstance(spec, str):
            out.append({"path": spec, "take": list(ALL_CHANNELS), "offset": 0, "index": i})
            continue
        path = spec.get("path") or spec.get("src")
        if not path:
            raise VmdError(f"source[{i}] missing path")
        out.append(
            {
                "path": path,
                "take": _parse_take(spec.get("take")),
                "offset": int(spec.get("offset") or 0),
                "index": i,
            }
        )
    return out


def _shift(keys: Iterable[Any], offset: int) -> List[Any]:
    if not offset:
        return [deepcopy(k) for k in keys]
    out = []
    for k in keys:
        nk = deepcopy(k)
        nk.frame = int(nk.frame) + offset
        out.append(nk)
    return out


def _filter_bones(keys: List[BoneKey], take: Sequence[str]) -> List[BoneKey]:
    want_all = "bones" in take
    want_face = "face_bones" in take
    if want_all:
        return keys
    if want_face:
        return [k for k in keys if k.name in FACE_BONE_NAMES]
    return []


def _merge_named(dst: list, incoming: list, on_conflict: str) -> int:
    """Merge by (name, frame). Return overwrite count."""
    index = {k.key(): i for i, k in enumerate(dst)}
    overwrites = 0
    for k in incoming:
        prev = index.get(k.key())
        if prev is None:
            index[k.key()] = len(dst)
            dst.append(k)
            continue
        overwrites += 1
        if on_conflict == "first":
            continue
        dst[prev] = k
    return overwrites


def _merge_frame(dst: list, incoming: list, on_conflict: str) -> int:
    index = {k.key(): i for i, k in enumerate(dst)}
    overwrites = 0
    for k in incoming:
        prev = index.get(k.key())
        if prev is None:
            index[k.key()] = len(dst)
            dst.append(k)
            continue
        overwrites += 1
        if on_conflict == "first":
            continue
        dst[prev] = k
    return overwrites


def _ik_enable_default(name: str) -> int:
    return 0 if "つま先" in name else 1


def apply_pmx_filter(motion: VmdMotion, pmx_path: str, *, pad_rest: bool = True) -> Dict[str, Any]:
    """Keep keys whose names exist on the PMX. Optional MMD-style frame-0 rest pad."""
    model = load_model(pmx_path)
    allow_b = bone_allowlist(model)
    allow_m = morph_allowlist(model)
    dropped_b = sum(1 for k in motion.bones if k.name not in allow_b)
    dropped_m = sum(1 for k in motion.morphs if k.name not in allow_m)
    motion.bones = [k for k in motion.bones if k.name in allow_b]
    motion.morphs = [k for k in motion.morphs if k.name in allow_m]

    padded_b = padded_m = 0
    if pad_rest:
        have_b = {k.name for k in motion.bones}
        have_m = {k.name for k in motion.morphs}
        interp = identity_interpolation()
        for slot in rest_bone_slots(model):
            if slot not in have_b:
                motion.bones.append(
                    BoneKey(
                        name=slot,
                        frame=0,
                        pos=(0.0, 0.0, 0.0),
                        rot=(0.0, 0.0, 0.0, 1.0),
                        interpolation=interp,
                    )
                )
                padded_b += 1
                have_b.add(slot)
        for slot in rest_morph_slots(model):
            if slot not in have_m:
                motion.morphs.append(MorphKey(name=slot, frame=0, weight=0.0))
                padded_m += 1
                have_m.add(slot)

    ik_order = ik_slot_names(model)
    ik_allow = set(ik_order)
    for ik in motion.ik:
        kept = [e for e in ik.iks if e.name in ik_allow]
        have = {e.name for e in kept}
        if pad_rest:
            for n in ik_order:
                if n not in have:
                    kept.append(IkEnable(name=n, enable=_ik_enable_default(n)))
                    have.add(n)
        rank = {n: i for i, n in enumerate(ik_order)}
        kept.sort(key=lambda e: rank.get(e.name, 10**9))
        ik.iks = kept
    if pad_rest and ik_order and not motion.ik:
        motion.ik.append(
            IkKey(
                frame=0,
                show=1,
                iks=[IkEnable(name=n, enable=_ik_enable_default(n)) for n in ik_order],
            )
        )

    motion.model_name = sjis_slot(model.name_jp, MODEL_NAME_LEN_0002)

    bmap = bone_index_map(model)
    mmap = morph_index_map(model)
    motion.bones.sort(key=lambda k: (k.frame, bmap.get(k.name, 10**9), k.name))
    motion.morphs.sort(key=lambda k: (k.frame, mmap.get(k.name, 10**9), k.name))
    motion.ik.sort(key=lambda k: k.frame)

    return {
        "pmx": model.path,
        "pmx_name_jp": model.name_jp,
        "dropped_bone_keys": dropped_b,
        "dropped_morph_keys": dropped_m,
        "padded_bone_keys": padded_b,
        "padded_morph_keys": padded_m,
        "ik_bones": ik_order,
        "pad_rest": pad_rest,
    }


def combine_vmd(
    sources: Sequence[SourceSpec],
    dst: Optional[str] = None,
    *,
    dry_run: bool = True,
    on_conflict: str = "last",
    concat: bool = False,
    gap: int = 0,
    model_name: Optional[str] = None,
    pmx: Optional[str] = None,
    pad_rest: bool = True,
) -> Dict[str, Any]:
    """Merge VMDs. Default overlay (same timeline). concat places each file after previous."""
    if on_conflict not in ("last", "first"):
        raise VmdError("on_conflict must be 'last' or 'first'")
    specs = _norm_sources(sources)
    out = VmdMotion(signature="Vocaloid Motion Data 0002", model_name="")
    collisions = {
        "bones": 0,
        "morphs": 0,
        "camera": 0,
        "light": 0,
        "shadow": 0,
        "ik": 0,
    }
    inputs: List[Dict[str, Any]] = []
    cursor = 0

    for spec in specs:
        path = os.path.abspath(spec["path"])
        motion = read_vmd(path)
        take = spec["take"]
        offset = spec["offset"]
        if concat:
            offset += cursor
        if not out.model_name:
            out.model_name = motion.model_name

        bones = _filter_bones(_shift(motion.bones, offset), take)
        morphs = _shift(motion.morphs, offset) if "morphs" in take else []
        camera = _shift(motion.camera, offset) if "camera" in take else []
        light = _shift(motion.light, offset) if "light" in take else []
        shadow = _shift(motion.shadow, offset) if "shadow" in take else []
        ik = _shift(motion.ik, offset) if "ik" in take else []

        collisions["bones"] += _merge_named(out.bones, bones, on_conflict)
        collisions["morphs"] += _merge_named(out.morphs, morphs, on_conflict)
        collisions["camera"] += _merge_frame(out.camera, camera, on_conflict)
        collisions["light"] += _merge_frame(out.light, light, on_conflict)
        collisions["shadow"] += _merge_frame(out.shadow, shadow, on_conflict)
        collisions["ik"] += _merge_frame(out.ik, ik, on_conflict)

        taken_max = 0
        for seq in (bones, morphs, camera, light, shadow, ik):
            if seq:
                taken_max = max(taken_max, max(k.frame for k in seq))
        inputs.append(
            {
                "path": path,
                "take": take,
                "offset": offset,
                "model_name": motion.model_name,
                "source_counts": {
                    "bones": len(motion.bones),
                    "morphs": len(motion.morphs),
                    "camera": len(motion.camera),
                    "light": len(motion.light),
                    "shadow": len(motion.shadow),
                    "ik": len(motion.ik),
                },
                "contributed": {
                    "bones": len(bones),
                    "morphs": len(morphs),
                    "camera": len(camera),
                    "light": len(light),
                    "shadow": len(shadow),
                    "ik": len(ik),
                },
            }
        )
        if concat:
            cursor = taken_max + 1 + int(gap)

    pmx_info: Optional[Dict[str, Any]] = None
    if pmx:
        pmx_info = apply_pmx_filter(out, pmx, pad_rest=pad_rest)
        if model_name is not None:
            out.model_name = model_name
        out.camera.sort(key=lambda k: k.frame)
        out.light.sort(key=lambda k: k.frame)
        out.shadow.sort(key=lambda k: k.frame)
    else:
        if model_name is not None:
            out.model_name = model_name
        out.bones.sort(key=lambda k: (k.frame, k.name))
        out.morphs.sort(key=lambda k: (k.frame, k.name))
        out.camera.sort(key=lambda k: k.frame)
        out.light.sort(key=lambda k: k.frame)
        out.shadow.sort(key=lambda k: k.frame)
        out.ik.sort(key=lambda k: k.frame)

    report: Dict[str, Any] = {
        "ok": True,
        "dry_run": dry_run,
        "mode": "concat" if concat else "overlay",
        "on_conflict": on_conflict,
        "model_name": out.model_name,
        "max_frame": max_frame(out),
        "counts": {
            "bones": len(out.bones),
            "morphs": len(out.morphs),
            "camera": len(out.camera),
            "light": len(out.light),
            "shadow": len(out.shadow),
            "ik": len(out.ik),
            "bone_names": len({k.name for k in out.bones}),
            "morph_names": len({k.name for k in out.morphs}),
        },
        "collisions": collisions,
        "pmx": pmx_info,
        "inputs": inputs,
        "output_path": None,
    }

    if dry_run:
        return report
    if not dst:
        return {**report, "ok": False, "error": "dst required when dry_run=False"}
    dst = os.path.abspath(dst)
    nbytes = write_vmd(dst, out)
    report["output_path"] = dst
    report["output_bytes"] = nbytes
    return report


class _AppendSource(argparse.Action):
    def __init__(self, option_strings, dest, **kwargs):
        self.kind = kwargs.pop("kind")
        super().__init__(option_strings, dest, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        items = getattr(namespace, self.dest, None) or []
        if self.kind == "dance":
            take = list(DANCE_TAKE)
        elif self.kind == "face":
            take = list(FACE_TAKE)
        else:
            take = list(ALL_CHANNELS)
        items.append({"path": values, "take": take, "offset": 0})
        setattr(namespace, self.dest, items)


class _SetLastOffset(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        items = getattr(namespace, "sources", None) or []
        if not items:
            raise argparse.ArgumentError(self, "--offset must follow a --src/--dance/--face")
        items[-1]["offset"] = int(values)
        namespace.sources = items


class _SetLastTake(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        items = getattr(namespace, "sources", None) or []
        if not items:
            raise argparse.ArgumentError(self, "--take must follow a --src/--dance/--face")
        items[-1]["take"] = _parse_take(values)
        namespace.sources = items


def _print_json(obj: Any) -> None:
    text = json.dumps(obj, ensure_ascii=False, indent=2)
    try:
        print(text)
    except UnicodeEncodeError:
        buf = getattr(sys.stdout, "buffer", None)
        if buf is not None:
            buf.write(text.encode("utf-8") + b"\n")
            return
        print(json.dumps(obj, ensure_ascii=True, indent=2))


def main(argv: Optional[list] = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (OSError, ValueError):
            pass
    p = argparse.ArgumentParser(
        description="Combine VMD files (dance + facial overlay). No Blender."
    )
    p.add_argument(
        "--src",
        dest="sources",
        action=_AppendSource,
        kind="all",
        help="VMD path (all channels). Repeatable. Order = overlay order.",
    )
    p.add_argument(
        "--dance",
        dest="sources",
        action=_AppendSource,
        kind="dance",
        help="VMD path; take bones+morphs+camera+light+shadow+ik.",
    )
    p.add_argument(
        "--face",
        dest="sources",
        action=_AppendSource,
        kind="face",
        help="VMD path; take morphs + face bones (目/あご/…).",
    )
    p.add_argument(
        "--take",
        action=_SetLastTake,
        help="Override take on the previous --src/--dance/--face (e.g. morphs,face_bones).",
    )
    p.add_argument(
        "--offset",
        action=_SetLastOffset,
        type=int,
        help="Frame offset for the previous --src/--dance/--face.",
    )
    p.add_argument("--dst", default=None)
    p.add_argument("--inspect", metavar="FILE", help="Dump VMD summary JSON; no merge.")
    p.add_argument("--inspect-pmx", metavar="FILE", help="Dump PMX bone/morph/IK summary; no merge.")
    p.add_argument(
        "--pmx",
        default=None,
        help="Target .pmx or rig JSON: filter names, stamp model name, pad rest.",
    )
    p.add_argument(
        "--rig",
        default=None,
        help="Same as --pmx for a JSON from --export-rig.",
    )
    p.add_argument(
        "--export-rig",
        metavar="PMX",
        help="Write bone/morph/IK name JSON from a PMX (no mesh). Needs --dst.",
    )
    p.add_argument(
        "--no-pad-rest",
        action="store_true",
        help="With --pmx, do not add frame-0 identity bones / zero morphs / extra IK.",
    )
    p.add_argument("--concat", action="store_true", help="Place each file after previous.")
    p.add_argument("--gap", type=int, default=0, help="Extra frames between concat clips.")
    p.add_argument(
        "--on-conflict",
        choices=("last", "first"),
        default="last",
        help="Same (name, frame): last (default) or first source wins.",
    )
    p.add_argument("--model-name", default=None, help="Header model name (Shift-JIS, 20 bytes).")
    p.add_argument("--apply", action="store_true", help="Write --dst (default is dry-run).")
    p.add_argument("--dry-run", action="store_true", help="Force no write.")
    p.set_defaults(sources=None)
    args = p.parse_args(argv)

    if args.inspect:
        try:
            report = inspect_vmd(args.inspect)
        except VmdError as e:
            _print_json({"ok": False, "error": str(e)})
            return 1
        _print_json(report)
        return 0

    if getattr(args, "inspect_pmx", None):
        try:
            report = inspect_pmx(args.inspect_pmx)
        except PmxError as e:
            _print_json({"ok": False, "error": str(e)})
            return 1
        _print_json(report)
        return 0

    if getattr(args, "export_rig", None):
        if not args.dst:
            _print_json({"ok": False, "error": "--dst required with --export-rig"})
            return 1
        try:
            report = write_rig(args.export_rig, args.dst)
        except PmxError as e:
            _print_json({"ok": False, "error": str(e)})
            return 1
        _print_json(report)
        return 0 if report.get("ok") else 1

    sources = args.sources or []
    if not sources:
        _print_json({"ok": False, "error": "need --src, --dance, and/or --face"})
        return 1
    dry = not args.apply
    if args.dry_run:
        dry = True
    if not dry and not args.dst:
        _print_json({"ok": False, "error": "--dst required with --apply"})
        return 1
    try:
        report = combine_vmd(
            sources,
            args.dst,
            dry_run=dry,
            on_conflict=args.on_conflict,
            concat=args.concat,
            gap=args.gap,
            model_name=args.model_name,
            pmx=args.rig or args.pmx,
            pad_rest=not args.no_pad_rest,
        )
    except (VmdError, PmxError) as e:
        _print_json({"ok": False, "error": str(e)})
        return 1
    _print_json(report)
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
