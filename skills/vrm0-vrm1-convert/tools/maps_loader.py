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
