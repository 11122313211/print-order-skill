#!/usr/bin/env bash
# PrintOps 引擎统一入口。
#
# 这个脚本存在的理由：引擎解析顺序与会话库落点是"一写就错"的确定性步骤，
# 不要让模型在对话里手写路径。正文只要求跑本脚本。
#
# 用法:
#   scripts/printops.sh check                解析引擎，报告根目录/版本/来源/会话库
#   scripts/printops.sh tools                列出引擎工具（L0/L1），权威来源
#   scripts/printops.sh ask [选项] "消息"     调用本地 host 处理一条消息（默认快路径）
#   scripts/printops.sh smoke                只跑 MCP / skill 冒烟
#
# 选项:
#   --session <id>    会话 ID（默认 printops；同一订单/对话固定用同一个）
#   --memory <path>   显式指定会话库（默认按引擎位置自动选可写路径）
#   --engine <path>   显式指定引擎根（优先级高于一切）
#   --with-mcp        走完整 MCP 冒烟（慢，仅契约验收时用）
#
# 引擎解析顺序: --engine → $PRINTOPS_HOME → 默认仓库路径 → 自动查找 → 本技能内置 engine/
# 会话库落点:   --memory → $PRINTOPS_MEMORY → <引擎根>/data（可写时） → $TMPDIR
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill_dir="$(cd "$script_dir/.." && pwd)"

min_version="1.1.0"
default_repo="$HOME/Desktop/print-order-agent-mvp-v0.1.0"
# 自动查找的根目录；/Volumes 等外接卷默认不扫（网络卷会拖慢或挂起）。
# 需要时用 PRINTOPS_SEARCH_ROOTS 覆盖，例如 PRINTOPS_SEARCH_ROOTS="$HOME /Volumes"。
search_roots="${PRINTOPS_SEARCH_ROOTS:-$HOME/Desktop $HOME/Documents $HOME/Projects $HOME/code $HOME/dev $HOME/src}"

engine_override=""
memory_override=""
session_id="${PRINTOPS_SESSION_ID:-printops}"
with_mcp=0

die() { echo "$*" >&2; exit 1; }

is_engine() { [ -f "$1/tools/printops_local_host.py" ] && [ -f "$1/agent.py" ]; }

resolve_engine() {
  local candidate
  # 显式 --engine 是用户的明确指向，无效就是错误，不能悄悄换用别的引擎。
  if [ -n "$engine_override" ]; then
    if is_engine "$engine_override"; then printf '%s\n' "${engine_override%/}"; return 0; fi
    die "--engine $engine_override 不是有效的 PrintOps 引擎根（需要 agent.py 与 tools/printops_local_host.py）。"
  fi
  if [ -n "${PRINTOPS_HOME:-}" ] && ! is_engine "$PRINTOPS_HOME"; then
    echo "warning: PRINTOPS_HOME=$PRINTOPS_HOME 不是有效引擎根，继续按默认顺序查找。" >&2
  fi
  for candidate in "${PRINTOPS_HOME:-}" "$default_repo"; do
    [ -n "$candidate" ] || continue
    if is_engine "$candidate"; then printf '%s\n' "${candidate%/}"; return 0; fi
  done
  local root found
  for root in $search_roots; do
    [ -d "$root" ] || continue
    found="$(find "$root" -maxdepth 4 -name printops_local_host.py -print -quit 2>/dev/null || true)"
    if [ -n "$found" ]; then printf '%s\n' "$(dirname "$(dirname "$found")")"; return 0; fi
  done
  if is_engine "$skill_dir/engine"; then printf '%s\n' "$skill_dir/engine"; return 0; fi
  return 1
}

version_ok() {
  [ -n "$1" ] || return 1
  awk -v have="$1" -v need="$min_version" 'BEGIN {
    n = split(have, h, "."); m = split(need, r, ".");
    for (i = 1; i <= (n > m ? n : m); i++) {
      a = (i <= n ? h[i] + 0 : 0); b = (i <= m ? r[i] + 0 : 0);
      if (a > b) exit 0;
      if (a < b) exit 1;
    }
    exit 0;
  }'
}

writable_dir() {
  local dir="$1" probe
  [ -d "$dir" ] || return 1
  probe="$dir/.printops-write-probe.$$"
  if ( : >"$probe" ) 2>/dev/null; then
    rm -f "$probe" 2>/dev/null || true
    return 0
  fi
  return 1
}

