# Tri→quad UV map — reference

## Algorithm

1. Reference **quad mesh** was built from **tri mesh** by dissolving shared edges between adjacent triangle pairs.
2. Each dissolve is identified by the **two UV coordinates** of that internal edge (`u1,v1` and `u2,v2`), rounded to `uv_precision` (default 4).
3. On a new mesh with the **same UV layout**, find the mesh edge whose loop UVs match that pair; if exactly **two triangles** share the edge, dissolve it.

```python
bmesh.ops.dissolve_edges(bm, edges=[edge], use_verts=False)
```

Vertices are **not** merged. UV corners are unchanged.

## Profile JSON schema

`profiles/<name>.json`:

| Field | Purpose |
|-------|---------|
| `profile` | Id passed to `apply_profile` / `export_reference` |
| `label` | Human description |
| `uv_layer` | UV layer name (default `UVMap`) |
| `uv_precision` | Decimal places for UV keys (default 4) |
| `co_precision` | Export-only: match tris to quads by 3D position on reference pair |
| `map_file` | Relative to skill root, e.g. `maps/face-quad-dissolve.csv` |
| `reference.source_object` | Tri reference object for export |
| `reference.result_object` | Quad result object for export |

## File sizes (face, 2116 joins)

| Format | Size |
|--------|------|
| CSV (`u1,v1,u2,v2` only) | ~59 KB |
| JSON compact (dissolve only) | ~69 KB |
| JSON pretty + `quad_uv` | ~908 KB |

## API summary (`tools/tri_to_quad_uv_map.py`)

| Function | Role |
|----------|------|
| `Profile.load(name)` | Load `profiles/<name>.json` |
| `export_reference(profile, …)` | Export CSV from profile reference objects |
| `export_map(src, dst, path, …)` | Low-level export (.csv or .json) |
| `apply_profile(profile, target_obj, dry_run=…)` | Apply profile map to target |
| `apply_map(target_obj, map_path, dry_run=…)` | Apply arbitrary map file |
| `load_map(path)` | Load CSV or JSON |
| `audit_topology(obj_name)` | `{3: n, 4: m}` face counts |
| `extract_dissolve_edges(…)` | Core pairing logic |

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `skipped > 0` on apply | UV drift, wrong layer, or topology already quads | Check `uv_layer`, re-export map from same UV template |
| Tris “in mirror bbox” but not on patch | Face on **main UV island**, not disconnected patch | Cluster by UV connectivity (see audit rule) |
| Export `join_count` low | Result mesh has tris/ngons or vert mismatch vs source | Ensure result is all quads from same vert pool as source |
| Seam failures | Duplicate UV keys, multiple edges | Rare; may need manual fixes at seams |

## Legacy paths

- `reference/face-quad-dissolve-map.json` — superseded by `maps/face-quad-dissolve.csv`
- `reference/tools/face_quad_uv_map.py` — shim to this skill’s tool module
