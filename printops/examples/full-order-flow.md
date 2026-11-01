# 示例：完整建单流（宣传册，从一句话到交接单）

何时读：第一次走完整流程、或新会话冷启动不确定节奏时。所有 JSON 都是 CLI 真实输出节选（`…` 表示省略），不要凭记忆复述——以你实际调用的返回为准。

场景：用户说——「我想印500份A4宣传册，32页骑马钉，157g哑粉纸，双面四色，下周内」

## 第 1 步：ingest（每轮用户输入都先跑它）

```bash
$CLI ingest --text "我想印500份A4宣传册，32页骑马钉，157g哑粉纸，双面四色，下周内"
```

关键返回（节选）：

```json
{
 "changed": ["productType", "quantity", "size", "pages", "paper",
             "printing", "binding", "deadline", "budget", "purpose",
             "dimensions.finishedSize"],
 "order": {
  "productType": "宣传册", "quantity": "500 份", "size": "210×297 mm",
  "pages": "32 页", "paper": "157 g/m² 哑粉纸", "printing": "双面四色",
  "binding": "骑马钉", "deadline": "下周", "budget": "优先交期"
 },
 "lowConfidence": {
  "budget": {"value": "优先交期", "confidence": 0.7},
  "purpose": {"value": "品牌宣传", "confidence": 0.68}
 },
 "fieldMeta": {"productType": {"value": "宣传册", "source": "rule", "confidence": 0.92, "…": "…"}}
}
```

助手动作：一行复述 changed（"识别到：500 份 A4 宣传册、32 页骑马钉、157g 哑粉纸、双面四色、下周交期"）；
**逐个确认 lowConfidence**（"这个是用作品牌宣传、优先保证交期对吗？"——未确认的弱推断不得写进交接单结论）；
`nextQuestions` 为空就不追问，不要硬凑问题。

## 第 2 步：用户确认弱推断 → set 落字段

用户回"对，品牌宣传用"。弱推断经用户确认后用 `set` 写入（视为用户确认值）：

```bash
$CLI set --field purpose="品牌宣传" --field budget="优先交期"
```

已确认过的字段不再重复问。`validation.ok` 且必答参数齐了就进方案。

## 第 3 步：recommend → 横向对比表呈现三档

```bash
$CLI recommend
```

真实返回的三档（数字原样引用，不心算）：

| 方案 | 印刷方式 | 材料 | 表面工艺 | 参考费用* | risk 转达要点 |
| --- | --- | --- | --- | --- | --- |
| 经济 | 合版 | 157 g/m² 哑粉纸 | 无特殊工艺 | ¥1139.73 - ¥1676.08 | 合版批次色差、不能指定专色 |
| 平衡 | 合版 | 200 g/m² 铜版纸 | 哑膜 | ¥1330.95 - ¥1957.28 | 覆膜增加加工时间和费用 |
| 质感 | 专版 | 300 g/m² 铜版纸 | 烫金/击凸 | ¥2125.74 - ¥3126.09 | 版费与起印量更高 |

\* 每档都要带"示例参数估算，不构成报价"。用户犹豫时按 `score`/`reason` 给一句建议，不替用户拍板。

## 第 4 步：select 记录选择

```bash
$CLI select --plan balanced
```

返回的 `selectedPlan.estimate` 是该档完整配置的估价（200g 铜版纸 + 哑膜 → ¥1330.95 - ¥1957.28）。

## 第 5 步：price（按订单自身参数计价，与方案档位价是两回事）

```bash
$CLI price
```

```json
{
 "schemaVersion": "2.0",
 "status": "ready",
 "displayRange": "¥1139.73 - ¥1676.08",
 "assumptions": ["印刷方式未指定，按合版模拟；不是供应商已确认的生产方式。",
                 "页数按含封面的总页数计算；封面未独立指定时按正文同纸。",
                 "未填写表面工艺，当前按无表面工艺模拟；新增工艺会重新计价。"],
 "missing": [], "unknown": null
}
```

要点：`price` 按**订单当前字段**计价（157g 哑粉纸、无工艺 → 接近经济档），
选定方案的档位价以 recommend/select 返回为准，两者不要混成一个数；
**`assumptions` 必须原样转达**（"按合版模拟"是计价口径，不是已确认的生产方式）。

## 第 6 步：quote（只准备，绝不发送）

```bash
$CLI quote
```

```json
{"requestId": "quote-f64cf33dccd941e28d8cdb8570353e3f",
 "status": "awaiting_human_confirmation", "providerId": "generic"}
```

`awaiting_human_confirmation` 表示草稿停住：发给哪家、怎么发，由用户自己决定。

## 第 7 步：handoff（人工逐字段确认后才算数）

```bash
$CLI handoff --out 交接单_宣传册.md
```

返回 `{"status": "ready", "requiresHumanConfirmation": true, "platform": "通用印刷平台"}`，
文件头部（真实内容）：

```markdown
# 印刷订单交接单（待人工确认）
- 知识版本：2026.09.05（示例价格参数表 2026.11.01，参考费用不构成报价）
- 选定方案：平衡方案（合版）；参考费用 ¥1330.95 - ¥1957.28
```

把全文展示给用户**逐字段确认**（特别是尺寸语义、页数、纸张），改了就回 ingest/set 再重新
handoff；明确告知"这是交接草稿，请自行发送给供应商"。`supplierReadiness` 有 `unsupported`
时如实转达，不换平台不硬推。
