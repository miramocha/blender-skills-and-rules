---
name: arkit-vroid-mmd-shapekeys
description: >-
  Creates Animasa-standard Japanese MMD shape keys on a Blender face mesh by
  baking mixes from existing VRoid (vroid*/Fcl_*) and ARKit sources without
  renaming or deleting those sources. Use when mapping ARKit or VRoid shape
  keys to MMD morphs, VMD face compatibility, まばたき / あいうえお names, or
  mmd_tools facial export.
---

# ARKit / VRoid → MMD shape keys

## When to use

- Need Animasa MMD morph names (`まばたき`, `あ`, `ウィンク`, `ｳｨﾝｸ２右`, …) for VMD / mmd_tools
- Face already has ARKit and/or VRoid (`vroid*` or `Fcl_*`) shape keys
- After cleanup **Phase D** (ARKit) and preferably **Phase F** (`Fcl_*` → `vroid*`)

**Order:** Phase D (ARKit) → tri→quad → MMD bakes. ARKit must be transferred on original **tri** topology; transferring after tri→quad yields offset keys, and MMD bakes inherit the offset.

Requires **Blender MCP** (`execute_blender_code`) or running [tools/map_mmd_shapekeys.py](tools/map_mmd_shapekeys.py) in Blender.

**Not** part of `run_full_pipeline()` — run standalone when MMD names needed.

## Hard guarantee

- **Never** rename, delete, or overwrite ARKit / `vroid*` / `Fcl_*` keys
- **Only add** new keys with exact MMD Japanese names (bake from temporary mix)
- If MMD name already exists → **skip** (no overwrite)
- VRM binds / drivers on sources stay valid

Result: mesh keeps ARKit + VRoid **and** gains MMD Animasa names.

## Before changing anything

1. Confirm face mesh (often `Face` / `face.main`).
2. List shape keys; classify ARKit / vroid / Fcl / existing MMD.
3. **Dry-run** `create_mmd_shape_keys(..., dry_run=True)`.
4. Review `will_create` / `missing_sources`; approve before apply.

## Workflow

```
Progress:
- [ ] 1. Find target mesh + shape key count
- [ ] 2. Dry-run core (or extended) mapping
- [ ] 3. User approves create list
- [ ] 4. Apply dry_run=False
- [ ] 5. Verify exact unicode names (esp. ｳｨﾝｸ２右)
- [ ] 6. Confirm ARKit/vroid/Fcl names still present
- [ ] 7. User saves .blend
```

### Dry-run

```python
import os

SKILL_TOOLS = r".../skills/arkit-vroid-mmd-shapekeys/tools"
exec(open(os.path.join(SKILL_TOOLS, "map_mmd_shapekeys.py"), encoding="utf-8").read())

result = create_mmd_shape_keys("Face", dry_run=True, set_scope="core")
# result["report"]["will_create"], ["missing_sources"], ["existing_mmd"]
```

### Apply

```python
result = create_mmd_shape_keys("Face", dry_run=False, set_scope="core")
# sources_untouched should be True
# scene["mmd_shapekey_map"] stores mmd → [{source, weight}, ...]
```

### Audit

```python
audit = audit_object_mmd_keys("Face", set_scope="core")
```

## Scope

| `set_scope` | Morphs |
|-------------|--------|
| `core` (default) | Animasa basic + `え` + common eye extras (`はぅ`, `びっくり`, …) |
| `extended` | Core plus mouth symbols / decorative; many skip if no source |

Source priority inside each mapping: **VRoid `vroid*` → `Fcl_*` → ARKit** composites.

Unmappable decorative morphs (`ω`, `はぁと`, …): reported skipped — hand sculpt, no fake proxy.

## Utility tools

| Tool | Entrypoints |
|------|-------------|
| [map_mmd_shapekeys.py](tools/map_mmd_shapekeys.py) | `create_mmd_shape_keys()`, `dry_run_mmd_mapping()`, `build_mmd_mapping()`, `resolve_sources()`, `classify_shape_keys()`, `audit_object_mmd_keys()` |

## Additional reference

- Full name lists + mapping table: [reference.md](reference.md)
- MCP examples: [examples.md](examples.md)

## Out of scope unless asked

- Renaming or removing ARKit / VRoid keys
- Wiring into `run_full_pipeline()`
- PMX/VMD export or mmd_tools bone setup
- Auto-sculpting morphs with no source geometry
