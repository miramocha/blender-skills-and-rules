# glTF MToon sidecar — reference

## Why not VRM

VRM 1.0 needs a humanoid. Extended-VRM **Allow Non-Humanoid Rig** inserts dummy hips/legs at export. MiraSite avatar load expects `gltf.userData.vrm`. Props should be **GLB + sidecar**.

VRMXT Blender is a **hook** on that exporter. It must not delete nodes. Do not add a “VRM without humanoid” option there.

## Sidecar shape

```json
{
  "specVersion": "1.0",
  "kind": "mtoon-sidecar",
  "blend": "v23-18blaster_merged.blend",
  "materials": {
    "Blue-Highlight": {
      "enabled": true,
      "alphaMode": "OPAQUE",
      "doubleSided": true,
      "color": [1, 1, 1, 1],
      "emissiveFactor": [0, 0, 0],
      "emissiveStrength": 0,
      "mtoon": {
        "shadeColorFactor": [0.965, 0.678, 0.867],
        "shadingToonyFactor": 0.95,
        "shadingShiftFactor": -0.2,
        "giEqualizationFactor": 1,
        "matcapFactor": [1, 1, 1],
        "parametricRimColorFactor": [0.017, 0.716, 0.799],
        "parametricRimFresnelPowerFactor": 100,
        "parametricRimLiftFactor": 0.25,
        "rimLightingMixFactor": 0,
        "outlineWidthMode": "screenCoordinates",
        "outlineWidthFactor": 0.0015,
        "outlineColorFactor": [0.039, 0.035, 0.075],
        "outlineLightingMixFactor": 1,
        "textures": {
          "base": { "name": "darkblue.png" },
          "shade": { "name": "darkblue.png" },
          "matcap": { "name": "mtoon_matcap_highlight" }
        }
      }
    }
  }
}
```

Source of truth: `Mtoon1Material.Mtoon1Output` sockets + `Mtoon1*Texture.Image` nodes (RNA lags when `mtoon1.enabled` is false). Texture refs are **basename only** (no `D:\…`, no `//`). `blend` is the `.blend` file name only.

`outlineWidthMode` int on the node: `0` none, `1` world, `2` screen.

## glTF export (Blender 5.x)

`bpy.ops.export_scene.gltf` with `export_animation_mode='NLA_TRACKS'` (retry `'ACTIONS'`). Keep `export_animations=True`, `export_nla_strips=True`, `export_skins=True`, `export_apply=False`.

Muted NLA stash tracks still export as named clips if mode is NLA tracks.

## Enable-wipe

Setting `material.vrm_addon_extension.mtoon1.enabled = True` rebuilds from empty RNA. Dump sidecar first; after enable call `restore_material_from_entry(mat, entry)`.

## Three apply

`applyMtoonSidecar` matches `mesh.material.name` to `materials[name]`. Pulls textures already on the GLB by **image/texture name**. Missing matcap: put the PNG next to the GLB and load separately, or bake it into the glTF by using the image on a dummy.

Outline: clone mesh material with `isOutline` like pixiv `MToonMaterialLoaderPlugin` when mode ≠ `none` and width > 0.

No stencil plugin for this path.
