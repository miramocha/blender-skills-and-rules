# Bone remap reference

## Hair converter (VRoid → standard)

See [tools/remap_bones.py](tools/remap_bones.py):

| Function | Purpose |
|----------|---------|
| `convert_vroid_hair_name()` | `Hair1_06` → `hair06.1` style |
| `build_vroid_hair_mapping()` | All `Hair*` bones on armature |
| `norm_hair_strand()` | Strand id normalization |

## Side suffix at end (fix `hair07l.7`)

| Function | Purpose |
|----------|---------|
| `side_suffix_at_end()` | `hair07l.7` → `hair07.7.l` |
| `build_hair_mirror_mapping()` | Strand pairs 01↔03, 02↔04 |

Strand 03 bones become `hair01.{link}.r`; strand 01 becomes `hair01.{link}.l`. Same for 02↔04 on `hair02.*`.

## Body converter (PascalCase + _L/_R)

See [tools/remap_bones.py](tools/remap_bones.py):

| Function | Purpose |
|----------|---------|
| `convert_body_bone_name()` | Single bone: bust, fingers, hood, limbs |
| `build_body_mapping()` | All non-hair bones on armature |
| `pascal_to_camel()` | Shared helper |

Center bones: `Root`, `Hips`, `Spine`, `Chest`, `UpperChest`, `Neck`, `Head`.
## Blender mirror troubleshooting

| Symptom | Likely cause |
|---------|----------------|
| Mirror ignores paired bone | Side not final suffix; use `.l`/`.r` at end |
| Wrong strand moves | Strand id differs between pairs; unify base (`hair01` not `hair01` vs `hair03`) |
| Mesh does not follow | Vertex group name ≠ bone name |
| Pose action broken | F-Curves still reference old or `J_Sec_*` paths |

Blender may accept `.L`/`.R` (uppercase) in some tools; ask user if lowercase fails.

## Meshes to scan

See [tools/audit_vroid_armature.py](tools/audit_vroid_armature.py):

| Function | Purpose |
|----------|---------|
| `scan_mesh_vertex_groups()` | Vertex groups on armature-bound meshes; flags stale `J_*` / `Hair*` names |
| `audit_vroid_armature()` | Prefix counts, `J_Sec_*` categories, bust weights — **no gender inference** |

Report: `bone_named_vgs`, count with non-zero weights, stale groups (old names after remap).
## Separate armatures

Check `obj.modifiers` type `ARMATURE` — each armature needs its own mapping. Skirt rigs often keep `SkirtSide0_01_L` until explicitly remapped.

## VRoid / VRM export bone prefixes (pre-remap)

Observed on VRoid Studio `.vrm` imports (2026-06). **Prefix family is identical across male and female models; bone count and `J_Sec_*` / `J_Opt_*` content vary by outfit, hair, and accessories — not by gender.**

| Prefix | Role | Typical count |
|--------|------|---------------|
| `Root` | Root bone (no `J_`) | 1 |
| `J_Bip_` | Humanoid biped (hips, spine, limbs, fingers, head) | 52 (stable) |
| `J_Sec_` | Secondary / spring-bone physics (hair, bust, skirt, tops) | varies (e.g. 14–66) |
| `J_Adj_` | Face adjust (`J_Adj_L_FaceEye`, `J_Adj_R_FaceEye`) | 2 |
| `J_Opt_` | Optional accessory chain (e.g. `J_Opt_C_CatTail1_01` … `_end_01`) | 0+ |

### Scanned models (side-by-side)

Three VRoid `.vrm` imports inspected in Blender MCP sessions. Same prefix scheme on all; differences are customization.

| | Male (coat + long hair) | Female (cat-tail accessory) | Female (hood + heavy hair) |
|--|-------------------------|----------------------------|----------------------------|
| **Total bones** | 121 | 78 | 111 |
| **`J_Bip_`** | 52 | 52 | 52 |
| **`J_Sec_`** | 66 | 14 | 56 |
| **`J_Adj_`** | 2 | 2 | 2 |
| **`J_Opt_`** | 0 | 9 | 0 |
| **Hair bones** | 48 | 10 | 39 |
| **Bust bones** | 4 (`Bust1`/`Bust2` L+R) | 4 (no `_end`) | 6 (includes `Bust2_end`) |
| **Bust VG weights on `Body`** | Yes — e.g. 101 verts on `J_Sec_L_Bust1` | (not scanned) | (not scanned) |
| **Outfit / accessory extras** | `J_Sec_*_CoatSkirt*` (14) | `J_Opt_C_CatTail*` (9) | `J_Sec_*_Hood*`, hood strings |
| **Sample `J_Sec_*` categories** | `Hair1/2/3`, `CoatSkirtBack/Front/Side*` | `Hair1–3`, `Bust*` | `Hair*`, `Bust*`, `Hood*` |

**Takeaway:** `J_Bip_` count is fixed at 52. Everything else scales with hair complexity, clothing physics, and accessories. Male model still ships `J_Sec_L_Bust1` … `J_Sec_R_Bust2` with non-zero chest weights.

Side token is **embedded** in VRoid names: `_L_`, `_R_`, `_C_` (not `.l`/`.r` suffix at end).

Examples:

- Humanoid: `J_Bip_C_Hips`, `J_Bip_L_UpperArm`, `J_Bip_R_Thumb3`
- Bust: `J_Sec_L_Bust1`, `J_Sec_R_Bust2`, optional `J_Sec_L_Bust2_end`
- Hair: `J_Sec_Hair{link}_{strand}`, e.g. `J_Sec_Hair1_01`, `J_Sec_Hair4_01_end`
- Hood / clothing: `J_Sec_C_Hood_01`, `J_Sec_L_HoodString2_end_01`, `J_Sec_L_TopsUpperArmInside_01`
- Accessory: `J_Opt_C_CatTail8_end_01`

After **blender-bone-remap**, `J_*` is stripped — e.g. `J_Sec_L_Bust1` → `Bust1_L`, `J_Bip_C_Hips` → `Hips`.

## Can VRoid base-model gender be inferred from bone prefix?

**No — not from prefix alone, and not reliably from bone names either.**

- VRoid Studio uses the **same skeleton structure for male and female** base models (`男女とも同じ構造`). Humanoid table includes `J_Sec_L_Bust1` … `J_Sec_R_Bust2` for both.
- `J_Bip_` / `J_Sec_` / `J_Adj_` / `J_Opt_` label **bone category**, not sex.
- **`Bust*` bones exist on male exports too** — they drive chest physics when used; absence/presence is not a gender flag. Male scan: all four bust bones had non-zero weights on `Body` (~101 verts each on `Bust1` L/R).
- **`J_Sec_*` extras** (skirt, hood, hair count) reflect **avatar customization**, not base gender.
- **VRM meta** (`VRMC_vrm.meta`) has no standard `gender` field — only title, authors, license, usage permissions.

**Reliable gender signals (outside bone prefix):**

- User / pipeline metadata (VRoid Studio project, platform upload UI — not embedded in VRM spec)
- Mesh silhouette and blend shapes (body morphs)
- Material / outfit naming (weak, outfit-specific)

**Heuristic script (low confidence):** [tools/audit_vroid_armature.py](tools/audit_vroid_armature.py) — inventory only; do **not** emit male/female from prefix or `Bust*` alone.
