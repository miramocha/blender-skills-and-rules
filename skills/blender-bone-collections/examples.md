# Bone collections — examples

## Standalone audit + apply

```python
import os

SKILL_TOOLS = r"D:\MiraGameDev\blender-skills-and-rules\skills\blender-bone-collections\tools"
exec(open(os.path.join(SKILL_TOOLS, "assign_bone_collections.py"), encoding="utf-8").read())

audit = audit_bone_collections(armature_object_name="Armature")
# audit["planned"] -> counts per Hair / Body / Clothing

apply = apply_bone_collections(armature_object_name="Armature", dry_run=False)
```

## Via full cleanup pipeline (Phase K)

```python
result = run_full_pipeline(skip_arkit=True, dry_run=False)
k = result["phases"]["K"]
# k["assigned"] -> {"Hair": 39, "Body": 78, "Clothing": 5}
```

## Sample planned split (VRoid pre-remap)

| Collection | Examples |
|------------|----------|
| Hair | `J_Sec_Hair1_01`, `J_Sec_Hair2_05` |
| Body | `J_Bip_C_Hips`, `J_Sec_L_Bust1`, `J_Adj_L_FaceEye` |
| Clothing | `hood.1`, `hoodString.2.l` (after remap) |

## Sample planned split (post-remap)

| Collection | Examples |
|------------|----------|
| Hair | `hair01.1.l`, `hair07.7.end.r` |
| Body | `hips`, `upperLeg.l`, `bust.2.l` |
| Clothing | `hood.1`, `hoodString.2.end.l` |
