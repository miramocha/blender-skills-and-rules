"""Synthetic VMD combine tests."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest

TOOLS = os.path.dirname(os.path.abspath(__file__))
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

from combine_vmd import combine_vmd  # noqa: E402
from vmd_io import (  # noqa: E402
    BoneKey,
    MorphKey,
    VmdMotion,
    identity_interpolation,
    inspect_vmd,
    read_vmd,
    write_vmd,
)


def _bone(name: str, frame: int, x: float = 0.0) -> BoneKey:
    return BoneKey(
        name=name,
        frame=frame,
        pos=(x, 0.0, 0.0),
        rot=(0.0, 0.0, 0.0, 1.0),
        interpolation=identity_interpolation(),
    )


def _morph(name: str, frame: int, w: float) -> MorphKey:
    return MorphKey(name=name, frame=frame, weight=w)


class VmdRoundtripTests(unittest.TestCase):
    def test_roundtrip_jp_names(self):
        m = VmdMotion(
            signature="Vocaloid Motion Data 0002",
            model_name="初音ミク",
            bones=[_bone("センター", 0, 1.5), _bone("左目", 10, 0.2)],
            morphs=[_morph("まばたき", 0, 1.0), _morph("あ", 5, 0.5)],
        )
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "a.vmd")
            write_vmd(path, m)
            back = read_vmd(path)
        self.assertEqual(back.model_name, "初音ミク")
        self.assertEqual(back.bones[0].name, "センター")
        self.assertEqual(back.bones[1].name, "左目")
        self.assertAlmostEqual(back.bones[0].pos[0], 1.5, places=5)
        self.assertEqual(back.morphs[0].name, "まばたき")
        self.assertAlmostEqual(back.morphs[1].weight, 0.5, places=5)

    def test_inspect_counts(self):
        m = VmdMotion(
            signature="x",
            model_name="m",
            bones=[_bone("右目", 3)],
            morphs=[_morph("あ", 1, 1.0)],
        )
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "i.vmd")
            write_vmd(path, m)
            info = inspect_vmd(path)
        self.assertTrue(info["ok"])
        self.assertEqual(info["counts"]["bones"], 1)
        self.assertEqual(info["face_bones_present"], ["右目"])
        self.assertEqual(info["max_frame"], 3)


class CombineTests(unittest.TestCase):
    def _pair(self, td: str):
        dance = VmdMotion(
            signature="x",
            model_name="dance_model",
            bones=[_bone("センター", 0, 1.0), _bone("左目", 0, 9.0)],
            morphs=[_morph("まばたき", 0, 1.0)],
        )
        face = VmdMotion(
            signature="x",
            model_name="face_model",
            bones=[_bone("左目", 0, 0.1), _bone("あご", 2, 0.0)],
            morphs=[_morph("あ", 0, 1.0), _morph("まばたき", 0, 0.0)],
        )
        dpath = os.path.join(td, "dance.vmd")
        fpath = os.path.join(td, "face.vmd")
        write_vmd(dpath, dance)
        write_vmd(fpath, face)
        return dpath, fpath

    def test_dance_face_overlay(self):
        with tempfile.TemporaryDirectory() as td:
            dpath, fpath = self._pair(td)
            outp = os.path.join(td, "out.vmd")
            report = combine_vmd(
                [
                    {"path": dpath, "take": "bones,morphs,camera,light,shadow,ik"},
                    {"path": fpath, "take": "morphs,face_bones"},
                ],
                outp,
                dry_run=False,
            )
            self.assertTrue(report["ok"])
            merged = read_vmd(outp)
        names = {b.name: b for b in merged.bones if b.frame == 0}
        self.assertIn("センター", names)
        self.assertAlmostEqual(names["センター"].pos[0], 1.0, places=5)
        self.assertAlmostEqual(names["左目"].pos[0], 0.1, places=5)
        morphs = {(m.name, m.frame): m.weight for m in merged.morphs}
        self.assertAlmostEqual(morphs[("あ", 0)], 1.0, places=5)
        self.assertAlmostEqual(morphs[("まばたき", 0)], 0.0, places=5)
        self.assertEqual(report["model_name"], "dance_model")
        self.assertEqual(report["collisions"]["bones"], 1)
        self.assertEqual(report["collisions"]["morphs"], 1)

    def test_dry_run_no_write(self):
        with tempfile.TemporaryDirectory() as td:
            dpath, fpath = self._pair(td)
            outp = os.path.join(td, "out.vmd")
            report = combine_vmd([dpath, fpath], outp, dry_run=True)
            self.assertTrue(report["dry_run"])
            self.assertFalse(os.path.exists(outp))
            self.assertIsNone(report["output_path"])

    def test_conflict_first(self):
        with tempfile.TemporaryDirectory() as td:
            dpath, fpath = self._pair(td)
            outp = os.path.join(td, "out.vmd")
            combine_vmd(
                [dpath, fpath],
                outp,
                dry_run=False,
                on_conflict="first",
            )
            merged = read_vmd(outp)
        morphs = {(m.name, m.frame): m.weight for m in merged.morphs}
        self.assertAlmostEqual(morphs[("まばたき", 0)], 1.0, places=5)

    def test_concat_gap(self):
        with tempfile.TemporaryDirectory() as td:
            a = VmdMotion(signature="x", model_name="a", bones=[_bone("センター", 10)])
            b = VmdMotion(signature="x", model_name="b", bones=[_bone("センター", 0)])
            ap = os.path.join(td, "a.vmd")
            bp = os.path.join(td, "b.vmd")
            write_vmd(ap, a)
            write_vmd(bp, b)
            outp = os.path.join(td, "out.vmd")
            report = combine_vmd(
                [ap, bp],
                outp,
                dry_run=False,
                concat=True,
                gap=5,
            )
            merged = read_vmd(outp)
        frames = sorted(k.frame for k in merged.bones)
        self.assertEqual(frames, [10, 16])
        self.assertEqual(report["max_frame"], 16)

    def test_pmx_filter_pad(self):
        from pmx_io import dumps_test_pmx

        with tempfile.TemporaryDirectory() as td:
            pmx_path = os.path.join(td, "m.pmx")
            with open(pmx_path, "wb") as f:
                f.write(
                    dumps_test_pmx(
                        "Tda式ミク・アペンド",
                        [
                            ("センター", False),
                            ("左足ＩＫ", True),
                            ("左つま先ＩＫ", True),
                            ("しっぽ１", False),
                        ],
                        ["あ", "にやり"],
                    )
                )
            dpath, fpath = self._pair(td)
            outp = os.path.join(td, "out.vmd")
            report = combine_vmd([dpath, fpath], outp, dry_run=False, pmx=pmx_path)
            self.assertTrue(report["ok"])
            self.assertEqual(report["pmx"]["padded_bone_keys"], 3)
            merged = read_vmd(outp)
        bone_names = {b.name for b in merged.bones}
        self.assertIn("センター", bone_names)
        self.assertNotIn("左目", bone_names)
        self.assertIn("しっぽ１", bone_names)
        morph_names = {m.name for m in merged.morphs}
        self.assertIn("あ", morph_names)
        self.assertIn("にやり", morph_names)
        self.assertNotIn("まばたき", morph_names)
        self.assertEqual(merged.model_name, "Tda式ミク・アペンド")
        self.assertEqual(len(merged.ik), 1)
        enables = {e.name: e.enable for e in merged.ik[0].iks}
        self.assertEqual(enables["左つま先ＩＫ"], 0)
        self.assertEqual(enables["左足ＩＫ"], 1)

    def test_pmx_stamps_name_when_source_has_ik(self):
        from pmx_io import dumps_test_pmx
        from vmd_io import IkEnable, IkKey

        with tempfile.TemporaryDirectory() as td:
            pmx_path = os.path.join(td, "m.pmx")
            with open(pmx_path, "wb") as f:
                f.write(dumps_test_pmx("Tda式ミク・アペンド", [("センター", False), ("左足ＩＫ", True)], ["あ"]))
            dance = VmdMotion(
                signature="x",
                model_name="PD Base",
                bones=[_bone("センター", 0)],
                ik=[IkKey(frame=0, show=1, iks=[IkEnable(name="左足ＩＫ", enable=1)])],
            )
            src = os.path.join(td, "d.vmd")
            write_vmd(src, dance)
            outp = os.path.join(td, "out.vmd")
            combine_vmd([src], outp, dry_run=False, pmx=pmx_path)
            merged = read_vmd(outp)
        self.assertEqual(merged.model_name, "Tda式ミク・アペンド")

    def test_export_rig_json_roundtrip(self):
        from pmx_io import dumps_test_pmx, write_rig

        with tempfile.TemporaryDirectory() as td:
            pmx_path = os.path.join(td, "m.pmx")
            with open(pmx_path, "wb") as f:
                f.write(
                    dumps_test_pmx(
                        "Tda式ミク・アペンド",
                        [("センター", False), ("左足ＩＫ", True)],
                        ["あ"],
                    )
                )
            rig_path = os.path.join(td, "m.rig.json")
            info = write_rig(pmx_path, rig_path)
            self.assertTrue(info["ok"])
            dpath, fpath = self._pair(td)
            outp = os.path.join(td, "out.vmd")
            report = combine_vmd([dpath, fpath], outp, dry_run=False, pmx=rig_path)
            self.assertEqual(report["pmx"]["pmx_name_jp"], "Tda式ミク・アペンド")
            merged = read_vmd(outp)
        self.assertEqual(merged.model_name, "Tda式ミク・アペンド")
        self.assertIn("センター", {b.name for b in merged.bones})
        self.assertNotIn("左目", {b.name for b in merged.bones})

    def test_cli_dance_face_apply(self):
        from combine_vmd import main

        with tempfile.TemporaryDirectory() as td:
            dpath, fpath = self._pair(td)
            outp = os.path.join(td, "out.vmd")
            rc = main(
                [
                    "--dance",
                    dpath,
                    "--face",
                    fpath,
                    "--dst",
                    outp,
                    "--apply",
                ]
            )
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.isfile(outp))


if __name__ == "__main__":
    unittest.main()
