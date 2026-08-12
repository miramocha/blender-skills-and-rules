# MToon theme + sync reference

## Shader node

- **Node name:** `Mtoon1Material.Mtoon1Output`
- **Matcap image node:** `Mtoon1MatcapTexture.Image`
- **Addon:** VRM Add-on for Blender (MToon 1.0)

## Theme JSON (`mtoon_theme.json`)

| Key | Role |
|-----|------|
| `accent` | Default parametric rim + `EmissionAccent` lit/shade/emission |
| `invertAccent` | Pink pair; VRM expr `invertAccent` swap target |
| `groups.rim` | Fresnel + lift (non-NoRim; `NoRim` → rim black, lift `0`, fresnel `1000`), lighting mix |
| `groups.outline` | Width mode `2` = screenCoordinates, width, color |
| `groups.shading` | Toony + GI (base mats only, not outline companions) |
| `groups.emission` | Default emissive (usually black) |
| `groups.highlight.image` | `mtoon_matcap_highlight` (`Highlight` class) |

`MatcapTexture`: keep linked MatCap Texture + factor white. Not both with `Highlight`. Legacy alias: `CustomMatcap`.

Outline Width Mode ints: `0` none, `1` worldCoordinates, `2` screenCoordinates.

## Material name parse

`{Identity}-{Class}.{Class}` + optional `MToon Outline (...)` + `.001`.

Identity: `_` only (`Face_Skin`). Texture slug = `identity.lower()`.

## invertAccent expression

VRM1 custom expression on armature `vrm_addon_extension.vrm1.expressions`.

| Bind `type` | Rest socket |
|-------------|-------------|
| `rimColor` | Parametric Rim Color (alpha `0`) |
| `color` | Lit Color (alpha `1`) |
| `shadeColor` | Shade Color (alpha `1`) |
| `emissionColor` | Emissive Factor (alpha `1`) |

RGB match epsilon `1e-3`. Rest ≈ accent → target invertAccent; rest ≈ invertAccent → target accent.

## Dummy / shared images (Phase C)

| Stem | Target |
|------|--------|
| `white_emissive` | `mtoon_none_white` |
| `hair.secondary_matcap` | `mtoon_none_black` |
| `light_matcap` | `mtoon_matcap_highlight` |
| `Shader_NoneBlack` | `mtoon_none_black` |
| `Shader_NoneNormal` | `mtoon_none_normal` |

## Legacy sync groups (no theme)

### `rim`

Parametric Rim Color, Fresnel Power, Lift, Rim LightingMix, Rim Color Texture, Expression Rim Color Bind.

### `shading`

Shading Toony, Shading Shift Texture Scale, Expression Shade Color Bind. **Not** Shading Shift.

## Scene stamp

After apply: `scene["mtoon_palette"]` JSON `{theme_path, theme_name, applied_hash}`.
