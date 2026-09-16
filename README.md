# PrintOps Skill

把一句口语化的中文印刷需求（"我想印 500 份三折页"）整理成**字段可溯源、经人工确认**的订单与交接单。
两个技能共用一个知识底座：`printops` 接本地引擎，`printops-lite` 无引擎也能用。

![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)
![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-3776AB.svg)
![Dependencies: none](https://img.shields.io/badge/dependencies-none-brightgreen.svg)
![Skill format: SKILL.md](https://img.shields.io/badge/format-SKILL.md-6f42c1.svg)

**[English](#english-summary)** · 中文

---

## English summary

Two agent skills that turn casual Chinese print-shop requests ("I want 500 tri-fold brochures")
into traceable, human-confirmed order handoffs.

| Skill | What it does | Needs |
| --- | --- | --- |
| `printops` | Default entry: completes specs, compares processes, estimates cost magnitude, prepares handoff/quote drafts, traces every field to its source | A local PrintOps engine — **a copy ships inside the skill** (~600KB, pure Python stdlib) |
| `printops-lite` | Knowledge-only: category profiles, process terminology, structured draft | Nothing |

```bash
./install.sh                                  # installs both into ${CODEX_HOME:-~/.codex}/skills
cd printops && ./scripts/printops.sh check    # resolve engine: repo first, bundled copy as fallback
./scripts/printops.sh ask "做500张A4名片，250g铜版纸，双面四色，下周内"
```

Design notes: `description` is the **only** metadata that reaches the model's skill catalog
(truncated at 500 chars); `whenToUse` is UI-only and never enters model context; command details live in
`scripts/` and `references/` so each `SKILL.md` stays small.

---

## 这是什么

| 技能 | 用途 | 依赖 |
| --- | --- | --- |
| **`printops`** | 默认入口：品类补齐、方案对比、费用量级、交接/询价草稿、字段溯源、订单状态 | **自带内置引擎**（约 600KB）；本机有引擎仓库时优先用仓库 |
| **`printops-lite`** | 纯知识版：品类参数、工艺术语、结构化草稿 | 无 |

设计原则是**渐进披露**：元数据负责"被选中"，正文负责"立刻能干"，细节与确定性操作下沉到
`references/` 与 `scripts/`。两个 `SKILL.md` 的正文都很短，因为每次调用都要和对话历史抢上下文。

分工原则：**模型负责理解和解释，规则内核负责约束与执行，人负责确认高风险结果。**

## 30 秒上手

```bash
git clone https://github.com/11122313211/printops-skill.git
cd printops-skill
./install.sh                  # 安装到 ${CODEX_HOME:-~/.codex}/skills/
```

装好后在支持 `SKILL.md` 的宿主里直接用自然语言提需求即可；也可以手动跑一遍：

```bash
cd printops
./scripts/printops.sh check     # 引擎根 / 版本 / 来源 / 会话库落点
./scripts/printops.sh ask "做500张A4名片，250g铜版纸，双面四色，下周内"
```

真实输出（`readiness` 100 表示必填字段已齐）：

```jsonc
{
  "workflowStage": "recommend",           // 方案选择
  "order": {
    "productType": "名片", "quantity": "500 张", "size": "A4",
    "paper": "250g 铜版纸", "printing": "双面四色", "deadline": "下周"
  },
  "validation": { "readiness": 100, "missing": [] },
  "nextAction": "下一步：比较并选择工艺方案"
}
```

跨轮是**修改同一订单**，不是新建：同一会话库里接着说"数量改成 1200 张" →
`{"productType": "名片", "quantity": "1200 张", "quantityValue": 1200, "paper": "250g 铜版纸", ...}`。

## 目录布局

```
printops-skill/
├── install.sh                 # 安装/更新到 ${CODEX_HOME:-~/.codex}/skills
├── validate-skills.py         # 自检：frontmatter 合法性 + 资源引用完整性
├── printops/
│   ├── SKILL.md               # 元数据（被选中）+ 正文（立刻能干）
│   ├── references/            # 权威细节：字段契约、17 类品类档案、引擎与安全
│   ├── scripts/
│   │   ├── printops.sh        #   引擎统一入口：check / tools / ask / smoke
│   │   ├── sync-engine.sh     #   仓库 → 内置副本，写指纹并跑冒烟
│   │   └── engine-check.sh    #   核对副本是否落后于仓库
│   ├── engine/                # 内置引擎副本（MIT，随 sync-engine.sh 覆盖）
│   └── agents/openai.yaml     # 宿主展示信息
└── printops-lite/
    ├── SKILL.md
    ├── references/
    └── scripts/check_draft.py #   草稿 JSON 的确定性校验
```

## 引擎：仓库优先，内置兜底

解析顺序：

```
--engine  →  $PRINTOPS_HOME  →  默认仓库路径  →  自动查找 tools/printops_local_host.py  →  技能内置 engine/
```

**有仓库就用仓库**（最新事实来源），没有仓库才用内置副本。显式 `--engine` 无效会直接报错，不会静默换用别的引擎。

```bash
cd printops
./scripts/printops.sh check    # 引擎根 / 版本（需 ≥ 1.1.0）/ 来源 / 会话库
./scripts/printops.sh tools    # 引擎工具清单（L0 只读 / L1 有副作用），权威来源
./scripts/printops.sh ask "…"  # 处理一条消息，跨轮自动沿用同一会话库
./scripts/printops.sh smoke    # 只跑 MCP/skill 冒烟
```

可选：`--session <id>`、`--memory <path>`、`--engine <path>`、`--with-mcp`。

内置副本是**手动同步**的快照，指纹记在 `printops/engine/SOURCE_INFO.txt`（来源仓库/版本/commit/同步时间）：

```bash
cd printops
./scripts/sync-engine.sh     # 从仓库刷新副本，写指纹，并跑一次 MCP 冒烟
./scripts/engine-check.sh    # 核对副本是否落后于仓库
```

## 自检

```bash
python3 validate-skills.py         # 检查本包全部技能
python3 validate-skills.py <目录>  # 检查指定技能目录
```

它按宿主的真实加载规则校验，专门拦住"技能好像不存在"这类**没有任何诊断**的故障：

- `name` 必须是 kebab-case；
- `description` 超过 500 字符会被截断；
- 调用开关必须是布尔（`true/false/yes/no/on/off/1/0`），写成别的类型会让**整个技能被丢弃**；
- `disableModelInvocation` 这类驼峰旧键会让技能被直接丢弃；
- 正文提到的 `references/` 与 `scripts/` 文件必须存在，并提示没有被引用的孤儿资源。

## 维护者：发布

发布脚本只依赖 `gh` 的登录态（不接触 token），幂等：仓库不存在就创建并推送，已存在就只推送。

```bash
gh auth login --hostname github.com --git-protocol https --web   # 首次
./publish.sh             # → 11122313211/printops-skill（public）
./publish.sh --private   # 私有
```

发布前建议先跑 `python3 validate-skills.py`，确保两个技能不会被宿主静默丢弃。

## 注意事项

- **数据落点**：会话库由 `scripts/printops.sh` 自动选择——真实仓库写 `<仓库根>/data/agent.sqlite3`；
  **内置副本一律不写技能目录**（技能可能装在云同步或只读位置），默认落 `${TMPDIR:-/tmp}`。
  要长期保留订单，用 `--memory <可写目录>/agent.sqlite3` 或设 `PRINTOPS_MEMORY`。
- **不要在技能目录里存真实客户订单**：技能目录常位于云同步位置。
- **内置副本可能落后**：它不会自动跟随引擎仓库更新；改动引擎后要跑 `scripts/sync-engine.sh` 再重新安装/打包。
- **不接真实供应商**：不发起外部请求、不代替用户确认、不给实时报价。

## 状态与已知限制

- 引擎版本 `1.1.0`，属**候选版**：真实供应商 live 接入与报价回写是 v1.2+，
  真实脱敏语料、真人走查与端到端浏览器冒烟仍未完成。**请不要对外宣称生产可用。**
- 费用来自版本化的示例参数表，`refPrice` 只是量级参考，不构成报价，必须与供应商报价分开呈现。
- 预检只基于浏览器提供的 PDF 元数据，不替代专业印前检查，也不读取原稿内容。
- 品类档案与工艺术语是知识快照（当前 `2026.09.05`），重新生成命令见
  `printops-lite/references/category-profiles.md` 开头。

## 在其它宿主上使用

同一份 `SKILL.md` 也能被其它支持该格式的宿主加载（例如放到 `~/.dsh/skills/<技能名>/`，发现深度只有一层，
不支持嵌套 `**/SKILL.md`）。几个容易踩的点：

- **`description` 是唯一进入模型上下文的元数据**：模型目录每行只有 `` - `name`: description ``，
  因此触发词与排除项都必须写在 `description` 里。
- **`whenToUse` 不进模型上下文**：它只出现在会话 API 与 GUI 目录里（实现上唯一消费者是 UI 层）。
  可以写给人看，但不要拿它承载路由信息。
- 调用开关只认布尔值；写错类型或使用驼峰旧键，技能会被静默丢弃——用 `validate-skills.py` 提前拦住。

## 相关仓库

- **[11122313211/PrintOps](https://github.com/11122313211/PrintOps)** —— 完整引擎仓库（字段模型、状态机、
  Web 工作台、HTTP/MCP 接口与测试套件）。本包内置的是它的最小运行集快照。
- 想改引擎行为请改引擎仓库，再 `sync-engine.sh` 同步；直接改 `printops/engine/` 会在下次同步时被覆盖。

## License

[MIT](LICENSE)。内置引擎副本来自 [PrintOps](https://github.com/11122313211/PrintOps)，
同样以 MIT 分发，其许可声明保留在 `printops/engine/LICENSE`。
