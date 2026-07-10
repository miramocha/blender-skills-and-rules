---
name: blender-bone-remap
description: >-
  Remaps and renames Blender armature bones (especially VRoid/VRM rigs) to a
  consistent lowercase convention with .l/.r mirror suffixes, updates vertex
  groups and animation paths, and handles hair strand mirror pairs. Use when the
  user asks to rename, clean up, or standardize bones, vertex groups, rig
  naming, VRoid hair bones, or symmetry/mirror bone pairs in Blender.
---

# Blender bone remap (VRoid / custom rigs)

## When to use

- Renaming bones for readability or Blender X-Axis Mirror / Symmetrize
- Migrating VRoid-style names (`Hair1_06`, `UpperLeg_L`, `J_Sec_*`) to a project standard
- Pairing mirrored strands or limbs under shared base names + `.l` / `.r`

Requires a **connected Blender MCP** (`execute_blender_code`) unless the user only wants a mapping plan.

**Umbrella pipeline:** this skill covers **Phase G** (custom bone remap) and **Phase H** (collider rename) of [vroid-vrm-blender-cleanup](../vroid-vrm-blender-cleanup/SKILL.md) (`run_full_pipeline()` — Phase G requires umbrella Phase A first).

## Before changing anything

1. **Confirm scope** with the user (hair only, main armature, skirt armature, all meshes).
2. **Inspect** the armature: bone list, parents, which meshes have matching vertex groups and non-zero weights.
3. **Dry-run** the full `old → new` map; report duplicates and unmapped bones.
4. **Save** or remind the user to save before applying.

Use AskQuestion when rules are ambiguous (abbreviation expansion, mirror strand pairs, `.l` vs `.L`, `_hairends` handling).

## Naming standard (default)

| Category | Pattern | Examples |
|----------|---------|----------|
| Center (no side) | `{part}` | `root`, `hips`, `spine`, `chest`, `upperChest`, `neck`, `head` |
| Limb / single bone | `{part}.{side}` | `upperLeg.l`, `shoulder.r`, `hand.l` |
| Digit chains | `{finger}.{link}.{side}` | `thumb.2.l`, `index.3.r` |
| Hair (strand-first) | `hair{strand}.{link}.{side}` | `hair06.1.l`, `hair07.7.r` |
| Hair (center strand) | `hair{strand}.{link}` | `hair05.1`, `hair06.3.end` |
| Hair tip bone | `...end` before side | `hair01.4.end.l`, `hair07.7.end.r` |
| Bust / props | `{name}.{n}.{side}` or `.end` | `bust.2.end.l`, `hoodString.2.l` |

**Mirror rule:** Blender symmetrize expects the **same base name** with `.l` / `.r` as the **last** suffix (after `.end` if present).

**Wrong for mirror:** `hair07l.7` (side embedded in strand id)  
**Right:** `hair07.7.l` ↔ `hair07.7.r`

**Hair mirror pairs (example):** physical strands 01↔03 and 02↔04 share one logical strand id:

- Strand 01 bones → `hair01.{link}.l`
- Strand 03 bones → `hair01.{link}.r` (not `hair03.*`)

## VRoid hair: parse old names

Old pattern: `Hair{segment}_{strand}` or `Hair{segment}_{strand}_end` or `Hair{seg}_{strand}_end_{L|R}`.

- First number = link along chain (1 = near head)
- After `_` = strand id (`06`, `07_L`, …)
- Remap to `hair{strand}.{link}` with side at end

Common typo fix when user asks: `Fung` → `Fang` (shape keys; separate from bones).

## VRoid body: parse old names

| Old | New |
|-----|-----|
| `UpperLeg_L` | `upperLeg.l` |
| `Thumb2_R` | `thumb.2.r` |
| `Bust2_end_L` | `bust.2.end.l` |
| `HoodString2_end_01_L` | `hoodString.2.end.l` |
| `Hood_01` | `hood.1` |

PascalCase + `_L`/`_R` → camelCase + `.{side}` at end.

## What must be updated together

| Data | Match bone names? | Notes |
|------|-------------------|--------|
| Armature bones | Yes | Two-pass via `__tmp__{old}` if collisions possible |
| Vertex groups | Yes (same string as bone) | Often auto-syncs on bone rename in recent Blender; verify |
| Action F-Curves | `pose.bones["Name"]` paths | Old `J_Sec_*` / `J_Bip_*` curves won't auto-fix |
| Constraint subtargets | Yes | Rare on hair; check pose constraints |
| Shape keys | No | Unless explicitly bone-driven |

