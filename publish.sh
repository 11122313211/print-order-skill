#!/usr/bin/env bash
# 发布前自检与打包。
#
# 用法:
#   ./publish.sh          校验技能 frontmatter/资源引用，并打包 dist/printops.skill
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$script_dir"

echo "== validate-skills =="
python3 validate-skills.py printops

echo "== 冒烟：catalog（只读命令）=="
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
( cd "$tmp" && python3 "$script_dir/printops/scripts/printops_cli.py" catalog | python3 -c "import json,sys; d=json.load(sys.stdin); assert d['ok'] and len(d['products'])==18, d; print('ok,', len(d['products']), '品类')" )

echo "== 打包 dist/printops.skill =="
python3 - "$script_dir" <<'PY'
import os, sys, zipfile
root = sys.argv[1]
out = os.path.join(root, "dist", "printops.skill")
os.makedirs(os.path.dirname(out), exist_ok=True)
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for dirpath, dirnames, filenames in os.walk(os.path.join(root, "printops")):
        dirnames[:] = [d for d in dirnames if d not in ("__pycache__", ".mimosa")]
        for fn in sorted(filenames):
            full = os.path.join(dirpath, fn)
            z.write(full, "printops/" + os.path.relpath(full, os.path.join(root, "printops")).replace(os.sep, "/"))
print("written:", out)
PY

echo "全部通过。"
