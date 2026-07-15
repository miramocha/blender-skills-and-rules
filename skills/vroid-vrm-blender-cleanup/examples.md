# VRoid VRM Blender cleanup — examples

## Full pipeline — IDOG DIGI session (A–K)

Avatar already open in Blender (`Armature`, `Face`). User declared **female** for ARKit.

```python
import os

SKILL = os.path.join(
    os.path.expanduser("~"), ".cursor", "skills", "vroid-vrm-blender-cleanup", "tools"
)

exec(open(os.path.join(SKILL, "run_full_pipeline.py")).read())

# 1. Dry-run full pipeline
result = run_full_pipeline(
    armature_object_name="Armature",
    face_mesh_object_name="Face",
    body_type="female",
    dry_run=True,
)
# Present result["phases"] to user; stop for approval

# 2. Apply
result = run_full_pipeline(
    armature_object_name="Armature",
    face_mesh_object_name="Face",
    body_type="female",
    dry_run=False,
)
```

**Expected phase results (illustrative):**

| Phase | Result |
|-------|--------|
| A | VRM `bones_rename` — `J_Bip_C_Hips` → `Hips`, etc. |
| B | 23 materials stripped of `N00_*` prefix |
| C | ~36 texture datablocks + disk PNGs renamed |
| B rescan | 9 `.001` materials still carrying `N00_*` cleaned |
| D | Face shape keys 58 → 126 (ARKit female template) |
| E | All Face shape key values zeroed |
| B rescan (ARKit) | `.001` ARKit duplicate materials cleaned |
| C cleanup (ARKit) | 13 legacy `.001` textures merged → canonical images, datablocks purged |
| J | Rim from face ref; GI = 1.0; Toony = 0.95; Emissive black; Shading Shift unchanged |
| F | 57 `Fcl_*` → `vroid*`; 14 VRM expression binds updated |
| G | 78 bones remapped; hair mirror pass applied |
| H | 44 collider Empties + 22 `collider_display_name` entries |
| I | `Body (merged)` → `Body`; `Face.baked` → `Face` |

**Summary check** (`result["summary"]` after apply):

```python
{
    "fcl_shape_keys_remaining": 0,
    "n00_materials_remaining": 0,
    "j_bip_collider_objects_remaining": 0,
    "merged_baked_mesh_data_remaining": 0,
    "mtoon_materials_needing_sync": 0,
}
```

Remind user to **save the .blend** after Phase C and at end.

### Full pipeline from .vrm import

```python
result = run_full_pipeline(
    import_filepath=r"D:\MiraArt\MiraComms\digi-idog\IDOG DIGI_mesh.vrm",
    body_type="female",
    dry_run=False,
)
```

### Skip ARKit (no body_type)

```python
result = run_full_pipeline(skip_arkit=True, dry_run=False)
# Runs A → B → C → F → G → H → I; D/E skipped with reason
```

## Phase Import — load VRM then cleanup

List folder:

```python
import os

SKILL = os.path.join(
    os.path.expanduser("~"), ".cursor", "skills", "vroid-vrm-blender-cleanup", "tools"
)

exec(open(os.path.join(SKILL, "import_vrm.py")).read())
listing = list_vrm_files(r"D:\MiraArt\MiraComms\digi-idog")
```

Import single file (new empty blend):

```python
result = run_phase_import(
    filepath=r"D:\MiraArt\MiraComms\digi-idog\IDOG DIGI_mesh.vrm",
    new_file=True,
    dry_run=False,
)
armature_object_name = result["armature_object_name"]
face_mesh_object_name = result["face_mesh_object_name"]
```

Then continue **A → I** via `run_full_pipeline()` or individual phase scripts.

## Phase A — VRM bone rename (mandatory)

```python
exec(open(os.path.join(SKILL, "vrm_bones_rename.py")).read())
result = run_phase_a(armature_object_name="Armature", dry_run=False)
```

## Phase B — Material names

