# VMD combine examples

## Inspect

```text
python skills/vmd-combine/tools/combine_vmd.py --inspect D:\motions\dance.vmd
python skills/vmd-combine/tools/combine_vmd.py --inspect D:\motions\face.vmd
```

## Dance + facial (usual)

```text
python skills/vmd-combine/tools/combine_vmd.py --dance D:\motions\dance.vmd --face D:\motions\face.vmd --dst D:\motions\combined.vmd
python skills/vmd-combine/tools/combine_vmd.py --dance D:\motions\dance.vmd --face D:\motions\face.vmd --dst D:\motions\combined.vmd --apply
```

## Full overlay (later file wins every colliding key)

```text
python skills/vmd-combine/tools/combine_vmd.py --src D:\motions\a.vmd --src D:\motions\b.vmd --dst D:\motions\out.vmd --apply
```

## Keep first file on collisions (e.g. keep dance blink)

```text
python skills/vmd-combine/tools/combine_vmd.py --src D:\motions\dance.vmd --src D:\motions\face.vmd --on-conflict first --dst D:\motions\out.vmd --apply
```

## Concat two dances with 30-frame gap

```text
python skills/vmd-combine/tools/combine_vmd.py --src D:\motions\a.vmd --src D:\motions\b.vmd --concat --gap 30 --dst D:\motions\medley.vmd --apply
```

## Delay facial 10 frames

```text
python skills/vmd-combine/tools/combine_vmd.py --dance D:\motions\dance.vmd --face D:\motions\face.vmd --offset 10 --dst D:\motions\out.vmd --apply
```

## Filter to a PMX (MMD-like)

```text
python skills/vmd-combine/tools/combine_vmd.py --inspect-pmx D:\models\Tda.pmx
python skills/vmd-combine/tools/combine_vmd.py --export-rig D:\models\Tda.pmx --dst D:\models\Tda.rig.json
python skills/vmd-combine/tools/combine_vmd.py --src D:\motions\dance.vmd --src D:\motions\face.vmd --rig D:\models\Tda.rig.json --dst D:\motions\out.vmd --apply
```

## `uvx` from GitHub

```text
uvx --from "git+https://github.com/miramocha/blender-skills-and-rules.git#subdirectory=skills/vmd-combine" combine-vmd --dance D:\motions\dance.vmd --face D:\motions\face.vmd --dst D:\motions\combined.vmd --apply
```

```text
uvx --from skills/vmd-combine combine-vmd --inspect IN.vmd
```
