# MMD PMX → VRM1 examples

## Dry-run then apply (MCP)

```python
import os

REPO = r"D:\MiraGameDev\blender-skills-and-rules"
SKILL_TOOLS = os.path.join(REPO, "skills", "mmd-pmx-to-vrm1", "tools")
_path = os.path.join(SKILL_TOOLS, "run_pmx_to_vrm1_setup.py")
_ns = {"__file__": _path}
exec(compile(open(_path, encoding="utf-8").read(), _path, "exec"), _ns)
run_pmx_to_vrm1_setup = _ns["run_pmx_to_vrm1_setup"]

pmx = r"D:\Models\example.pmx"

dry = run_pmx_to_vrm1_setup(filepath=pmx, dry_run=True, scale=0.08)
assert dry["dry_run"] is True
# dry["import"]["filepath"], dry["setup"]["planned_humanoid"]

out = run_pmx_to_vrm1_setup(filepath=pmx, dry_run=False, scale=0.08)
assert out.get("applied") is True
arm = out["armature_object_name"]
missing = out["audit"]["required_missing"]
# missing should be [] for standard Animasa-like skeletons
```

## Import into current blend (no new empty file)

```python
out = run_pmx_to_vrm1_setup(
    filepath=r"D:\Models\example.pmx",
    dry_run=False,
    new_file=False,
)
```

## Audit existing MMD armature already in scene

```python
import os

SKILL_TOOLS = os.path.join(
    r"D:\MiraGameDev\blender-skills-and-rules",
    "skills",
    "mmd-pmx-to-vrm1",
    "tools",
)
_ns = {}
for name in ("audit_vrm1_setup.py", "setup_vrm1.py", "mmd_vrm1_bone_map.py"):
    p = os.path.join(SKILL_TOOLS, name)
    exec(compile(open(p, encoding="utf-8").read(), p, "exec"), _ns)

# Enable + assign without re-import
_ns["setup_vrm1_on_armature"]("Armature", dry_run=False, model_name="MyModel")
audit = _ns["audit_vrm1_setup"]("Armature")
```

## What “ready” looks like

| Check | Expect |
|-------|--------|
| `spec_version` | `"1.0"` |
| Required humanoid slots | All non-empty |
| Expression morph binds | > 0 if PMX had まばたき / あ… |
| `shapekeys_untouched` | `True` — MMD key names unchanged |
| Export | **Not** run by skill |
