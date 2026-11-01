#!/usr/bin/env python3
"""printops skill 冒烟测试（零依赖，纯标准库）。

独立运行:
    python tests/smoke_test.py          # 退出码 0 = 全部通过，1 = 有失败

publish.sh 在打包前调用本文件作为发布门禁。tests/ 位于仓库根、不随
install.sh 进入安装副本（安装副本的验证走 publish.sh 与运行时自检）；
本测试在自身创建的临时目录里驱动 printops_cli.py，不读写仓库与技能目录。
"""
from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
CLI = REPO / "printops" / "scripts" / "printops_cli.py"

failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "ok" if condition else "FAIL"
    print(f"  [{status}] {label}" + (f"：{detail}" if detail and not condition else ""))
    if not condition:
        failures.append(label)


def run_cli(cwd: pathlib.Path, *args: str) -> dict:
    out = subprocess.run([sys.executable, str(CLI), *args], cwd=cwd,
                         capture_output=True, text=True, encoding="utf-8")
    assert out.returncode == 0, (args, out.stderr)
    return json.loads(out.stdout)


def smoke_catalog(cwd: pathlib.Path) -> None:
    print("catalog：品类清单")
    data = run_cli(cwd, "catalog")
    check("ok 且 18 个品类", data["ok"] and len(data["products"]) == 18)
    check("知识版本随输出返回", data.get("knowledgeVersion") == "2026.09.05",
          str(data.get("knowledgeVersion")))


def smoke_full_flow(cwd: pathlib.Path) -> None:
    print("完整订单流：ingest→set→price→quote→handoff→reset")
    ingest = run_cli(cwd, "ingest", "--text", "印1000张名片，90×54mm，双面四色")
    check("识别品类与字段", ingest["ok"] and ingest["order"]["productType"] == "名片"
          and ingest["order"]["quantityValue"] == 1000)
    check("弱推断被标记", isinstance(ingest.get("lowConfidence"), dict))
    run_cli(cwd, "set", "--field", "paper=300g铜版纸")
    estimate = run_cli(cwd, "price")["estimate"]
    check("估价 schema 2.0", estimate["schemaVersion"] == "2.0")
    check("估价就绪", estimate["status"] == "ready", estimate["status"])
    check("区间以 ¥ 呈现", estimate["displayRange"].startswith("¥"),
          estimate["displayRange"])
    check("计价假设可转达", isinstance(estimate.get("assumptions"), list)
          and estimate["assumptions"])
    quote = run_cli(cwd, "quote")["quote"]
    check("询价停在人工确认", quote["status"] == "awaiting_human_confirmation")
    handoff = run_cli(cwd, "handoff", "--out", "冒烟交接单.md")
    check("交接单就绪且需人工确认", handoff["status"] == "ready"
          and handoff["requiresHumanConfirmation"] is True)
    check("交接单文件非空",
          (cwd / "冒烟交接单.md").stat().st_size > 0)
    check("reset 删除订单", run_cli(cwd, "reset")["ok"])


def smoke_multi_product(cwd: pathlib.Path) -> None:
    print("多产品拆单：名片+纸杯")
    detect = run_cli(cwd, "ingest", "--text", "做500张名片和200个纸杯")
    check("检测为多产品", detect.get("multiProduct") is True
          and detect.get("hint"))
    card = run_cli(cwd, "ingest", "--file", "名片.json", "--text",
                   "做500张名片和200个纸杯", "--pick-item", "0")
    cup = run_cli(cwd, "ingest", "--file", "纸杯.json", "--text",
                  "做500张名片和200个纸杯", "--pick-item", "1")
    check("拆单0=名片500张", card["order"]["productType"] == "名片"
          and card["order"]["quantityValue"] == 500)
    check("拆单1=纸杯200个", cup["order"]["productType"] == "纸杯"
          and cup["order"]["quantityValue"] == 200)


def smoke_terms(cwd: pathlib.Path) -> None:
    print("terms：术语解释")
    data = run_cli(cwd, "terms", "哑粉纸和铜版纸有什么区别")
    check("解释可用且带知识版本", data["ok"] and bool(data.get("answer"))
          and data.get("knowledgeVersion") == "2026.09.05")


def main() -> int:
    if not CLI.exists():
        print(f"error: 找不到 {CLI}", file=sys.stderr)
        return 1
    cwd = pathlib.Path(tempfile.mkdtemp(prefix="printops-smoke-"))
    try:
        smoke_catalog(cwd)
        smoke_full_flow(cwd)
        smoke_multi_product(cwd)
        smoke_terms(cwd)
    finally:
        shutil.rmtree(cwd, ignore_errors=True)
    if failures:
        print(f"\n{len(failures)} 项失败：{', '.join(failures)}", file=sys.stderr)
        return 1
    print("\n全部通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
