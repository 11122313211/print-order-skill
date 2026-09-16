#!/usr/bin/env bash
# 核对内置引擎副本与仓库是否一致。
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
repo="${1:-${PRINTOPS_HOME:-/Users/Admin/Desktop/print-order-agent-mvp-v0.1.0}}"
info="$root/engine/SOURCE_INFO.txt"

if [ ! -f "$info" ]; then
  echo "内置引擎缺少 SOURCE_INFO.txt（先运行 scripts/sync-engine.sh）" >&2
  exit 1
fi

built="$(sed -n 's/^commit: *//p' "$info" | awk '{print $1}')"
worktree="$(sed -n 's/^worktree: *//p' "$info")"
now="$(git -C "$repo" rev-parse --short HEAD 2>/dev/null || echo unknown)"

echo "内置引擎: $built${worktree:+   (同步时工作区: $worktree)}"
echo "本机仓库: $now   ($repo)"
if [ "$built" = "$now" ]; then
  echo "状态: 一致，无需同步"
else
  echo "状态: 不一致 —— 运行 scripts/sync-engine.sh 刷新内置副本"
fi
