# Bone remap examples (VRoid-style rig)

## Hair strand 06 (center, 3 links)

| Old | New |
|-----|-----|
| `Hair1_06` | `hair06.1` |
| `Hair2_06` | `hair06.2` |
| `Hair3_06` | `hair06.3` |
| `Hair3_06_end` | `hair06.3.end` |

## Hair strand 07 (side, long chain)

| Old | New |
|-----|-----|
| `Hair1_07_L` | `hair07.1.l` |
| `Hair7_07_L` | `hair07.7.l` |
| `Hair7_07_end_L` | `hair07.7.end.l` |

After side-at-end fix: same names (already correct if mapped from `hair07l.7` → `hair07.7.l`).

## Mirror strands 01 + 03

| Old (physical strand) | New (logical pair) |
|-----------------------|-------------------|
| `Hair1_01` | `hair01.1.l` |
| `Hair1_03` | `hair01.1.r` |
| `Hair4_01_end` | `hair01.4.end.l` |
| `Hair4_03_end` | `hair01.4.end.r` |

Strand ids `03` and `04` disappear from names; pair is encoded in `.l`/`.r`.

## Body samples

| Old | New |
|-----|-----|
| `UpperLeg_L` | `upperLeg.l` |
| `FaceEye_R` | `faceEye.r` |
| `Thumb2_L` | `thumb.2.l` |
| `Bust2_end_L` | `bust.2.end.l` |
| `HoodString2_end_01_L` | `hoodString.2.end.l` |

## Phased session summary

1. Hair VRoid names → `hair{strand}.{link}`
2. Side embedded in strand → `hair07.7.l`
3. Mirror pairs 01/03, 02/04 → shared `hair01.*` / `hair02.*` + `.l`/`.r`
4. Body 70 bones → lowercase + `.l`/`.r`
5. Skirt armature — pending separate pass

## VRM collider Empties (after `J_Bip_*` bone remap)

| Old object / `collider_display_name` | New |
|----------------------------------------|-----|
| `J_Bip_C_Head_collider_0` | `head.collider.0` |
| `J_Bip_C_Head_collider_0.1` | `head.collider.0.1` |
| `J_Bip_L_UpperArm_collider_1` | `upperArm.l.collider.1` |
| `J_Bip_R_LowerArm_collider_3.1` | `lowerArm.r.collider.3.1` |

Also updates `spring_bone1.collider_groups[*].vrm_name` prefix (uuid suffix kept).

```python
exec(open(SKILL_TOOLS + "/rename_vrm_colliders.py").read())
apply_vrm_collider_renames(armature_object_name="Armature", dry_run=False)
```

`_hairends` on hair meshes: not renamed with bones; optional `hair.ends` if user requests.
