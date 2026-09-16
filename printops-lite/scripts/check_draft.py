#!/usr/bin/env python3
"""校验 printops-lite 产出的订单草稿 JSON：字段白名单、置信度、证据、verified 口径。

权威口径见 references/order-contract.md；本脚本是它的可执行镜像（知识快照 2026.09.05）。
它只做确定性检查，不判断语义是否正确。

用法:
    python3 scripts/check_draft.py draft.json
    echo '<json>' | python3 scripts/check_draft.py -

退出码: 0 = 无 error（可能有 warning）；1 = 有 error；2 = 输入不是合法 JSON。
"""

from __future__ import annotations

import json
import sys
from typing import Any

KNOWLEDGE_VERSION = "2026.09.05"

# 与 references/order-contract.md 的字段白名单同步。
ORDER_FIELDS = {
    "productType", "productTypes", "items", "purpose", "quantity", "quantityValue",
    "quantityUnit", "size", "dimensions", "pages", "orientation", "paper", "printing",
    "finishing", "binding", "deadline", "budget", "platform", "productSpecs",
}
ITEM_ONLY_FIELDS = {"itemId", "selectedOption", "orderGenerated", "uploadedFile", "itemIndex"}
REQUIRED_FIELDS = ("productType", "quantity", "size", "paper", "printing", "deadline")
TOP_LEVEL_KEYS = {"patch", "evidence", "confidence", "questions", "risks",
                  "knowledgeVersion", "verified"}
EVIDENCE_SOURCES = {"user", "rule", "model", "recommendation", "system"}
CONFIDENCE_BLOCK = 0.75

errors: list[str] = []
warnings: list[str] = []


def error(message: str) -> None:
    errors.append(message)


def warn(message: str) -> None:
    warnings.append(message)


def check_patch(patch: Any) -> None:
    if not isinstance(patch, dict):
        error("patch 必须是对象")
        return
    unknown = sorted(set(patch) - ORDER_FIELDS)
    if unknown:
        error(f"patch 含白名单外的字段（必须拒绝，不得写入订单）: {', '.join(unknown)}")
    specs = patch.get("productSpecs")
    if specs is not None:
        if not isinstance(specs, dict):
            error("patch.productSpecs 必须是对象")
        elif not patch.get("productType"):
            warn("patch.productSpecs 非空但缺 productType，无法按品类档案校验专属 key")
    items = patch.get("items")
    if items is not None:
        if not isinstance(items, list):
            error("patch.items 必须是数组")
            return
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                error(f"patch.items[{index}] 必须是对象")
                continue
            bad = sorted(set(item) - ORDER_FIELDS - ITEM_ONLY_FIELDS)
            if bad:
                error(f"patch.items[{index}] 含白名单外的字段: {', '.join(bad)}")
            if not item.get("itemId"):
                warn(f"patch.items[{index}] 缺少稳定 itemId")


def check_confidence(confidence: Any) -> None:
    if confidence is None:
        warn("缺少 confidence：弱推断字段必须标低置信度，否则会被当成已确认")
        return
    if not isinstance(confidence, dict):
        error("confidence 必须是对象（字段 → 0..1）")
        return
    unknown = sorted(set(confidence) - ORDER_FIELDS)
    if unknown:
        warn(f"confidence 含白名单外的字段: {', '.join(unknown)}")
    for field, value in confidence.items():
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            error(f"confidence.{field} 必须是数字")
        elif not 0.0 <= float(value) <= 1.0:
            error(f"confidence.{field} = {value} 超出 0..1")
        elif float(value) < CONFIDENCE_BLOCK:
            warn(f"confidence.{field} = {value} < {CONFIDENCE_BLOCK}：该字段视为未确认，必须变成追问，不得进入交接单")


def check_evidence(evidence: Any, patch: Any) -> None:
    if evidence is None:
        warn("缺少 evidence：每个生产字段都应有用户原话出处")
        return
    if not isinstance(evidence, list):
        error("evidence 必须是数组")
        return
    covered = set()
    for index, entry in enumerate(evidence):
        if not isinstance(entry, dict):
            error(f"evidence[{index}] 必须是对象")
            continue
        field = entry.get("field")
        if not field:
            error(f"evidence[{index}] 缺少 field")
        else:
            covered.add(field)
        source = entry.get("source")
        if source not in EVIDENCE_SOURCES:
            error(f"evidence[{index}].source = {source!r} 不在 {sorted(EVIDENCE_SOURCES)}")
        if not entry.get("quote"):
            warn(f"evidence[{index}] 缺少 quote（用户原话），无法溯源")
    if isinstance(patch, dict):
        filled = [key for key, value in patch.items()
                  if value not in (None, "", [], {}) and key not in ITEM_ONLY_FIELDS]
        missing = sorted(set(filled) - covered)
        if missing:
            warn(f"这些已填字段没有 evidence: {', '.join(missing)}")


def check_required(patch: Any) -> None:
    if not isinstance(patch, dict):
        return
    missing = [field for field in REQUIRED_FIELDS if not patch.get(field)]
    if missing:
        warn(f"必填字段仍缺失（应作为 questions 追问）: {', '.join(missing)}")


def check_draft(draft: Any) -> None:
    if not isinstance(draft, dict):
        error("草稿必须是 JSON 对象")
        return
    unknown = sorted(set(draft) - TOP_LEVEL_KEYS)
    if unknown:
        warn(f"顶层含契约外的键（会被忽略）: {', '.join(unknown)}")
    if draft.get("verified") is not False:
        error("verified 必须固定为 false：lite 版结论未经引擎校验")
    version = draft.get("knowledgeVersion")
    if version != KNOWLEDGE_VERSION:
        warn(f"knowledgeVersion = {version!r}，当前知识快照是 {KNOWLEDGE_VERSION}")
    check_patch(draft.get("patch"))
    check_confidence(draft.get("confidence"))
    check_evidence(draft.get("evidence"), draft.get("patch"))
    check_required(draft.get("patch"))


def main(argv: list[str]) -> int:
    if len(argv) > 2 or (len(argv) == 2 and argv[1] in ("-h", "--help")):
        print(__doc__.strip())
        return 0 if len(argv) == 2 else 2
    if len(argv) == 2 and argv[1] != "-":
        try:
            raw = open(argv[1], encoding="utf-8").read()
        except OSError as exc:
            print(f"读不到 {argv[1]}: {exc}", file=sys.stderr)
            return 2
    else:
        raw = sys.stdin.read()
    try:
        draft = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"不是合法 JSON: {exc}", file=sys.stderr)
        return 2

    check_draft(draft)
    for message in warnings:
        print(f"warning: {message}")
    for message in errors:
        print(f"error: {message}")
    print(f"\n结果: {len(errors)} 个 error, {len(warnings)} 个 warning")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
