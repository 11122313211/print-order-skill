#!/usr/bin/env bash
# 从 PrintOps 仓库同步内置引擎副本（技能包维护者用）。
# 用法: scripts/sync-engine.sh [仓库路径]   默认取 $PRINTOPS_HOME 或标准路径
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
repo="${1:-${PRINTOPS_HOME:-/Users/Admin/Desktop/print-order-agent-mvp-v0.1.0}}"
engine="$root/engine"

if [ ! -f "$repo/agent.py" ] || [ ! -f "$repo/tools/printops_local_host.py" ]; then
  echo "不是 PrintOps 仓库：$repo" >&2
  echo "用法: scripts/sync-engine.sh [仓库路径]" >&2
  exit 1
fi

modules=(agent.py nlu.py order_model.py product_knowledge.py tools.py supplier_adapters.py llm_adapter.py mcp_server.py)
scripts=(printops_local_host.py dsh_mcp_smoke.py dsh_mcp_launcher.py)

mkdir -p "$engine/tools" "$engine/data"
for name in "${modules[@]}"; do cp "$repo/$name" "$engine/$name"; done
for name in "${scripts[@]}"; do cp "$repo/tools/$name" "$engine/tools/$name"; done
rm -rf "$engine/.dsh/skills"
mkdir -p "$engine/.dsh"
cp -R "$repo/.dsh/skills" "$engine/.dsh/skills"
if [ -f "$repo/VERSION" ]; then cp "$repo/VERSION" "$engine/VERSION"; fi
if [ -f "$repo/LICENSE" ]; then cp "$repo/LICENSE" "$engine/LICENSE"; fi

commit="$(git -C "$repo" rev-parse --short HEAD 2>/dev/null || echo unknown)"
worktree="clean"
if [ -n "$(git -C "$repo" status --porcelain 2>/dev/null)" ]; then worktree="dirty"; fi

{
  echo "sourceRepo: $repo"
  echo "version: $(cat "$engine/VERSION" 2>/dev/null || echo unknown)"
  echo "commit: $commit"
  echo "worktree: $worktree"
  echo "syncedAt: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$engine/SOURCE_INFO.txt"

echo "已同步内置引擎："
cat "$engine/SOURCE_INFO.txt"

# 同步后立即做一次冒烟，避免把坏副本带进技能包。
if [ -f "$engine/tools/dsh_mcp_smoke.py" ]; then
  echo
  echo "冒烟检查："
  if python3 "$engine/tools/dsh_mcp_smoke.py" >/dev/null 2>&1; then
    echo "  通过：MCP stdio / L0 工具边界"
  else
    echo "  失败：请先修复仓库，再重新同步（副本未通过冒烟）" >&2
    exit 1
  fi
fi
