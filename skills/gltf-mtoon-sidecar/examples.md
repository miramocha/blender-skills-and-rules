# Examples

## Blaster

Open `D:\MiraArt\2026blaster\2026blaster_merged.blend` (not the old `v23-18` path).

Dump + export next to MiraSite models (after approval):

```python
out = r"D:\MiraGameDev\MiraSite\public\models\blaster"
dump_mtoon_sidecar(os.path.join(out, "mtoon.json"), dry_run=False)
export_prop_gltf(os.path.join(out, "blaster.glb"), dry_run=False)
```

Expected material keys: `Blue-Highlight`, `Darkblue-Highlight`, `Glow-NoOutline.EmissionAccent`. Glow/rim follow `mtoon_theme.json` **accent** (magenta), not `invertAccent`.

Clips (NLA stash names): `ActivateGun`, `ActivateHandle`, `ActivateCoupling.Merged` (CW action), `ActivateCoupling.Merged.CCW`. No stale `ActivateCoupling`. After export, strip sampled extra bones so Gun / Handle / hook sets stay disjoint. Play Gun + Handle + **one** coupling layer.

## Restore after MToon enable wipe

```python
import json
from dump_mtoon_sidecar import restore_material_from_entry

doc = json.load(open(r"D:\MiraArt\v23-5gun\Glow-NoOutline.EmissionAccent.mtoon-backup.json", encoding="utf-8"))
# backup may be raw socks; prefer a full sidecar materials[] entry
entry = doc["materials"]["Glow-NoOutline.EmissionAccent"]  # if dump_mtoon_sidecar format
restore_material_from_entry(bpy.data.materials["Glow-NoOutline.EmissionAccent"], entry)
```