resolve_memory() {
  local root="$1" dir tmp
  if [ -n "$memory_override" ]; then printf '%s\n' "$memory_override"; return 0; fi
  if [ -n "${PRINTOPS_MEMORY:-}" ]; then printf '%s\n' "$PRINTOPS_MEMORY"; return 0; fi
  # 只有真实仓库才把会话库写进它的 data/；技能内置副本一律不写——
  # 技能目录可能被装在云同步位置或只读位置，不该承载真实订单。
  if [ "$is_bundled" -eq 0 ]; then
    dir="$root/data"
    if [ ! -d "$dir" ]; then mkdir -p "$dir" 2>/dev/null || true; fi
    if writable_dir "$dir"; then printf '%s\n' "$dir/agent.sqlite3"; return 0; fi
  fi
  tmp="${TMPDIR:-/tmp}"; tmp="${tmp%/}"
  printf '%s\n' "$tmp/printops-agent.sqlite3"
}

cmd=""
case "${1:-}" in
  check|tools|ask|smoke) cmd="$1"; shift ;;
  ""|-h|--help|help) sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
  *) die "未知子命令：$1（可用：check / tools / ask / smoke）" ;;
esac

while [ "$#" -gt 0 ]; do
  case "$1" in
    --session) session_id="${2:-}"; [ -n "$session_id" ] || die "--session 需要值"; shift 2 ;;
    --memory) memory_override="${2:-}"; [ -n "$memory_override" ] || die "--memory 需要值"; shift 2 ;;
    --engine) engine_override="${2:-}"; [ -n "$engine_override" ] || die "--engine 需要值"; shift 2 ;;
    --with-mcp) with_mcp=1; shift ;;
    --) shift; break ;;
    -*) die "未知选项：$1" ;;
    *) break ;;
  esac
done

engine_root="$(resolve_engine || true)"
[ -n "$engine_root" ] || die "找不到 PrintOps 引擎。请设置 PRINTOPS_HOME，或改用 printops-lite 技能做知识解答（不要编造引擎结论）。"
version="$(cat "$engine_root/VERSION" 2>/dev/null || echo unknown)"
version_ok "$version" || die "引擎版本 $version 低于要求的 ${min_version}（引擎根：${engine_root}）。"
is_bundled=0
[ "$engine_root" = "$skill_dir/engine" ] && is_bundled=1
memory_path="$(resolve_memory "$engine_root")"

case "$cmd" in
  check)
    echo "engineRoot: $engine_root"
    echo "version:    $version"
    echo "python:     $(command -v python3 || echo '缺失')"
    echo "sessionDb:  $memory_path"
    if [ "$is_bundled" -eq 1 ]; then
      echo "source:     技能内置副本（可能落后于仓库）"
      [ -f "$engine_root/SOURCE_INFO.txt" ] && sed 's/^/            /' "$engine_root/SOURCE_INFO.txt"
      case "$memory_path" in
        "$TMPDIR"*|/tmp/*|/var/folders/*)
          echo "hint:       技能内置副本不写技能目录，会话库落在临时目录（重启会清）。"
          echo "           要保留跨天订单，用 --memory <可写目录>/agent.sqlite3 或 PRINTOPS_MEMORY。" ;;
      esac
    else
      echo "source:     本机仓库（最新事实来源）"
    fi
    ;;
  tools)
    ( cd "$engine_root" && python3 - <<'PY'
import mcp_server

for level, names in (("L0", mcp_server.L0_TOOLS), ("L1", mcp_server.L1_TOOLS)):
    for name in sorted(names):
        print(f"{level}  {name:<26} {mcp_server.MCP_TOOL_DESCRIPTIONS.get(name, '')}")
PY
    )
    ;;
  ask)
    [ "$#" -gt 0 ] || die '缺少消息：scripts/printops.sh ask "做500张三折页"'
    message="$*"
    args=(--session-id "$session_id" --memory-path "$memory_path" --message "$message")
    [ "$with_mcp" -eq 1 ] || args+=(--no-mcp)
    ( cd "$engine_root" && python3 tools/printops_local_host.py "${args[@]}" )
    ;;
  smoke)
    ( cd "$engine_root" && python3 tools/dsh_mcp_smoke.py )
    ;;
esac
