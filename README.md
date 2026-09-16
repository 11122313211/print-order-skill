# PrintOps · 印刷订单助理

> 把客户一句「我想印 500 份三折页」，变成一张**每个字段都有出处、并经人工确认**的订单交接单。

PrintOps 是装进你现有 AI 助手的一个技能包（Skill），给印刷门店、印刷电商客服、印刷厂接单员和企业采购用：
**你只管用大白话说需求，参数补齐、术语对齐、下单前的核对，交给它。**

![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)
![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-3776AB.svg)
![Dependencies: none](https://img.shields.io/badge/dependencies-none-brightgreen.svg)
![Data: stays local](https://img.shields.io/badge/data-stays%20local-success.svg)

---

## 这些场景，如果你眼熟，它就是给你做的

| 今天常见的做法 | 代价 |
| --- | --- |
| 客户："印一批宣传册，A4 差不多，上次那种纸" | 参数缺一半，来回追问五六轮 |
| 客服手敲进表格、在微信里问 | 页数、工艺、尺寸记错，做完才发现 |
| 报价凭感觉 | 报低了亏本，报高了丢单 |
| 出了问题 | 没人说得清"客户当时到底说的是什么" |

PrintOps 把这段流程搬进对话，并且**每一步都留下证据**。

## 它给你带来什么

**一次把参数问全。** 只问最小必要的问题——品类、数量、尺寸、纸张、印刷方式、交期。
不会甩给客户一张 20 项的表格；17 个常见品类各有自己的追问话术与起印量口径。

**每个字段都能溯源。** 订单里每个值都带着出处：客户原话（"500份"）、默认值，还是推断出来的。
证据与置信度留在订单里，事后可以复盘、可以追责。

**不确定就追问，不确定就不写。** 置信度低于 0.75 的生产参数会被**拦住**，不会带着猜测进入下单环节；
交接单与询价草稿必须由人确认后才生成——工具不替你做决定。

**像聊天一样改单。** "数量改成 1200 张""不要覆膜""再加个手提袋"——都是对**同一张订单**的修改，
跨轮不丢已有参数，不会越改越乱。

**它不编参数。** 金额、交期、供应商能力，没有依据就不说。费用只给**量级参考**，
并且必须与供应商报价分开展示，避免把估算当承诺。

## 一分钟看到效果

```bash
cd printops
./scripts/printops.sh ask "做500张A4名片，250g铜版纸，双面四色，下周内"
```

真实输出（`readiness` 100 = 必填字段已齐）：

```jsonc
{
  "workflowStage": "recommend",           // 进入"方案比较"阶段
  "order": {
    "productType": "名片", "quantity": "500 张", "size": "A4",
    "paper": "250g 铜版纸", "printing": "双面四色", "deadline": "下周"
  },
  "validation": { "readiness": 100, "missing": [] },
  "nextAction": "下一步：比较并选择工艺方案"
}
```

接着补一句"数量改成 1200 张"，它改的是**同一张订单**，而不是新建一单：

```jsonc
{"productType": "名片", "quantity": "1200 张", "quantityValue": 1200, "paper": "250g 铜版纸", ...}
```

## 谁适合用

- **印刷门店 / 网店客服**：客户说什么就录什么，缺的参数一次问清，报价前先自检。
- **印刷厂接单与客服**：接单口径统一，字段可追溯，减少"客户没说清楚"的扯皮。
- **企业市场部 / 采购**：自己要印物料，先把需求理清楚再找供应商，少走弯路。
- **独立设计师 / 自由职业者**：客户口述需求 → 结构化交接单，减少反复确认。

## 30 秒上手

```bash
git clone https://github.com/11122313211/print-order-skill.git
cd print-order-skill
./install.sh                     # 安装到 ${CODEX_HOME:-~/.codex}/skills/
```

装好后，在你的 AI 助手里直接说需求即可，例如：
"做 500 张 A4 名片，250g 铜版纸，双面四色，下周内"。

想先手动验证一遍：

```bash
cd printops
./scripts/printops.sh check      # 自检：引擎、版本、订单数据落点
./scripts/printops.sh ask "…"    # 处理一条需求
```

## 两个版本，按你的机器选

| 版本 | 适合谁 | 需要什么 |
| --- | --- | --- |
| **`printops`**（默认） | 常规使用：要校验、要溯源、要费用量级、要交接草稿 | 什么都不用装——引擎（约 600KB，纯 Python 标准库）已随包内置 |
| **`printops-lite`** | 只想查参数、查术语，或环境不允许跑脚本 | 无 |

`printops-lite` 的结论会明确标注"未经引擎校验"，只作草稿使用。

## 支持的品类（17 类）

宣传册 · 画册 · 单页 · 折页 · 名片 · PVC 卡 · 吊牌 · 联单 · 信封封套 · 标签 ·
包装盒 · 手提袋 · 纸杯 · 海报 · 喷画 · PVC 展板 · 数码快印

每一类都有对应的参数表、起印量口径与印刷方式提示（合版 / 专版）。
不在档案里的品类，它会如实说明超出范围，而不是硬塞进最接近的品类。

## 数据与安全

- **全部在本机运行。** 技能与引擎不发起任何外部网络请求，不连接供应商、不上传内容
  （宿主 AI 助手自身的模型调用除外）。
- **零依赖。** 纯 Python 标准库，不需要 `pip install`，不引入第三方包。
- **订单数据在你自己机器上。** 有引擎仓库时写在仓库的 `data/` 下；否则默认落在系统临时目录，
  可用 `--memory <路径>` 或 `PRINTOPS_MEMORY` 指定长期位置。
- **不要把真实客户订单存进技能目录**——技能目录常在云同步位置。
- **人工确认闸门。** 交接单、询价草稿必须由人确认；工具不代替你联系供应商、不代替你答应客户。

## 我们刻意不做的事

把边界说清楚，比多做几件事更重要：

- **不做平面设计，不做印前文件制作与修复。**
- **不接真实供应商**：不下单、不问价、不承诺交期与产能。
- **不给确定报价**：费用来自版本化示例参数表，只是量级参考，不构成报价。
- **不代替人确认**：任何对外交付物都要人点头。
- **不猜**：立体造型件（纸模型、异形摆件）明确超出品类范围，会直说，而不是套一个近似的品类。

## 常见问题

**要不要联网？要不要 API Key？**
不要。装好即用，全部在本机运行。

**费用估算准不准？**
它是量级参考，不是报价。参数表随版本走（当前 `2026.09.05`），始终与供应商报价分开呈现。

**能对接我们的 ERP / 供应商系统吗？**
暂不直接对接。引擎带本地 HTTP / MCP 接口，供应商实时接入与报价回写排在 v1.2。

**会不会把客户资料发出去？**
不会。技能与引擎不发起任何外部请求。

**能用在别的 AI 助手里吗？**
任何遵循 `SKILL.md` 目录约定的宿主都可以加载。

**只认中文需求吗？**
是——它就是为中文印刷业务写的：中文口语与别名（"三折页""不干胶""彩盒"）都能识别。

## 版本状态与路线图

- 当前引擎版本 **1.1.0（候选版）**：适合内部试点与人工把关流程，尚未接入真实供应商。
- 上游引擎仓库维护着 **280+ 项自动化测试**；本包每次同步引擎后会自动跑一遍 MCP 冒烟。
- 路线图：v1.2 —— 供应商 live 接入、报价回写；随后补齐真实脱敏语料与端到端走查。

## 面向开发者 / 维护者

<details>
<summary>引擎解析顺序、内置副本同步、自检与发布</summary>

**引擎解析顺序**（有仓库用仓库，没仓库用内置副本）：

```
--engine → $PRINTOPS_HOME → 默认仓库路径 → 自动查找 → 技能内置 engine/
```

**常用命令**：

```bash
cd printops
./scripts/printops.sh check      # 引擎根 / 版本 / 来源 / 会话库
./scripts/printops.sh tools      # 引擎工具清单（L0 只读 / L1 有副作用）
./scripts/printops.sh ask "…"    # 可选 --session / --memory / --engine / --with-mcp
./scripts/printops.sh smoke      # 只跑 MCP / skill 冒烟
./scripts/sync-engine.sh         # 从引擎仓库刷新内置副本，写指纹，并跑冒烟
./scripts/engine-check.sh        # 核对内置副本是否落后于引擎仓库
python3 validate-skills.py       # 校验 frontmatter 与资源引用
./publish.sh                     # 发布到 11122313211/print-order-skill（幂等）
```

**目录布局**：

```
print-order-skill/
├── install.sh                 # 安装 / 更新到 ${CODEX_HOME:-~/.codex}/skills
├── validate-skills.py         # 技能自检（拦住"技能好像不见了"的无诊断故障）
├── publish.sh                 # 发布（只依赖 gh 登录态）
├── printops/
│   ├── SKILL.md               # 元数据 + 立刻能干的正文
│   ├── references/            # 字段契约、17 类品类档案、引擎与安全
│   ├── scripts/               # printops.sh / sync-engine.sh / engine-check.sh
│   ├── engine/                # 内置引擎副本（MIT，带来源指纹）
│   └── agents/openai.yaml
└── printops-lite/
    ├── SKILL.md
    ├── references/
    └── scripts/check_draft.py # 草稿 JSON 的确定性校验
```

**内置副本是快照**：它不会自动跟随引擎仓库。改完引擎请跑 `sync-engine.sh` 再重新安装 / 打包，
`engine-check.sh` 可核对是否落后，指纹记在 `printops/engine/SOURCE_INFO.txt`。

</details>

## 相关仓库

- **[11122313211/PrintOps](https://github.com/11122313211/PrintOps)** —— 完整引擎仓库（字段模型、状态机、
  Web 工作台、HTTP/MCP 接口与测试套件）。本包内置的是它的最小运行集快照。

## English summary

Two agent skills that turn casual Chinese print-shop requests ("I want 500 tri-fold brochures") into
traceable, human-confirmed order handoffs.

- `printops` — default entry: completes specs, compares processes, estimates cost magnitude, prepares
  handoff/quote drafts, traces every field to its source. A ~600KB pure-stdlib engine ships inside the skill.
- `printops-lite` — knowledge-only fallback: category profiles, process terminology, structured drafts.

Everything runs locally: no network calls, no third-party dependencies, no API keys.

## License

[MIT](LICENSE)。内置引擎副本来自 [PrintOps](https://github.com/11122313211/PrintOps)，
同样以 MIT 分发，许可声明保留在 `printops/engine/LICENSE`。
