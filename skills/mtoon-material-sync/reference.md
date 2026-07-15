# MToon sync reference

## Shader node

- **Node name:** `Mtoon1Material.Mtoon1Output`
- **Addon:** VRM Add-on for Blender (MToon 1.0 node group)
- Materials without this node are skipped.

## Sync groups

### `rim`

| Input | Type | Typical face/skin value |
|-------|------|-------------------------|
| Parametric Rim Color | RGBA | `(1, 1, 1, 1)` white |
| Parametric Rim Fresnel Power | float | `100` |
| Parametric Rim Lift | float | `0.15`–`0.25` (project preference) |
| Rim LightingMix | float | `1.0` |
| Rim Color Texture | RGBA default | `(1, 1, 1, 1)` when unlinked |
| Expression Rim Color Bind | Vector | `(0, 0, 0)` |

### `shading`

| Input | Type | Typical face/skin value |
|-------|------|-------------------------|
| GI Equalization Factor | float | **`1.0`** (fixed project target; not from reference) |
| Shading Toony | float | **`0.95`** (fixed project target; not from reference) |
| Shading Shift Texture Scale | float | `1.0` |
| Expression Shade Color Bind | Vector | `(0, 0, 0)` |

**Not synced:** `Shading Shift` — face often `0.875`, body/cloth `0.0`, hair negative.

### `emission`

| Input | Type | Project target |
|-------|------|----------------|
| Emissive Factor | RGBA | **`(0, 0, 0, 1)`** black — unlinks `Emissive Texture` |

**Not synced:** `Emissive Strength`, `Expression Emission Color Bind` (left per material unless already matching reference).

## Common VRoid mismatches (before sync)

| Material kind | Often differs |
|---------------|----------------|
| Body / cloth | Shading Shift `0.0`, rim color black — shift left alone |
| Hair | Shading Toony `~0.795`, Shading Shift negative, linked emissive texture — shift left alone; emission forced black |
| Eyes / face decals | May already match face |
| Outline | Different toony/shift; optional `include_outline=True` |

## Apply rules

1. Read **unlinked** default values from reference inputs.
2. Override **GI Equalization Factor** to **`1.0`**, **Shading Toony** to **`0.95`**, and **Emissive Factor** to **black** on every MToon material (reference included).
3. For each target material with matching input socket:
   - Remove incoming links if reference uses a default value.
   - Copy `default_value`.
4. Skip sockets missing on target (e.g. outline variant).
5. Do **not** copy linked texture graphs automatically.

## Result dict keys

**Audit:** `reference_values`, `rows` (per-material `diffs`), `materials_needing_sync`

**Apply:** `updated`, `updated_count`, `remaining_materials_needing_sync`, `remaining_rows`
