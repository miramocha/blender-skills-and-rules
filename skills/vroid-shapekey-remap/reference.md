# VRoid shape key reference

## Parser (default)

See [tools/remap_shapekeys.py](tools/remap_shapekeys.py):

| Symbol | Purpose |
|--------|---------|
| `CATEGORY_MAP` | `ALL`→`All`, `BRW`→`Brow`, `EYE`→`Eye`, `MTH`→`Mouth`, `HA`→`Teeth` |
| `convert_fcl_shape_key()` | `Fcl_*` → `vroid*` camelCase |
| `build_fcl_mapping()` | All keys on a mesh |
| `dry_run_mapping()` | Duplicates + name conflicts |
| `apply_shape_key_mapping()` | Rename key_blocks |

## Segment patterns

| Pattern | Example |
|---------|---------|
| Full face | `Fcl_ALL_Joy` → `vroidAllJoy` |
| Brow | `Fcl_BRW_Surprised` → `vroidBrowSurprised` |
| Eye + side | `Fcl_EYE_Joy_R` → `vroidEyeJoyR` |
| Mouth viseme | `Fcl_MTH_O` → `vroidMouthO` |
| Mouth skin | `Fcl_MTH_SkinFung_L` → `vroidMouthSkinFangL` |
| Teeth + index | `Fcl_HA_Fung2_Up` → `vroidTeethFang2Up` |
| Teeth short | `Fcl_HA_Short_Low` → `vroidTeethShortLow` |

## Dry-run checks

Use `dry_run_mapping(mapping, existing_names=...)` from [tools/remap_shapekeys.py](tools/remap_shapekeys.py). Returns `duplicates` and `conflicts`.

## Drivers / animation

After rename, run `scan_fcl_driver_refs()` from [tools/remap_shapekeys.py](tools/remap_shapekeys.py) to list drivers with `key_blocks` paths (flags stale `Fcl_*`).

VRoid `.vrm` / Unity exports use blend shape names from export time — plan a re-export after rename.

## Customization hooks

| User request | Adjustment |
|--------------|--------------|
| Keep abbreviations | `CATEGORY_MAP[cat] = cat` or `cap_first(cat.lower())` |
| `vroid_` snake prefix | Join with `_` instead of camelCase |
| No typo fix | Pass `fix_fung=False` to `convert_fcl_shape_key()` |
| Include all keys | Separate pass; do not use `Fcl_` guard |

## Related skills

- **blender-bone-remap** — armature bones, vertex groups, `.l`/`.r` at end
