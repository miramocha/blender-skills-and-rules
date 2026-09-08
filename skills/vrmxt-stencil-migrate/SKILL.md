---
name: vrmxt-stencil-migrate
description: >-
  Headless stdlib Python migration of retired VRMXT / MToonXT stencil JSON to the
  root stencil graph (extensions.VRMXT_materials_mtoonxt.stencil). Converts
  stencilRelationships and per-material stencil/outlineStencil ops. Use when
  rewriting a .vrm / .glb / extracted glTF JSON that still has the old stencil
  draft, before import into current VRMXT Blender or UniVRMXT.
---

# VRMXT stencil migrate (headless)

## When to use

- A `.vrm` / `.glb` (or extracted `.gltf` / `.json`) still has **retired** MToonXT stencil:
  - root `extensions.VRMXT_materials_mtoonxt.stencilRelationships`
  - per-material `stencil` / `outlineStencil` `{op, materials}`
  - leftover `VRMC_materials_mtoonxt` extra name
- Need a disk rewrite **without Blender or Unity**

**Not** Blender MCP. **Not** UniVRMXT runtime. **Not** part of `run_full_pipeline()`. Do **not** confuse with [vrm0-vrm1-convert](../vrm0-vrm1-convert/SKILL.md) (that rewrites VRM 0.x ↔ 1.0). Beyond-Vtuber-Tools `tools/migrate_stencil_draft.py` only **renames** an existing graph and **refuses** material-op-only files; this skill also **inverts ops → graph**.

Current schema: root `extensions.VRMXT_materials_mtoonxt.stencil[]` with `writers` / `readers` and presentation flags. Spec: Extended-VRM-Specs `specs/extensions/materials/vrmxt-materials-mtoonxt/stencil.md`.

## Prerequisites

- Python 3.9+ (stdlib only)
- Input is glTF 2.0 **GLB** (`.vrm` / `.glb`) or a JSON glTF document

## Hard rules

- Dry-run first (`dry_run=True`); write only after user approval
- Never overwrite `--src`. `--dst` must be a different path
- Preserve the GLB **binary tail** (BIN and any later chunks) byte-for-byte; only rewrite the JSON chunk
- Keep non-stencil MToonXT fields (`faceSdf`, `zTest`, …)
- Drop `outlineStencil` (`same` or a second op). Body and outline share one graph entry
- Do not invent presentation flags the ops cannot encode (`writersSelfOcclude: false`, custom depth tests, show-through without `insideOverlay`). Those drafts already need a root graph — fail or keep the graph; do not guess
- Default ops invert is **writer-clip**, matching `mirabunny2026_mtoonxt_stencil.migrated.vrm`: the `inside`/`outside` material is the writer and `materials` are readers; `writersOnlyInsideReaders` / `writersOnlyOutsideReaders` follow the op. `insideOverlay` is always writer-clip overlay (`writersOnlyInsideReaders` + `showWritersThroughOccluders`)
- `--polarity reader-clip` inverts the other way: `write` = writer, `inside`/`outside` on the clip material lists the writers (no only-inside/outside flags)
- Coalesce equivalent rows (same writers + presentation, union readers) unless `--no-coalesce`
- Point `sys.path` at **this repo** `skills/vrmxt-stencil-migrate/tools`, not only `~/.cursor/skills`

## Agent workflow

```python
import os, sys, json

REPO = r"D:\MiraGameDev\blender-skills-and-rules"
SKILL_TOOLS = os.path.join(REPO, "skills", "vrmxt-stencil-migrate", "tools")
sys.path.insert(0, SKILL_TOOLS)
from migrate_mtoonxt_stencil import migrate_path

src = r"D:\avatars\old-stencil.vrm"
dst = r"D:\avatars\old-stencil.migrated.vrm"

report = migrate_path(src, dst, dry_run=True)
print(json.dumps(report, indent=2, ensure_ascii=False))

# After approval
report = migrate_path(src, dst, dry_run=False)
```

CLI:

```text
python skills/vrmxt-stencil-migrate/tools/migrate_mtoonxt_stencil.py --src IN.vrm --dst OUT.vrm
python skills/vrmxt-stencil-migrate/tools/migrate_mtoonxt_stencil.py --src IN.vrm --dst OUT.vrm --apply
python skills/vrmxt-stencil-migrate/tools/migrate_mtoonxt_stencil.py --src IN.gltf.json --dst OUT.gltf.json --polarity reader-clip --apply
```

Default CLI is dry-run. `--apply` writes `--dst`.

## Report schema

| Field | Meaning |
|-------|---------|
| `ok` | Migrate (or dry-run plan) succeeded |
| `dry_run` | No file written |
| `actions` | What changed (`renamed stencilRelationships`, `converted material ops`, coalesce, …) |
| `notes` | Non-fatal skips (bad row, dropped outlineStencil) |
| `polarity` | `reader-clip` or `writer-clip` |
| `stencil_count` | Rows in the output `stencil` array |
| `had_material_ops` | Input had per-material `stencil` / `outlineStencil` |
| `error` | Present when `ok` is false |

## Ops invert (writer-clip, default)

Output reference: MiraSite `public/models/mira-bunny/mirabunny2026_mtoonxt_stencil.migrated.vrm` (three rows: each iris writes White inside; Hair writes Brow outside). Do not vendor that GLB into the skill; tests skip if the files are absent.

| Material op | Graph |
|-------------|--------|
| `write` | Ignored except as a completeness check. Needs at least one clip op |
| `inside` / `outside` + `materials: [readers]` | This material is the writer; `comparison` plus `writersOnlyInsideReaders` / `writersOnlyOutsideReaders` |
| `insideOverlay` + `materials: [readers]` | This material is the writer; `writersOnlyInsideReaders` + `showWritersThroughOccluders` |
| `same` / `outlineStencil` | Dropped |

Write-only files (no clip op) fail: the old shorthand cannot encode a complete entry.

## Checks

```text
python skills/vrmxt-stencil-migrate/tools/test_migrate_mtoonxt_stencil.py
```
