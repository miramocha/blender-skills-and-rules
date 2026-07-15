# Tri→quad UV map — examples

## Face — new VRM import (proven)

```python
import sys
sys.path.insert(0, r"D:\MiraGameDev\blender-skills-and-rules\skills\tri-to-quad-uv-map\tools")
import bpy
import tri_to_quad_uv_map as tq

obj = bpy.data.objects["Face.Tris"]
bpy.context.view_layer.objects.active = obj
bpy.ops.object.mode_set(mode="EDIT")

assert tq.apply_profile("face", "Face.Tris", dry_run=True)["skipped"] == 0
tq.apply_profile("face", "Face.Tris", dry_run=False)
# audit: {4: 2116}
```

## Body — first-time map creation

1. In reference `.blend`: keep `Body.only` (4232 tris typical), build `Body.only.quad` (manual dissolve or prior workflow).
2. Export:

```python
tq.export_reference("body", src_obj="Body.only", dst_obj="Body.only.quad")
# writes maps/body-quad-dissolve.csv
```

3. New import:

```python
tq.apply_profile("body", "Body.Tris", dry_run=True)
tq.apply_profile("body", "Body.Tris", dry_run=False)
```

## Custom hair profile

`profiles/hair.json`:

```json
{
  "profile": "hair",
  "label": "VRoid hair",
  "uv_layer": "UVMap",
  "uv_precision": 4,
  "map_file": "maps/hair-quad-dissolve.csv",
  "reference": {
    "source_object": "Hair.only",
    "result_object": "Hair.only.quad"
  }
}
```

```python
tq.export_reference("hair")
tq.apply_profile("hair", "Hair.Tris", dry_run=False)
```

## Verify selection has no tris (linked faces)

```python
from collections import Counter
import bmesh

obj = bpy.data.objects["Face.only.quad"]
bm = bmesh.from_edit_mesh(obj.data)
sel_faces = set()
for v in bm.verts:
    if v.select:
        for f in v.link_faces:
            sel_faces.add(f)
print(dict(Counter(len(f.verts) for f in sel_faces)))
```

Use UV **island** clustering for “mirror patch” audits — not bbox alone. See audit rule.
