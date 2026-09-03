# glTF MToon sidecar — reference

## Why not VRM

VRM 1.0 needs a humanoid. Extended-VRM **Allow Non-Humanoid Rig** inserts dummy hips/legs at export. MiraSite avatar load expects `gltf.userData.vrm`. Props should be **GLB + sidecar**.

VRMXT Blender is a **hook** on that exporter. It must not delete nodes. Do not add a “VRM without humanoid” option there.

## Sidecar shape

```json
{
  "specVersion": "1.0",
  "kind": "mtoon-sidecar",
  "blend": "2026blaster_merged.blend",
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
        "parametricRimColorFactor": [0.799, 0.006, 0.407],
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

`bpy.ops.export_scene.gltf` with `export_animation_mode='NLA_TRACKS'` (retry `'ACTIONS'`). Keep `export_animations=True`, `export_nla_strips=True`, `export_skins=True`, `export_apply=True` (modifiers except armature).

Muted NLA stash tracks still export as named clips if mode is NLA tracks.

Clip **name** is the NLA **track** name. `export_prop_gltf` copies the first strip name onto the stash track for export, then restores `[Action Stash]*`. A strip named `ActivateCoupling.Merged` whose action is `ActivateCoupling.Merged.CW` ships as `ActivateCoupling.Merged`.

### Sampling vs Action keys

`export_force_sampling=True` (current `export_prop_gltf`) evaluates the whole armature. Every clip gets loc/rot/scale on bones the Action never keyed.

three.js `AnimationMixer` treats those as real tracks (usually replace). Playing Handle + Gun: Handle’s sampled rest on `handle` holds the gun body still. Coupling sampled rest on `hook*` holds hooks still.

**Source of truth is the Action fcurves**, not the GLB. After write, drop channels whose node name is not in that Action. Drop leftover clips (stale Actions). Re-strip after every export until sampling is off or the exporter filters bones.

Clear pose (`pose.transforms_clear`) before export so unkeyed bones sample identity, not a leftover viewport pose.

### Interpolation and hold poses

glTF has LINEAR / STEP / CUBICSPLINE. Blender **BACK** / bounce / elastic are baked by sampling. A clip that keys **up then back to rest** will clamp on rest in three.js (`LoopOnce` + `clampWhenFinished`). For a toggle that **holds** the raised pose: rest on the first key, hold value on the last key, LINEAR (or STEP). Last keyed value is what three.js holds.

Scene `frame_start` 1 → first sample at `1/fps` seconds. Mixer `t=0` can flash bind pose for one frame if the first key is not at time 0.

### Layering

Give each clip a disjoint bone set (`handle` vs `firing.handle` vs `hook*`). Two coupling variants still share hooks — only one on at a time.

## Enable-wipe

Setting `material.vrm_addon_extension.mtoon1.enabled = True` rebuilds from empty RNA. Dump sidecar first; after enable call `restore_material_from_entry(mat, entry)`.

## Three apply

`applyMtoonSidecar` matches `mesh.material.name` to `materials[name]`. Pulls textures already on the GLB by **image/texture name**. Missing matcap: export packs MToon Image nodes onto temp `MToonSidecarPack` planes (`pack_mtoon_images=True`). Apply strips those meshes after reading textures. `textureLookupKeys` aliases `blue.png` ↔ `blue`.

Outline: clone mesh material with `isOutline` like pixiv `MToonMaterialLoaderPlugin` when mode ≠ `none` and width > 0.

No stencil plugin for this path.
