---
name: uv-topology-symmetry
description: >-
  Audit UV topology mirror symmetry on Blender meshes (VRoid atlases) and assign
  TriQuad vertex groups for left/right quad-tri split plus mismatch highlight.
  Use after partial tri-to-quad-uv-map to find faces without a UV mirror partner.
---

# UV topology symmetry

## When to use

- Check whether UV **topology** mirrors across the atlas midline (not 3D mesh symmetry)
- After [tri-to-quad-uv-map](../tri-to-quad-uv-map/SKILL.md) — verify both sides converted evenly
- Highlight faces/verts that **lack a mirror partner** in UV space

Mirror axis: `u_center` from profile (default `null` → bbox center of active UVs, usually **0.5** on VRoid body/face atlases).

## Vertex groups written

| Group | Contents |
|-------|----------|
| `TriQuad.Left.Quad` / `TriQuad.Left.Tri` | Left UV half by face centroid; quad vs tri |
| `TriQuad.Right.Quad` / `TriQuad.Right.Tri` | Right UV half |
| `TriQuad.Left` / `TriQuad.Right` | Union of quad + tri per side |
| `TriQuad.Center` | Faces on centerline (`U ≈ u_center`) |
| `TriQuad.Mismatch` | **All verts on faces without UV mirror partner** |
| `TriQuad.Mismatch.Left` / `.Right` | Mismatch subset per side |

## MCP / Scripting

```python
import os
import sys

SKILL_TOOLS = os.path.join(r"...", "skills", "uv-topology-symmetry", "tools")
sys.path.insert(0, SKILL_TOOLS)
import uv_topology_symmetry as uvs

# Audit only
report = uvs.audit_uv_symmetry("Body.Torso")
print(report["symmetric"], report["unmatched_left_faces"], report["unmatched_right_faces"])

# Assign all TriQuad groups (includes mismatch highlight)
uvs.assign_triquad_vertex_groups("Body.Torso")

# Audit + assign in one call
result = uvs.audit_and_assign("Body.Torso")
```

Fixed mirror line (VRoid body atlas):

```python
uvs.audit_and_assign("Body.Torso", u_center=0.5)
```

## Check in Blender

1. **Edit mode** → **Ctrl+G** → Select by Vertex Group → `TriQuad.Mismatch`
2. Compare `TriQuad.Left.Quad` vs `TriQuad.Right.Quad` for partial tri→quad
3. **Weight Paint** — solo one group for color overlay

## Audit fields

| Field | Meaning |
|-------|---------|
| `symmetric` | Both edge + face mirror checks pass |
| `edge_symmetric` | Every left UV edge has mirrored right edge (and vice versa) |
| `face_symmetric` | Every left face shape has mirrored right face (and vice versa) |
| `unmatched_left_faces` / `unmatched_right_faces` | Face-count without mirror partner |
| `mesh_3d_bilateral_balanced` | 3D X-axis vert balance (separate from UV symmetry) |

## Profile

`profiles/default.json` — `uv_layer`, `uv_precision`, optional `u_center`, vertex group names.

## Related

- [tri-to-quad-uv-map](../tri-to-quad-uv-map/SKILL.md) — UV-keyed dissolve replay
- [hair-tris-to-quad](../hair-tris-to-quad/SKILL.md) — `Hair.Cap` / `Hair.Strip` groups (strand mesh, not atlas symmetry)
