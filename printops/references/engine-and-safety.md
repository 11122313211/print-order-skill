# 引擎、接口与安全边界

技能内的统一入口是 `scripts/printops.sh`（`check` / `tools` / `ask` / `smoke`）：它负责引擎解析、版本校验、
会话库落点与参数拼装，正文只要求调用它，不需要手写路径。引擎根解析顺序：
`--engine` → `$PRINTOPS_HOME` → `/Users/Admin/Desktop/print-order-agent-mvp-v0.1.0` →
按 `tools/printops_local_host.py` 在 `$PRINTOPS_SEARCH_ROOTS`（默认 `~/Desktop ~/Documents ~/Projects ~/code ~/dev ~/src`）
里搜索 → 技能内置 `engine/`。显式给出的 `--engine` 无效会直接报错，不会静默换用其它引擎。
下文 `<引擎根>` 即解析结果。
环境：Python 3.9+，零第三方依赖；脚本用自身位置推导引擎根与技能目录，可从任意目录调用。
版本要求：≥ 1.1.0（读 `<引擎根>/VERSION` 确认）；获取方式：`git clone https://github.com/11122313211/PrintOps.git`。

## 内置引擎副本

本技能自带 `engine/`（约 630KB：6 个领域模块 + `llm_adapter.py` + `mcp_server.py` + 3 个 tools 脚本 +
`.dsh/skills/` 5 个 dsh skill + `VERSION` + `LICENSE`），脱离仓库可独立运行，用于没有本机仓库的机器。

- 优先级：`--engine` → `$PRINTOPS_HOME` → 默认路径 → 自动查找 → 内置副本；**有仓库就用仓库**。
- 快照信息：`engine/SOURCE_INFO.txt`（来源仓库、版本、commit、同步时间）。
- 刷新：`scripts/sync-engine.sh`（同步后自动跑一次 MCP/skill 冒烟）；核对：`scripts/engine-check.sh`。
- 数据落点：由 `scripts/printops.sh` 自动决定。真实仓库用 `<仓库根>/data/agent.sqlite3`（不可写时回落临时目录）；
  **内置副本一律不写技能目录**，默认 `${TMPDIR:-/tmp}/printops-agent.sqlite3`，要用固定位置就传
  `--memory <可写目录>/agent.sqlite3` 或设 `$PRINTOPS_MEMORY`。云同步目录不要存真实订单。
- 许可证：内置引擎随包分发，`engine/LICENSE`（MIT）必须保留。

## 统一入口脚本

| 目的 | 命令 |
| --- | --- |
| 解析引擎并报告根/版本/来源/会话库 | `scripts/printops.sh check` |
| 列出引擎工具（L0/L1，权威） | `scripts/printops.sh tools` |
| 处理一条消息 | `scripts/printops.sh ask "…"` |
| 只跑 MCP/skill 冒烟 | `scripts/printops.sh smoke` |

可用选项：`--session <id>`（默认 `printops`，也可用 `$PRINTOPS_SESSION_ID`）、`--memory <path>`、
`--engine <path>`、`--with-mcp`（默认走 `--no-mcp` 快路径，仅契约验收时需要 MCP 冒烟）。

## 命令

下表是 `<引擎根>` 下的原始命令（单条消息、跨轮会话与冒烟已由 `scripts/printops.sh` 封装，
只有调试引擎本身时才需要手写；Web 工作台脚本不代启）：

