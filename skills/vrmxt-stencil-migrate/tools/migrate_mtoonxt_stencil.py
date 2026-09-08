"""Migrate retired MToonXT stencil JSON to the root stencil graph. Stdlib only."""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Sequence, Tuple

from glb_json import GlbError, join_glb, split_glb

EXT = "VRMXT_materials_mtoonxt"
EXT_LEGACY = "VRMC_materials_mtoonxt"
SPEC_VERSION = "1.0"
POLARITY_READER = "reader-clip"
POLARITY_WRITER = "writer-clip"

COMPARISON_OUTSIDE = "outside"
COMPARISON_INSIDE = "inside"
OP_WRITE = "write"
OP_INSIDE = "inside"
OP_OUTSIDE = "outside"
OP_INSIDE_OVERLAY = "insideOverlay"
OP_SAME = "same"

PRESENTATION_DEFAULTS: Dict[str, Any] = {
    "comparison": COMPARISON_OUTSIDE,
    "showWritersThroughOccluders": False,
    "writersOnlyInsideReaders": False,
    "writersOnlyOutsideReaders": False,
    "writersSelfOcclude": True,
    "ignoreOccludedReaderAreas": True,
    "writersWriteColor": True,
    "writersWriteDepth": True,
    "readersWriteDepth": True,
    "writerDepthTest": "lessEqual",
    "readerDepthTest": "lessEqual",
}


class MigrateError(ValueError):
    pass


def _as_dict(value: Any) -> Optional[Dict[str, Any]]:
    return value if isinstance(value, dict) else None


def _as_list(value: Any) -> Optional[List[Any]]:
    return value if isinstance(value, list) else None


def _unique_ints(values: Sequence[Any], n_materials: int, *, label: str) -> List[int]:
    out: List[int] = []
    seen = set()
    for value in values:
        if not isinstance(value, int) or isinstance(value, bool):
            raise MigrateError(f"{label} must be material indices")
        if value < 0 or value >= n_materials:
            raise MigrateError(f"{label} index {value} is out of range")
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _ensure_extensions_used(gltf: MutableMapping[str, Any], name: str) -> None:
    used = gltf.get("extensionsUsed")
    if not isinstance(used, list):
        gltf["extensionsUsed"] = [name]
        return
    if name not in used:
        used.append(name)


def _drop_extensions_used(gltf: MutableMapping[str, Any], name: str) -> None:
    used = gltf.get("extensionsUsed")
    if not isinstance(used, list):
        return
    gltf["extensionsUsed"] = [item for item in used if item != name]
    if not gltf["extensionsUsed"]:
        gltf.pop("extensionsUsed", None)


def _ext_in_use(gltf: Mapping[str, Any], name: str) -> bool:
    root = _as_dict(gltf.get("extensions"))
    if root and name in root:
        return True
    for material in gltf.get("materials") or []:
        if not isinstance(material, dict):
            continue
        extras = _as_dict(material.get("extensions"))
        if extras and name in extras:
            return True
    return False


def _rename_ext_key(container: MutableMapping[str, Any], notes: List[str]) -> None:
    if EXT_LEGACY not in container:
        return
    legacy = container[EXT_LEGACY]
    if EXT in container:
        current = container[EXT]
        if current != legacy:
            raise MigrateError(
                f"conflicting {EXT_LEGACY} and {EXT} objects; resolve one extra first"
            )
        del container[EXT_LEGACY]
        notes.append(f"dropped duplicate {EXT_LEGACY}")
        return
    container[EXT] = legacy
    del container[EXT_LEGACY]
    notes.append(f"renamed {EXT_LEGACY} -> {EXT}")


