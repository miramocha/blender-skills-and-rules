# MToon theme compile — examples

## Stamp names then compile

```python
import os

REPO = r"D:\MiraGameDev\blender-skills-and-rules"
TOOLS = os.path.join(REPO, "skills", "mtoon-material-sync", "tools")
THEME = os.path.join(REPO, "mtoon_theme.json")
exec(open(os.path.join(TOOLS, "compile_mtoon_theme.py"), encoding="utf-8").read())

stamp = stamp_mtoon_classes(theme_path=THEME, dry_run=True)
# result["rows"] — old → new names

stamp = stamp_mtoon_classes(theme_path=THEME, dry_run=False)
audit = audit_mtoon_theme(theme_path=THEME)
result = apply_mtoon_theme(theme_path=THEME, dry_run=False)
```

Expected: `Face.Skin` → `Face_Skin`; eyes get `-NoOutline.NoRim`; `Glow` → `Glow-NoOutline.EmissionAccent`; Highlight mats use `mtoon_matcap_highlight`; expr renamed `invertAccent`.

## Edit theme, re-apply to another incremental

1. Change `accent` / `invertAccent` / outline width in `mtoon_theme.json`.
2. Open `_036.blend`.
3. `apply_mtoon_theme(theme_path=THEME, dry_run=False)` — no re-extract.

## Phase J with theme

```python
result = run_full_pipeline(dry_run=False, theme_path=THEME)
# result["phases"]["J"]["mode"] == "theme"
```

Without `mtoon_theme.json`, Phase J falls back to `apply_mtoon_sync(reference_material="Face_Skin")`.
