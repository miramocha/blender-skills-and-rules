---
name: gltf-mtoon-sidecar
description: >-
  Export a non-humanoid Blender prop as GLB plus MToon sidecar JSON, then apply
  pixiv MToonMaterial in three.js without VRMC_vrm / dummy hips. Use when shipping
  guns or props to MiraSite/three-vrmxt, dumping MToon after enable-wipe, NLA clip
  GLB, or applying mtoon.json beside a glTF.
---

# glTF + MToon sidecar (non-humanoid)

Props (guns, weapons) with VRM Add-on **MToon 1.0** in Blender. **Not** a VRM 1.0 avatar. Do **not** Allow Non-Humanoid Rig (injects dummy hips). Do **not** register `VRMLoaderPlugin` for this file.

glTF export **destroys** MToon (PBR leftover). Sidecar JSON is the look. `applyMtoonSidecar` in `@vrmxt/three-vrmxt` rebuilds pixiv `MToonMaterial`. No `VRMXT_materials_mtoonxt` unless the user asks for stencil (guns: skip).

## Progress checklist

```
- [ ] look — MToon authored in .blend (theme/classes via mtoon-material-sync)
- [ ] dump-dry-run — dump_mtoon_sidecar(..., dry_run=True) (skip_hidden default)
- [ ] dump-write — dry_run=False → mtoon.json
- [ ] export-dry-run — export_prop_gltf(..., dry_run=True)
- [ ] export-write — GLB, animation_mode NLA_TRACKS (fallback ACTIONS)
- [ ] three — GLTFLoader only + applyMtoonSidecar(gltf, json); AnimationMixer on gltf.animations
```

## Hard rules

- Dry-run dump/export first; write after approval
- Skip `MToon Outline (*)` datablocks in the sidecar
- Dump only materials on **visible** view-layer objects (`skip_hidden=True`). Hidden backups still `users` the same datablocks — visibility is the filter, not `mat.users` alone
- Mute NLA stash so clips stay **separate** (`export_animation_mode='NLA_TRACKS'`)
- Clear armature pose to rest before export. `export_force_sampling=True` bakes **every bone** into every clip (identity rest on unused bones). Layered three.js actions **replace** those tracks and freeze other clips. After export, keep only bones actually keyed on that Action (see reference). Do not treat GLB channel counts as the Action.
- Export installs temp `MToonSidecarPack.*` planes so unused MToon maps (matcap) enter the GLB, then deletes them. `applyMtoonSidecar` **removes** leftover pack meshes after harvesting textures (hidden meshes still inflate `Box3`). Do not save the .blend with those objects.
- `export_apply=True` — mesh modifiers (subdiv, Mirror, etc.). Armature not applied; skins stay. Shape keys skipped if other modifiers exist.
- `use_visible=True` — Khronos default is **false**. Hidden viewport objects (`hide_get`, collection hide) otherwise ship and stack on the live mesh (double frame / backup arms). Pack dummy planes stay visible so maps still pack; `applyMtoonSidecar` strips them after harvest.
- Enabling VRM MToon on a duplicate **wipes** RNA; dump JSON **before** enable, `restore_material_from_entry` after
- MiraSite `parseVrmBytes` requires `userData.vrm` — **new loader path** for these GLBs

## MCP

```python
import os, sys, json

REPO_TOOLS = os.path.join(r"...", "skills", "gltf-mtoon-sidecar", "tools")
sys.path.insert(0, REPO_TOOLS)
from dump_mtoon_sidecar import dump_mtoon_sidecar, restore_material_from_entry
from export_gltf_prop import export_prop_gltf

out_dir = r"D:\path\to\out"
dump = dump_mtoon_sidecar(os.path.join(out_dir, "mtoon.json"), dry_run=True)
print(json.dumps({k: dump[k] for k in dump if k != "document"}, indent=2))
dump = dump_mtoon_sidecar(os.path.join(out_dir, "mtoon.json"), dry_run=False)

exp = export_prop_gltf(os.path.join(out_dir, "prop.glb"), dry_run=True)
exp = export_prop_gltf(os.path.join(out_dir, "prop.glb"), dry_run=False)
```

Default export packs MToon Image nodes via dummy planes (`pack_mtoon_images=True`). Sidecar still stores basenames only. Sibling PNGs only if pack is off. `export_prop_gltf` sets `use_visible=True`; do not turn that off to “get everything.”

## Three.js

```js
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'
import { applyMtoonSidecar } from '@vrmxt/three-vrmxt'
import { AnimationMixer } from 'three'

const loader = new GLTFLoader()
// no VRMLoaderPlugin
const gltf = await loader.loadAsync('/models/prop/prop.glb')
const sidecar = await fetch('/models/prop/mtoon.json').then((r) => r.json())
applyMtoonSidecar(gltf, sidecar)
const mixer = new AnimationMixer(gltf.scene)
for (const clip of gltf.animations) mixer.clipAction(clip) // play/weight as layers
```

Same-bone clips still fight (pick one coupling variant). Sampled rest on unused bones also fights — strip those channels. See [reference.md](reference.md).

## Related

- [mtoon-material-sync](../mtoon-material-sync/SKILL.md) — theme / classes in Blender
- Not [vrm0-vrm1-convert](../vrm0-vrm1-convert/SKILL.md) (humanoid VRM files)
