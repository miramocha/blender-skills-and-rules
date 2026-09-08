"""Synthetic tests for MToonXT stencil JSON migration."""

from __future__ import annotations

import json
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = os.path.dirname(os.path.abspath(__file__))
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

from glb_json import join_glb, split_glb  # noqa: E402
from migrate_mtoonxt_stencil import (  # noqa: E402
    EXT,
    EXT_LEGACY,
    MigrateError,
    migrate_gltf,
    migrate_path,
)

TAIL = struct.pack("<II", 4, 0x004E4942) + bytes([0, 1, 254, 255])


def glb_bytes(document):
    return join_glb(document, TAIL)


class TestMigrateGltf(unittest.TestCase):
    def test_iris_white_ops_to_graph(self):
        gltf = {
            "materials": [
                {
                    "name": "Iris",
                    "extensions": {
                        EXT: {
                            "specVersion": "1.0",
                            "stencil": {"op": "inside", "materials": [1]},
                            "outlineStencil": {"op": "same"},
                        }
                    },
                },
                {
                    "name": "White",
                    "extensions": {EXT: {"specVersion": "1.0", "stencil": {"op": "write"}}},
                },
            ]
        }
        report = migrate_gltf(gltf)
        self.assertTrue(report["ok"])
        extra = gltf["extensions"][EXT]
        self.assertEqual(report["polarity"], "writer-clip")
        self.assertEqual(
            extra["stencil"],
            [
                {
                    "writers": [0],
                    "readers": [1],
                    "comparison": "inside",
                    "writersOnlyInsideReaders": True,
                }
            ],
        )
        self.assertNotIn("extensions", gltf["materials"][0])
        self.assertNotIn("extensions", gltf["materials"][1])
        self.assertIn(EXT, gltf["extensionsUsed"])

    def test_inside_overlay_is_writer_clip(self):
        gltf = {
            "materials": [
                {"extensions": {EXT: {"stencil": {"op": "write"}}}},
                {
                    "extensions": {
                        EXT: {"stencil": {"op": "insideOverlay", "materials": [0]}}
                    }
                },
            ]
        }
        migrate_gltf(gltf)
        self.assertEqual(
            gltf["extensions"][EXT]["stencil"],
            [
                {
                    "writers": [1],
                    "readers": [0],
                    "comparison": "inside",
                    "showWritersThroughOccluders": True,
                    "writersOnlyInsideReaders": True,
                }
            ],
        )

    def test_reader_clip_polarity(self):
        gltf = {
            "materials": [
                {"extensions": {EXT: {"stencil": {"op": "write"}}}},
                {"extensions": {EXT: {"stencil": {"op": "outside", "materials": [0]}}}},
            ]
        }
        migrate_gltf(gltf, polarity="reader-clip")
        self.assertEqual(
            gltf["extensions"][EXT]["stencil"],
            [{"writers": [0], "readers": [1]}],
        )

    def test_renames_relationships_strips_ops_keeps_face_sdf(self):
        graph = [
            {
                "writers": [0],
                "readers": [1],
                "writersWriteColor": False,
                "writersSelfOcclude": False,
                "writerDepthTest": "always",
            }
        ]
        gltf = {
            "extensions": {EXT: {"specVersion": "1.0", "stencilRelationships": graph}},
            "materials": [
                {
                    "extensions": {
                        EXT: {
                            "specVersion": "1.0",
                            "stencil": {"op": "write"},
                            "faceSdf": {"enabled": True},
                        }
                    }
                },
                {"extensions": {EXT: {"specVersion": "1.0", "stencil": {"op": "inside", "materials": [0]}}}},
            ],
        }
        migrate_gltf(gltf)
        self.assertEqual(gltf["extensions"][EXT]["stencil"], graph)
        self.assertNotIn("stencilRelationships", gltf["extensions"][EXT])
        self.assertNotIn("stencil", gltf["materials"][0]["extensions"][EXT])
        self.assertEqual(gltf["materials"][0]["extensions"][EXT]["faceSdf"], {"enabled": True})

    def test_legacy_extension_name(self):
        gltf = {
            "extensionsUsed": [EXT_LEGACY],
            "extensions": {EXT_LEGACY: {"specVersion": "1.0", "stencil": [{"writers": [0], "readers": [1]}]}},
            "materials": [{}, {}],
        }
        migrate_gltf(gltf)
        self.assertIn(EXT, gltf["extensions"])
        self.assertNotIn(EXT_LEGACY, gltf["extensions"])
        self.assertIn(EXT, gltf["extensionsUsed"])
        self.assertNotIn(EXT_LEGACY, gltf["extensionsUsed"])

    def test_write_only_fails(self):
        gltf = {"materials": [{"extensions": {EXT: {"stencil": {"op": "write"}}}}]}
        with self.assertRaisesRegex(MigrateError, "write ops but no clip"):
            migrate_gltf(gltf)

    def test_conflicting_graphs_fail(self):
        gltf = {
            "extensions": {
                EXT: {
                    "stencilRelationships": [{"writers": [0], "readers": [1]}],
                    "stencil": [],
                }
            },
            "materials": [{}, {}],
        }
        with self.assertRaisesRegex(MigrateError, "conflicting"):
            migrate_gltf(gltf)

    def test_coalesce_same_writers(self):
        gltf = {
            "materials": [
                {"extensions": {EXT: {"stencil": {"op": "inside", "materials": [2]}}}},
                {"extensions": {EXT: {"stencil": {"op": "inside", "materials": [2]}}}},
                {"extensions": {EXT: {"stencil": {"op": "write"}}}},
            ]
        }
        migrate_gltf(gltf, polarity="reader-clip")
        self.assertEqual(
            gltf["extensions"][EXT]["stencil"],
            [{"writers": [2], "readers": [0, 1], "comparison": "inside"}],
        )

    def test_idempotent(self):
        gltf = {
            "extensionsUsed": [EXT],
            "extensions": {EXT: {"specVersion": "1.0", "stencil": [{"writers": [0], "readers": [1]}]}},
            "materials": [{}, {}],
        }
        migrate_gltf(gltf)
        again = json.loads(json.dumps(gltf))
        migrate_gltf(again)
        self.assertEqual(again, gltf)

    def test_writer_clip_outside_is_default(self):
        gltf = {
            "materials": [
                {"extensions": {EXT: {"stencil": {"op": "write"}}}},
                {"extensions": {EXT: {"stencil": {"op": "outside", "materials": [0]}}}},
            ]
        }
        migrate_gltf(gltf)
        self.assertEqual(
            gltf["extensions"][EXT]["stencil"],
            [
                {
                    "writers": [1],
                    "readers": [0],
                    "writersOnlyOutsideReaders": True,
                }
            ],
        )


