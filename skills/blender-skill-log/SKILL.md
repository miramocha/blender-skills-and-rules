---
name: blender-skill-log
description: >-
  Log Blender skill execution for MCP execute_blender_code workflows. Writes JSON
  lines to config/skill_execution.log and prints the same line for MCP stdout
  capture. Use when auditing pipeline phases, debugging skill runs, or tailing
  recent Blender skill activity.
---

# Blender skill execution log

## When to use

- Log start/end/errors for Blender MCP skill runs
- Tail recent execution history across multiple `execute_blender_code` calls
- Debug pipeline phases without relying on Blender System Console history

Requires **Blender MCP** (`execute_blender_code`) or running [tools/blender_skill_log.py](tools/blender_skill_log.py) in the Scripting workspace.

## Log location

Inside Blender:

```python
from pathlib import Path
import bpy

Path(bpy.utils.user_resource("CONFIG")) / "skill_execution.log"
```

Typical Windows path:

`%APPDATA%\Blender Foundation\Blender\<version>\config\skill_execution.log`

## Load helper

```python
import os

REPO_TOOLS = os.path.join(r"...", "skills", "blender-skill-log", "tools")
SKILL_TOOLS = os.path.join(
    os.path.expanduser("~"), ".cursor", "skills", "blender-skill-log", "tools"
)
if os.path.isdir(REPO_TOOLS):
    SKILL_TOOLS = REPO_TOOLS

_log_path = os.path.join(SKILL_TOOLS, "blender_skill_log.py")
_log_ns = {"__file__": _log_path}
exec(compile(open(_log_path, encoding="utf-8").read(), _log_path, "exec"), _log_ns)
skill_log = _log_ns["skill_log"]
tail_skill_log = _log_ns["tail_skill_log"]
```

## Write log lines

```python
skill_log(
    "phase_start",
    skill="vroid-vrm-blender-cleanup",
    phase="B",
    dry_run=True,
)

skill_log(
    "phase_end",
    skill="vroid-vrm-blender-cleanup",
    phase="B",
    dry_run=True,
    status="ok",
    renamed=12,
)

skill_log(
    "phase_error",
    skill="tri-to-quad-uv-map",
    phase="dissolve",
    error="mesh object not found: Hair.Back",
)
```

Each call:

1. `print()`s `[skill] {json}` — MCP returns this in response `stdout`
2. Appends the same JSON line to `skill_execution.log`

## Tail recent log

```python
result = tail_skill_log(lines=50)
```

Returns:

| Field | Meaning |
|-------|---------|
| `path` | Absolute log file path |
| `exists` | Whether file exists |
| `line_count` | Total lines in file |
| `tail` | Raw last N lines |
| `tail_parsed` | Parsed JSON objects (fallback `{"raw": "..."}`) |

Assign `result` when running via MCP so the agent gets structured tail data.

## Event conventions

| Event | When |
|-------|------|
| `pipeline_start` | Orchestrator begins |
| `pipeline_end` | Orchestrator finishes |
| `phase_start` | Single phase begins |
| `phase_done` | Single phase finished |
| `phase_error` | Phase raised exception |
| `self_test` | Helper smoke test |

Recommended payload fields: `skill`, `phase`, `dry_run`, `status`, `skipped`, `error`, `applied`, `elapsed_ms`.

## Timing

Each `phase_start` / `phase_done` pair should include **`elapsed_ms`** (milliseconds, `time.perf_counter()`).

Orchestrators may also log:

| Field | Meaning |
|-------|---------|
| `elapsed_ms` on `pipeline_end` | Total wall time for full run |
| `phase_timings_ms` | `{phase: elapsed_ms, ...}` summary dict |

## MCP notes

- No dedicated MCP log tool exists — use this helper inside `execute_blender_code`
- Blender 5.x does not expose System Console / Info editor history to Python
- No default session `.log` files were found on disk for this install; file logging is intentional

## Integration

`vroid-vrm-blender-cleanup` orchestrator (`run_full_pipeline.py`) loads this helper and logs `pipeline_start`, `phase_start`, `phase_done` (with `elapsed_ms`), and `pipeline_end` automatically when the script is present.

`tri-to-quad-uv-map` (`apply_profile`) and `hair-tris-to-quad` (`apply_tris_to_quads`) log each profile/step with `elapsed_ms` when the helper is installed.
