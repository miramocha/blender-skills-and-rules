"""
Blender skill execution logging for MCP execute_blender_code workflows.
Run via MCP or Blender Scripting workspace.

    from blender_skill_log import skill_log, tail_skill_log

    skill_log("phase_start", skill="vroid-vrm-blender-cleanup", phase="B", dry_run=True)
    skill_log("phase_end", skill="vroid-vrm-blender-cleanup", phase="B", status="ok")
    tail_skill_log()
"""

from __future__ import annotations

import datetime
import json
import time
from pathlib import Path
from typing import Any, Callable, Optional

import bpy

DEFAULT_LOG_NAME = "skill_execution.log"
DEFAULT_TAIL_LINES = 50
SKILL_NAME = "blender-skill-log"


def perf_elapsed_ms(start: float) -> float:
    """Milliseconds since ``time.perf_counter()`` start."""
    return round((time.perf_counter() - start) * 1000, 2)


def resolve_skill_log_script(*search_roots: Path | str) -> Optional[Path]:
    """Locate ``blender_skill_log.py`` under sibling or home skill trees."""
    candidates: list[Path] = []
    home = Path.home() / ".cursor" / "skills" / "blender-skill-log" / "tools" / "blender_skill_log.py"
    candidates.append(home)

    for root in search_roots:
        root_path = Path(root)
        if root_path.is_file() and root_path.name == "blender_skill_log.py":
            candidates.insert(0, root_path)
            continue
        if root_path.is_dir():
            candidates.append(
                root_path / "blender-skill-log" / "tools" / "blender_skill_log.py"
            )
            candidates.append(root_path.parent / "blender-skill-log" / "tools" / "blender_skill_log.py")

    seen: set[str] = set()
    for path in candidates:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        if path.is_file():
            return path
    return None


def load_skill_log(*search_roots: Path | str) -> Optional[Callable[..., dict]]:
    """Import ``skill_log`` from disk when helper not already on ``sys.modules``."""
    script = resolve_skill_log_script(*search_roots)
    if script is None:
        return None
    import importlib.util

    spec = importlib.util.spec_from_file_location("blender_skill_log", script)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    fn = getattr(mod, "skill_log", None)
    return fn if callable(fn) else None


def log_path(log_name: str = DEFAULT_LOG_NAME) -> Path:
    config = bpy.utils.user_resource("CONFIG")
    if not config:
        raise RuntimeError("bpy.utils.user_resource('CONFIG') returned empty path")
    return Path(config) / log_name


def skill_log(
    event: str,
    *,
    skill: Optional[str] = None,
    log_name: str = DEFAULT_LOG_NAME,
    **data: Any,
) -> dict:
    """Append one JSON line to the skill log and print for MCP stdout capture."""
    payload: dict[str, Any] = {
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
        "event": event,
    }
    if skill is not None:
        payload["skill"] = skill
    payload.update(data)

    line = json.dumps(payload, ensure_ascii=False, default=str)
    print(f"[skill] {line}")

    path = log_path(log_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")

    return payload


def tail_skill_log(
    lines: int = DEFAULT_TAIL_LINES,
    log_name: str = DEFAULT_LOG_NAME,
    parse_json: bool = True,
) -> dict:
    """Return the tail of the skill execution log."""
    path = log_path(log_name)
    if not path.is_file():
        return {
            "path": str(path),
            "exists": False,
            "line_count": 0,
            "tail": [],
            "tail_parsed": [],
        }

    all_lines = path.read_text(encoding="utf-8").splitlines()
    tail = all_lines[-lines:] if lines > 0 else all_lines
    parsed: list[Any] = []
    if parse_json:
        for line in tail:
            try:
                parsed.append(json.loads(line))
            except json.JSONDecodeError:
                parsed.append({"raw": line})

    return {
        "path": str(path),
        "exists": True,
        "line_count": len(all_lines),
        "tail": tail,
        "tail_parsed": parsed,
    }


if __name__ == "__main__":
    skill_log("self_test", skill=SKILL_NAME, status="ok")
    result = tail_skill_log(lines=5)
