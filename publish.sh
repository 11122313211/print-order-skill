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

echo "== 上游对齐检查 =="
upstream_dir="${PRINTOPS_UPSTREAM:-$script_dir/../PrintOps-main}"
if [ -d "$upstream_dir/.git" ]; then
    python3 sync_upstream.py --upstream "$upstream_dir"
else
    echo "未找到上游仓库（$upstream_dir），跳过对齐检查"
fi

echo "== 冒烟：tests/smoke_test.py（catalog+订单流+多产品+terms）=="
python3 "$script_dir/tests/smoke_test.py"

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
