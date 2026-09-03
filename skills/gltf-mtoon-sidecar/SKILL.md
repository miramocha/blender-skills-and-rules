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
- [ ] dump-dry-run — dump_mtoon_sidecar(..., dry_run=True)
- [ ] dump-write — dry_run=False → mtoon.json
- [ ] export-dry-run — export_prop_gltf(..., dry_run=True)
- [ ] export-write — GLB, animation_mode NLA_TRACKS (fallback ACTIONS)
- [ ] three — GLTFLoader only + applyMtoonSidecar(gltf, json); AnimationMixer on gltf.animations
```

## Hard rules

- Dry-run dump/export first; write after approval
- Skip `MToon Outline (*)` datablocks in the sidecar
- Mute NLA stash so clips stay **separate** (`export_animation_mode='NLA_TRACKS'`)
- `export_apply=False` (keep armature / skins)
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

Copy referenced PNG **names** (`mtoon.textures.*.name`) next to the GLB if glTF omit unused MToon maps (matcap). Sidecar never stores local directories.

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

Same-bone clips still fight (pick one coupling variant). See [reference.md](reference.md).

## Related

- [mtoon-material-sync](../mtoon-material-sync/SKILL.md) — theme / classes in Blender
- Not [vrm0-vrm1-convert](../vrm0-vrm1-convert/SKILL.md) (humanoid VRM files)
