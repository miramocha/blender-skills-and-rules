---
name: tri-to-quad-uv-map
description: >-
  Replay tri→quad topology on Blender meshes that share the same VRoid UV layout.
  UV-keyed edge dissolve from CSV maps; optional material_token filters by Phase B
  workflow name (e.g. Face.Skin). Skips when map file is missing or empty.
---

# Tri-to-quad UV map

## When to use

- VRoid **face**, **mouth**, **eyelash**, **iris**, **eyehighlight**, **body** meshes with tris but **same UV layout** as a reference quad conversion
- Portable replay via CSV (`u1,v1,u2,v2` dissolve edges) — not `tris_convert_to_quads`
- **Hair** → use [hair-tris-to-quad](../hair-tris-to-quad/SKILL.md) instead (UV varies per hairstyle)

## Profiles

JSON in `profiles/` — e.g. `face.json`:

| Field | Purpose |
|-------|---------|
| `map_file` | CSV path relative to skill root |
| `material_token` | Workflow material name (`Face.Skin`) — resolved via Phase B `resolve_material_by_token()` |
| `uv_layer` | Usually `UVMap` |

## MCP / Scripting

```python
import os
import sys

SKILL_TOOLS = os.path.join(r"...", "skills", "tri-to-quad-uv-map", "tools")
sys.path.insert(0, SKILL_TOOLS)
import tri_to_quad_uv_map as tq

# Audit material + map before apply
audit = tq.audit_material_on_object("Face", "Face.Skin")

# Dry-run (skips if maps/face-quad-dissolve.csv missing)
result = tq.apply_profile("face", target_obj="Face", dry_run=True)
if result.get("skipped"):
    print(result["reason"])  # map_not_found | empty_map | material_not_on_object | ...

result = tq.apply_profile("face", target_obj="Face", dry_run=False)
```

## Skip reasons

| `reason` | Meaning |
|----------|---------|
| `map_not_found` | Profile CSV/JSON map file does not exist |
| `empty_map` | Map file has no dissolve rows |
| `material_not_found` | `material_token` not in `bpy.data.materials` |
| `material_not_on_object` | Material exists but not assigned to target mesh |
| `mesh_object_not_found` | Invalid target object |
| `material_resolver_unavailable` | Phase B cleanup tools not on disk |

## Material filter

When `material_token` is set, only tri pairs on that **material slot** are dissolved. Safe to run on full `Face` object with many slots — eyes/brow tris are ignored.

Requires **vroid-vrm-blender-cleanup** Phase B tools for name resolution (`N00_…_Face_00_SKIN` → `Face.Skin`).
