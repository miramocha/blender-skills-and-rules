# VRM 0.x ↔ 1.0 convert — examples

Repo tools path:

```python
import os, sys, json

REPO = r"D:\MiraGameDev\blender-skills-and-rules"
SKILL_TOOLS = os.path.join(REPO, "skills", "vrm0-vrm1-convert", "tools")
sys.path.insert(0, SKILL_TOOLS)
from convert_vrm import convert_vrm
```

## Dry-run (no write)

```python
report = convert_vrm(
    src=r"D:\avatars\model.vrm",
    dst=r"D:\avatars\model.vrm1.vrm",
    direction="auto",
    dry_run=True,
)
print(json.dumps(report, indent=2, ensure_ascii=False))
```

CLI:

```text
python skills/vrm0-vrm1-convert/tools/convert_vrm.py --src D:\avatars\model.vrm --dst D:\avatars\model.vrm1.vrm
```

## Apply 0→1

```python
report = convert_vrm(
    src=r"D:\avatars\model.vrm",
    dst=r"D:\avatars\model.vrm1.vrm",
    direction="0to1",
    dry_run=False,
)
```

```text
python skills/vrm0-vrm1-convert/tools/convert_vrm.py --src D:\avatars\model.vrm --dst D:\avatars\model.vrm1.vrm --direction 0to1 --apply
```

## Apply 1→0 (lossy)

```python
report = convert_vrm(
    src=r"D:\avatars\model.vrm1.vrm",
    dst=r"D:\avatars\model.vrm0.vrm",
    direction="1to0",
    dry_run=False,
)
print("dropped:", report["dropped"])
print("approximated:", report["approximated"])
```

```text
python skills/vrm0-vrm1-convert/tools/convert_vrm.py --src D:\avatars\model.vrm1.vrm --dst D:\avatars\model.vrm0.vrm --direction 1to0 --apply
```

## `uvx` from GitHub

Does not change the skill `sys.path` import. Needs [uv](https://docs.astral.sh/uv/).

```text
uvx --from "git+https://github.com/miramocha/blender-skills-and-rules.git#subdirectory=skills/vrm0-vrm1-convert" convert-vrm --src D:\avatars\model.vrm --dst D:\avatars\model.vrm1.vrm --direction 0to1 --apply
```

Local editable check:

```text
uvx --from skills/vrm0-vrm1-convert convert-vrm --src IN.vrm --dst OUT.vrm
```

## Tests

```text
cd skills/vrm0-vrm1-convert/tools
python -m unittest test_convert_vrm -v
```
