#!/usr/bin/env python3
# PrintOps skill CLI — 基于上游 11122313211/PrintOps@7226a25（v1.3.0）核心模块，同步日期 2026-11-01。
# 基线指纹与同步说明见同目录 SOURCE_INFO.txt。
"""PrintOps CLI：印刷订单智能体的确定性内核。

把 PrintOps 的规则感知（nlu）、订单契约（order_model）、8 个白名单工具
（tools）和品类知识库（product_knowledge）封装成命令行接口，供 skill 编排：
模型负责对话与呈现，字段抽取、校验、方案、估价、交接单全部走本地确定性
规则计算。全部计算在本机完成，无网络请求、无第三方依赖（Python 3.9+）。

状态文件（--file，默认 ./printops-order.json）结构：
    {"schemaVersion": 1, "knowledgeVersion": "...",
     "order": {...订单字段...},
     "meta": {"lowConfidence": {...}, "selectedPlan": {...}}}

路径边界（与 a-share skill 的输出外置规范一致）：
- 所有路径先在原始输入上拒绝 ``..``，再经 Path.resolve() 规范化；
- 写操作（订单状态、交接单输出）只允许落在当前工作目录子树内，
  订单状态绝不写回 skill 目录。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from nlu import perceive
from order_model import (DIMENSION_DEFAULTS, DIMENSION_LABELS, LABELS,
                         ORDER_DEFAULTS, normalize_order_dimensions,
                         normalize_order_quantity)
from product_knowledge import (KNOWLEDGE_VERSION, PRICE_MODEL_VERSION,
                               parameter_state, profile_for)
from tools import (estimate_price, explain_print_term, match_supplier_capability,
                   preflight_file, prepare_handoff, recommend_processes,
                   request_supplier_quote, validate_order)
from supplier_adapters import PLATFORMS

STATE_VERSION = 1
CONFIRM_THRESHOLD = 0.75  # PrintOps 规则：低于该置信度的字段必须人工确认
SKIP_PATCH_KEYS = ("items", "productTypes")
PLAN_IDS = ("economy", "balanced", "premium")
# 数量串是否自带单位：裸数字（如"数量改成1200"）不应覆盖已确认的数量单位
QUANTITY_UNIT_IN_TEXT = (r"[0-9]\s*(?:万|千|百)?\s*"
                         r"(?:平方米|平米|㎡|份|本|册|张|个|件|盒|套|包|箱|杯|块|枚)")


def emit(payload: dict, exit_code: int = 0) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=1))
    sys.exit(exit_code)


def fail(message: str) -> None:
    emit({"ok": False, "error": message}, 1)


def safe_path(path: str, for_write: bool = False) -> Path:
    """校验并规范化调用方提供的文件路径。

    先在原始输入上显式拒绝任何 ``..``，再经 Path.resolve() 折叠成绝对路径；
    写操作额外限制在当前工作目录子树内，防止订单状态或交接单被写到
    工作目录之外（skill 目录保持只读）。
    """
    raw = str(path).strip()
    if not raw:
        fail("路径不能为空。")
    if ".." in Path(raw).parts:
        fail(f"路径不允许包含 ..：{path}")
    resolved = Path(raw).expanduser().resolve()
    if for_write:
        cwd = Path.cwd().resolve()
        try:
            inside = resolved.is_relative_to(cwd)
        except (ValueError, OSError):  # 跨盘符等无公共父目录的情形
            inside = False
        if not inside:
            fail(f"写入路径必须位于当前工作目录内（{cwd}）：{path}")
    return resolved


def load_state(path: str) -> dict | None:
    state_file = safe_path(path)
    if not state_file.is_file():
        return None
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        fail(f"订单文件损坏或不可读（{state_file}）：{exc}。可重命名留档后用 ingest 重新建单。")
    if not isinstance(state, dict) or not isinstance(state.get("order"), dict):
        fail(f"订单文件格式异常（{state_file}），缺少 order 对象。")
    state.setdefault("meta", {})
    state["meta"].setdefault("lowConfidence", {})
    state["meta"].setdefault("selectedPlan", None)
    return state


def save_state(path: str, state: dict) -> None:
    state["schemaVersion"] = STATE_VERSION
    state["knowledgeVersion"] = KNOWLEDGE_VERSION
    state_file = safe_path(path, for_write=True)
    state_file.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def new_state() -> dict:
    return {"schemaVersion": STATE_VERSION,
            "knowledgeVersion": KNOWLEDGE_VERSION,
            "order": deepcopy(ORDER_DEFAULTS),
            "meta": {"lowConfidence": {}, "selectedPlan": None, "fieldMeta": {}}}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def record_field(meta: dict, path: str, value, source: str, confidence: float) -> None:
    """登记字段溯源（简化版 fieldMeta）：最后一次写入的值、来源、置信度与时间。"""
    meta.setdefault("fieldMeta", {})[path] = {
        "value": value, "source": source,
        "confidence": round(float(confidence), 2), "updatedAt": _now()}


def compact_order(order: dict) -> dict:
    out = {}
    for key, value in order.items():
        if key == "dimensions":
            dims = {dk: dv for dk, dv in value.items() if dv}
            if dims:
                out[key] = dims
        elif key == "productSpecs":
            if value:
                out[key] = value
        elif value not in ("", None, [], {}):
            out[key] = value
    return out


def slim_validation(validation: dict) -> dict:
    profile = validation.get("productProfile") or {}
    parameters = [{"key": item.get("key"), "label": item.get("label"),
                   "value": item.get("value", ""), "filled": item.get("filled", False),
                   "required": item.get("required", False),
                   "question": item.get("question", "")}
                  for item in profile.get("parameters", []) if item.get("key")]
    return {"ok": validation.get("ok"),
            "missing": validation.get("missing", []),
            "productMissing": validation.get("productMissing", []),
            "warnings": validation.get("warnings", []),
            "suggestions": validation.get("suggestions", []),
            "risks": validation.get("risks", []),
            "readiness": validation.get("readiness"),
            "productReadiness": profile.get("readiness"),
            "minQuantity": profile.get("minQuantity"),
            "parameters": parameters,
            "multiProduct": validation.get("multiProduct"),
            "knowledgeVersion": validation.get("knowledgeVersion")}


def text_has_quantity_unit(text: str, value) -> bool:
    """检查用户原话中该数量数字后面是否紧跟单位（区分显式单位与品类默认单位）。"""
    normalized = unicodedata.normalize("NFKC", text or "")
    num = str(int(value)) if isinstance(value, (int, float)) and float(value).is_integer() else str(value)
    for match in re.finditer(re.escape(num), normalized):
        tail = normalized[match.end():match.end() + 3]
        if re.match(r"\s*(?:万|千|百)?\s*(?:平方米|平米|㎡|份|本|册|张|个|件|盒|套|包|箱|杯|块|枚)", tail):
            return True
    return False


def merge_patch(order: dict, meta: dict, patch: dict, confidence: dict,
                unit_explicit: bool | None = None) -> list[str]:
    """把 perceive 输出合并进订单；返回发生变化的字段路径列表。

    ``unit_explicit`` 为 True/False 时表示调用方已在用户原话层面判断过
    数量是否自带单位；None 时退回检查 patch 显示串。
    """
    changed: list[str] = []
    low = meta.setdefault("lowConfidence", {})
    pre_product = order.get("productType")
    pre_unit = order.get("quantityUnit")
    pre_value = order.get("quantityValue")
    for key, value in patch.items():
        if value in (None, "", [], {}):
            continue
        if key == "productSpecs" and isinstance(value, dict):
            specs = order.setdefault("productSpecs", {})
            for sk, sv in value.items():
                if sv not in (None, "", [], {}) and specs.get(sk) != sv:
                    specs[sk] = sv
                    changed.append(f"productSpecs.{sk}")
                    record_field(meta, f"productSpecs.{sk}", sv, "rule",
                                 confidence.get(f"productSpecs.{sk}", confidence.get(sk, 0.85)))
            continue
        if key == "dimensions" and isinstance(value, dict):
            dims = order.setdefault("dimensions", deepcopy(DIMENSION_DEFAULTS))
            for dk, dv in value.items():
                if dv and dk in dims and dims.get(dk) != dv:
                    dims[dk] = dv
                    changed.append(f"dimensions.{dk}")
                    record_field(meta, f"dimensions.{dk}", dv, "rule",
                                 confidence.get(f"dimensions.{dk}", 0.9))
                    if dk == "finishedSize":
                        order["size"] = dv
            continue
        if key not in ORDER_DEFAULTS:
            continue
        if order.get(key) != value:
            order[key] = value
            changed.append(key)
        level = confidence.get(key, 0.85)
        if changed and changed[-1] == key:
            record_field(meta, key, value, "rule", level)
        if level >= CONFIRM_THRESHOLD:
            low.pop(key, None)
        elif changed and changed[-1] == key:
            low[key] = {"value": value, "confidence": level}
    normalize_order_quantity(order)
    explicit = (unit_explicit if unit_explicit is not None
                else bool(re.search(QUANTITY_UNIT_IN_TEXT, str(patch.get("quantity") or ""))))
    if (pre_unit and pre_value is not None and order.get("quantityValue") != pre_value
            and order.get("productType") == pre_product and not explicit):
        # 裸数字改数量：沿用订单原单位，避免被品类默认单位覆盖（1200 本 -> 1200 份）
        count = order.get("quantityValue")
        count_text = str(int(count)) if isinstance(count, (int, float)) and float(count).is_integer() else str(count)
        order["quantityUnit"] = pre_unit
        order["quantity"] = f"{count_text} {pre_unit}"
        normalize_order_quantity(order)
        record_field(meta, "quantity", order["quantity"], "rule", confidence.get("quantity", 0.85))
        record_field(meta, "quantityUnit", pre_unit, "rule", confidence.get("quantity", 0.85))
    normalize_order_dimensions(order)
    # 低置信度登记与当前值不一致即视为已处理
    for key in list(low):
        if order.get(key) != low[key].get("value"):
            low.pop(key)
    return changed


def cmd_ingest(args) -> None:
    state = load_state(args.file) or new_state()
    order, meta = state["order"], state["meta"]
    patch, confidence = perceive(args.text, product_hint=str(order.get("productType") or ""))
    items = patch.get("items") if isinstance(patch.get("items"), list) else []
    if len(items) > 1 and args.pick_item is None:
        emit({"ok": False, "multiProduct": True,
              "detected": patch.get("productTypes") or [item.get("productType") for item in items],
              "items": [{"index": idx, "productType": item.get("productType", ""),
                         "quantity": item.get("quantity", "")}
                        for idx, item in enumerate(items)],
              "hint": ("检测到多个印刷品。请为每种产品分别建单：对同一句需求分别执行 ingest，"
                       "各指向不同的 --file 并加 --pick-item 0 / --pick-item 1；"
                       "之后的追问、方案和交接单也按订单文件分别进行。")})
        return
    changed = merge_patch(order, meta,
                          {key: value for key, value in patch.items() if key not in SKIP_PATCH_KEYS},
                          confidence,
                          unit_explicit=(text_has_quantity_unit(args.text, patch.get("quantityValue"))
                                         if patch.get("quantity") is not None else None))
    if items:
        idx = args.pick_item if args.pick_item is not None else 0
        if not isinstance(idx, int) or not 0 <= idx < len(items):
            fail(f"--pick-item 无效：可用范围 0-{len(items) - 1}。")
        # 单项拆分：产品项字段优先于句级共享字段
        for key, value in items[idx].items():
            if value not in (None, "", [], {}):
                for path in merge_patch(order, meta, {key: value}, {key: 0.85}):
                    if path not in changed:
                        changed.append(path)
    save_state(args.file, state)
    validation = validate_order(order)
    profile = validation.get("productProfile") or {}
    questions = [item.get("question", "") for item in profile.get("missing", []) if item.get("question")]
    field_meta = meta.get("fieldMeta", {})
    emit({"ok": True, "file": args.file, "changed": changed,
          "order": compact_order(order),
          "lowConfidence": meta.get("lowConfidence", {}),
          "fieldMeta": {path: field_meta[path] for path in changed if path in field_meta},
          "validation": slim_validation(validation),
          "nextQuestions": questions,
          "knowledgeVersion": KNOWLEDGE_VERSION})


def cmd_status(args) -> None:
    state = load_state(args.file)
    if state is None:
        emit({"ok": False, "error": f"未找到订单文件（{args.file}）。请先对用户的印刷需求执行 ingest 建单。"})
        return
    order, meta = state["order"], state["meta"]
    validation = validate_order(order)
    profile = validation.get("productProfile") or {}
    questions = [item.get("question", "") for item in profile.get("missing", []) if item.get("question")]
    emit({"ok": True, "file": args.file, "order": compact_order(order),
          "lowConfidence": meta.get("lowConfidence", {}),
          "selectedPlan": meta.get("selectedPlan"),
          "fieldMeta": meta.get("fieldMeta", {}),
          "validation": slim_validation(validation),
          "nextQuestions": questions, "knowledgeVersion": KNOWLEDGE_VERSION})


def _parse_field_args(pairs: list[str]) -> list[tuple[str, str]]:
    fields = []
    for pair in pairs:
        key, sep, value = pair.partition("=")
        key, value = key.strip(), value.strip()
        if not sep or not key or not value:
            fail(f"--field 需要 key=value 形式，收到：{pair!r}")
        fields.append((key, value))
    return fields


def cmd_set(args) -> None:
    state = load_state(args.file)
    if state is None:
        fail(f"未找到订单文件（{args.file}）。请先执行 ingest 建单。")
    order, meta = state["order"], state["meta"]
    changed = []
    for key, value in _parse_field_args(args.field):
        if key.startswith("dimensions."):
            sub = key.split(".", 1)[1]
            if sub not in DIMENSION_DEFAULTS:
                fail(f"未知尺寸语义：{key}。可用：{'、'.join(DIMENSION_DEFAULTS)}（如 dimensions.finishedSize=210×285mm）")
            dims = order.setdefault("dimensions", deepcopy(DIMENSION_DEFAULTS))
            if dims.get(sub) != value:
                dims[sub] = value
                changed.append(key)
            if sub == "finishedSize":
                order["size"] = value
        elif key in ORDER_DEFAULTS and key not in ("items", "productTypes", "productSpecs", "dimensions"):
            if order.get(key) != value:
                order[key] = value
                changed.append(key)
        else:
            fail(f"未知订单字段：{key}。顶层字段可用：{'、'.join(k for k in ORDER_DEFAULTS if k not in ('items', 'productTypes', 'productSpecs', 'dimensions'))}，或 dimensions.<语义>。")
        meta.get("lowConfidence", {}).pop(key, None)
    normalize_order_quantity(order)
    normalize_order_dimensions(order)
    for path in changed:
        if path.startswith("dimensions."):
            record_field(meta, path, order["dimensions"][path.split(".", 1)[1]], "user", 1.0)
        else:
            record_field(meta, path, order.get(path), "user", 1.0)
    save_state(args.file, state)
    validation = validate_order(order)
    profile = validation.get("productProfile") or {}
    questions = [item.get("question", "") for item in profile.get("missing", []) if item.get("question")]
    field_meta = meta.get("fieldMeta", {})
    emit({"ok": True, "file": args.file, "changed": changed,
          "order": compact_order(order),
          "lowConfidence": meta.get("lowConfidence", {}),
          "fieldMeta": {path: field_meta[path] for path in changed if path in field_meta},
          "validation": slim_validation(validation),
          "nextQuestions": questions, "knowledgeVersion": KNOWLEDGE_VERSION})


def cmd_set_spec(args) -> None:
    state = load_state(args.file)
    if state is None:
        fail(f"未找到订单文件（{args.file}）。请先执行 ingest 建单。")
    order, meta = state["order"], state["meta"]
    specs = order.setdefault("productSpecs", {})
    changed = []
    for key, value in _parse_field_args(args.field):
        if key in DIMENSION_DEFAULTS:
            fail(f"{key} 是尺寸语义字段，请用 set dimensions.{key}={value}（尺寸语义有单一落位，不进 productSpecs）。")
        if specs.get(key) != value:
            specs[key] = value
            changed.append(f"productSpecs.{key}")
        meta.get("lowConfidence", {}).pop(key, None)
    normalize_order_dimensions(order)
    for path in changed:
        record_field(meta, path, order["productSpecs"][path.split(".", 1)[1]], "user", 1.0)
    save_state(args.file, state)
    validation = validate_order(order)
    field_meta = meta.get("fieldMeta", {})
    emit({"ok": True, "file": args.file, "changed": changed,
          "order": compact_order(order),
          "fieldMeta": {path: field_meta[path] for path in changed if path in field_meta},
          "validation": slim_validation(validation), "knowledgeVersion": KNOWLEDGE_VERSION})


def cmd_recommend(args) -> None:
    state = load_state(args.file)
    if state is None:
        fail(f"未找到订单文件（{args.file}）。请先执行 ingest 建单。")
    order = state["order"]
    validation = validate_order(order)
    plans = recommend_processes(order)
    payload = {"ok": True, "file": args.file, "plans": plans,
               "selectedPlan": state["meta"].get("selectedPlan"),
               "validation": slim_validation(validation),
               "knowledgeVersion": KNOWLEDGE_VERSION}
    if not plans:
        payload["note"] = ("多产品订单需拆分后分别推荐（见 validation.multiProduct）；"
                           "或订单品类参数不足，请先按 validation.nextQuestions 补齐。")
    emit(payload)


def cmd_select(args) -> None:
    state = load_state(args.file)
    if state is None:
        fail(f"未找到订单文件（{args.file}）。请先执行 ingest 建单。")
    if args.plan not in PLAN_IDS:
        fail(f"--plan 只能是 {'、'.join(PLAN_IDS)} 之一。")
    plans = recommend_processes(state["order"])
    plan = next((item for item in plans if item.get("id") == args.plan), None)
    if plan is None:
        fail("当前订单暂无可用方案，请先补齐参数（status / validation）。")
    state["meta"]["selectedPlan"] = plan
    save_state(args.file, state)
    emit({"ok": True, "file": args.file, "selectedPlan": plan, "knowledgeVersion": KNOWLEDGE_VERSION})


def cmd_price(args) -> None:
    state = load_state(args.file)
    if state is None:
        fail(f"未找到订单文件（{args.file}）。请先执行 ingest 建单。")
    emit({"ok": True, "file": args.file, "estimate": estimate_price(state["order"]),
          "selectedPlan": state["meta"].get("selectedPlan"),
          "pricingModelVersion": PRICE_MODEL_VERSION, "knowledgeVersion": KNOWLEDGE_VERSION})


def cmd_handoff(args) -> None:
    state = load_state(args.file)
    if state is None:
        fail(f"未找到订单文件（{args.file}）。请先执行 ingest 建单。")
    order = state["order"]
    order["platform"] = args.platform
    result = prepare_handoff(order)
    plan = state["meta"].get("selectedPlan")
    lines = ["# 印刷订单交接单（待人工确认）", "",
             f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
             f"- 知识版本：{KNOWLEDGE_VERSION}（示例价格参数表 {PRICE_MODEL_VERSION}，参考费用不构成报价）"]
    if plan:
        lines.append(f"- 选定方案：{plan.get('title')}（{plan.get('printMode')}）；参考费用 {plan.get('refPrice')}")
    lines += ["", "```text", result.get("text", ""), "```", "",
              "---", "本交接单由 PrintOps 规则引擎生成为交接草稿；提交给任何供应商前，请逐字段人工确认。"]
    markdown = "\n".join(lines)
    out_file = safe_path(args.out, for_write=True) if args.out else None
    if out_file is not None:
        out_file.write_text(markdown + "\n", encoding="utf-8")
    emit({"ok": result.get("status") == "ready", "file": args.file,
          "status": result.get("status"), "reason": result.get("reason"),
          "platform": result.get("platform", {}).get("name", args.platform),
          "requiresHumanConfirmation": result.get("requiresHumanConfirmation", True),
          "text": result.get("text", ""), "markdown": markdown,
          "out": str(out_file) if out_file is not None else None,
          "supplierReadiness": result.get("supplierReadiness"),
          "selectedPlan": plan, "knowledgeVersion": KNOWLEDGE_VERSION})


def cmd_capability(args) -> None:
    state = load_state(args.file)
    if state is None:
        fail(f"未找到订单文件（{args.file}）。请先执行 ingest 建单。")
    result = match_supplier_capability(state["order"], args.platform)
    emit({"ok": True, "file": args.file, "capability": result,
          "note": "能力匹配基于静态档案，凡 needsReview 项都需供应商人工确认。",
          "knowledgeVersion": KNOWLEDGE_VERSION})


def cmd_quote(args) -> None:
    state = load_state(args.file)
    if state is None:
        fail(f"未找到订单文件（{args.file}）。请先执行 ingest 建单。")
    result = request_supplier_quote(state["order"], args.platform)
    emit({"ok": result.get("status") not in ("blocked", None), "file": args.file,
          "quote": result,
          "note": "询价草稿只是准备动作：绝不自动发送；供应商确认口径以人工确认为准。",
          "knowledgeVersion": KNOWLEDGE_VERSION})


def cmd_terms(args) -> None:
    emit({"ok": True, **explain_print_term(args.question), "knowledgeVersion": KNOWLEDGE_VERSION})


def cmd_catalog(args) -> None:
    if args.product:
        profile = profile_for(args.product)
        emit({"ok": True, "product": args.product, "profile": profile,
              "knowledgeVersion": KNOWLEDGE_VERSION})
        return
    from product_knowledge import PRODUCT_CATALOG
    emit({"ok": True,
          "products": [{"id": name, "category": profile_for(name).get("category", ""),
                        "minQuantity": profile_for(name).get("minQuantity")}
                       for name in PRODUCT_CATALOG],
          "knowledgeVersion": KNOWLEDGE_VERSION})


def cmd_platforms(_args) -> None:
    emit({"ok": True, "platforms": [{"id": pid, "name": item.get("name", pid),
                                     "mode": item.get("mode", "export"),
                                     "supplierProfile": item.get("supplierProfile", {})}
                                    for pid, item in PLATFORMS.items()]})


def scan_pdf_clues(path: str) -> dict:
    """零依赖 PDF 轻量扫描：只提取线索，不做生产级结论。"""
    pdf_file = safe_path(path)
    if not pdf_file.is_file():
        fail(f"找不到文件：{pdf_file}")
    data = pdf_file.read_bytes()
    text_head = data[:2048]
    version = re.search(rb"%PDF-(\d\.\d)", text_head)
    pages = len(re.findall(rb"/Type\s*/Page\b", data)) - len(re.findall(rb"/Type\s*/Pages\b", data))

    def find_box(name: str) -> list | None:
        match = re.search(rb"/" + name.encode() + rb"\s*\[([^\]]+)\]", data)
        if not match:
            return None
        try:
            return [float(part) for part in match.group(1).split()[:4]]
        except ValueError:
            return None

    color_spaces = sorted({token.decode("ascii", "ignore") for token in
                           (b"/DeviceRGB", b"/DeviceCMYK", b"/DeviceGray", b"/Separation", b"/DeviceN")
                           if token in data})
    return {"isPdf": data[:5] == b"%PDF-" or b"%PDF-" in text_head,
            "pdfVersion": version.group(1).decode("ascii") if version else None,
            "pageCount": pages if pages > 0 else None,
            "hasEof": b"%%EOF" in data[-4096:],
            "boxes": {"media": find_box("MediaBox"), "trim": find_box("TrimBox"),
                      "bleed": find_box("BleedBox")},
            "colorSpaces": color_spaces,
            "fontEmbedding": "embedded" if (b"/FontFile" in data or b"/FontFile2" in data
                                            or b"/FontFile3" in data) else "unknown",
            "imageCount": len(re.findall(rb"/Subtype\s*/Image\b", data)) or None,
            "hasTransparency": b"/SMask" in data or b"/Transparency" in data,
            "hasOverprint": b"/OP " in data or b"/op " in data,
            "fileSizeBytes": len(data)}


def cmd_preflight(args) -> None:
    state = load_state(args.file) if args.file else None
    pdf_file = safe_path(args.pdf)
    if not pdf_file.is_file():
        fail(f"找不到文件：{pdf_file}")
    clues = scan_pdf_clues(args.pdf)
    order = (state or {}).get("order", {})
    dimensions = order.get("dimensions", {})
    expected = dimensions.get("finishedSize") or order.get("size") or ""
    result = preflight_file(file_name=pdf_file.name, size_bytes=clues["fileSizeBytes"],
                            page_count=clues.get("pageCount"), encrypted=False,
                            readable=bool(clues["isPdf"]),
                            inspection=clues, expected_size=expected or None)
    emit({"ok": result.get("ok", False), "pdf": str(pdf_file),
          "result": result, "clues": clues,
          "disclaimer": "零依赖轻量扫描只提供印前线索，不替代专业预检；压缩对象流可能导致页数等字段解析不到。",
          "knowledgeVersion": KNOWLEDGE_VERSION})


def cmd_reset(args) -> None:
    state_file = safe_path(args.file, for_write=True)
    if state_file.is_file():
        state_file.unlink()
        emit({"ok": True, "file": args.file, "reset": True})
    else:
        emit({"ok": True, "file": args.file, "reset": False, "note": "文件不存在，无需重置。"})


def main() -> None:
    parser = argparse.ArgumentParser(prog="printops_cli.py",
                                     description="PrintOps 印刷订单智能体 CLI（本地规则内核，无网络请求）")
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name: str, help_text: str) -> argparse.ArgumentParser:
        child = sub.add_parser(name, help=help_text)
        child.add_argument("--file", default="printops-order.json",
                           help="订单状态 JSON 文件路径（默认 ./printops-order.json，写在当前工作目录）")
        return child

    p = add("ingest", "理解一句需求描述，抽取字段并合并进订单（主入口，每轮用户输入都调用）")
    p.add_argument("--text", required=True, help="用户原话")
    p.add_argument("--pick-item", type=int, default=None,
                   help="多产品需求时选择第 N 个产品项（从 0 开始）建单")
    p.set_defaults(func=cmd_ingest)

    add("status", "查看当前订单、校验结果和待追问问题").set_defaults(func=cmd_status)

    p = add("set", "直接设置顶层订单字段（用户明确回答后使用）；尺寸语义用 dimensions.<语义>")
    p.add_argument("--field", action="append", required=True, help="字段赋值，如 --field paper=250g铜版纸")
    p.set_defaults(func=cmd_set)

    p = add("set-spec", "设置品类专属参数 productSpecs（如 labelShape=圆形、boxSizeInner=…）")
    p.add_argument("--field", action="append", required=True, help="参数赋值，如 --field labelShape=圆形")
    p.set_defaults(func=cmd_set_spec)

    add("recommend", "生成经济/平衡/质感三档工艺方案").set_defaults(func=cmd_recommend)
    p = add("select", "记录用户选择的方案")
    p.add_argument("--plan", required=True, choices=list(PLAN_IDS), help="方案 ID")
    p.set_defaults(func=cmd_select)

    add("price", "按示例价格参数表估算参考费用（不构成报价）").set_defaults(func=cmd_price)

    p = add("capability", "将订单与目标平台能力档案逐字段匹配（支持/待确认/不支持）")
    p.add_argument("--platform", default="generic", help="目标平台 ID（见 platforms 命令）")
    p.set_defaults(func=cmd_capability)

    p = add("quote", "生成询价草稿（仅准备，绝不自动发送，需人工确认）")
    p.add_argument("--platform", default="generic", help="目标平台 ID（见 platforms 命令）")
    p.set_defaults(func=cmd_quote)

    p = add("handoff", "生成订单交接单草稿（必须人工确认，绝不自动提交）")
    p.add_argument("--platform", default="generic", help="目标平台 ID（见 platforms 命令）")
    p.add_argument("--out", default=None, help="交接单 Markdown 输出路径（当前工作目录内）；省略则只输出 JSON")
    p.set_defaults(func=cmd_handoff)

    p = sub.add_parser("terms", help="解释印刷术语（哑粉纸/出血/覆膜/专色…）")
    p.add_argument("question", help="术语问题原文")
    p.set_defaults(func=cmd_terms)

    p = sub.add_parser("catalog", help="查询品类目录与品类参数")
    p.add_argument("--product", default=None, help="品类名（如 名片）；省略则列出全部品类")
    p.set_defaults(func=cmd_catalog)

    sub.add_parser("platforms", help="列出目标平台与能力档案").set_defaults(func=cmd_platforms)

    p = sub.add_parser("preflight", help="PDF 本地轻量预检（页数/加密/页面框/颜色空间等线索）")
    p.add_argument("pdf", help="PDF 文件路径")
    p.add_argument("--file", default=None, help="关联订单文件（用于与成品尺寸比对）")
    p.set_defaults(func=cmd_preflight)

    add("reset", "删除订单状态文件，重新开始").set_defaults(func=cmd_reset)

    args = parser.parse_args()
    try:
        args.func(args)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 —— CLI 边界统一兜底为 JSON 错误
        fail(f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
