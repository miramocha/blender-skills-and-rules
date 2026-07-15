---
name: tri-to-quad-uv-map
description: >-
  Replay tri→quad face topology on VRoid/VRM meshes by UV dissolve-edge map (CSV).
  Portable across imports with same UV layout; profiles for face, body, etc. Export
  once from reference tri+quad pair; apply to target mesh via Blender MCP. Do not
  use tris_convert_to_quads when topology must match reference. Use for Face.Tris,
  Body.Tris, quad cleanup, or mirroring manual UV quad conversion to new avatars.
---

# Tri→quad UV map replay

## When to use

- New VRM import: mesh is **all tris** but UV matches a **reference** you already converted to quads
- **Face**, **Body**, or other regions with stable VRoid UV — one map per profile
- User wants **same join topology** as manual dissolve (not Blender **Tris to Quads** operator)

Requires **Blender MCP** (`execute_blender_code`) unless user runs the script in Scripting.

Related: `.cursor/rules/blender-uv-island-audit.mdc` — audit UV islands by **connectivity**, not bbox.

## Progress checklist

```
- [ ] pick-profile — face, body, or custom profiles/<name>.json
- [ ] map-exists — maps/<profile>-quad-dissolve.csv present (export once if not)
- [ ] dry-run — apply_profile(..., dry_run=True); skipped should be 0
- [ ] apply — apply_profile(..., dry_run=False)
- [ ] verify — audit_topology; target all quads (or expected counts)
```

## Profiles

| Profile | Map | Reference objects (export) | Typical apply target |
|---------|-----|---------------------------|----------------------|
| `face` | `maps/face-quad-dissolve.csv` | `Face.only` → `Face.only.quad` | `Face.Tris`, `Face` |
| `body` | `maps/body-quad-dissolve.csv` | `Body.only` → `Body.only.quad` | `Body.Tris`, `Body` |

Add `profiles/<name>.json` + export map for hair, gloves, etc.

## MCP execution pattern

Set `SKILL_TOOLS` to this skill’s `tools/` folder.

```python
import os
import sys

SKILL_ROOT = r"D:\MiraGameDev\blender-skills-and-rules\skills\tri-to-quad-uv-map"
SKILL_TOOLS = os.path.join(SKILL_ROOT, "tools")
sys.path.insert(0, SKILL_TOOLS)

import tri_to_quad_uv_map as tq

# Dry-run then apply (face on new import)
obj = bpy.data.objects["Face.Tris"]
bpy.context.view_layer.objects.active = obj
bpy.ops.object.mode_set(mode="EDIT")

dry = tq.apply_profile("face", "Face.Tris", dry_run=True)
# expect applied == targets, skipped == 0

result = tq.apply_profile("face", "Face.Tris", dry_run=False)
audit = tq.audit_topology("Face.Tris")  # expect {4: N}
```

### Export reference map (once per profile)

After manual or scripted quad conversion on reference `.blend`:

```python
tq.export_reference("face")  # uses profiles/face.json → maps/face-quad-dissolve.csv
# or override objects:
tq.export_reference("body", src_obj="Body.only", dst_obj="Body.only.quad")
```

### Custom profile / path

```python
tq.export_map(
    "Hair.only", "Hair.only.quad",
    os.path.join(SKILL_ROOT, "maps", "hair-quad-dissolve.csv"),
    profile="hair",
    uv_layer="UVMap",
)

tq.apply_map("Hair.Tris", os.path.join(SKILL_ROOT, "maps", "hair-quad-dissolve.csv"), dry_run=False)
```

## Map format (CSV default)

```csv
# tri-to-quad-uv-map v1 profile=face uv_layer=UVMap uv_precision=4 joins=2116
u1,v1,u2,v2
0.5235,0.3642,0.5339,0.3769
```

Each row = **internal UV edge** dissolved when joining two tris into one quad. ~57 KB for face (vs ~908 KB pretty JSON with quad corners).

JSON still supported for `apply_map` / `export_map(..., ".json")`.

## Rules

1. **Do not** use `bpy.ops.mesh.tris_convert_to_quads` when user requires reference topology.
2. **Dry-run first** on every new avatar; investigate any `skipped > 0`.
3. Map is keyed by **UV only** — vert indices and world positions may differ per import.
4. **Same UV layer** as export (`UVMap` unless profile overrides).
5. Target mesh should be **tris** (or mixed); each dissolve requires **exactly two** adjacent tris on that UV edge.

## New profile workflow

1. Duplicate reference mesh: `Body.only` (tris), convert to `Body.only.quad`.
2. Copy `profiles/body.json`, adjust `reference` object names and `map_file`.
3. `export_reference("body")`.
4. On imports: `apply_profile("body", "Body.Tris")`.

See [reference.md](reference.md) and [examples.md](examples.md).
