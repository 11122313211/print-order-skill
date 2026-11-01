#!/usr/bin/env python3
"""对齐检查/同步：print-order-skill 的引擎快照 ↔ PrintOps 上游仓库。

用法:
    python3 sync_upstream.py [--upstream <PrintOps 路径>] [--apply]

不带 --apply 时只做对齐检查，发现漂移即退出码 1（可作发布门禁）：
- 上游 HEAD 与 SOURCE_INFO.txt 记录的基线 commit 是否一致；
- 快照文件正文与上游 HEAD blob 逐字比对（行尾归一化）；
- 依赖闭包检查：快照模块 import 的"上游根目录本地模块"是否都已纳入快照
  ——上游把函数拆成新兄弟模块时自动发现（v1.3.0 拆分事件的教训）。

--apply 时把漂移文件按上游 HEAD 重新蒸馏（加基线头注释）、重写 SOURCE_INFO.txt
的动态字段。printops_cli.py / SKILL.md 是 skill 自有文件，同步永不触碰；
同步后必须运行 publish.sh 做全链路冒烟（CLI 与新引擎的 API 兼容由它把关）。
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent
SCRIPTS = REPO / "printops" / "scripts"
SOURCE_INFO = SCRIPTS / "SOURCE_INFO.txt"
SOURCE_REPO = "https://github.com/11122313211/PrintOps"
CORE_MODULES = ("nlu.py", "order_model.py", "tools.py",
                "product_knowledge.py", "supplier_adapters.py")
IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+([A-Za-z_][A-Za-z0-9_]*)", re.M)
HEADER_LINE = "# PrintOps v{version} snapshot (upstream 11122313211/PrintOps@{sha}, synced {today}).\n"


def git(upstream: Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(upstream), *args],
                         capture_output=True, text=True, encoding="utf-8")
    if out.returncode != 0:
        fail(f"git -C {upstream} {' '.join(args)} 失败：{out.stderr.strip()}")
    return out.stdout


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    sys.exit(1)


def normalize(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").removesuffix("\n")


def upstream_head(upstream: Path) -> str:
    return git(upstream, "rev-parse", "--short", "HEAD").strip()


def upstream_version(upstream: Path) -> str:
    return (upstream / "VERSION").read_text(encoding="utf-8").strip()


def snapshot_set(upstream: Path) -> set[str]:
    """核心五模块 + 传递 import 闭包（只收上游根目录真实存在的本地模块）。"""
    files: set[str] = set()
    queue = list(CORE_MODULES)
    while queue:
        name = queue.pop()
        if name in files:
            continue
        files.add(name)
        blob = normalize(git(upstream, "show", f"HEAD:{name}"))
        for module in dict.fromkeys(IMPORT_RE.findall(blob)):
            if (upstream / f"{module}.py").exists():
                queue.append(f"{module}.py")
    return files


def skill_body(path: Path) -> str:
    lines = path.read_text(encoding="utf-8").split("\n")
    return normalize("\n".join(lines[1:]))  # 首行是基线头注释


def parse_baseline() -> tuple[str, str]:
    text = SOURCE_INFO.read_text(encoding="utf-8")
    version = re.search(r"^upstreamVersion:\s*(\S+)", text, re.M)
    commit = re.search(r"^upstreamCommit:\s*(\S+)", text, re.M)
    if not (version and commit):
        fail(f"{SOURCE_INFO} 缺少 upstreamVersion/upstreamCommit 记录")
    return version.group(1), commit.group(1)


def check(upstream: Path, do_sync: bool) -> int:
    head = upstream_head(upstream)
    version = upstream_version(upstream)
    baseline_version, baseline_commit = parse_baseline()
    print(f"上游 {upstream}")
    print(f"  HEAD {head}（VERSION {version}）｜快照基线 {baseline_commit}（v{baseline_version}）")
    drift = head != baseline_commit or version != baseline_version
    print(f"  基线{'漂移' if drift else '一致'}")

    wanted = snapshot_set(upstream)
    missing_files = sorted(name for name in wanted if not (SCRIPTS / name).exists())
    if missing_files:
        print(f"  闭包缺文件：{', '.join(missing_files)}")
        drift = True

    changed: list[str] = []
    for name in sorted(wanted & {p.name for p in SCRIPTS.glob("*.py")}):
        want = normalize(git(upstream, "show", f"HEAD:{name}"))
        if skill_body(SCRIPTS / name) != want:
            changed.append(name)
    if changed:
        print(f"  正文漂移：{', '.join(changed)}")
        drift = True
    if not drift:
        print("对齐：快照与上游 HEAD 逐字一致，闭包完整。")
        return 0

    if not do_sync:
        print("存在漂移：运行 `python3 sync_upstream.py --apply` 重新蒸馏，"
              "随后必须运行 publish.sh 全链路冒烟。")
        return 1
    return sync(upstream, wanted, version, head)


def sync(upstream: Path, wanted: set[str], version: str, head: str) -> int:
    header = HEADER_LINE.format(version=version, sha=head, today=date.today().isoformat())
    for name in sorted(wanted):
        blob = normalize(git(upstream, "show", f"HEAD:{name}"))
        (SCRIPTS / name).write_text(header + blob + "\n", encoding="utf-8", newline="\n")
        print(f"  已蒸馏 {name}")

    card = SCRIPTS / "rate_cards" / "cn-local-reference.json"
    if (upstream / "rate_cards" / "cn-local-reference.json").exists():
        card.write_bytes(git(upstream, "show", "HEAD:rate_cards/cn-local-reference.json")
                         .encode("utf-8"))
        print("  已同步 rate_cards/cn-local-reference.json")

    sys.path.insert(0, str(SCRIPTS))
    import product_knowledge  # 读刚蒸馏副本里的版本号，保证 SOURCE_INFO 与文件一致
    extras = sorted(wanted - set(CORE_MODULES))
    SOURCE_INFO.write_text(
        f"sourceRepo: {SOURCE_REPO}\n"
        f"upstreamVersion: {version}\n"
        f"upstreamCommit: {head}\n"
        f"syncedAt: {date.today().isoformat()}\n"
        f"knowledgeVersion: {product_knowledge.KNOWLEDGE_VERSION}\n"
        f"priceModelVersion: {product_knowledge.PRICE_MODEL_VERSION}\n"
        "files:\n" + "".join(f"  - {name}\n" for name in sorted(wanted)) +
        "data:\n  - rate_cards/cn-local-reference.json\n"
        "note: 以上文件为上游引擎模块快照（仅文件头加一行基线注释，逻辑未改）；\n"
        "  集合 = 核心五模块 + 传递 import 闭包（sync_upstream.py 自动推导，\n"
        "  上游拆分新兄弟模块时自动纳入）；rate_cards/ 为估价费率卡数据，\n"
        "  由 pricing_engine.DEFAULT_RATE_CARD 按\"模块同级 rate_cards/ 目录\"解析。\n"
        "  其余文件（printops_cli.py、SKILL.md）为 skill 自有代码。\n"
        "license: MIT（上游 LICENSE 见 https://github.com/11122313211/PrintOps）；\n"
        "  品类口径参考盛大印刷公开产品导航（sd2000.com）等公开信息整理。\n"
        "syncCheck: 比对上游对应路径文件头注释中的 commit 与本文件是否一致；\n"
        "  上游升级后运行 sync_upstream.py --sync 并回归 publish.sh 全链路冒烟。\n",
        encoding="utf-8", newline="\n")
    print(f"  SOURCE_INFO.txt → v{version}@{head}（快照 {len(wanted)} 个文件，"
          f"闭包新增 {', '.join(extras) if extras else '无'}）")
    print("同步完成。必须运行 publish.sh 做全链路冒烟后再提交。")
    return 0


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    default_upstream = REPO.parent / "PrintOps-main"
    parser.add_argument("--upstream", type=Path, default=default_upstream,
                        help=f"PrintOps 上游仓库路径（默认 {default_upstream}，"
                             "可用环境变量 PRINTOPS_UPSTREAM 覆盖默认值）")
    parser.add_argument("--apply", action="store_true", help="重新蒸馏漂移文件并更新基线记录")
    args = parser.parse_args()
    upstream = Path(args.upstream)
    if not (upstream / ".git").is_dir():
        fail(f"上游仓库不存在：{upstream}")
    return check(upstream, args.apply)


if __name__ == "__main__":
    raise SystemExit(main())
