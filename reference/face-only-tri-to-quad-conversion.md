# Face.only → Face.only.quad conversion record

> **Superseded by skill:** [skills/tri-to-quad-uv-map](../skills/tri-to-quad-uv-map/SKILL.md)  
> Portable map: `skills/tri-to-quad-uv-map/maps/face-quad-dissolve.csv` (~59 KB)

## Summary (reference scene)

| Property | Face.only | Face.only.quad |
|----------|-----------|----------------|
| Vertices | 2266 | 2266 |
| Faces | 4232 tris | 2116 quads |
| Method | — | Dissolve shared edge per adjacent tri pair |

## Portable replay

- **Not** vert indices or world positions
- **Yes** UV edge pairs `(u1,v1,u2,v2)` in CSV
- Apply: `tri_to_quad_uv_map.apply_profile("face", "Face.Tris")`

## Legacy JSON

`reference/face-quad-dissolve-map.json` (~908 KB) — optional; CSV preferred.

See skill [reference.md](../skills/tri-to-quad-uv-map/reference.md) for full format and body/custom profiles.