| Before | After |
|--------|-------|
| `N00_006_01_Shoes_01_CLOTH (Instance)` | `Shoes_01_CLOTH (Instance)` |
| `N00_000_01_Body_00_SKIN (Instance)` | `Body_00_SKIN (Instance)` |
| `MToon Outline (N00_000_Hair_00_HAIR_01 (Instance))` | `MToon Outline (Hair_00_HAIR_01 (Instance))` |

## Phase C — Material slugs (MToon textures)

| Material name | Slug |
|---------------|------|
| `Body_00_SKIN (Instance)` | `body_00_skin` |
| `MToon Outline (Face_00_SKIN (Instance))` | `outline_face_00_skin` |

### Per-material textures

Material `Body_00_SKIN (Instance)` after Phase B:

| Old image stem | Slot | New name |
|----------------|------|----------|
| `..._10` (shared lit + shade) | base + shade | `body_00_skin_base` |
| `..._11` | normal | `body_00_skin_normal` |

### Global placeholders

| Before | After |
|--------|-------|
| `Shader_NoneBlack` | `mtoon_none_black` |
| `Shader_NoneNormal.001` | `mtoon_none_normal` |
| `MatcapWarp` | `mtoon_matcap_warp` |
| `MatcapWarp_01` | `mtoon_matcap_warp_face` |

## Phase D — ARKit shape keys (Beyond Expressions)

Only when user said **male** or **female** and Beyond addon is ready:

```python
exec(open(os.path.join(SKILL, "transfer_arkit_shapekeys.py")).read())
result = run_phase_d(body_type="female", face_mesh_name="Face", dry_run=False)
```

| `body_type` | `vrm_shapekey_transfer_source` |
|-------------|-------------------------------|
| `female` | `VROID_Female_Face` |
| `male` | `VROID_Male_Face` |

## Phase E — Reset shape keys

```python
exec(open(os.path.join(SKILL, "reset_shape_keys.py")).read())
result = run_phase_e(mesh_name="Face", dry_run=False, phase_d_result=phase_d_result)
```

## Phase F — Fcl shape key rename

```python
SHAPEKEY = os.path.join(
    os.path.expanduser("~"), ".cursor", "skills", "vroid-shapekey-remap", "tools"
)
exec(open(os.path.join(SHAPEKEY, "remap_shapekeys.py")).read())
result = remap_object_fcl_keys("Face", fix_vrm_expression_binds=True)
```

| Before | After |
|--------|-------|
| `Fcl_BRW_Angry` | `vroidBrowAngry` |
| `Fcl_EYE_Close_L` | `vroidEyeCloseL` |

## Phase G + K + H — Bones, collections, and colliders

Orchestrator runs **G → K → H** automatically. Phase K assigns Hair / Body / Clothing bone collections after remap.

```python
BC_TOOLS = os.path.join(
    os.path.expanduser("~"), ".cursor", "skills", "blender-bone-collections", "tools"
)
exec(open(os.path.join(BC_TOOLS, "assign_bone_collections.py")).read())
audit = audit_bone_collections(armature_object_name="Armature")
result = apply_bone_collections(armature_object_name="Armature", dry_run=False)
# result["assigned"] -> {"Hair": 61, "Body": 61, "Clothing": 0}
```

See **blender-bone-remap** and **blender-bone-collections** examples for details.

## Phase I — Mesh datablock cleanup

```python
exec(open(os.path.join(SKILL, "clean_mesh_datablocks.py")).read())
audit = audit_mesh_datablock_names()
result = clean_mesh_datablock_names(dry_run=False)
```

| Before (mesh data) | After |
|------------------|-------|
| `Body (merged)` | `Body` |
| `Face.baked` | `Face` |
| `Hair (merged).001` | `Hair` |

## End summary — when gender was omitted

After A–C without ARKit:

```python
exec(open(os.path.join(SKILL, "check_beyond_expressions.py")).read())
beyond_check = beyond_expressions_ready()
# Ask: Beyond Expressions available? Apply ARKit? Male or female?
```

## MCP dry-run snippet (single phase)

```python
exec(open(os.path.join(SKILL, "clean_vroid_material_names.py")).read())
result = run_phase_b(dry_run=True)
```

```python
exec(open(os.path.join(SKILL, "rename_mtoon_textures.py")).read())
result = audit_mtoon_textures()
```
