#!/usr/bin/env bash
# 安装或更新 PrintOps 技能包里的技能到 Codex 技能目录。
#
# 技能目录资产布局固定为 SKILL.md + {references,scripts,agents,engine}，
# 本脚本按同一份清单复制与清理，避免残留上一版的文件。
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
codex_home="${CODEX_HOME:-$HOME/.codex}"
managed_dirs=(references scripts agents engine)

install_one() {
  name="$1"
  src="$here/$name"
  target="$codex_home/skills/$name"

  if [ ! -f "$src/SKILL.md" ]; then
    echo "跳过 ${name}：找不到 $src/SKILL.md" >&2
    return 1
  fi

  mkdir -p "$target"

  # 只清理本技能包自己管理的路径，不动同目录下的其它内容。
  rm -f "$target/SKILL.md"
  shopt -s nullglob
  # 旧布局把维护脚本放在技能根目录，一并清掉，避免升级后留下失效副本。
  rm -f "$target"/*.sh
  shopt -u nullglob
  for dir in "${managed_dirs[@]}"; do
    rm -rf "${target:?}/$dir"
  done

  cp "$src/SKILL.md" "$target/SKILL.md"
  for dir in "${managed_dirs[@]}"; do
    [ -d "$src/$dir" ] || continue
    cp -R "$src/$dir" "$target/$dir"
  done

  # cp -R 的权限位受 umask 影响，脚本显式补回可执行位。
  shopt -s nullglob
  for script in "$target"/scripts/*.sh "$target"/scripts/*.py; do
    chmod +x "$script"
  done
  shopt -u nullglob

  echo "已安装: $target"
}

if [ "$#" -eq 0 ]; then
  set -- printops printops-lite
fi

for name in "$@"; do
  install_one "$name"
done
