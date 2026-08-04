# ARKit / VRoid → MMD examples

## Typical Face mesh after Phase D + F

Sources present (unchanged by this skill):

| Kind | Examples |
|------|----------|
| VRoid | `vroidMouthA`, `vroidEyeCloseL`, `vroidBrowAngry`, … |
| ARKit | `eyeBlinkLeft`, `jawOpen`, `mouthSmileLeft`, … |
| Basis | `Basis` |

After `create_mmd_shape_keys("Face", dry_run=False)` — **added** (examples):

| MMD | Likely sources |
|-----|----------------|
| `あ` | `vroidMouthA` |
| `い` | `vroidMouthI` |
| `う` | `vroidMouthU` |
| `え` | `vroidMouthE` |
| `お` | `vroidMouthO` |
| `まばたき` | `vroidEyeClose` or L+R / ARKit blinks |
| `ウィンク` | `vroidEyeCloseL` |
| `ウィンク右` | `vroidEyeCloseR` |
| `ｳｨﾝｸ２右` | `vroidEyeJoyR` or `eyeBlinkRight`+`eyeSquintRight` |
| `笑い` | `vroidEyeJoy` |
| `怒り` | `vroidBrowAngry` |

ARKit / VRoid rows above still exist with same names.

## Dry-run then apply (MCP)

```python
import os

SKILL_TOOLS = os.path.join(
    r"D:\MiraGameDev\blender-skills-and-rules",
    "skills",
    "arkit-vroid-mmd-shapekeys",
    "tools",
)
exec(open(os.path.join(SKILL_TOOLS, "map_mmd_shapekeys.py"), encoding="utf-8").read())

dry = create_mmd_shape_keys("Face", dry_run=True, set_scope="core")
print(dry["report"]["will_create_count"], dry["report"]["missing_sources"])

# after approval:
out = create_mmd_shape_keys("Face", dry_run=False, set_scope="core")
assert out.get("sources_untouched") is True
```

## Fcl_* still present (before Phase F)

Resolver accepts both:

- `vroidMouthA` **or** `Fcl_MTH_A` → `あ`
- `vroidEyeClose_L` form is `vroidEyeCloseL` / `Fcl_EYE_Close_L` → `ウィンク`

Prefer running **vroid-shapekey-remap** first so VRoid names are consistent; Fcl fallback still works.

## Extended scope

```python
result = create_mmd_shape_keys("Face", dry_run=True, set_scope="extended")
# ぺろっ ← tongueOut; 口角下げ ← mouthFrown*; ω / はぁと often in unmapped_no_candidates
```

## Skip when MMD already exists

If mesh already has `まばたき`, dry-run lists it under `existing_mmd` and does not recreate.
