#!/usr/bin/env bash
# 安装 printops skill 到本地技能目录。
#
# 用法:
#   ./install.sh [目标技能根目录]
#
# 不带参数时依次安装到（存在即装）:
#   ~/.agents/skills/printops-<版本>     ZCode 等遵循 .agents 约定的宿主
#   ${CODEX_HOME:-~/.codex}/skills/...   Codex
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
src="$script_dir/printops"
version="1.3.0"
name="printops-$version"

[ -f "$src/SKILL.md" ] || { echo "找不到 $src/SKILL.md，请在仓库根目录运行。" >&2; exit 1; }

targets=()
if [ -n "${1:-}" ]; then
  case "$1" in
    -*) echo "目标目录不能以 - 开头：$1" >&2; exit 1 ;;
    */*|.) ;;  # 允许相对/绝对路径，仅拒绝选项样式输入
  esac
  targets+=("$1")
else
  [ -d "$HOME/.agents/skills" ] || mkdir -p -- "$HOME/.agents/skills" 2>/dev/null || true
  [ -d "$HOME/.agents/skills" ] && targets+=("$HOME/.agents/skills")
  codex_skills="${CODEX_HOME:-$HOME/.codex}/skills"
  if [ -d "$codex_skills" ]; then targets+=("$codex_skills"); fi
fi

[ ${#targets[@]} -gt 0 ] || { echo "未找到可用技能目录，请传入目标目录：./install.sh ~/.agents/skills" >&2; exit 1; }

for base in "${targets[@]}"; do
  rm -rf -- "$base/$name"
  mkdir -p -- "$base/$name"
  cp -R -- "$src/." "$base/$name/"
  echo "已安装到 $base/$name"
done

echo "完成。重启宿主或新开会话后，说一句印刷需求（如"做500张A4名片"）即可触发。"
