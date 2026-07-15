---
name: hair-tris-to-quad
description: >-
  Convert VRoid hair tris to quads with Blender tris_convert_to_quads at 90° face
  and shape angles. Assigns Hair.Cap and Hair.Strip vertex groups before convert.
  Hair UV varies per hairstyle — not tri-to-quad-uv-map CSV.
---

# Hair tris to quad

## When to use

- Full **`Hair`** mesh (or merged hair objects) still triangulated after import
- **Not** [tri-to-quad-uv-map](../tri-to-quad-uv-map/SKILL.md) — face/mouth/body use fixed UV CSV dissolve maps

## Method

1. **Vertex groups** (from UV cap detection on tris): `Hair.Cap`, `Hair.Strip`
2. Stock Blender **Tris to Quads** on the whole mesh:

| Setting | Value |
|---------|-------|
| Max Face angle | **90°** |
| Max Shape angle | **90°** |

Caps: **2 tris**, **4 verts**, UV on one **horizontal line** (`v` constant).

## MCP / Scripting

```python
import os
import sys

SKILL_TOOLS = os.path.join(r"...", "skills", "hair-tris-to-quad", "tools")
sys.path.insert(0, SKILL_TOOLS)
import hair_tris_to_quad as hq

result = hq.apply_tris_to_quads("Hair", dry_run=True)   # assigns vtx groups, no convert
hq.apply_tris_to_quads("Hair", dry_run=False)           # groups + convert

# Groups only
hq.assign_cap_strip_vertex_groups("Hair")
```

`assign_vertex_groups=False` skips group write. Dry-run still assigns groups when tris present.

## Strand pattern (experimental)

Isolated **`Strand`** test meshes only — UV diagonal dissolve, skips caps:

```python
hq.apply_strand_pattern("Strand", dry_run=False)
```

Do **not** use on full `Hair` (atlas packing breaks global UV pairing).

## Profile

`profiles/hair.json` — default 90° / 90° angles, vertex group names.