BUNNY_DIR = Path(r"D:\MiraGameDev\MiraSite\public\models\mira-bunny")
BUNNY_OPS = BUNNY_DIR / "mirabunny2026_mtoonxt_stencil.vrm"
BUNNY_MIGRATED = BUNNY_DIR / "mirabunny2026_mtoonxt_stencil.migrated.vrm"


class TestBunnyMigratedRef(unittest.TestCase):
    @unittest.skipUnless(BUNNY_OPS.is_file() and BUNNY_MIGRATED.is_file(), "mira-bunny VRM pair missing")
    def test_default_migrate_matches_migrated_vrm_stencil(self):
        golden, _, _ = split_glb(BUNNY_MIGRATED.read_bytes())
        expected = golden["extensions"][EXT]["stencil"]
        with tempfile.TemporaryDirectory() as tmp:
            dst = Path(tmp) / "out.vrm"
            report = migrate_path(str(BUNNY_OPS), str(dst), dry_run=False)
            self.assertTrue(report["ok"], report)
            self.assertEqual(report["polarity"], "writer-clip")
            got, _, _ = split_glb(dst.read_bytes())
            self.assertEqual(got["extensions"][EXT]["stencil"], expected)


class TestMigratePath(unittest.TestCase):
    def test_glb_preserves_binary_tail(self):
        document = {
            "asset": {"version": "2.0"},
            "extensions": {EXT: {"specVersion": "1.0", "stencilRelationships": [{"writers": [0], "readers": [1]}]}},
            "materials": [{}, {}],
        }
        raw = glb_bytes(document)
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "old.vrm"
            dst = Path(tmp) / "new.vrm"
            src.write_bytes(raw)
            report = migrate_path(str(src), str(dst), dry_run=True)
            self.assertTrue(report["ok"])
            self.assertFalse(dst.exists())
            report = migrate_path(str(src), str(dst), dry_run=False)
            self.assertTrue(report["ok"])
            out = dst.read_bytes()
            _, tail, _ = split_glb(out)
            self.assertEqual(tail, TAIL)
            json_len = struct.unpack_from("<I", out, 12)[0]
            migrated = json.loads(out[20 : 20 + json_len])
            self.assertEqual(
                migrated["extensions"][EXT]["stencil"],
                [{"writers": [0], "readers": [1]}],
            )
            self.assertEqual(migrate_path(str(dst), str(Path(tmp) / "again.vrm"), dry_run=False)["ok"], True)

    def test_json_sidecar(self):
        payload = {
            "materials": [
                {"extensions": {EXT: {"stencil": {"op": "outside", "materials": [1]}}}},
                {"extensions": {EXT: {"stencil": {"op": "write"}}}},
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "draft.gltf.json"
            dst = Path(tmp) / "out.gltf.json"
            src.write_text(json.dumps(payload), encoding="utf-8")
            report = migrate_path(str(src), str(dst), dry_run=False)
            self.assertTrue(report["ok"])
            out = json.loads(dst.read_text(encoding="utf-8"))
            self.assertEqual(out["extensions"][EXT]["stencil"][0]["writers"], [0])
            self.assertEqual(out["extensions"][EXT]["stencil"][0]["readers"], [1])
            self.assertTrue(out["extensions"][EXT]["stencil"][0]["writersOnlyOutsideReaders"])


if __name__ == "__main__":
    unittest.main()
