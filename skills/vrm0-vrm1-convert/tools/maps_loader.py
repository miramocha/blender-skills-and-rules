"""Load mapping tables shipped next to this package."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any, Dict

MAPS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "maps")


@lru_cache(maxsize=None)
def load_map(name: str) -> Dict[str, Any]:
    path = os.path.join(MAPS_DIR, name)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def invert_str_map(fwd: Dict[str, str]) -> Dict[str, str]:
    inv: Dict[str, str] = {}
    for k, v in fwd.items():
        inv.setdefault(v, k)
    return inv


# UniVRM MigrationMToonMaterial: world cm→m; screen is “half height = 100%” → VRM1 height=1.
OUTLINE_WORLD_0_TO_1 = 0.01
OUTLINE_SCREEN_0_TO_1 = 0.01 * 0.5  # 1/200


def outline_width_0_to_1(mode: str, width: float) -> float:
    if mode == "worldCoordinates":
        return width * OUTLINE_WORLD_0_TO_1
    if mode == "screenCoordinates":
        return width * OUTLINE_SCREEN_0_TO_1
    return width


def outline_width_1_to_0(mode: str, width: float) -> float:
    if mode == "worldCoordinates":
        return width / OUTLINE_WORLD_0_TO_1
    if mode == "screenCoordinates":
        return width / OUTLINE_SCREEN_0_TO_1
    return width
