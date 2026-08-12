# MMD PMX → VRM1 reference

## Operators

| Op | Role |
|----|------|
| `bpy.ops.mmd_tools.import_model` | Import `.pmx` / `.pmd` |
| `bpy.ops.vrm.assign_vrm1_humanoid_human_bones_automatically` | Auto humanoid from bone names / heuristics |
| `bpy.ops.vrm.assign_vrm1_expressions_from_mmd` | Bind Animasa MMD morphs → VRM1 presets |

Enable VRM1 without creating bones:

```python
armature.data.vrm_addon_extension.spec_version = "1.0"
```

Humanoid slot write:

```python
hb = armature.data.vrm_addon_extension.vrm1.humanoid.human_bones
hb.hips.node.bone_name = "下半身"
```

## mmd_tools hierarchy

After import:

- Root **Empty** with `mmd_type == "ROOT"` and `mmd_root`
- Child **Armature** (`mmd_type == "ARMATURE"`)
- Mesh objects under root and/or armature

Skill detects via `find_mmd_hierarchy()` on newly created objects.

## Default import kwargs

| Prop | Default in skill | Notes |
|------|------------------|-------|
| `scale` | `0.08` | mmd_tools default ≈ 0.08 |
| `types` | all: MESH, ARMATURE, PHYSICS, DISPLAY, MORPHS | Flag set |
| `clean_model` | `True` | |
| `rename_bones` | `True` | L/R suffix for Blender; map covers JP + EN + suffixes |
| `fix_bone_order` | `True` | |

## MMD → VRM1 humanoid (fallback map)

Keep bone **names**; only fill empty VRM1 slots. Prefer auto-assign first.

| VRM1 slot | JP candidates | EN / mmd_tools L/R candidates (examples) |
|-----------|---------------|------------------------------------------|
| `hips` | `下半身` | `Lower Body`, `LowerBody`, `Hip`, `Hips` |
| `spine` | `上半身` | `Upper Body`, `UpperBody`, `Spine` |
| `chest` | `上半身2`, `上半身２` | `Upper Body 2`, `UpperBody2`, `Chest` |
| `upper_chest` | `上半身3`, `上半身３` | `Upper Body 3`, `UpperBody3` |
| `neck` | `首` | `Neck` |
| `head` | `頭` | `Head` |
| `left_eye` | `左目`, `目.L` | `Eye_L`, `Eye.L`, `Left Eye` |
| `right_eye` | `右目`, `目.R` | `Eye_R`, `Eye.R`, `Right Eye` |
| `jaw` | `あご`, `顎` | `Jaw` |
| `left_shoulder` | `左肩`, `肩.L` | `Shoulder_L`, `Shoulder.L` |
| `left_upper_arm` | `左腕`, `腕.L` | `Arm_L`, `Arm.L` |
| `left_lower_arm` | `左ひじ`, `ひじ.L` | `Elbow_L`, `Elbow.L` |
| `left_hand` | `左手首`, `手首.L` | `Wrist_L`, `Wrist.L`, `Hand_L` |
| `right_shoulder` | `右肩`, `肩.R` | `Shoulder_R`, `Shoulder.R` |
| `right_upper_arm` | `右腕`, `腕.R` | `Arm_R`, `Arm.R` |
| `right_lower_arm` | `右ひじ`, `ひじ.R` | `Elbow_R`, `Elbow.R` |
| `right_hand` | `右手首`, `手首.R` | `Wrist_R`, `Wrist.R`, `Hand_R` |
| `left_upper_leg` | `左足`, `足.L` | `Leg_L`, `Leg.L` |
| `left_lower_leg` | `左ひざ`, `ひざ.L` | `Knee_L`, `Knee.L` |
| `left_foot` | `左足首`, `足首.L` | `Ankle_L`, `Ankle.L`, `Foot_L` |
| `left_toes` | `左つま先`, `つま先.L` | `Toe_L`, `Toe.L`, `Toes_L` |
| `right_upper_leg` | `右足`, `足.R` | `Leg_R`, `Leg.R` |
| `right_lower_leg` | `右ひざ`, `ひざ.R` | `Knee_R`, `Knee.R` |
| `right_foot` | `右足首`, `足首.R` | `Ankle_R`, `Ankle.R`, `Foot_R` |
| `right_toes` | `右つま先`, `つま先.R` | `Toe_R`, `Toe.R`, `Toes_R` |

Finger slots (optional): classic `左親指０` **or** mmd_tools `親指０.L` / `人指１.L` / … → VRM thumb/index/middle/ring/little. See `FINGER_MAP` in [mmd_vrm1_bone_map.py](tools/mmd_vrm1_bone_map.py).

**L/R rename:** With mmd_tools `rename_bones=True` (skill default), paired bones become JP base + `.L`/`.R` (e.g. `腕.L`), not `左腕`. Map covers both.

**Hips note:** Prefer `下半身` over `センター`. `センター` is MMD root motion — only used if no lower-body bone matches.

## Required VRM1 humanoid slots

Audit fails readiness when any of these are empty:

`hips`, `spine`, `head`, `left_upper_arm`, `left_lower_arm`, `left_hand`, `right_upper_arm`, `right_lower_arm`, `right_hand`, `left_upper_leg`, `left_lower_leg`, `left_foot`, `right_upper_leg`, `right_lower_leg`, `right_foot`

## Expressions vs shape keys

`bpy.ops.vrm.assign_vrm1_expressions_from_mmd` only writes VRM1 **expression binds** (pointers to existing shape keys). It must not rename or delete MMD morph names.

Skill verifies with a before/after snapshot of all mesh shape-key names under the imported hierarchy (`shapekeys_untouched` in setup result).

## Meta stub defaults

| Field | Default |
|-------|---------|
| `vrm_name` | PMX file stem or mmd_root name |
| `version` | `1.0.0` |
| `authors` | one entry from root name / `"Unknown"` |
| `avatar_permission` | `onlyAuthor` |
| `commercial_usage` | `personalNonProfit` |
| `credit_notation` | `required` |
| `allow_redistribution` | `False` |
| `modification` | `prohibited` |

User should edit license fields before any public export.

## T-pose

After humanoid slots are filled, skill runs `bpy.ops.vrm.make_estimated_humanoid_t_pose` and sets `vrm1.humanoid.pose = "currentPose"`. Rest pose stays MMD (often A-ish); **Pose Mode** becomes VRM T. Export uses current pose.

## Materials

Skill sets `material.vrm_addon_extension.mtoon1.enabled = True` on materials used by imported meshes, stamps **Lit Color** (`pbr_metallic_roughness.base_color_factor`) to **white** `(1,1,1,1)`, and sets **alpha mode** to **cutout** (`alpha_mode = "MASK"`). Enabling MToon1 alone often leaves Lit black on MMD mats even when `mmd_material.diffuse_color` is white. No theme compile — use [mtoon-material-sync](../mtoon-material-sync/SKILL.md) later if needed.

## Caveats

- Non-standard PMX bone names → auto + fallback both miss slots; assign manually in VRM Add-on UI.
- Physics import creates rigid bodies; spring bones are **not** converted here (`assign_spring_bone1_from_mmd` exists on the add-on but is out of this skill’s default path).
- Scale `0.08` is typical MMD→Blender meters; override per model.
