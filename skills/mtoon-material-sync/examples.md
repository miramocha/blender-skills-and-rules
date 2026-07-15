# MToon material sync — examples

## Default — match all mats to face skin

```python
import os

SKILL_TOOLS = r"D:\MiraGameDev\blender-skills-and-rules\skills\mtoon-material-sync\tools"
exec(open(os.path.join(SKILL_TOOLS, "sync_mtoon_attributes.py"), encoding="utf-8").read())

result = audit_mtoon_sync()
# Present result["rows"] — materials with diff_count > 0

result = apply_mtoon_sync(dry_run=False)
```

Expected: body/hair/cloth **rim** align with `Face_00_SKIN (Instance)`; **GI Equalization** = `1.0`, **Shading Toony** = `0.95`, **Emissive Factor** black everywhere; **Shading Shift** unchanged per slot.

## Rim only

```python
result = apply_mtoon_sync(groups=["rim"], dry_run=False)
```

Use when shade shift/toony should stay per slot (e.g. hair keeps softer toony). Shading Shift is never in default groups.

## Bump rim lift project-wide

1. Set **Parametric Rim Lift** on reference material in Blender UI (e.g. `0.25`).
2. Re-run sync:

```python
result = apply_mtoon_sync(dry_run=False)
```

Or MCP one-liner after manual reference edit:

```python
import bpy
TARGET = 0.25
for mat in bpy.data.materials:
    node = mat.node_tree.nodes.get("Mtoon1Material.Mtoon1Output") if mat.use_nodes else None
    if node and node.inputs.get("Parametric Rim Lift"):
        node.inputs["Parametric Rim Lift"].default_value = TARGET
```

## Include outline materials

```python
result = apply_mtoon_sync(include_outline=True, dry_run=False)
```

Outline node may lack `Expression Rim Color Bind` — script skips missing sockets.

## Sample audit row

```json
{
  "material": "HAIR_01 (Instance)",
  "diff_count": 2,
  "diffs": [
    "Shading Toony",
    "Parametric Rim Color"
  ]
}
```

After apply, same material should have `diff_count: 0` on re-audit.
