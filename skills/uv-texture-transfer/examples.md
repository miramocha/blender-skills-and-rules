# UV texture transfer examples

## Hair: overlapping UVMap → unique UVMap.Unwrapped (normal)

Hair strands share `hair.secondary_normal` on Purple + Yellow. Dest islands are packed (often rotated) so `kind="normal"`. Lit/shade are 16×16 solids → `switch_render_uv=True` is safe.

```python
import os, sys
SKILL_TOOLS = os.path.join(r"...", "skills", "uv-texture-transfer", "tools")
sys.path.insert(0, SKILL_TOOLS)
import uv_texture_transfer as uvt

print(uvt.audit_uv_transfer("Hair"))

result = uvt.transfer_uv_texture(
    "Hair",
    source_uv="UVMap",
    dest_uv="UVMap.Unwrapped",
    image="hair.secondary_normal",
    kind="normal",
    size=4096,
    assign=True,
    switch_render_uv=True,
    dry_run=False,
)
# result["save_path"] → hair.secondary_normal_Unwrapped.png (or _unwrapped slug)
# Purple + Yellow VRM Normal Texture → new image
```

## Color / albedo only (no tangent re-encode)

```python
uvt.transfer_uv_texture(
    "Body",
    source_uv="UVMap",
    dest_uv="UVMap.Unwrapped",
    image="body_skin_base",
    kind="color",
    size=2048,
    switch_render_uv=False,  # other maps still on UVMap
    dry_run=False,
)
```

## Dry-run fields to check

| Field | Meaning |
|-------|---------|
| `warnings` | Rotated islands + `kind=color`; other atlases vs `switch_render_uv` |
| `rotation.needs_tangent_reencode` | Dest islands rotated vs source |
| `assign_materials` | Mats that currently use the source image |
| `save_path` | New PNG; source file is never overwritten |
