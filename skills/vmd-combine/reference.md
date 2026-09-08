# VMD combine — reference

## File layout (little-endian)

| Section | Notes |
|---------|--------|
| Signature | 30 bytes. `Vocaloid Motion Data 0002` or legacy `Vocaloid Motion Data file` |
| Model name | 20 bytes Shift-JIS (0002) or 10 bytes (legacy). Writer always emits 0002 |
| Bone keys | `uint32` count; each 15-byte name + frame + pos xyz + quat xyzw + 64-byte interp |
| Morph keys | `uint32` count; each 15-byte name + frame + float weight |
| Camera | 61 bytes/key; optional (EOF allowed) |
| Light | 28 bytes/key; optional |
| Self-shadow | 9 bytes/key; optional |
| IK | variable (`frame`, show, per-bone enable); optional |

Truncated tail after morphs is valid. Huge counts vs remaining bytes → `VmdError`.

Names: cp932, null-padded. 15-byte bone/morph slots **truncate** long JP names the same way MMD does.

## Overlay vs concat

- **Overlay** (default): same frame 0. Union of keyframes. Collision key bones/morphs = `(name, frame)`; camera/light/shadow/ik = `(frame,)`.
- **Concat**: each source starts at `max_frame(previous taken keys) + 1 + gap`, plus any per-source `offset`.

## `take` tokens

`all`, `bones`, `morphs`, `face_bones` / `face-bones`, `face` / `facial` (= morphs+face_bones), `camera`, `light`, `shadow`, `ik`.

`bones` includes face bones. `face_bones` without `bones` keeps only names in `FACE_BONE_NAMES`.

## `FACE_BONE_NAMES`

`目` `両目` `左目` `右目` `あご` `顎` `歯` `舌` `Eyeball_L` `Eyeball_R` `Eye_L` `Eye_R`

Unknown face-control bones stay on the dance file unless `--take bones` on the face VMD (`--face FACE.vmd --take morphs,bones` — usually wrong). Prefer inspect, then explicit `--take`.

## Interpolation

Unmodified 64-byte bone / 24-byte camera tables copy through. Combine does not resample or bezier-mix overlapping curves — last whole keyframe wins.

## PMX filter (MMD save)

`--pmx` / `--rig` keeps VMD keys whose Shift-JIS names exist on the model (JP or EN, 15-byte truncated). Drops PD-only skirt/FACE_* tracks if the rig lacks them.

`--export-rig MODEL.pmx --dst MODEL.rig.json` writes UTF-8 JSON: `name_jp`/`name_en`, bone `{index,name_jp,name_en,is_ik}`, morph `{index,name_jp,name_en}`. No vertices, faces, materials, textures. Combine then uses `--rig` (no PMX needed).

JSON is still **derived from that PMX**. Do not commit a Tda dump to a public repo; keep next to the user's model.

With pad (default): model bones with no keys get frame 0 identity (MMD bezier table); unused morphs get weight 0; IK list expands to all PMX IK bones (`つま先` enable 0, else 1). Header model name = JP name (20-byte SJIS).

`--no-pad-rest` = filter only.

## Related

- Mesh morph **names** for playback: [arkit-vroid-mmd-shapekeys](../arkit-vroid-mmd-shapekeys/SKILL.md)
- PMX import (Blender): [mmd-pmx-to-vrm1](../mmd-pmx-to-vrm1/SKILL.md)