Rename **only groups with weights** if user wants minimal diff; rename **all** matching groups on deforming meshes for consistency.

**Separate armatures** (e.g. `Skirt.Armature`) need their own map — do not assume main-armature renames apply.

## Workflow

```
Progress:
- [ ] 1. List bones + categorize (hair / body / prop / other armature)
- [ ] 2. Agree naming rules + mirror pairs with user
- [ ] 3. Build mapping dict; dry-run (duplicates, unmapped)
- [ ] 4. Apply bones (temp rename → final)
- [ ] 5. Apply vertex groups on scoped meshes
- [ ] 6. Patch F-Curves + constraint subtargets
- [ ] 7. Rename VRM collider Empties + sync `spring_bone1` metadata (after `J_Bip_*` bone remap)
- [ ] 8. Verify (mirror pairs, weights, pose test, collider audit)
```

### Apply order (bones)

1. Build complete `mapping: old_name → new_name`
2. Pass 1: `bone.name = f"__tmp__{old}"` for all keys
3. Pass 2: `bone.name = new` from temp
4. Rename vertex groups on each mesh in scope
5. Replace `pose.bones["old"]` in all `bpy.data.actions` fcurves

### Step 7 — VRM collider names (after `J_Bip_*` bone remap)

VRoid imports spawn **Empty** collider helpers (`J_Bip_C_Head_collider_0`, …) and store the same strings in VRM1 `spring_bone1.collider_display_name`. Bone rename does **not** update these. `parent_bone` is usually already correct; **object names and display names are not.**

**Audit:**

```python
import os

SKILL_TOOLS = r".../skills/blender-bone-remap/tools"
exec(open(os.path.join(SKILL_TOOLS, "rename_vrm_colliders.py")).read())
audit = audit_vrm_colliders(armature_object_name="Armature")
```

**Apply** (renames Empties + `collider_display_name` + `vrm_name` prefix; keeps uuid suffix):

```python
result = apply_vrm_collider_renames(armature_object_name="Armature", dry_run=False)
```

Naming: `J_Bip_C_Head_collider_0` → `head.collider.0`, `J_Bip_L_UpperArm_collider_1.1` → `upperArm.l.collider.1.1`.

VRM0 `secondary_animation` collider groups use **bone pointers** only — usually already updated by bone remap. No object-name sync needed there.

Pass custom `bone_mapping={"J_Bip_C_Head": "head", ...}` when defaults do not match your rig.

### Verify

- No bones left matching `^[A-Z]` or `_(L|R)$` (if full cleanup was requested)
- Every `.l` bone has matching `.r` partner where expected
- Sample mesh: weighted groups still exist under new names
- Pose mode: move `.l` bone with X-Axis Mirror enabled

## Phased rollout (recommended)

1. **Hair** on main armature + hair meshes
2. **Body** on main armature + body/clothes meshes
3. **Secondary armatures** (skirt, accessories)
4. **Animation** — retarget or drop stale `J_Sec_*` actions

## Custom groups

Non-bone groups (e.g. `_hairends`) are **not** updated by bone rename. Ask before renaming; map explicitly if needed.

## Utility script

For apply logic and parsers, read and run (via MCP) [tools/remap_bones.py](tools/remap_bones.py). Armature audit: [tools/audit_vroid_armature.py](tools/audit_vroid_armature.py).

```python
# Minimal MCP usage pattern:
# SKILL_TOOLS = r".../skills/blender-bone-remap/tools"
# exec(open(SKILL_TOOLS + "/remap_bones.py").read())
# mapping = build_vroid_hair_mapping(arm.data) | build_body_mapping(arm.data)
# apply_mapping(mapping, armature_object_name='Armature')
```

## Utility tools

| Tool | Entrypoints |
|------|-------------|
| [remap_bones.py](tools/remap_bones.py) | `build_vroid_hair_mapping()`, `build_body_mapping()`, `apply_mapping()`, `dry_run_mapping()` |
| [audit_vroid_armature.py](tools/audit_vroid_armature.py) | `audit_vroid_armature()`, `scan_mesh_vertex_groups()` |
| [rename_vrm_colliders.py](tools/rename_vrm_colliders.py) | `audit_vrm_colliders()`, `apply_vrm_collider_renames()`, `convert_collider_object_name()` |

## Additional reference

- Full convention tables and edge cases: [reference.md](reference.md)
- Worked examples from a VRoid rig: [examples.md](examples.md)

## Out of scope unless asked

- Re-parenting bones, changing roll/rest pose, re-weighting meshes
- VRM humanoid slot reassignment (usually follows bone rename automatically)
- Auto-fixing all historical actions without user confirmation
