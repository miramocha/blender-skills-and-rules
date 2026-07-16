---
name: tri-to-quad-uv-map
description: >-
  Replay tri→quad topology on Blender meshes that share the same VRoid UV layout.
  UV-keyed edge dissolve from CSV maps; optional material_token filters by Phase B
  workflow name (e.g. Face.Skin, Hair.Back on Body). Skips when map file is missing or empty.
---

# Tri-to-quad UV map

## When to use

- VRoid meshes with tris but **same UV layout** as a reference quad conversion
- Portable replay via CSV (`u1,v1,u2,v2` dissolve edges) — not `tris_convert_to_quads`
- **Face region** (often split across objects): `Face.Skin`, `Mouth.Face`, `Brow.Face`, `Eyelash.Face`, `Eyeline.Face`
- **Eye region**: `Iris.Eye`, `EyeHighlight.Eye`, `EyeWhite.Eye`
- **Body object** (`Body` mesh): `Body.Skin`, **`Hair.Back`** — back-of-head hair is a **material slot on Body**, same fixed body UV atlas (not the strand `Hair` mesh)
- **`Hair` object** (strand layers `Hair.{NN}`) → use [hair-tris-to-quad](../hair-tris-to-quad/SKILL.md) instead (UV atlas varies per hairstyle)

## Profiles

JSON in `profiles/` — e.g. `face.json`:

| Field | Purpose |
|-------|---------|
| `map_file` | CSV path relative to skill root |
| `material_token` | Workflow material name (`Face.Skin`) — resolved via Phase B `resolve_material_by_token()` |
| `uv_layer` | Usually `UVMap` |

One profile per **material slot**, not per object. Run multiple profiles against the same mesh when it carries several slots (e.g. `Body`).

| Profile | `material_token` | Target object | Map status |
|---------|------------------|---------------|------------|
| `face` | `Face.Skin` | `Face` (skin slot) | ✓ |
| `mouth` | `Mouth.Face` | `Face` | ✓ |
| `eyebrow` | `Brow.Face` | `Face` / `eyebrow` | ✓ |
| `eyelash` | `Eyelash.Face` | `Face` / `Eyelash` | ✓ |
| `eyeline` | `Eyeline.Face` | `Face` / `Eyeline` | ✓ |
| `iris` | `Iris.Eye` | `Iris` / eye slot | ✓ |
| `eyehighlight` | `EyeHighlight.Eye` | eye slot | ✓ |
| `eyewhite` | `EyeWhite.Eye` | `EyeWhite` | ✓ |
| `body` | `Body.Skin` | `Body` | — |
| `hairback` | `Hair.Back` | `Body` (slot 1) / `HairBack` | ✓ |

Clothing slots on `Body` (`Hoodie.Cloth`, `Shoes.Cloth`, …) are outfit-specific — no project CSV yet.

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
# result["elapsed_ms"] — profile wall time; see blender-skill-log skill_execution.log
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
| `material_not_found` | Token not in scene — re-run Phase B workflow rename or check slot assignment |
| `shape_keys_addon_unavailable` | Mesh has shape keys but **Apply Modifiers With Shape Keys** addon not enabled |

## Material filter

When `material_token` is set, only tri pairs on that **material slot** are dissolved. Safe to run on a multi-slot mesh — other slots are ignored.

Examples:

- `Face` with many slots — `apply_profile("face", …)` touches `Face.Skin` only
- `Body` with skin + back hair + clothing — run `body` then `hairback` separately; each CSV only dissolves its slot

```python
# Body: skin then back-of-head hair (same UV atlas, different slots)
tq.apply_profile("body", target_obj="Body", dry_run=False)
tq.apply_profile("hairback", target_obj="Body", dry_run=False)
```

Requires **vroid-vrm-blender-cleanup** Phase B tools for name resolution (`N00_…_Face_00_SKIN` → `Face.Skin`, `N00_…_HairBack_00_HAIR` → `Hair.Back`).

## Workflow (after separate-by-material)

1. **Duplicate** target mesh (`{Object}.NormalSrc`, hidden) — pre-tri topology for normals
2. **Apply** tri→quad dissolve map (`apply_profile`)
3. **Data Transfer** face-corner custom normals from duplicate → result  
   - Mapping: **Nearest Corner of Nearest Face** (`POLYINTERP_NEAREST`)
4. **Apply** modifier (stock `modifier_apply`, or shape-key-safe addon when needed)
5. **Cleanup** duplicate: delete, or if target has shape keys and transfer succeeded → rename to **`{Object}.old`**, hide viewport + render

Enabled by default (`transfer_normals=True`). Skipped when:

| `normal_transfer.reason` | Meaning |
|--------------------------|---------|
| `shape_keys_addon_unavailable` | Target has shape keys but **Apply Modifiers With Shape Keys** addon is not enabled |
| `addon_unavailable` | Same — operator `object.apply_modifiers_with_shape_keys` missing |
| `dry_run` | Audit only |
| `no_dissolves_applied` | Map matched nothing |
| `disabled` | `transfer_normals=False` |
| `transfer_failed` | Data Transfer or addon apply raised an error |

### Shape keys + normal transfer

When the target mesh has shape keys (e.g. full `Face` before per-slot split), normal transfer uses the third-party addon operator:

```python
bpy.ops.object.apply_modifiers_with_shape_keys(
    collection_property=[
        {"name": "TriQuad.NormalTransfer", "apply_modifier": True},
        {"name": "Armature", "apply_modifier": False},
    ]
)
```

Dependency check:

```python
import tri_to_quad_uv_map as tq
tq.shape_keys_modifier_apply_available()  # hasattr(bpy.ops.object, "apply_modifiers_with_shape_keys")
```

Install **Apply Modifiers With Shape Keys** from Blender Extensions (or equivalent) and enable it before running tri→quad on shape-key meshes.

Meshes **without** shape keys still use stock `bpy.ops.object.modifier_apply` and **delete** the normal-source duplicate.

When the target has shape keys and normal transfer succeeds, the pre-topology duplicate is kept as a hidden **`Face.old`** (or `{target}.old`) object — tri topology + original shape keys for reference/recovery. **One archive per target**; later profiles reuse existing `Face.old` and delete their normal-source duplicate.

```python
# Default: dissolve + normal transfer (Body.only, no shape keys)
tq.apply_profile("body", target_obj="Body.only", dry_run=False)

# Face with ARKit shape keys — normal transfer when addon enabled
tq.apply_profile("face", target_obj="Face", dry_run=False)

# Dissolve only
tq.apply_profile("body", target_obj="Body.only", transfer_normals=False)
```

## Verify symmetry

After apply, run [uv-topology-symmetry](../uv-topology-symmetry/SKILL.md) — assigns `TriQuad.Mismatch` for faces without a UV mirror partner.
