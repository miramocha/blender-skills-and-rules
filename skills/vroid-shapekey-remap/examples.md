# VRoid shape key examples (`face.main`)

57 `Fcl_*` keys were renamed; 79 other keys left unchanged (ARKit, custom, Japanese).

## All / brow / eye

| Old | New |
|-----|-----|
| `Fcl_ALL_Neutral` | `vroidAllNeutral` |
| `Fcl_ALL_Angry` | `vroidAllAngry` |
| `Fcl_BRW_Joy` | `vroidBrowJoy` |
| `Fcl_EYE_Natural` | `vroidEyeNatural` |
| `Fcl_EYE_Close_L` | `vroidEyeCloseL` |
| `Fcl_EYE_Close_R` | `vroidEyeCloseR` |
| `Fcl_EYE_Iris_Hide` | `vroidEyeIrisHide` |

## Mouth

| Old | New |
|-----|-----|
| `Fcl_MTH_Close` | `vroidMouthClose` |
| `Fcl_MTH_A` | `vroidMouthA` |
| `Fcl_MTH_SkinFung` | `vroidMouthSkinFang` |
| `Fcl_MTH_SkinFung_R` | `vroidMouthSkinFangR` |

## Teeth (HA → Teeth, Fung → Fang)

| Old | New |
|-----|-----|
| `Fcl_HA_Hide` | `vroidTeethHide` |
| `Fcl_HA_Fung1` | `vroidTeethFang1` |
| `Fcl_HA_Fung1_Low` | `vroidTeethFang1Low` |
| `Fcl_HA_Short_Up` | `vroidTeethShortUp` |

## Left unchanged (examples)

| Name | Reason |
|------|--------|
| `Basis` | Rest basis |
| `browInnerUp` | ARKit / custom |
| `eyeBlinkLeft` | ARKit |
| `_mouthPress+CatMouth` | Custom combo |
| `あ`, `まばたき` | Japanese / legacy |

## MCP one-liner pattern

```python
import os
SKILL_TOOLS = r".../skills/vroid-shapekey-remap/tools"
exec(open(os.path.join(SKILL_TOOLS, "remap_shapekeys.py")).read())
result = remap_object_fcl_keys("Face", dry_run_only=True)
# after approval:
result = remap_object_fcl_keys(
    "Face",
    dry_run_only=False,
    fix_vrm_expression_binds=True,
    armature_object_name="Armature",
)
```

## VRM expression bind fix (after rename)

VRM0 viseme/expression binds keep `Fcl_*` in bind `index` until step 5 runs:

| Expression | Old bind `index` | New |
|------------|------------------|-----|
| `Neutral` | `Fcl_ALL_Neutral` | `vroidAllNeutral` |
| `A` | `Fcl_MTH_A` | `vroidMouthA` |
| `Blink_L` | `Fcl_EYE_Close_L` | `vroidEyeCloseL` |
