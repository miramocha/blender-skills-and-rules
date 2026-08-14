---
name: uv-texture-transfer
description: >-
  Bake a Blender texture from one UV map onto another on the same mesh (Cycles).
  Tangent-space normals use NORMAL bake so packed/rotated islands re-encode;
  albedo/masks use EMIT. Use when transferring VRM/MToon normals or color maps
  from overlapping UVs to a unique unwrap (e.g. UVMap → UVMap.Unwrapped).
---

# UV texture transfer

Same-mesh UV remap bake. Sample `source_uv`, write a **new** image on `dest_uv`. Does not overwrite the source file.

Requires **Blender MCP** (`execute_blender_code`) or Scripting workspace. Engine must be able to switch to **Cycles** (EEVEE `NORMALS` bake is geometry only — wrong for maps).

## When to use

- Mesh has two UV layers (overlapping atlas + unique unwrap)
- VRM MToon **Normal Texture** (or any Image Texture) still laid out on the old UV
- Dest islands may be **packed/rotated** — color-copy of a normal map would be wrong

Not for: baking high→low cages, selected-to-active, or tri→quad topology ([tri-to-quad-uv-map](../tri-to-quad-uv-map/SKILL.md) / [hair-tris-to-quad](../hair-tris-to-quad/SKILL.md)).

## Kind

| `kind` | Bake | Use for |
|--------|------|---------|
| `normal` | Cycles `NORMAL` + tangent | Tangent-space normal maps (reorients for island rotation) |
| `color` | Cycles `EMIT` | Albedo, masks, packed color — **not** normals if dest islands rotated |

Omit `kind` to guess from image name / VRM normal slot.

## Agent workflow

1. `audit_uv_transfer(object)` — UVs, images, rotation hint, warnings
2. Confirm `size` (unique unwrap of overlapping hair often needs **2048+**, not source 512)
3. `transfer_uv_texture(..., dry_run=True)` then apply `dry_run=False`
4. `switch_render_uv=True` only when **all** sampled maps should use dest UV (16×16 solids are fine; other atlases will break)

Do **not** `image.reload()` after save — that wiped a generated bake to flat blue. Tool packs, then `save(filepath=)`.

## MCP / Scripting

```python
import os
import sys

SKILL_TOOLS = os.path.join(
    os.path.expanduser("~"), ".cursor", "skills", "uv-texture-transfer", "tools"
)
REPO_TOOLS = os.path.join(r"...", "skills", "uv-texture-transfer", "tools")
if os.path.isdir(REPO_TOOLS):
    SKILL_TOOLS = REPO_TOOLS

sys.path.insert(0, SKILL_TOOLS)
import uv_texture_transfer as uvt

audit = uvt.audit_uv_transfer("Hair")
plan = uvt.transfer_uv_texture(
    "Hair",
    source_uv="UVMap",
    dest_uv="UVMap.Unwrapped",
    image="hair.secondary_normal",
    kind="normal",
    size=4096,
    switch_render_uv=True,
    dry_run=True,
)
result = uvt.transfer_uv_texture(
    "Hair",
    source_uv="UVMap",
    dest_uv="UVMap.Unwrapped",
    image="hair.secondary_normal",
    kind="normal",
    size=4096,
    switch_render_uv=True,
    dry_run=False,
)
```

Replace `...` with the blender-skills-and-rules workspace root.

## Parameters

| Arg | Default | Notes |
|-----|---------|--------|
| `image` | VRM normal on object mats | Source image datablock name |
| `kind` | guessed | `normal` \| `color` |
| `size` | source size | `int` square, or `(w, h)` |
| `margin` | `16` | `ADJACENT_FACES` |
| `samples` | `16` | Cycles; denoising off |
| `save_path` | next to source `{name}_{dest_slug}.png` | Never the source path |
| `assign` | `True` | Rewire VRM `*.index.source` + Image Texture nodes that used the source |
| `switch_render_uv` | `False` | Set dest UV `active_render` (MToon empty UV Map follows this) |
| `materials` | object slots | Limit assign list |
| `dry_run` | `True` | Audit plan only |

Temp bake mat `_UVTransferBake` is always removed. Render engine / samples restored.

## Related

- [hair-tris-to-quad](../hair-tris-to-quad/SKILL.md) — strand Hair topology, not UV bake
- [mtoon-material-sync](../mtoon-material-sync/SKILL.md) — theme compile after maps are wired
- Examples: [examples.md](examples.md)
