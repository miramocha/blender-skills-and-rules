# VRMXT stencil migrate — examples

Repo tools path:

```python
import os, sys, json

REPO = r"D:\MiraGameDev\blender-skills-and-rules"
SKILL_TOOLS = os.path.join(REPO, "skills", "vrmxt-stencil-migrate", "tools")
sys.path.insert(0, SKILL_TOOLS)
from migrate_mtoonxt_stencil import migrate_path, migrate_gltf
```

## Dry-run (no write)

```python
report = migrate_path(
    src=r"D:\avatars\model.vrm",
    dst=r"D:\avatars\model.migrated.vrm",
    dry_run=True,
)
print(json.dumps(report, indent=2, ensure_ascii=False))
```

CLI:

```text
python skills/vrmxt-stencil-migrate/tools/migrate_mtoonxt_stencil.py --src D:\avatars\model.vrm --dst D:\avatars\model.migrated.vrm
```

## Apply graph rename

Root `stencilRelationships` → `stencil`, strip leftover material ops:

```python
report = migrate_path(
    src=r"D:\avatars\draft-graph.vrm",
    dst=r"D:\avatars\draft-graph.migrated.vrm",
    dry_run=False,
)
```

## Apply material ops (Iris inside White)

Default `writer-clip` matches `mirabunny2026_mtoonxt_stencil.migrated.vrm`: Iris writes, White is the reader (`writersOnlyInsideReaders`).

```python
report = migrate_path(
    src=r"D:\avatars\ops-only.gltf.json",
    dst=r"D:\avatars\ops-only.migrated.gltf.json",
    dry_run=False,
)
```

Writer-first overlay (`insideOverlay` on the subject listing mask materials) converts without changing polarity.

## Reader-clip polarity

Old invert where White writes and Iris clips (`inside` on the clip listing writers):

```text
python skills/vrmxt-stencil-migrate/tools/migrate_mtoonxt_stencil.py --src IN.vrm --dst OUT.vrm --polarity reader-clip --apply
```
