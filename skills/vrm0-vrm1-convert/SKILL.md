---
name: vrm0-vrm1-convert
description: >-
  Headless stdlib Python conversion of .vrm GLB files between VRM 0.x and VRM 1.0
  (extension maps + coordinate/BIN rewrite). No Blender, no Unity. Use when
  converting VRM0 to VRM1 or VRM1 to VRM0 on disk, migrating VRMC_* extras, or
  rewriting VRM glTF extensions without opening Blender.
---

# VRM 0.x ↔ 1.0 convert (headless)

## When to use

- Convert a `.vrm` file **on disk** between VRM 0.x (`extensions.VRM`) and VRM 1.0 (`VRMC_vrm` + `VRMC_springBone` + `VRMC_materials_mtoon`)
- Need a converter **without Blender or Unity**
- Dry-run a drop/approx report before writing

**Not** Blender MCP. **Not** UniVRM as a runtime (maps ported from UniVRM C#). **Not** part of `run_full_pipeline()`. Do **not** auto-feed output into [vroid-vrm-blender-cleanup](../vroid-vrm-blender-cleanup/SKILL.md).

## Prerequisites

- Python 3 (stdlib only)
- Input is glTF 2.0 **GLB** with `.vrm` / `.glb` wrapper
- Optional: [uv](https://docs.astral.sh/uv/) for `uvx` (npx-style)

## Hard rules

- Dry-run first (`dry_run=True`); write only after user approval
- Mapping tables from `tools/maps/` (UniVRM / vrm-specification). Do not invent socket or preset names
- Output is **one** spec — never dual-write `VRM` + `VRMC_vrm`
- 1→0 must list `dropped[]` (VRM1-only data). Never silent strip
- Mesh topology / morph targets / skins / textures stay; numeric coords rewrite where UniVRM does
- License enum coerce is lossy — put it in `approximated[]`, do not invent new license text

## Agent workflow

```python
import os, sys, json

SKILL_TOOLS = os.path.join(r"...", "skills", "vrm0-vrm1-convert", "tools")
sys.path.insert(0, SKILL_TOOLS)
from convert_vrm import convert_vrm

src = r"D:\path\to\avatar.vrm"
dst = r"D:\path\to\avatar.vrm1.vrm"

# Dry-run (no write)
report = convert_vrm(src, dst, direction="auto", dry_run=True)
print(json.dumps(report, indent=2))

# Apply after approval
report = convert_vrm(src, dst, direction="auto", dry_run=False)
```

CLI:

```text
python skills/vrm0-vrm1-convert/tools/convert_vrm.py --src IN.vrm --dst OUT.vrm
python skills/vrm0-vrm1-convert/tools/convert_vrm.py --src IN.vrm --dst OUT.vrm --apply
python skills/vrm0-vrm1-convert/tools/convert_vrm.py --src IN.vrm --dst OUT.vrm --direction 0to1 --apply
```

Default CLI is dry-run. `--apply` writes `--dst`.

**`uvx`** (does **not** replace the skill `sys.path` workflow). Package root is this skill folder (`subdirectory=`):

```text
uvx --from "git+https://github.com/miramocha/blender-skills-and-rules.git#subdirectory=skills/vrm0-vrm1-convert" convert-vrm --src IN.vrm --dst OUT.vrm --apply
```

`direction`: `auto` (0.x→1.0 or 1.0→0.x), `0to1`, `1to0`. File with **both** extensions: pass an explicit direction.

## Report schema

| Field | Meaning |
|-------|---------|
| `ok` | Convert (or dry-run plan) succeeded |
| `from` / `to` | `0.x` or `1.0` |
| `dry_run` | No file written |
| `dropped` | VRM1-only (or unmappable) fields stripped on 1→0; usually empty on 0→1 |
| `approximated` | Enum / topology / license coerce |
| `counts` | Humanoid / expression / spring / MToon tallies on **output** spec |
| `output_path` | Set only when `dry_run=False` |

## What convert does

1. Split GLB (JSON + BIN)
2. Detect `VRM` vs `VRMC_vrm`
3. Rewrite mesh/node/IBM coords (net `(-x, y, -z)` — UniVRM Vrm0→Unity→Vrm1)
4. Swap extensions (spring/lookAt JSON vecs: `(-x, y, z)` per `MigrateVector3`)
5. Patch `extensionsUsed` / `extensionsRequired`
6. Write GLB unless dry-run

See [reference.md](reference.md) for tables and [examples.md](examples.md) for commands.

## Tests

```text
python -m unittest tools.test_convert_vrm
```

from `skills/vrm0-vrm1-convert/`, or `python -m unittest test_convert_vrm` from `tools/`.
