"""Synthetic GLB tests for VRM 0.x ↔ 1.0 convert."""

from __future__ import annotations

import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = os.path.dirname(os.path.abspath(__file__))
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

from convert_vrm import convert_vrm  # noqa: E402
from coords import vec3_mesh  # noqa: E402
from glb_io import read_glb, write_glb  # noqa: E402
from migrate_1_to_0 import migrate_mtoon_1_to_0  # noqa: E402


def _vrm0_gltf(positions):
    count = len(positions) // 3
    return {
        "asset": {"version": "2.0"},
        "buffers": [{"byteLength": count * 12}],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": count * 12}],
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5126,
                "count": count,
                "type": "VEC3",
                "max": [1, 1, 1],
                "min": [0, 0, 0],
            }
        ],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "targets": [{"POSITION": 0}]}]}],
        "nodes": [
            {"name": "hips", "mesh": 0, "translation": [1.0, 2.0, 3.0], "children": [1]},
            {"name": "head", "translation": [0.0, 1.0, 0.0]},
        ],
        "scenes": [{"nodes": [0]}],
        "scene": 0,
        "materials": [{"name": "Skin", "pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1]}}],
        "textures": [{"source": 0}],
        "images": [{"name": "thumb"}],
        "extensionsUsed": ["VRM"],
        "extensions": {
            "VRM": {
                "specVersion": "0.0",
                "meta": {
                    "title": "Test",
                    "version": "1",
                    "author": "Unit",
                    "allowedUserName": "Everyone",
                    "violentUssageName": "Disallow",
                    "sexualUssageName": "Disallow",
                    "commercialUssageName": "Allow",
                    "texture": 0,
                },
                "humanoid": {
                    "humanBones": [
                        {"bone": "hips", "node": 0},
                        {"bone": "head", "node": 1},
                        {"bone": "leftThumbProximal", "node": 1},
                    ]
                },
                "blendShapeMaster": {
                    "blendShapeGroups": [
                        {
                            "name": "A",
                            "presetName": "a",
                            "isBinary": False,
                            "binds": [{"mesh": 0, "index": 0, "weight": 100}],
                            "materialValues": [],
                        }
                    ]
                },
                "firstPerson": {
                    "lookAtTypeName": "Bone",
                    "firstPersonBoneOffset": {"x": 1.0, "y": 0.0, "z": 0.5},
                    "meshAnnotations": [{"mesh": 0, "firstPersonFlag": "Auto"}],
                },
                "secondaryAnimation": {
                    "colliderGroups": [
                        {
                            "node": 1,
                            "colliders": [{"offset": {"x": 0.1, "y": 0.0, "z": 0.0}, "radius": 0.05}],
                        }
                    ],
                    "boneGroups": [
                        {
                            "comment": "hair",
                            "stiffiness": 1.0,
                            "gravityPower": 0.0,
                            "gravityDir": {"x": 0.0, "y": -1.0, "z": 0.0},
                            "dragForce": 0.5,
                            "center": -1,
                            "hitRadius": 0.02,
                            "bones": [1],
                            "colliderGroups": [0],
                        }
                    ],
                },
                "materialProperties": [
                    {
                        "name": "Skin",
                        "shader": "VRM/MToon",
                        "renderQueue": 2000,
                        "floatProperties": {
                            "_BlendMode": 0,
                            "_ShadeShift": 0.2,
                            "_ShadeToony": 0.9,
                            "_OutlineWidthMode": 0,
                            "_IndirectLightIntensity": 0.1,
                        },
                        "vectorProperties": {
                            "_Color": [1, 1, 1, 1],
                            "_ShadeColor": [0.8, 0.8, 0.8, 1],
                        },
                        "textureProperties": {},
                        "keywordMap": {},
                        "tagMap": {},
                    }
                ],
            }
        },
    }


def _pack_positions(xyz):
    return struct.pack("<" + "f" * len(xyz), *xyz)


class ConvertTests(unittest.TestCase):
    def test_0_to_1_mesh_and_maps(self):
        pos = [1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 0.5, 0.5, 0.5]
        gltf = _vrm0_gltf(pos)
        blob = _pack_positions(pos)
        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, "in.vrm")
            dst = os.path.join(td, "out.vrm")
            with open(src, "wb") as f:
                f.write(write_glb(gltf, blob))
            dry = convert_vrm(src, dst, direction="0to1", dry_run=True)
            self.assertTrue(dry["ok"], dry)
            self.assertTrue(dry["dry_run"])
            self.assertIsNone(dry["output_path"])
            self.assertEqual(dry["to"], "1.0")
            self.assertGreaterEqual(dry["counts"]["humanoid_bones"], 2)
            self.assertEqual(dry["counts"]["expression_presets"], 1)

            applied = convert_vrm(src, dst, direction="0to1", dry_run=False)
            self.assertTrue(applied["ok"], applied)
            out_gltf, out_bin = read_glb(Path(dst).read_bytes())
            self.assertIn("VRMC_vrm", out_gltf["extensions"])
            self.assertNotIn("VRM", out_gltf["extensions"])
            x, y, z = struct.unpack_from("<fff", out_bin, 0)
            nx, ny, nz = vec3_mesh(1.0, 2.0, 3.0)
            self.assertAlmostEqual(x, nx)
            self.assertAlmostEqual(y, ny)
            self.assertAlmostEqual(z, nz)
            t = out_gltf["nodes"][0]["translation"]
            self.assertAlmostEqual(t[0], -1.0)
            self.assertAlmostEqual(t[1], 2.0)
            self.assertAlmostEqual(t[2], -3.0)
            vrm1 = out_gltf["extensions"]["VRMC_vrm"]
            self.assertEqual(vrm1["meta"]["name"], "Test")
            self.assertEqual(vrm1["meta"]["avatarPermission"], "everyone")
            self.assertEqual(vrm1["meta"]["commercialUsage"], "personalProfit")
            self.assertEqual(vrm1["humanoid"]["humanBones"]["hips"]["node"], 0)
            self.assertEqual(vrm1["humanoid"]["humanBones"]["leftThumbMetacarpal"]["node"], 1)
            aa = vrm1["expressions"]["preset"]["aa"]
            self.assertAlmostEqual(aa["morphTargetBinds"][0]["weight"], 1.0)
            self.assertEqual(aa["morphTargetBinds"][0]["node"], 0)
            off = vrm1["lookAt"]["offsetFromHeadBone"]
            self.assertAlmostEqual(off[0], -1.0)
            self.assertAlmostEqual(off[2], 0.5)
            col = out_gltf["extensions"]["VRMC_springBone"]["colliders"][0]["shape"]["sphere"]["offset"]
            self.assertAlmostEqual(col[0], -0.1)
            mtoon = out_gltf["materials"][0]["extensions"]["VRMC_materials_mtoon"]
            self.assertAlmostEqual(mtoon["shadingShiftFactor"], 0.2)
            self.assertAlmostEqual(mtoon["giEqualizationFactor"], 0.9)

    def test_roundtrip_0_1_0(self):
        pos = [0.2, 0.3, 0.4, 0.0, 1.0, 0.0, -0.1, 0.0, 0.2]
        gltf = _vrm0_gltf(pos)
        blob = _pack_positions(pos)
        with tempfile.TemporaryDirectory() as td:
            a = os.path.join(td, "a.vrm")
            b = os.path.join(td, "b.vrm")
            c = os.path.join(td, "c.vrm")
            with open(a, "wb") as f:
                f.write(write_glb(gltf, blob))
            r1 = convert_vrm(a, b, direction="0to1", dry_run=False)
            self.assertTrue(r1["ok"], r1)
            r2 = convert_vrm(b, c, direction="1to0", dry_run=False)
            self.assertTrue(r2["ok"], r2)
            self.assertTrue(any("meta." in x or "VRMC_vrm.meta" in x for x in r2["dropped"]))
            back, back_bin = read_glb(Path(c).read_bytes())
            self.assertIn("VRM", back["extensions"])
            v0 = back["extensions"]["VRM"]
            self.assertEqual(v0["meta"]["title"], "Test")
            bones = {h["bone"]: h["node"] for h in v0["humanoid"]["humanBones"]}
            self.assertEqual(bones["hips"], 0)
            self.assertEqual(bones["leftThumbProximal"], 1)
            self.assertEqual(v0["firstPerson"]["firstPersonBone"], 1)
            self.assertIn("curve", v0["firstPerson"]["lookAtHorizontalInner"])
            self.assertEqual(v0["meta"]["licenseName"], "Redistribution_Prohibited")
            clip = v0["blendShapeMaster"]["blendShapeGroups"][0]
            self.assertEqual(clip["presetName"], "a")
            self.assertAlmostEqual(clip["binds"][0]["weight"], 100.0)
            x, y, z = struct.unpack_from("<fff", back_bin, 0)
            self.assertAlmostEqual(x, 0.2, places=5)
            self.assertAlmostEqual(y, 0.3, places=5)
            self.assertAlmostEqual(z, 0.4, places=5)

    def test_1_to_0_drops_constraint_and_capsule(self):
        gltf = {
            "asset": {"version": "2.0"},
            "buffers": [{"byteLength": 12}],
            "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 12}],
            "accessors": [{"bufferView": 0, "componentType": 5126, "count": 1, "type": "VEC3"}],
            "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
            "nodes": [{"name": "hips", "mesh": 0, "translation": [0, 1, 0]}],
            "scenes": [{"nodes": [0]}],
            "scene": 0,
            "materials": [{"name": "M", "extensions": {"VRMC_materials_mtoon": {"specVersion": "1.0"}}}],
            "extensionsUsed": ["VRMC_vrm", "VRMC_springBone", "VRMC_node_constraint", "VRMC_materials_mtoon"],
            "extensions": {
                "VRMC_vrm": {
                    "specVersion": "1.0",
                    "meta": {"name": "N", "authors": ["A"], "licenseUrl": "https://vrm.dev/licenses/1.0/"},
                    "humanoid": {"humanBones": {"hips": {"node": 0}}},
                    "expressions": {"preset": {}, "custom": {}},
                },
                "VRMC_springBone": {
                    "specVersion": "1.0",
                    "colliders": [
                        {
                            "node": 0,
                            "shape": {
                                "capsule": {
                                    "offset": [0, 0, 0],
                                    "radius": 0.1,
                                    "tail": [0, 0.1, 0],
                                }
                            },
                        }
                    ],
                    "colliderGroups": [{"colliders": [0]}],
                    "springs": [],
                },
                "VRMC_node_constraint": {"specVersion": "1.0", "constraint": {}},
            },
        }
        blob = struct.pack("<fff", 0.0, 0.0, 0.0)
        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, "v1.vrm")
            dst = os.path.join(td, "v0.vrm")
            with open(src, "wb") as f:
                f.write(write_glb(gltf, blob))
            r = convert_vrm(src, dst, direction="1to0", dry_run=False)
            self.assertTrue(r["ok"], r)
            self.assertTrue(any("VRMC_node_constraint" in x for x in r["dropped"]))
            self.assertTrue(any("capsule" in x for x in r["dropped"]))
            out, _ = read_glb(Path(dst).read_bytes())
            self.assertNotIn("VRMC_vrm", out.get("extensions") or {})
            self.assertIn("VRM", out["extensions"])

    def test_1_to_0_mask_is_cutout_not_opaque(self):
        dropped: list = []
        prop = migrate_mtoon_1_to_0(
            {},
            {
                "name": "Hair",
                "alphaMode": "MASK",
                "alphaCutoff": 0.5,
                "extensions": {"VRMC_materials_mtoon": {"specVersion": "1.0"}},
            },
            dropped,
        )
        self.assertEqual(prop["floatProperties"]["_BlendMode"], 1.0)
        self.assertEqual(prop["floatProperties"]["_Cutoff"], 0.5)
        self.assertEqual(prop["floatProperties"]["_SrcBlend"], 1.0)
        self.assertEqual(prop["floatProperties"]["_DstBlend"], 0.0)
        self.assertEqual(prop["floatProperties"]["_ZWrite"], 1.0)
        self.assertEqual(prop["floatProperties"]["_AlphaToMask"], 1.0)
        self.assertTrue(prop["keywordMap"]["_ALPHATEST_ON"])
        self.assertFalse(prop["keywordMap"]["_ALPHABLEND_ON"])
        self.assertEqual(prop["tagMap"]["RenderType"], "TransparentCutout")
        self.assertEqual(prop["renderQueue"], 2450)

        opaque = migrate_mtoon_1_to_0(
            {},
            {
                "name": "Glow",
                "alphaMode": "OPAQUE",
                "extensions": {"VRMC_materials_mtoon": {"specVersion": "1.0"}},
            },
            dropped,
        )
        self.assertEqual(opaque["floatProperties"]["_BlendMode"], 0.0)
        self.assertFalse(opaque["keywordMap"]["_ALPHATEST_ON"])
        self.assertEqual(opaque["tagMap"]["RenderType"], "Opaque")

        blend = migrate_mtoon_1_to_0(
            {},
            {
                "name": "Lash",
                "alphaMode": "BLEND",
                "extensions": {
                    "VRMC_materials_mtoon": {
                        "specVersion": "1.0",
                        "transparentWithZWrite": False,
                    }
                },
            },
            dropped,
        )
        self.assertEqual(blend["floatProperties"]["_BlendMode"], 2.0)
        self.assertTrue(blend["keywordMap"]["_ALPHABLEND_ON"])
        self.assertFalse(blend["keywordMap"]["_ALPHATEST_ON"])
        self.assertEqual(blend["tagMap"]["RenderType"], "Transparent")


if __name__ == "__main__":
    unittest.main()
