---
name: blender-t-a-pose
description: >-
  Toggle a Blender VRoid/VRM armature between T-pose and A-pose by rotating
  upperArm bones and optional upperLeg spread. Use when the user asks for
  T-pose, A-pose, rest pose arms/legs, or to switch/toggle bind pose.
---

# Blender T ↔ A pose

## When to use

- Switch avatar **T-pose ↔ A-pose** in Pose Mode
- Setup for skinning, screenshots, or comparing rest poses
- After bone remap (`upperArm.l` / `upperLeg.l`) or still on VRM names (`UpperArm_L`)

Requires **Blender MCP** (`execute_blender_code`) unless run in Scripting workspace.

## Behavior

| Pose | What |
|------|------|
| **T** | Clear `upperArm.*` + `upperLeg.*` pose rotation |
| **A** | Arms: local **Z** ±`angle_deg` (default **35°**). Legs: local **Z** spread ±`leg_spread_deg` (default **8°**, `include_legs=True`) |

Shoulders / forearms / lower legs unchanged. Stores `scene["ta_pose_state"]` as `"T"` or `"A"`.

## MCP / Scripting

```python
import os
import sys

SKILL_TOOLS = os.path.join(
    os.path.expanduser("~"), ".cursor", "skills", "blender-t-a-pose", "tools"
)
# Repo: skills/blender-t-a-pose/tools
sys.path.insert(0, SKILL_TOOLS)
import toggle_t_a_pose as ta

result = ta.detect_pose("Armature")
result = ta.toggle_t_a_pose("Armature")
result = ta.apply_a_pose("Armature", angle_deg=35, leg_spread_deg=8)
result = ta.apply_a_pose("Armature", include_legs=False)  # arms only
result = ta.apply_t_pose("Armature")
```

## Bone name aliases

| Role | Names |
|------|-------|
| Upper arm L/R | `upperArm.l` / `.r`, `UpperArm_L` / `_R`, `J_Bip_L_UpperArm` / `_R_` |
| Upper leg L/R | `upperLeg.l` / `.r`, `UpperLeg_L` / `_R`, `J_Bip_L_UpperLeg` / `_R_` |

## Workflow

```
- [ ] detect — report T / A / other
- [ ] toggle or apply_t / apply_a
- [ ] verify — detect_pose again
```

## Utility

| Script | Entrypoints |
|--------|-------------|
| [toggle_t_a_pose.py](tools/toggle_t_a_pose.py) | `detect_pose()`, `toggle_t_a_pose()`, `apply_t_pose()`, `apply_a_pose()` |
