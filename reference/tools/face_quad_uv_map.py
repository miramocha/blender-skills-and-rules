"""Deprecated: use skills/tri-to-quad-uv-map/tools/tri_to_quad_uv_map.py"""

from __future__ import annotations

import sys
from pathlib import Path

_SKILL_TOOLS = Path(__file__).resolve().parents[2] / "skills" / "tri-to-quad-uv-map" / "tools"
if str(_SKILL_TOOLS) not in sys.path:
    sys.path.insert(0, str(_SKILL_TOOLS))

from tri_to_quad_uv_map import *  # noqa: F401,F403
