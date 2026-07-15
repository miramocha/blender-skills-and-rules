---
name: mtoon-material-sync
description: >-
  Sync MToon 1.0 rim-light and shading (toony/shift) parametric attributes across
  Blender materials from a reference material for a consistent VRoid/VRM look.
  Dry-run audit then apply via Blender MCP execute_blender_code. Use when matching
  rim lights, Shading Toony, or unifying MToon rim look across avatar mats.
---

# MToon material sync

## When to use

- All avatar materials should share the same **rim lighting** response
- **Shading Toony** should match face reference across body, hair, cloth
- **Shading Shift** stays **per-material** (face skin differs from body/hair/cloth)
- After VRoid cleanup or manual rim tweaks on one material — propagate to the rest

Requires **Blender MCP** (`execute_blender_code`) unless the user runs the script in the Scripting workspace.

Related: [vroid-vrm-blender-cleanup](../vroid-vrm-blender-cleanup/SKILL.md) **Phase J** in `run_full_pipeline()` — runs after material/texture cleanup and ARKit rescans.

## Before changing anything

1. **Blender open** with target `.blend` loaded; MCP connected.
2. **Pick reference material** — default token `Face_Skin` (matches any material name containing that string) unless user names another.
3. **Dry-run → show diff table → user approval → apply → verify**.

Use AskQuestion when reference material is unclear or user wants outline materials included.

## Progress checklist

```
- [ ] pick-reference — Confirm reference material (default Face skin)
- [ ] audit-dry-run — List materials + differing MToon inputs
- [ ] user-approve — Pause before writes
- [ ] apply-sync — Copy parametric values to all MToon materials
- [ ] verify — Re-audit; report remaining diffs
```

## What gets synced (default)

Target node: `Mtoon1Material.Mtoon1Output` on each material.

| Group | Inputs |
|-------|--------|
| **rim** | Parametric Rim Color, Parametric Rim Fresnel Power, Parametric Rim Lift, Rim LightingMix, Rim Color Texture, Expression Rim Color Bind |
| **shading** | Shading Toony, Shading Shift Texture Scale, Expression Shade Color Bind |

**Not synced:** Shading Shift (per slot), Shade Color tint, linked shade/normal/matcap textures.

**Outline materials** (`MToon Outline (...)`) are **skipped by default** — different node variant, missing some sockets.

## MCP execution pattern

Set `SKILL_TOOLS` to this skill’s `tools/` folder.

```python
import os

SKILL_TOOLS = os.path.join(
    os.path.expanduser("~"),
    ".cursor",
    "skills",
    "mtoon-material-sync",
    "tools",
)
# Repo: skills/mtoon-material-sync/tools

exec(open(os.path.join(SKILL_TOOLS, "sync_mtoon_attributes.py"), encoding="utf-8").read())

# Audit only
result = audit_mtoon_sync(reference_material="Face_Skin")

# After approval
result = apply_mtoon_sync(reference_material="Face_Skin", dry_run=False)
```

### Options

```python
# Rim only
result = apply_mtoon_sync(groups=["rim"], dry_run=False)

# Include outline materials
result = apply_mtoon_sync(include_outline=True, dry_run=False)

# Different reference
result = apply_mtoon_sync(reference_material="Body_Skin", dry_run=False)
```

### Override single value after sync

```python
# Example: bump rim lift globally without changing reference material
result = apply_mtoon_sync(dry_run=False)
# then MCP one-liner on all MToon outputs, or re-run with updated reference mat
```

## Full pipeline (Phase J)

Included automatically when running `run_full_pipeline()` from **vroid-vrm-blender-cleanup**:

```python
result = run_full_pipeline(
    reference_material="Face_Skin",
    dry_run=False,
)
# result["phases"]["J"] — materials_needing_sync / updated_count
```

Skip with `phases={"A","B","C","F","G","H","I"}` (omit `"J"`).

- `remaining_materials_needing_sync` should be `0` after apply
- Spot-check hair/body/cloth in Material Preview
- Outline mats may still differ if `include_outline=False`

## Out of scope unless asked

- MToon texture image renames (see vroid-vrm-blender-cleanup Phase B/C)
- Shade Color tint per material
- Linked texture graph rewiring beyond clearing links when reference uses defaults
- MToon 0.x / non-VRM-addon shaders

## Utility script

| Script | Entrypoints |
|--------|-------------|
| [sync_mtoon_attributes.py](tools/sync_mtoon_attributes.py) | `audit_mtoon_sync()`, `apply_mtoon_sync()`, `run_mtoon_sync()`, `run_phase_j()` |

Full input tables: [reference.md](reference.md). Worked examples: [examples.md](examples.md).

Return structured `result` dicts from MCP code (assign `result = ...` after exec).
