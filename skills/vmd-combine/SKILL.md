---
name: vmd-combine
description: >-
  Headless stdlib Python merge of MikuMikuDance .vmd files (dance + facial overlay,
  optional concat, optional PMX or mesh-less rig JSON filter like MMD save). No
  Blender. Use when combining VMD motions, exporting bone/morph names from a .pmx,
  filtering to a target model, or concatenating clips without opening MMD or Blender.
---

# VMD combine (headless)

## When to use

- Merge two or more `.vmd` files **on disk**
- Typical: **dance** (bones / camera) + **facial** (morphs + 目/あご)
- Inspect bone/morph names and frame range before merge

**Not** Blender MCP. **Not** mmd_tools. **Not** part of `run_full_pipeline()`. Face *shape keys* on a mesh still come from [arkit-vroid-mmd-shapekeys](../arkit-vroid-mmd-shapekeys/SKILL.md); this skill only edits motion files.

## Prerequisites

- Python 3.9+ (stdlib only)
- Optional: [uv](https://docs.astral.sh/uv/) for `uvx`

## Hard rules

- Dry-run first (`dry_run=True` / CLI without `--apply`); write only after user approval
- Do not invent bone or morph names — copy bytes from sources (Shift-JIS names, 15-byte slots)
- Overlay is the default (same timeline). `--concat` is sequential, not a second overlay
- Same `(name, frame)`: `on_conflict="last"` (default) or `"first"`
- `--dance` takes body motion **and** morphs; `--face` adds morphs + face bones. Same `(name, frame)` → later source wins (`on_conflict`)
- `--pmx MODEL.pmx` — keep bones/morphs on that model (MMD save). Stamp JP model name. Pad missing bones @ frame 0 identity, morphs @ 0, extra IK (`つま先` enable 0)
- `--face` takes morphs + `FACE_BONE_NAMES` only, not body bones

## Agent workflow

```python
import os, sys, json

SKILL_TOOLS = os.path.join(r"...", "skills", "vmd-combine", "tools")
sys.path.insert(0, SKILL_TOOLS)
from combine_vmd import combine_vmd
from vmd_io import inspect_vmd

dance = r"D:\path\to\dance.vmd"
face = r"D:\path\to\face.vmd"
dst = r"D:\path\to\combined.vmd"

print(json.dumps(inspect_vmd(dance), ensure_ascii=False, indent=2))
print(json.dumps(inspect_vmd(face), ensure_ascii=False, indent=2))

report = combine_vmd(
    [
        {"path": dance, "take": "bones,camera,light,shadow,ik"},
        {"path": face, "take": "morphs,face_bones"},
    ],
    dst,
    dry_run=True,
)
print(json.dumps(report, ensure_ascii=False, indent=2))

report = combine_vmd(
    [
        {"path": dance, "take": "bones,camera,light,shadow,ik"},
        {"path": face, "take": "morphs,face_bones"},
    ],
    dst,
    dry_run=False,
)
```

CLI (default dry-run):

```text
python skills/vmd-combine/tools/combine_vmd.py --inspect IN.vmd
python skills/vmd-combine/tools/combine_vmd.py --dance DANCE.vmd --face FACE.vmd --dst OUT.vmd
python skills/vmd-combine/tools/combine_vmd.py --dance DANCE.vmd --face FACE.vmd --dst OUT.vmd --apply
python skills/vmd-combine/tools/combine_vmd.py --src A.vmd --src B.vmd --pmx MODEL.pmx --dst OUT.vmd --apply
python skills/vmd-combine/tools/combine_vmd.py --inspect-pmx MODEL.pmx
python skills/vmd-combine/tools/combine_vmd.py --export-rig MODEL.pmx --dst MODEL.rig.json
python skills/vmd-combine/tools/combine_vmd.py --src A.vmd --src B.vmd --rig MODEL.rig.json --dst OUT.vmd --apply
python skills/vmd-combine/tools/combine_vmd.py --src A.vmd --src B.vmd --concat --gap 0 --dst OUT.vmd --apply
```

**`uvx`:**

```text
uvx --from "git+https://github.com/miramocha/blender-skills-and-rules.git#subdirectory=skills/vmd-combine" combine-vmd --dance DANCE.vmd --face FACE.vmd --dst OUT.vmd --apply
```

## Source order

CLI flags append in the order given. `--dance` then `--face` → body from dance, face bones/morphs from face overwrite same-frame collisions.

| Flag | Default `take` |
|------|----------------|
| `--src` | all channels |
| `--dance` | `bones,morphs,camera,light,shadow,ik` |
| `--face` | `morphs,face_bones` |
| `--take` | override on **previous** source |
| `--pmx` | Filter + rest pad to this PMX **or** rig JSON |
| `--rig` | Same as `--pmx` for JSON from `--export-rig` |
| `--export-rig` | PMX → name JSON (`--dst`); no mesh |
| `--no-pad-rest` | Filter names only, no frame-0 pads |

`--src` + `--src` = full overlay (later wins). Use `--dance`/`--face` when files share leftover channels you do not want.

## Report schema

| Field | Meaning |
|-------|---------|
| `ok` | Parse + merge (or dry-run plan) succeeded |
| `dry_run` | No file written |
| `mode` | `overlay` or `concat` |
| `on_conflict` | `last` or `first` |
| `max_frame` | Highest frame in **output** |
| `counts` | Bone/morph/camera/… keyframe tallies |
| `collisions` | Overwritten same `(name, frame)` counts |
| `inputs` | Per-file `take`, offset, source vs contributed counts |
| `pmx` | Set when `--pmx` used: dropped/padded counts |

## Tests

```text
python -m unittest tools.test_combine_vmd
```

from `skills/vmd-combine/`, or `python -m unittest test_combine_vmd` from `tools/`.

## Additional resources

- Format + face-bone list: [reference.md](reference.md)
- Commands: [examples.md](examples.md)