def _material_extras(material: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    extras = _as_dict(material.get("extensions"))
    if extras is None:
        return None
    return _as_dict(extras.get(EXT)) or _as_dict(extras.get(EXT_LEGACY))


def _parse_op(extra: Mapping[str, Any], key: str) -> Optional[Tuple[str, List[Any]]]:
    block = _as_dict(extra.get(key))
    if block is None:
        return None
    op = block.get("op")
    if not isinstance(op, str):
        raise MigrateError(f"material {key}.op must be a string")
    materials = block.get("materials")
    if materials is None:
        materials = []
    if not isinstance(materials, list):
        raise MigrateError(f"material {key}.materials must be an array")
    return op, materials


def _entry_key(entry: Mapping[str, Any]) -> Tuple[object, ...]:
    writers = tuple(sorted(set(entry.get("writers") or ())))
    presentation: List[object] = []
    for name, default in PRESENTATION_DEFAULTS.items():
        presentation.append(entry.get(name, default))
    extras = tuple(
        sorted(
            (k, json.dumps(v, sort_keys=True, default=str))
            for k, v in entry.items()
            if k not in ("writers", "readers") and k not in PRESENTATION_DEFAULTS
        )
    )
    return (writers, tuple(presentation), extras)


def _serialize_new_entry(
    writers: Sequence[int],
    readers: Sequence[int],
    *,
    comparison: str = COMPARISON_OUTSIDE,
    show_through: bool = False,
    only_inside: bool = False,
    only_outside: bool = False,
) -> Dict[str, Any]:
    entry: Dict[str, Any] = {"writers": list(writers), "readers": list(readers)}
    optional = (
        ("comparison", comparison, COMPARISON_OUTSIDE),
        ("showWritersThroughOccluders", show_through, False),
        ("writersOnlyInsideReaders", only_inside, False),
        ("writersOnlyOutsideReaders", only_outside, False),
    )
    for key, value, default in optional:
        if value != default:
            entry[key] = value
    return entry


def coalesce_stencil_entries(entries: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    by_key: Dict[Tuple[object, ...], Dict[str, Any]] = {}
    for raw in entries:
        writers = list(raw.get("writers") or [])
        readers = list(raw.get("readers") or [])
        entry = dict(raw)
        entry["writers"] = writers
        entry["readers"] = readers
        key = _entry_key(entry)
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = entry
            result.append(entry)
            continue
        writer_set = set(existing["writers"])
        for reader in readers:
            if reader not in existing["readers"] and reader not in writer_set:
                existing["readers"].append(reader)
    return result


def _ops_to_graph(
    materials: Sequence[Any],
    polarity: str,
    notes: List[str],
) -> List[Dict[str, Any]]:
    n = len(materials)
    parsed: List[Optional[Tuple[str, List[int]]]] = []
    for i, material in enumerate(materials):
        extra = _material_extras(material) if isinstance(material, dict) else None
        if extra is None:
            parsed.append(None)
            continue
        body = _parse_op(extra, "stencil")
        outline = _parse_op(extra, "outlineStencil")
        if outline is not None and outline[0] not in (OP_SAME, OP_WRITE) and body is not None:
            if outline[0] != body[0] or outline[1] != body[1]:
                notes.append(
                    f"dropped outlineStencil on material {i} (body+outline share one graph entry)"
                )
        if body is None:
            parsed.append(None)
            continue
        op, targets = body
        if op == OP_SAME:
            parsed.append(None)
            continue
        parsed.append((op, _unique_ints(targets, n, label=f"material {i} stencil.materials")))

    entries: List[Dict[str, Any]] = []
    used_clip = False
    for i, item in enumerate(parsed):
        if item is None:
            continue
        op, targets = item
        if op == OP_WRITE:
            continue
        if op == OP_INSIDE_OVERLAY:
            if not targets:
                raise MigrateError(
                    f"material {i} insideOverlay needs stencil.materials (reader indices)"
                )
            writers, readers = [i], targets
            if i in readers:
                raise MigrateError(f"material {i} cannot be both writer and reader")
            entries.append(
                _serialize_new_entry(
                    writers,
                    readers,
                    comparison=COMPARISON_INSIDE,
                    show_through=True,
                    only_inside=True,
                )
            )
            used_clip = True
            continue
        if op not in (OP_INSIDE, OP_OUTSIDE):
            raise MigrateError(f"material {i} has unknown stencil.op {op!r}")
        if not targets:
            raise MigrateError(f"material {i} {op} needs stencil.materials")
        comparison = COMPARISON_INSIDE if op == OP_INSIDE else COMPARISON_OUTSIDE
        if polarity == POLARITY_WRITER:
            writers, readers = [i], targets
            only_inside = op == OP_INSIDE
            only_outside = op == OP_OUTSIDE
            entries.append(
                _serialize_new_entry(
                    writers,
                    readers,
                    comparison=comparison,
                    only_inside=only_inside,
                    only_outside=only_outside,
                )
            )
        else:
            writers, readers = targets, [i]
            entries.append(_serialize_new_entry(writers, readers, comparison=comparison))
        if i in writers and i in readers:
            raise MigrateError(f"material {i} cannot be both writer and reader")
        used_clip = True

    if not used_clip:
        write_only = [
            i for i, item in enumerate(parsed) if item is not None and item[0] == OP_WRITE
        ]
        if write_only:
            raise MigrateError(
                "material-op draft has write ops but no clip ops; "
                "re-author a root stencil graph or add inside/outside/insideOverlay"
            )
    return coalesce_stencil_entries(entries)


def _root_ext(gltf: MutableMapping[str, Any], create: bool) -> Optional[Dict[str, Any]]:
    root_exts = _as_dict(gltf.get("extensions"))
    if root_exts is None:
        if not create:
            return None
        root_exts = {}
        gltf["extensions"] = root_exts
    extra = _as_dict(root_exts.get(EXT))
    if extra is None:
        if not create:
            return None
        extra = {}
        root_exts[EXT] = extra
    return extra


def migrate_gltf(
    gltf: MutableMapping[str, Any],
    *,
    polarity: str = POLARITY_WRITER,
    coalesce: bool = True,
) -> Dict[str, Any]:
    if polarity not in (POLARITY_READER, POLARITY_WRITER):
        raise MigrateError(f"unknown polarity {polarity!r}")

    notes: List[str] = []
    actions: List[str] = []
    work = gltf

    root_exts = _as_dict(work.get("extensions"))
    if root_exts is not None:
        _rename_ext_key(root_exts, notes)

    materials = work.get("materials")
    if not isinstance(materials, list):
        materials = []
        work["materials"] = materials
    for material in materials:
        if isinstance(material, dict):
            extras = _as_dict(material.get("extensions"))
            if extras is not None:
                _rename_ext_key(extras, notes)

    extra = _as_dict((_as_dict(work.get("extensions")) or {}).get(EXT)) or {}
    old_graph = extra.get("stencilRelationships")
    new_graph = extra.get("stencil")
    if old_graph is not None and new_graph is not None and old_graph != new_graph:
        raise MigrateError("conflicting root stencil and stencilRelationships")
    if old_graph is not None and not isinstance(old_graph, list):
        raise MigrateError("stencilRelationships must be an array")
    if new_graph is not None and not isinstance(new_graph, list):
        raise MigrateError("stencil must be an array")

    had_ops = False
    for material in materials:
        extra_mat = _material_extras(material) if isinstance(material, dict) else None
        if extra_mat and ("stencil" in extra_mat or "outlineStencil" in extra_mat):
            had_ops = True
            break

    graph: Optional[List[Any]] = None
    if isinstance(old_graph, list):
        graph = copy.deepcopy(old_graph)
        actions.append("renamed stencilRelationships -> stencil")
    elif isinstance(new_graph, list):
        graph = copy.deepcopy(new_graph)
        if had_ops:
            actions.append("kept root stencil; dropped material ops")
        else:
            actions.append("already root stencil")
    elif had_ops:
        graph = _ops_to_graph(materials, polarity, notes)
        actions.append(f"converted material ops -> stencil ({polarity})")

    for material in materials:
        if not isinstance(material, dict):
            continue
        extras = _as_dict(material.get("extensions"))
        if extras is None:
            continue
        extra_mat = _as_dict(extras.get(EXT))
        if extra_mat is None:
            continue
        extra_mat.pop("stencil", None)
        extra_mat.pop("outlineStencil", None)
        if set(extra_mat) <= {"specVersion"}:
            del extras[EXT]
            if not extras:
                material.pop("extensions", None)

    if graph is not None:
        n = len(materials)
        cleaned: List[Dict[str, Any]] = []
        for i, raw in enumerate(graph):
            row = _as_dict(raw)
            if row is None:
                notes.append(f"skipped non-object stencil[{i}]")
                continue
            writers = _unique_ints(row.get("writers") or [], n, label="writers")
            readers = _unique_ints(row.get("readers") or [], n, label="readers")
            if not writers or not readers:
                notes.append(f"skipped stencil[{i}] (empty writers or readers)")
                continue
            if set(writers) & set(readers):
                raise MigrateError(f"stencil[{i}] has overlapping writers and readers")
            if row.get("writersOnlyInsideReaders") and row.get("writersOnlyOutsideReaders"):
                raise MigrateError(
                    f"stencil[{i}] sets both writersOnlyInsideReaders and writersOnlyOutsideReaders"
                )
            entry = dict(row)
            entry["writers"] = writers
            entry["readers"] = readers
            cleaned.append(entry)
        if coalesce:
            before = len(cleaned)
            cleaned = coalesce_stencil_entries(cleaned)
            if len(cleaned) < before:
                actions.append(f"coalesced {before} -> {len(cleaned)} stencil rows")
        graph = cleaned

    root = _as_dict(work.get("extensions"))
    extra_out = _as_dict(root.get(EXT)) if root else None
    if graph:
        if extra_out is None:
            extra_out = _root_ext(work, create=True)
            assert extra_out is not None
        extra_out.pop("stencilRelationships", None)
        extra_out["specVersion"] = extra_out.get("specVersion") or SPEC_VERSION
        extra_out["stencil"] = graph
        _ensure_extensions_used(work, EXT)
    else:
        if extra_out is not None:
            extra_out.pop("stencilRelationships", None)
            extra_out.pop("stencil", None)
            if set(extra_out) <= {"specVersion"}:
                root = _as_dict(work.get("extensions"))
                if root is not None:
                    root.pop(EXT, None)
                    if not root:
                        work.pop("extensions", None)

    if not _ext_in_use(work, EXT):
        _drop_extensions_used(work, EXT)
    _drop_extensions_used(work, EXT_LEGACY)
    if _ext_in_use(work, EXT_LEGACY):
        _ensure_extensions_used(work, EXT_LEGACY)

    stencil_count = 0
    root_now = _as_dict(work.get("extensions"))
    extra_now = _as_dict(root_now.get(EXT)) if root_now else None
    if extra_now and isinstance(extra_now.get("stencil"), list):
        stencil_count = len(extra_now["stencil"])

    return {
        "ok": True,
        "actions": actions,
        "notes": notes,
        "polarity": polarity,
        "stencil_count": stencil_count,
        "had_material_ops": had_ops,
    }


def migrate_bytes(data: bytes, **kwargs: Any) -> Tuple[bytes, Dict[str, Any]]:
    document, tail, kind = split_glb(data)
    report = migrate_gltf(document, **kwargs)
    return join_glb(document, tail, kind), report


def _is_glb(path: str, data: bytes) -> bool:
    ext = os.path.splitext(path)[1].lower()
    if ext in {".vrm", ".glb"}:
        return True
    return data.startswith(b"glTF")


def migrate_path(
    src: str,
    dst: Optional[str] = None,
    *,
    dry_run: bool = True,
    polarity: str = POLARITY_WRITER,
    coalesce: bool = True,
) -> Dict[str, Any]:
    src = os.path.abspath(src)
    with open(src, "rb") as handle:
        raw = handle.read()

    is_glb = _is_glb(src, raw)
    try:
        if is_glb:
            document, tail, kind = split_glb(raw)
        else:
            document = json.loads(raw.decode("utf-8"))
            tail, kind = b"", 0
    except (GlbError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": str(exc), "src": src}

    work = copy.deepcopy(document)
    try:
        report = migrate_gltf(work, polarity=polarity, coalesce=coalesce)
    except MigrateError as exc:
        return {"ok": False, "error": str(exc), "src": src}

    if dst is None:
        root, ext = os.path.splitext(src)
        dst = root + ".migrated" + ext
    dst = os.path.abspath(dst)
    report.update({"src": src, "dst": dst, "dry_run": dry_run, "glb": is_glb})

    if dry_run:
        return report
    if dst == src:
        return {"ok": False, "error": "refusing to overwrite src; pass a different --dst", "src": src}

    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    if is_glb:
        out = join_glb(work, tail, kind)
        with open(dst, "wb") as handle:
            handle.write(out)
    else:
        with open(dst, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(work, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    return report


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Migrate retired MToonXT stencil JSON to extensions.VRMXT_materials_mtoonxt.stencil"
    )
    parser.add_argument("--src", required=True, help=".vrm / .glb / .gltf / .json")
    parser.add_argument("--dst", help="output path (default: SRC.migrated + suffix)")
    parser.add_argument("--apply", action="store_true", help="write dst (default is dry-run)")
    parser.add_argument(
        "--polarity",
        choices=(POLARITY_READER, POLARITY_WRITER),
        default=POLARITY_WRITER,
        help="how to invert inside/outside material ops (default writer-clip; insideOverlay is always writer-clip overlay)",
    )
    parser.add_argument("--no-coalesce", action="store_true", help="do not merge equivalent stencil rows")
    args = parser.parse_args(argv)
    report = migrate_path(
        args.src,
        args.dst,
        dry_run=not args.apply,
        polarity=args.polarity,
        coalesce=not args.no_coalesce,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