| 目的 | 命令 |
| --- | --- |
| Web 工作台 | `python3 server.py` → http://localhost:4174/ |
| 单条规则模式消息 | `python3 tools/printops_local_host.py --session-id <id> --message "…"`（快速查询加 `--no-mcp`） |
| 沿用同一会话（跨轮必带） | 上条命令加 `--memory-path <可写路径>/agent.sqlite3`；不加则每次都是空会话 |
| 逐行交互 | 加 `--interactive`（每行一条消息，逐行输出 JSON） |
| 只跑 MCP/skill 冒烟 | 加 `--smoke`（不能与 `--message`/`--interactive`/`--no-mcp` 同时用） |
| 受信 MCP launcher | `python3 tools/dsh_mcp_launcher.py --session-id <id> --capabilities L0` |
| 只看 launcher argv | 上条命令加 `--dry-run` |
| MCP transcript 冒烟 | `python3 tools/dsh_mcp_smoke.py` |
| 单元/契约/安全测试 | `python3 -m unittest discover -s tests -p "test_*.py"` |
| 评测 | `python3 tests/evaluate_agent.py` |
| 敏感信息扫描 / Git 边界 | `python3 tools/secret_scan.py`、`python3 tools/repo_guard.py` |

后三项测试与扫描脚本只存在于完整仓库，技能内置副本里没有。

## HTTP 接口

`GET /api/health` 免令牌；其余接口都要求 `X-PrintOps-Token`，跨来源请求返回 403。

- GET：`/api/health`、`/api/settings`、`/api/platforms`、`/api/tools`、`/api/products`
- POST：`/api/session`、`/api/session/context`、`/api/chat`、`/api/choose`、`/api/generate`、`/api/confirm`、
  `/api/platform`、`/api/preflight`、`/api/tools/call`、`/api/quote/status`、`/api/quote/cancel`、
  `/api/settings`（写入模型配置）、`/api/model/test`
- 静态白名单只有 `/`、`/index.html`、`/app.js`、`/styles.css`；源码、文档与运行时数据一律 404。

## MCP 工具与能力等级

- **L0（默认，只读/无副作用）**：`validate_order`、`get_order_context`、`recommend_processes`、
  `explain_print_term`、`estimate_price`、`match_supplier_capability`。
- **L1（`--capabilities L0,L1`）**：`preflight_file`、`prepare_handoff`、`request_supplier_quote`、`apply_order_patch`。
- **L2 未实现**：外部副作用必须另起进程；launcher 拒绝 L2 与 `--allow-any-session`。
- 工具只作用于绑定会话的当前订单，不接受外部传入的整单覆盖；`apply_order_patch` 只接受带证据、置信度与
  `expectedRevision` 的增量 patch。
- 模型路径最多 3 轮有界工具调用；重复“工具名 + 参数”会被阻止；模型只回自然语言时按本地意图兜底调用工具；
  工具结果会回传模型总结，失败则回落到确定性规则。

## 安全模型

- 本地访问令牌（进程内随机生成并注入页面）+ 静态白名单 + 跨来源 403。
- SSRF 防护：模型 endpoint 默认拒绝环回/私有/CGNAT/保留/链路本地地址；仅在
  `PRINTOPS_ALLOW_PRIVATE_LLM_HOSTS=1` 时允许受信内网 endpoint。
- API Key 只保存在本机 `data/llm_config.json`（权限 600），不进日志、导出与 Git；也可用
  `PRINTOPS_LLM_URL` / `PRINTOPS_LLM_KEY` / `PRINTOPS_LLM_MODEL` 环境变量提供。
- 模型模式为显式 opt-in：只发送精简订单摘要与受限工具参数，模型不接管订单状态；未配置模型时全程走
  确定性规则模式，数据不出本机。
- SQLite 启用 WAL 与 5s busy_timeout；损坏会话隔离到 `data/corrupted/`。
- Launcher 用 argv 直接 `execve`，不经过 shell；session 必须由受信宿主传入具体值。

## 已知限制（v1.1.0 候选版）

- 真实供应商 live 接入与真实报价回写属于 v1.2+；供应商能力档案是静态示例，“支持/待确认/不支持”只是档案比对，
  不代表产能、价格或交期。
- 真实脱敏语料 20 例、真人走查、真实 dsh headless 端到端与浏览器冒烟仍未完成——不要对外宣称生产可用或通用稳定。
- 费用来自示例参数表，`refPrice` 只是量级参考，必须与 `refPriceBasis`（不构成报价）一起呈现。
- 预检只基于浏览器提供的 PDF 元数据，不替代专业印前检查，也不读取原稿内容。
