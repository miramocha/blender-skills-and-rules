---
name: mtoon-material-sync
description: >-
  Compile workspace mtoon_theme.json onto VRM MToon 1.0 materials using CSS-like
  class suffixes (NoRim, NoOutline, Highlight, MatcapTexture, EmissionAccent). Also legacy
  rim/shading sync from a reference material. Dry-run then apply via Blender MCP.
  Use when unifying rim, outline, emission, matcap hide/highlight/texture, invertAccent
  expression, or applying a shared look across save-increment .blends.
---

# MToon material sync + theme compile

## When to use

- Apply one workspace **theme** to the open `.blend` (including incrementals)
- Stamp / compile material class names (`Face_Skin-NoRim.NoOutline`)
- Hide vs opt-in **Highlight** / **MatcapTexture**, `EmissionAccent`, `NoRim` black rim + lift 0 + fresnel 1000
- Sync VRM custom expression **`invertAccent`** (was `rimPink`)
- Legacy: copy rim/toony from one reference mat (no theme file)

Requires **Blender MCP** (`execute_blender_code`) unless run in Scripting workspace.

Related: [vroid-vrm-blender-cleanup](../vroid-vrm-blender-cleanup/SKILL.md) **Phase J**. Rules: `vroid-material-names`, `mtoon-material-classes`.

## Progress checklist

```
- [ ] theme — workspace mtoon_theme.json (extract once if missing)
- [ ] dummy-images — mtoon_none_white / mtoon_none_black / mtoon_matcap_highlight
- [ ] stamp-dry-run — stamp_mtoon_classes(dry_run=True)
- [ ] user-approve-stamp — rename datablocks
- [ ] audit-theme — audit_mtoon_theme(theme_path=...)
- [ ] user-approve-compile — apply_mtoon_theme(dry_run=False)
- [ ] verify — remaining diffs + invertAccent binds
```

## MCP pattern

```python
import os

REPO = r"D:\MiraGameDev\blender-skills-and-rules"  # workspace root
SKILL_TOOLS = os.path.join(REPO, "skills", "mtoon-material-sync", "tools")
THEME = os.path.join(REPO, "mtoon_theme.json")

exec(open(os.path.join(SKILL_TOOLS, "compile_mtoon_theme.py"), encoding="utf-8").read())

stamp = stamp_mtoon_classes(theme_path=THEME, dry_run=True)
# after approval
stamp = stamp_mtoon_classes(theme_path=THEME, dry_run=False)

audit = audit_mtoon_theme(theme_path=THEME)
result = apply_mtoon_theme(theme_path=THEME, dry_run=False)
```

Pass **absolute** `theme_path` — Blender cannot see Cursor root.

Bootstrap JSON (first time only; then edit the file, do not re-extract from incrementals):

```python
extract_mtoon_theme(reference_material="Face_Skin", out_path=THEME)
```

## Class compile (v1)

| Class | Effect |
|-------|--------|
| *(none)* | Rim = `accent` + theme lift; hide matcap (`mtoon_none_white` + black factor); emission black |
| `NoRim` | Rim **black**; **lift 0**; **fresnel 1000** |
| `NoOutline` | Skip Outline Width Mode; still stamp width + color |
| `Highlight` | `mtoon_matcap_highlight` + factor white |
| `MatcapTexture` | Keep linked MatCap Texture + factor white (error if both with `Highlight`) |
| `EmissionAccent` | Lit + shade + emissive = `accent` |
| `InvertEmissionAccent` | Those three = `invertAccent` |
| `EmissionTexture` | Keep emissive texture; factor white; strength `1` (only one Emission* class) |

Expr **`invertAccent`**: rename from `rimPink`. Rebuild binds — sockets whose rest RGB ≈ accent ↔ invertAccent (rim / lit / shade / emission). Unique albedo / black emission → no bind.

## Legacy reference sync

Still in [sync_mtoon_attributes.py](tools/sync_mtoon_attributes.py) if no theme file:

```python
exec(open(os.path.join(SKILL_TOOLS, "sync_mtoon_attributes.py"), encoding="utf-8").read())
result = apply_mtoon_sync(reference_material="Face_Skin", dry_run=False)
```

## Phase J

`run_phase_j()` / `run_full_pipeline()`: if `mtoon_theme.json` found (repo root or `theme_path=`), compile theme; else old reference sync.

```python
result = run_full_pipeline(dry_run=False, theme_path=THEME)
```

## Utility scripts

| Script | Entrypoints |
|--------|-------------|
| [compile_mtoon_theme.py](tools/compile_mtoon_theme.py) | `audit_mtoon_theme()`, `apply_mtoon_theme()`, `stamp_mtoon_classes()`, `extract_mtoon_theme()`, `sync_invert_accent_expression()` |
| [sync_mtoon_attributes.py](tools/sync_mtoon_attributes.py) | `audit_mtoon_sync()`, `apply_mtoon_sync()`, `run_phase_j()` |

Return structured `result` dicts from MCP (`result = ...`).
