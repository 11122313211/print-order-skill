# 订单字段契约

权威实现：`order_model.py`（字段默认值与校验）、`agent.py`（状态机与人工确认闸门）。
本文件是给模型用的口径说明；与代码冲突时以代码为准。

## 字段白名单

订单级：`productType`、`productTypes[]`、`items[]`、`purpose`、`quantity`、`quantityValue`、`quantityUnit`、
`size`、`dimensions`、`pages`、`orientation`、`paper`、`printing`、`finishing`、`binding`、`deadline`、
`budget`、`platform`、`productSpecs{}`。

产品项（`items[]` 每项）：与上面同名的生产字段，外加稳定的 `itemId`、`selectedOption`、`orderGenerated`、`uploadedFile`。

| 字段 | 标签 | 字段 | 标签 |
| --- | --- | --- | --- |
| `productType` | 印刷品 | `pages` | 页数 |
| `purpose` | 使用场景 | `orientation` | 版式方向 |
| `quantity` | 数量 | `paper` | 纸张/材料 |
| `size` | 成品尺寸 | `printing` | 印刷颜色 |
| `finishing` | 表面工艺 | `binding` | 装订/后道 |
| `deadline` | 交期 | `budget` | 预算偏好 |
| `platform` | 目标平台 | `productSpecs` | 品类专属参数 |

- 必填：`productType`、`quantity`、`size`、`paper`、`printing`、`deadline`。缺失时 `validate_order` 返回 `missing`，
  交接/询价返回 `blocked / order_not_ready`。
- `quantity` 保留用户原文（“500 张”），`quantityValue` / `quantityUnit` 存结构化数值与单位；
  “万/千/百”按 10000/1000/100 换算。各品类默认单位见 `category-profiles.md`。
- 增量写入只走 patch，不做整单替换：`apply_order_patch` 只接受 `patch` + `evidence` + `confidence` + `expectedRevision`
  （patch 最多 32 个属性），并且不接收完整 `order` / `items` 覆盖。

## 尺寸语义

| key | 含义 | 说明 |
| --- | --- | --- |
| `dimensions.finishedSize` | 成品尺寸 | 交付到手的最终尺寸 |
| `dimensions.expandedSize` | 展开尺寸 | 折页等展开后的尺寸 |
| `dimensions.dieCutSize` | 刀模尺寸 | 异形/模切件 |
| `dimensions.packageSize` | 包装三维尺寸 | 长×宽×高；盒、袋还要写明内尺寸/外尺寸 |

- 有标签的输入按语义落位（“展开 420×285” → `expandedSize`）；不要把平面尺寸写成三维规格，也不要把三维规格塞进 `finishedSize`。
- 开数参考：大度 889×1194mm、正度 787×1092mm。

## 证据与置信度

- 每个生产字段都带 `fieldMeta`：`value`、`source`（`user` / `rule` / `model` / `recommendation` / `system`）、
  `sourceLabel`、`confidence`、`runId`、`updatedAt`。
- 规则感知分级：显式标签或单位（“500 张”“双面四色”）≥0.9；裸数字与“差不多/看着办”一类模糊表达低于 0.75。
- **低于 0.75 的生产字段视为未确认**：`generate`、`prepare_handoff`、`request_supplier_quote` 会返回
  `blocked / low_confidence` 并列出 `uncertain`。此时只输出追问，不要继续生成。
- 缺证据的字段可以留在草稿，但必须标低置信度，且不得进入交接单。

## 校验、闸门与阻断原因

| `status` / `reason` | 触发条件 | 正确反应 |
| --- | --- | --- |
| `order_not_ready` | 必填字段缺失 | 补齐 `missing` 列出的字段 |
| `low_confidence` | 存在未确认生产字段 | 逐字段追问确认 |
| `selection_required` | 工艺方案未选 | 在 3 档方案里让用户选择 |
| `item_not_found` | 指定产品项不存在 | 重新对齐 `itemId` / `itemIndex` |
| `duplicate_blocked` | 重复的“工具名 + 参数” | 不要重试同一调用 |

其他关键状态：

- **多产品订单**：`validate_order` 返回每项 `itemValidations`；存在未完成产品项时，推荐、估价、交接、询价统一
  `blocked`，不生成合并结果。对话可用 `activeItemIndex`、接口可用 `itemIndex` 把更新限制在单个产品项内。
- **询价草稿**：状态 `awaiting_human_confirmation`，含 `requestId` 与稳定 `idempotencyKey`；订单、文件或目标平台变化
  会把活动请求标记为 `stale`；支持状态查询与取消；人工确认前绝不发起外部请求。
- **确认状态**：`not_ready` → `pending` → `confirmed`，只有 `confirm` 能推进；交接单与确认状态会持久化在会话中。
- **导出**：交接单文本 + JSON / CSV / Markdown。

## 品类参数

`productSpecs` 的 key 按所选品类档案校验；未知 key 必须拒绝或进 `rejectedFields`。完整参数表见 `category-profiles.md`。
