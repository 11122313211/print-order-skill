#!/usr/bin/env bash
# 把本技能包发布/推送到 GitHub。
#
# 用法:
#   ./publish.sh                          # 发布到 11122313211/printops-skill（public）
#   ./publish.sh --private                # 私有仓库
#   ./publish.sh someone/other-repo       # 指定仓库
#
# 前置: 先在你自己的终端里登录一次（凭证由 gh 保管，本脚本不接触 token）：
#   gh auth login --hostname github.com --git-protocol https --web
#
# 幂等：仓库已存在就只推送；不存在则创建并推送。
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$here"

slug="11122313211/printops-skill"
visibility="--public"
description="中文商业印刷需求 → 字段可溯源、经人工确认的订单交接单（printops / printops-lite）"

die() { echo "$*" >&2; exit 1; }

while [ "$#" -gt 0 ]; do
  case "$1" in
    --public) visibility="--public"; shift ;;
    --private) visibility="--private"; shift ;;
    -h|--help) sed -n '2,12p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*) die "未知选项：$1" ;;
    *) slug="$1"; shift ;;
  esac
done

case "$slug" in
  */*) : ;;
  *) die "仓库名要写成 owner/name，收到：$slug" ;;
esac

command -v gh >/dev/null 2>&1 || die "未安装 gh（https://cli.github.com/）"
gh auth status >/dev/null 2>&1 || die "gh 未登录。先在终端执行：
  gh auth login --hostname github.com --git-protocol https --web"
git rev-parse --git-dir >/dev/null 2>&1 || die "当前目录不是 git 仓库（先 git init 并提交）"

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "提示：工作区有未提交的改动，本次只会推送已提交的内容。" >&2
fi

branch="$(git branch --show-current)"
[ -n "$branch" ] || die "当前处于游离 HEAD，先切回分支再发布。"

if gh repo view "$slug" >/dev/null 2>&1; then
  echo "仓库已存在：$slug"
  if git remote get-url origin >/dev/null 2>&1; then
    git remote set-url origin "https://github.com/$slug.git"
  else
    git remote add origin "https://github.com/$slug.git"
  fi
  git push -u origin "$branch"
else
  echo "创建仓库并推送：$slug（$visibility）"
  gh repo create "$slug" "$visibility" --source=. --remote=origin --push \
    --description "$description"
fi

echo
echo "已发布: https://github.com/$slug"
gh repo view "$slug" --json url,visibility,defaultBranchRef \
  --template '{{.url}}  {{.visibility}}  {{.defaultBranchRef.name}}{{"\n"}}'
