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

echo "== 冒烟：catalog（只读命令）=="
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
( cd "$tmp" && python3 "$script_dir/printops/scripts/printops_cli.py" catalog | python3 -c "import json,sys; d=json.load(sys.stdin); assert d['ok'] and len(d['products'])==18, d; print('ok,', len(d['products']), '品类')" )

echo "== 冒烟：完整订单流（ingest→set→price→quote→handoff→reset）=="
( cd "$tmp" && python3 - "$script_dir/printops/scripts/printops_cli.py" <<'PY'
import json, pathlib, subprocess, sys
cli = sys.argv[1]

def run(*args):
    out = subprocess.run([sys.executable, cli, *args], capture_output=True,
                         text=True, encoding="utf-8")
    assert out.returncode == 0, (args, out.stderr)
    return json.loads(out.stdout)

ing = run("ingest", "--text", "印1000张名片，90×54mm，双面四色")
assert ing["ok"] and ing["order"]["productType"] == "名片", ing
run("set", "--field", "paper=300g铜版纸")
est = run("price")["estimate"]
assert est["schemaVersion"] == "2.0" and est["status"] == "ready", est["status"]
assert est["displayRange"].startswith("¥"), est["displayRange"]
quote = run("quote")
assert quote["quote"]["status"] == "awaiting_human_confirmation", quote
handoff = run("handoff", "--out", "冒烟交接单.md")
assert handoff["status"] == "ready" and handoff["requiresHumanConfirmation"] is True, handoff
assert pathlib.Path("冒烟交接单.md").stat().st_size > 0
assert run("reset")["ok"]
print("ok: ingest→price(schema 2.0)→quote→handoff→reset 全链路通过")
PY
)

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
