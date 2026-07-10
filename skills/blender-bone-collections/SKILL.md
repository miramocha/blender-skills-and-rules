---
name: blender-bone-collections
description: >-
  Assign Blender armature bones to Hair, Body, and Clothing bone collections
  using name rules and optional mesh weight hints. Pipeline Phase K in
  vroid-vrm-blender-cleanup. Use when organizing rig layers, bone collection
  filters, or categorizing VRoid/remapped bones for animation workflow.
---

# Blender bone collections (Hair / Body / Clothing)

## When to use

- Organize a VRoid/VRM armature into **Hair**, **Body**, **Clothing** bone collections
- After bone rename/remap (Phase G) so names are stable
- Before animation or export when collection visibility matters

Requires **Blender MCP** (`execute_blender_code`) unless scripts run in Scripting workspace.

Related: [blender-bone-remap](../blender-bone-remap/SKILL.md) (Phase G), [vroid-vrm-blender-cleanup](../vroid-vrm-blender-cleanup/SKILL.md) (orchestrator Phase **K**).

## Collections (default)

| Collection | Bones |
|------------|-------|
| **Hair** | `hair*`, `Hair*`, `J_Sec_Hair*`; mesh-weight hint: Hair / Twintails only |
| **Body** | Humanoid `J_Bip_*`, limbs, spine, head, bust, faceEye, `root`, default fallback |
| **Clothing** | `hood*`, `hoodString*`; mesh-weight hint: Tops / Shoes / Skirt / Cloth only |

## Workflow

```
- [ ] audit — planned Hair/Body/Clothing assignment table
- [ ] user-approve — pause before writes
- [ ] apply — create collections, assign bones, verify
```

## MCP execution

```python
import os

SKILL_TOOLS = os.path.join(
    os.path.expanduser("~"), ".cursor", "skills", "blender-bone-collections", "tools"
)

exec(open(os.path.join(SKILL_TOOLS, "assign_bone_collections.py"), encoding="utf-8").read())

result = audit_bone_collections(armature_object_name="Armature")
result = apply_bone_collections(armature_object_name="Armature", dry_run=False)
```

## Pipeline (Phase K)

Runs automatically in `run_full_pipeline()` **after Phase G** (custom bone remap), before colliders (H).

```python
result = run_full_pipeline(dry_run=True)  # includes K by default
```

Skip: `phases={"A","B","C","F","G","H","I","J"}` (omit `"K"`).

## Verify

- `remaining_unassigned` should be `0`
- `remaining_mismatches` empty
- Blender Armature → Bone Collections shows Hair / Body / Clothing counts

## Utility script

| Script | Entrypoints |
|--------|-------------|
| [assign_bone_collections.py](tools/assign_bone_collections.py) | `audit_bone_collections()`, `apply_bone_collections()`, `run_phase_k()` |

Details: [reference.md](reference.md). Examples: [examples.md](examples.md).
