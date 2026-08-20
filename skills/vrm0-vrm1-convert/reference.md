# VRM 0.x ↔ 1.0 convert — reference

Ported from UniVRM (not run as Unity). Spec sources:

- [MigrationVrm.cs](https://github.com/vrm-c/UniVRM/blob/master/Packages/VRM10/Runtime/Migration/MigrationVrm.cs)
- [MigrationVrmMeta.cs](https://github.com/vrm-c/UniVRM/blob/master/Packages/VRM10/Runtime/Migration/MigrationVrmMeta.cs)
- [MigrationVrmExpression.cs](https://github.com/vrm-c/UniVRM/blob/master/Packages/VRM10/Runtime/Migration/MigrationVrmExpression.cs)
- [MigrationVrmHumanoid.cs](https://github.com/vrm-c/UniVRM/blob/master/Packages/VRM10/Runtime/Migration/MigrationVrmHumanoid.cs)
- [MigrationVrmSpringBone.cs](https://github.com/vrm-c/UniVRM/blob/master/Packages/VRM10/Runtime/Migration/MigrationVrmSpringBone.cs)
- [MigrationVrmFirstPersonAndLookAt.cs](https://github.com/vrm-c/UniVRM/blob/master/Packages/VRM10/Runtime/Migration/MigrationVrmFirstPersonAndLookAt.cs)
- [MigrationVector3.cs](https://github.com/vrm-c/UniVRM/blob/master/Packages/VRM10/Runtime/Migration/MigrationVector3.cs)
- [Model.ConvertCoordinate](https://github.com/vrm-c/UniVRM/blob/master/Packages/VRM10/vrmlib/Runtime/Model.cs)
- [vrm-specification](https://github.com/vrm-c/vrm-specification)

JSON tables live in [tools/maps/](tools/maps/).

## Coordinates

| Space | Geometry |
|-------|----------|
| VRM-0 | +X right, +Y up, −Z forward (RH) |
| Unity | +X right, +Y up, +Z forward (LH) |
| VRM-1 | −X right, +Y up, +Z forward (RH) |

UniVRM migrate: `ModelReader(Vrm0)` then `ConvertCoordinate(Vrm1)` = Vrm0→Unity→Vrm1.

- Vrm0↔Unity: reverse **Z** + UV V-flip + triangle flip
- Vrm1↔Unity: reverse **X** + UV V-flip + triangle flip

**Net VRM0 file → VRM1 file (this tool):**

- Positions / normals / node translation: `(x, y, z) → (−x, y, −z)`
- UV and triangle indices: **unchanged** (two flips cancel)
- Inverse bind / node `matrix`: `R M R` with `R = diag(−1, 1, −1, 1)`
- Node / animation rotation: 180° about Y

Same transform is an involution → 1→0 mesh path is identical.

**Extension JSON vectors** (spring `offset` / `gravityDir`, lookAt `offsetFromHeadBone`) use UniVRM `MigrateVector3`: `(x, y, z) → (−x, y, z)` only. Reverse 1→0: negate X again.

## Humanoid

See [tools/maps/humanoid_bones.json](tools/maps/humanoid_bones.json). Thumb rename:

| VRM0 | VRM1 |
|------|------|
| `leftThumbProximal` | `leftThumbMetacarpal` |
| `leftThumbIntermediate` | `leftThumbProximal` |
| (same for right) | |

Node indices unchanged.

## Expression presets

See [tools/maps/presets.json](tools/maps/presets.json). Notable:

| VRM0 `presetName` | VRM1 |
|-------------------|------|
| `a` `i` `u` `e` `o` | `aa` `ih` `ou` `ee` `oh` |
| `joy` `sorrow` `fun` | `happy` `sad` `relaxed` |
| `blink_l` / `blink_r` | `blinkLeft` / `blinkRight` |
| `unknown` | try clip `name` as preset, else custom |

Morph bind: VRM0 `mesh` index → node that references that mesh. Weight `× 0.01` (0–100 → 0–1). Reverse `× 100`.

## Meta / license

See [tools/maps/meta.json](tools/maps/meta.json).

| VRM0 | VRM1 |
|------|------|
| `title` | `name` |
| `author` | `authors[]` |
| `texture` (texture index) | `thumbnailImage` (image index) |
| `Everyone` / `OnlyAuthor` / `ExplicitlyLicensedPerson` | `everyone` / `onlyAuthor` / `onlySeparatelyLicensedPerson` |
| `commercialUssageName` Allow | `personalProfit` (**not** corporation) |
| `violentUssageName` / `sexualUssageName` | `allowExcessivelyViolentUsage` / `allowExcessivelySexualUsage` bools |

VRM1 defaults (UniVRM): `creditNotation=required`, `modification=prohibited`, `allowRedistribution=false`, political/religious false. `licenseUrl` = `https://vrm.dev/licenses/1.0/`.

## Spring bones

0→1: each VRM0 collider in a group becomes a VRM1 collider (sphere) + group of indices. Bone groups expand along `children[0]` chains; extra siblings start new springs. Leaf joints get a 7 cm `_end` node (UniVRM / spec PR 255). `stiffiness` typo is VRM0 spec.

1→0: spheres regrouped by node. **Capsule colliders dropped.** Springs flatten to a boneGroup with **first joint** as `bones[]` root (chain topology approximated).

## MToon

See [tools/maps/mtoon.json](tools/maps/mtoon.json). World outline width: VRM0 centimetres → VRM1 metres (`× 0.01`). Screen outline width: VRM0 “half screen height = 100%” → VRM1 “screen height = 1” (`× 1/200`, UniVRM). `giEqualizationFactor = 1 - _IndirectLightIntensity`. Unity `_MainTex` ST → `KHR_texture_transform` with V-flip. `shadingShiftTexture` has no VRM0 twin → drop on 1→0.

## 1→0 dropped (typical)

- `VRMC_node_constraint`
- Capsule spring colliders
- `meta`: `allowAntisocialOrHateUsage`, `allowPoliticalOrReligiousUsage`, `allowRedistribution`, `creditNotation`, `modification`, `copyrightInformation`, `thirdPartyLicenses`, `licenseUrl`
- `shadingShiftTexture` and other MToon1-only sockets
