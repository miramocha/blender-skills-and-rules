# ARKit / VRoid → MMD shape key reference

Canonical names and candidate sources. Runtime table lives in [tools/map_mmd_shapekeys.py](tools/map_mmd_shapekeys.py) (`CORE_MAPPINGS` / `EXTENDED_MAPPINGS`).

## Guarantee

- Never rename, delete, or overwrite ARKit / `vroid*` / `Fcl_*` keys.
- Only **create** MMD-named keys (bake from temporary mix).
- Skip if MMD name already exists.

## Animasa core names (exact unicode)

Copy-paste safe. Halfwidth wink name is intentional for VMD compatibility.

### Brow

```
真面目
困る
にこり
怒り
上
下
```

### Eye

```
まばたき
笑い
ウィンク
ウィンク２
ウィンク右
ｳｨﾝｸ２右
```

### Mouth

```
あ
い
う
え
お
にやり
```

### Core extras (still in `core` set)

```
はぅ
なごみ
びっくり
じと目
なぬ！
```

`え` is included even when old Animasa Miku lacked it — needed for lip-sync.

## Extended names (optional `set_scope="extended"`)

Hand-sculpt often required; script skips when no source resolves.

### Eye extras

```
下まぶた上げ
瞳大
瞳小
ハイライト消し
はぁと
星目
はちゅ目
恐ろしい子！
睨み
白目
```

### Mouth extras

```
▲
∧
ω
ω□
はんっ！
えー
口角上げ
口角下げ
ぺろっ
```

### Other

```
頬染め
青ざめ
```

## Core mapping (priority order)

Each row: try **source groups** in order. Within a group, first **fully present** candidate set wins. Weights default to `1.0` unless noted.

| MMD | VRoid / Fcl candidates (prefer) | ARKit fallback |
|-----|--------------------------------|----------------|
| `あ` | `vroidMouthA` / `Fcl_MTH_A` | `jawOpen` @ 1.0 |
| `い` | `vroidMouthI` / `Fcl_MTH_I` | `mouthStretchLeft`+`mouthStretchRight` @ 1.0 |
| `う` | `vroidMouthU` / `Fcl_MTH_U` | `mouthFunnel` @ 1.0, else `mouthPucker` |
| `え` | `vroidMouthE` / `Fcl_MTH_E` | `jawOpen`@0.5 + `mouthStretchLeft`+`Right`@0.7 |
| `お` | `vroidMouthO` / `Fcl_MTH_O` | `jawOpen`@0.7 + `mouthFunnel`@0.5 |
| `まばたき` | `vroidEyeClose` / `Fcl_EYE_Close`; else L+R close | `eyeBlinkLeft`+`eyeBlinkRight` |
| `ウィンク` | `vroidEyeCloseL` / `Fcl_EYE_Close_L` | `eyeBlinkLeft` |
| `ウィンク右` | `vroidEyeCloseR` / `Fcl_EYE_Close_R` | `eyeBlinkRight` |
| `ウィンク２` | `vroidEyeJoyL` / `Fcl_EYE_Joy_L`; else close L | `eyeBlinkLeft`+`eyeSquintLeft` |
| `ｳｨﾝｸ２右` | `vroidEyeJoyR` / `Fcl_EYE_Joy_R`; else close R | `eyeBlinkRight`+`eyeSquintRight` |
| `笑い` | `vroidEyeJoy` / `Fcl_EYE_Joy`; else `vroidAllJoy` | `mouthSmileLeft`+`mouthSmileRight` |
| `にやり` | `vroidMouthFun` / `Fcl_MTH_Fun`; else smile mouth | `mouthSmileLeft`+`mouthSmileRight` |
| `怒り` | `vroidBrowAngry` / `Fcl_BRW_Angry`; else `vroidAllAngry` | `browDownLeft`+`browDownRight` |
| `困る` | `vroidBrowSorrow` / `Fcl_BRW_Sorrow` | `browInnerUp` + `browDownLeft`+`Right`@0.4 |
| `にこり` | `vroidBrowFun` / `Fcl_BRW_Fun`; else `vroidBrowJoy` | `browOuterUpLeft`+`browOuterUpRight`@0.5 + smiles@0.3 |
| `真面目` | `vroidBrowAngry`@0.5 (approx) / `Fcl_BRW_Angry`@0.5 | `browDownLeft`+`Right`@0.6 |
| `上` | (none typical) | `browOuterUpLeft`+`browOuterUpRight` |
| `下` | (none typical) | `browDownLeft`+`browDownRight` |
| `びっくり` | `vroidEyeSurprised` / `Fcl_EYE_Surprised`; else brow surprised | `eyeWideLeft`+`eyeWideRight` + `browInnerUp` |
| `はぅ` | `vroidEyeSpread` / `Fcl_EYE_Spread` | `eyeWideLeft`+`eyeWideRight`@0.7 |
| `なごみ` | `vroidEyeJoy`@0.5 (soft) | `eyeSquintLeft`+`eyeSquintRight` |
| `じと目` | (skip if no custom) | `eyeSquintLeft`+`eyeSquintRight`@0.8 + `browDown*`@0.3 |
| `なぬ！` | `vroidEyeSurprised` + `vroidBrowSurprised` | `eyeWide*` + `browInnerUp` + `browOuterUp*` |

## ARKit 52 blend shape names

Lower camelCase as transferred by Beyond Expressions / Perfect Sync:

```
browDownLeft
browDownRight
browInnerUp
browOuterUpLeft
browOuterUpRight
cheekPuff
cheekSquintLeft
cheekSquintRight
eyeBlinkLeft
eyeBlinkRight
eyeLookDownLeft
eyeLookDownRight
eyeLookInLeft
eyeLookInRight
eyeLookOutLeft
eyeLookOutRight
eyeLookUpLeft
eyeLookUpRight
eyeSquintLeft
eyeSquintRight
eyeWideLeft
eyeWideRight
jawForward
jawLeft
jawOpen
jawRight
mouthClose
mouthDimpleLeft
mouthDimpleRight
mouthFrownLeft
mouthFrownRight
mouthFunnel
mouthLeft
mouthLowerDownLeft
mouthLowerDownRight
mouthPressLeft
mouthPressRight
mouthPucker
mouthRight
mouthRollLower
mouthRollUpper
mouthShrugLower
mouthShrugUpper
mouthSmileLeft
mouthSmileRight
mouthStretchLeft
mouthStretchRight
mouthUpperUpLeft
mouthUpperUpRight
noseSneerLeft
noseSneerRight
tongueOut
```

## Scene audit key

After apply, script stores `scene["mmd_shapekey_map"]`:

```python
{
  "あ": [{"source": "vroidMouthA", "weight": 1.0}],
  "まばたき": [
    {"source": "eyeBlinkLeft", "weight": 1.0},
    {"source": "eyeBlinkRight", "weight": 1.0},
  ],
  ...
}
```

## Related skills

- [vroid-shapekey-remap](../vroid-shapekey-remap/SKILL.md) — Phase F `Fcl_*` → `vroid*`
- [vroid-vrm-blender-cleanup](../vroid-vrm-blender-cleanup/SKILL.md) — Phase D ARKit transfer
