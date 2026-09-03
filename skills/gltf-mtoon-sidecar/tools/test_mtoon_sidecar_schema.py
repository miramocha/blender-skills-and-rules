"""Schema helper tests (no Blender)."""

from __future__ import annotations

import os
import sys
import unittest

TOOLS = os.path.dirname(os.path.abspath(__file__))
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

from mtoon_sidecar_schema import (  # noqa: E402
    outline_mode_from_int,
    portable_basename,
    rgb,
    rgba,
    wrap_document,
)


class TestSchema(unittest.TestCase):
    def test_outline_modes(self) -> None:
        self.assertEqual(outline_mode_from_int(0), "none")
        self.assertEqual(outline_mode_from_int(2.0), "screenCoordinates")
        self.assertEqual(outline_mode_from_int(1), "worldCoordinates")
        self.assertEqual(outline_mode_from_int(None), "none")

    def test_rgb_rgba(self) -> None:
        self.assertEqual(rgb([0.1, 0.2, 0.3, 1.0]), [0.1, 0.2, 0.3])
        self.assertEqual(rgba([1, 0, 0]), [1.0, 0.0, 0.0, 1.0])

    def test_wrap(self) -> None:
        doc = wrap_document({"Glow": {"color": [1, 0, 0, 1]}}, blend=r"D:\MiraArt\v23-5gun\v23-18blaster_merged.blend")
        self.assertEqual(doc["kind"], "mtoon-sidecar")
        self.assertEqual(doc["specVersion"], "1.0")
        self.assertEqual(doc["blend"], "v23-18blaster_merged.blend")
        self.assertIn("Glow", doc["materials"])

    def test_portable_basename(self) -> None:
        self.assertEqual(portable_basename(r"D:\MiraArt\bunny2026\textures\darkblue.png"), "darkblue.png")
        self.assertEqual(portable_basename("//textures/mtoon_matcap_highlight.png"), "mtoon_matcap_highlight.png")
        self.assertEqual(portable_basename("darkblue.png"), "darkblue.png")


if __name__ == "__main__":
    unittest.main()
