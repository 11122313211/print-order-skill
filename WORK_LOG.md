# PrintOps 技能包：工作过程与总结

> 时间：2026-09-15 ｜ 范围：把 PrintOps 引擎内置进技能、维持“仓库优先”的单一事实来源

## 1. 目标与决策

用户提出两个问题：(a) 技能能否脱离桌面上的 MVP 仓库独立运行；(b) 引擎能否直接放进技能里。

实测结论：**能**。把引擎最小集拷到空目录后，品类识别、缺失字段校验、跨轮订单状态、MCP 冒烟全部正常。
因此采用 **“内置兜底、仓库优先”** 方案，而不是二选一：

- 解析顺序：`$PRINTOPS_HOME` → 默认路径 → 自动查找 → 技能内置副本 `engine/`。
- 有仓库时永远用仓库（最新事实来源）；只有确实没有仓库时才用内置副本。
- 内置副本带来源指纹（commit / 版本 / 同步时间），可核对、可刷新。

## 2. 影响分析（先想清楚再改）

| 影响面 | 具体影响 | 处置 |
| --- | --- | --- |
| 体积 | 技能从约 63KB 增至约 652KB（引擎 632KB） | 可接受；上下文档位不受影响（只有 `SKILL.md` 会进上下文，`engine/` 只在运行时被调用） |
| 版本漂移 | 仓库改了规则/价格表，技能内副本不会自动跟着变 | 仓库优先 + `SOURCE_INFO.txt` 指纹 + `engine-check.sh` 核对 + `sync-engine.sh` 刷新 |
| 更新路径 | 从 1 条变 2 条（改仓库 → 同步 → 重装） | 脚本化：`./sync-engine.sh` 后自动跑冒烟；README 写明顺序 |
| 测试覆盖 | 内置副本不在仓库 236 项测试范围内 | 同步脚本每次自动执行 MCP/skill 冒烟，不通过就退出 |
| 数据落点 | 会话库若写进技能目录会因沙箱不可写而失败（实测 `Operation not permitted`） | 会话库改放可写目录（仓库 `data/` 或 `$TMPDIR`）；同时警示云同步目录不要存真实订单 |
| 许可证 | 随包分发 MIT 代码需要保留许可声明 | 内置 `engine/LICENSE` |
| 安全补丁 | 引擎安全修复必须同步到副本，否则两套行为不一致 | 列入发布纪律；`engine-check.sh` 提供可核对口径 |
| 回滚/卸载 | 可能需要回退到无引擎版本 | `install.sh` 覆盖安装并只清理自己管理的路径；删除 `engine/` 即回到薄路由形态 |
| 仓库工具链 | `secret_scan.py` / `repo_guard.py` 不覆盖技能副本 | 技能目录不放密钥；模型模式（API Key）仍建议只用仓库或环境变量 |

## 3. 实施步骤

1. 验证最小引擎集：6 个领域模块 + `llm_adapter.py` + `mcp_server.py` + 3 个 `tools/*.py`，
   外加 `.dsh/skills/`（本地 host 要求该目录存在）与 `data/`。共 17 个文件、632KB。
2. 组装技能：`printops/engine/`（引擎副本 + `VERSION` + `LICENSE` + `SOURCE_INFO.txt`）。
3. 维护脚本：`sync-engine.sh`（仓库 → 副本，写指纹，跑冒烟）、`engine-check.sh`（比对 commit）。
4. 改写 `SKILL.md`：引擎解析顺序加入第 4 项“内置副本”，写明仓库优先、维护命令、数据落点警示。
5. 更新 `references/engine-and-safety.md`：内置引擎章节（组成、优先级、指纹、刷新、许可证、数据）。
6. 更新打包脚本 `install.sh`：除 `SKILL.md`/`references`/`agents` 外，复制 `engine/` 与 `*.sh` 并保留可执行位。
7. 全量验证 → 部署到桌面母版与 `~/.codex/skills` → 重打 zip。

## 4. 验证记录

| 项目 | 做法 | 结果 |
| --- | --- | --- |
| 脱离仓库运行 | 空目录拷贝最小集后执行本地 host | 通过（品类识别、缺字段、13 项工具结果） |
| MCP 边界 | 不传 `--no-mcp`，走完整 stdio 冒烟 | 通过（5 个 dsh skill 被发现） |
| 跨轮状态 | 同一 `--memory-path` 连续两条消息 | 通过（“500 张三折页” → “数量改成 1200 张”仍为折页） |
| 技能规范 | skill-creator `quick_validate.py` | 两个技能均通过 |
| 安装脚本 | 用临时假 `CODEX_HOME` 试装（全装 / 只装 lite） | 通过；`printops` 652KB、`printops-lite` 40KB |
| 同步脚本 | 从仓库同步并写指纹 | 通过，冒烟通过 |
| 一致性核对 | `engine-check.sh` | 通过（修正后报“一致”；曾误报，见下） |

### 过程中发现并修复的问题

1. **内置副本缺 `llm_adapter.py`**：`mcp_server.py` 依赖它，缺文件时 MCP 启动失败 → 补入。
   这是最初“最小集 = 7 个文件”估算的疏漏，实际需要 9 个 Python 文件。
2. **本地 host 要求 `.dsh/skills/` 存在**：缺失时直接报错 → 副本内保留该目录的 5 个 dsh skill。
3. **`engine-check.sh` 误报**：脏工作区备注被并进 commit 字符串，导致永远“不一致” → 改为
   `commit` 与 `worktree` 分两行，比较只用 commit。
4. **技能目录不可写**：把会话库指向 `<技能目录>/engine/data/` 时，被测环境报
   `PermissionError: Operation not permitted`（`~/.codex` 不在可写范围）→ 技能指引改为
   “有仓库用仓库 `data/`、没有仓库用 `$TMPDIR` 等可写路径，不要写进技能目录”。

## 5. 已知限制与后续

- 内置副本是**手动同步**的：技能里的引擎不会自动跟随仓库；发布前需要跑 `./sync-engine.sh`。
- 副本没有独立的测试套件，只跑冒烟；真正的回归仍在仓库侧执行。
- 若将来把引擎发成正式发布物（GitHub release / 包管理器），应改为“技能声明版本 + 拉取发布物”，
  内置副本可退化成纯离线兜底或直接移除。

## 6. 结论（闭环）

- 两个问题都有了确定答案：技能可脱离桌面仓库运行；引擎可以放进技能，且已按“仓库优先、内置兜底”
  落地，附带可核对的指纹与刷新脚本。
- 风险最高的两项（版本漂移、数据落点）都有显式处置：前者靠优先级 + 指纹 + 核对脚本，后者靠文档警示。
- 许可证与安全补丁两项合规要求已处理（`LICENSE` 随包、同步纪律写入文档）。
- 交付物：桌面母版 `printops-skill/`、`printops-skill.zip`、`~/.codex/skills/printops`、
  `~/.codex/skills/printops-lite`，三处内容一致。

---

# 第二轮：按渐进披露重排技能结构

> 时间：2026-09-16 ｜ 范围：只改工作区母版，未安装到 `~/.codex` 或 `~/.dsh`
> 目标：减少每次加载的上下文占用、提升被选中率与工具识别效率

## 7. 先核对实现，再决定怎么写

参照"元数据负责被选中、正文负责立刻能干、资源负责细节"的三层模型，但**不能照抄结论**——
直接读了宿主实现（`dsh-skill-filesystem` / `dsh-tool-skill` / `dsh-skill`）后有三个关键事实：

| 事实 | 依据 | 对写法的影响 |
| --- | --- | --- |
| 模型目录每行只有 `` - `name`: description `` | `renderCatalogEntries()` | 触发词**与排除项**都必须进 `description`，它是唯一路由面 |
| `description` 超过 500 字符会被截断 | `DEFAULT_CATALOG_DESCRIPTION_MAX_LENGTH = 500` | 预算按 500 卡，实际控制在 200 出头留余量 |
| **`whenToUse` 不进模型上下文** | 唯一消费者是 `dsh-api-session-controller`（会话 API / GUI 目录）；测试夹具注为"仅供 UI 目录渲染验收" | 可以写给人看，但**不能**把排除项、路由条件挪进去——放进去等于没写 |
| 调用开关必须是布尔，驼峰旧键直接丢弃技能 | `frontmatterBoolean()` / `rejectLegacyInvocationKey()` | 增加机器自检，提前拦住"技能好像不存在"这类无诊断故障 |

## 8. 结构变更

| 变更 | 内容 | 收益 |
| --- | --- | --- |
| 正文瘦身 | `printops` 正文 133 → 78 行（约 -41%，且**新增**了工具速查）；`printops-lite` 55 → 54 行（篇幅相当，主要是重排：9 行对比表压成 2 行，腾出的位置给了自检步骤） | 每次调用少付约四成正文成本 |
| 命令下沉为脚本 | 新增 `printops/scripts/printops.sh`（`check`/`tools`/`ask`/`smoke`） | 引擎解析顺序、版本校验、会话库落点从"要求模型照做"变成"跑一条命令" |
| 工具速查进正文 | 按 L0/L1 分组列出 10 个工具，并指向 `printops.sh tools` 取权威清单 | 工具识别不再需要先读 `references/` |
| 维护脚本归位 | `sync-engine.sh`、`engine-check.sh` 迁入 `scripts/` | 资产布局统一，安装脚本可用一份清单复制与清理 |
| 新增确定性校验 | `printops-lite/scripts/check_draft.py` | 草稿 JSON 的白名单/置信度/证据/`verified` 由脚本判定，不靠模型自觉 |
| 新增机器自检 | `validate-skills.py` | 校验 frontmatter 合法性 + 正文资源引用是否存在 + 孤儿资源提示 |
| 安装脚本清单化 | `install.sh` 按 `managed_dirs` 复制与清理，并清掉旧布局遗留在根目录的 `*.sh` | 升级不残留上一版文件，同时不动同目录下别人的文件 |

## 9. 行为变更（需要知情）

1. **默认走快路径**：`printops.sh ask` 默认带 `--no-mcp`（跳过 MCP transcript 冒烟），要契约验收时加 `--with-mcp`。
   规则结果不受影响，只是不再每次调用都验一遍 MCP。
2. **内置副本不再写技能目录**：会话库落点改为——真实仓库写 `<仓库根>/data/agent.sqlite3`；
   内置副本**一律不写技能目录**，默认落 `${TMPDIR:-/tmp}`，可用 `--memory` / `$PRINTOPS_MEMORY` 覆盖。
   第一轮只在文档里警示"不要写进技能目录"，这一轮把它变成了脚本里的硬规则。
   > 这是本次唯一一处"文档说要避免、但默认行为其实会踩"的修正：试装到可写的技能目录时，
   > 旧逻辑会把会话库写进技能目录内部。
3. **自动查找默认不扫 `/Volumes`**：改为扫 `$PRINTOPS_SEARCH_ROOTS`（默认 `~/Desktop ~/Documents ~/Projects
   ~/code ~/dev ~/src`），避免网络卷挂起；要恢复旧行为就设 `PRINTOPS_SEARCH_ROOTS="$HOME /Volumes"`。
4. **`--engine` 硬失败**：显式指定的引擎根无效时直接报错，不再静默换用别的引擎（避免用错数据源）。
   `$PRINTOPS_HOME` 无效则告警后继续按默认顺序查找。

## 10. 验证记录

| 项目 | 做法 | 结果 |
| --- | --- | --- |
| 元数据能否被加载 | 用 DSH 依赖的 `yaml@2` + 逐行复刻 `parseFrontmatter`/`parseInvocationPolicy` 解析两个 `SKILL.md` | 通过；目录行长度 225 / 197 字符，未触发截断 |
| frontmatter 自检 | `validate-skills.py`；另造非法样本（非 kebab-case + 驼峰键 + 引用不存在的文件） | 两个技能通过；非法样本报 3 个 error 且退出码 1 |
| 引擎入口 | `check`（自然解析→仓库／强制内置副本）、`tools`（10 个工具带 L0/L1 与中文说明） | 通过 |
| 跨轮状态 | 同一 `--memory` 连续两条消息：`做500张三折页` → `数量改成1200张` | 通过：`productType` 仍为折页，`quantity` 1200 张，纸张保留 |
| 落点规则 | 内置副本、真实仓库（沙箱不可写）、显式 `--memory` 三种情况 | 内置副本→`$TMPDIR`；仓库不可写→回落 `$TMPDIR`；显式路径优先 |
| 错误路径 | 版本 0.9.0、无效 `--engine`、无效 `$PRINTOPS_HOME`、完全找不到引擎 | 分别：报错退出 1 / 报错退出 1 / 告警后回退 / 报错退出 1 |
| 草稿校验器 | 合法草稿、含越界字段与 `verified:true` 的坏草稿、stdin、非法 JSON | 0 error / 3 error / 通过 / 退出码 2 |
| 安装脚本 | 假 `CODEX_HOME` 全装；再造旧布局残留（根目录 `sync-engine.sh` + 外来 `stale.txt`）重装 | 布局正确、脚本可执行、旧脚本被清、外来文件保留；装好的副本 `check` 可跑 |
| 变量展开 | 扫描 `$var` 紧跟中日韩字符的位置 | 修复 3 处（`$min_version（`、`$engine_root）`、`$name：`） |

### 过程中发现并修复的问题

1. **bash 把多字节括号吞进变量名**：`"…$min_version（引擎根…"` 触发 `min_version�: unbound variable`，
   错误信息本身也变成乱码。中文提示里的 `$var` 一律改 `${var}`；顺带修掉了 `install.sh` 里同样的
   `$name：`（原有代码，只在"跳过某技能"分支暴露）。
2. **会话库会写进技能目录**：落点探测原本只看目录是否可写，装到可写的技能目录时会把真实订单写进技能内部 →
   改为"内置副本一律不写技能目录"。
3. **跨技能路径误报**：`printops-lite` 正文引用了另一个技能的 `scripts/printops.sh`，自检报"文件不存在" →
   正文改为不依赖跨技能路径的描述，自检只校验本技能资源目录内的引用。
4. **`--engine` 静默回退**：无效路径会悄悄改用其它引擎，等于用错事实来源 → 改为硬失败。
5. **孤儿资源无法发现**：新增自检后确认 `references/`、`scripts/` 下每个文件都被正文引用（无孤儿）。

## 11. 已知限制与后续

- **引擎自带的 5 个 `.dsh/skills/*` 未改动**：它们属于引擎，`sync-engine.sh` 会整目录覆盖，
  改了也留不住；技能正文已注明"只作参考，不要手改"。要改得先改仓库。
- **未做真实 DSH 加载实测**：本轮只复刻了解析器与目录渲染，没把技能放进 `~/.dsh/skills` 跑一遍
  （用户要求先只改工作区）。首次部署时建议真的装一次并观察会话里的 `<available_skills>` 行。
- **`check_draft.py` 的白名单是文档镜像**：与 `references/order-contract.md` 同步，引擎升级后要一起核对。
- **`printops.sh tools` 依赖 `mcp_server.py` 的 `L0_TOOLS`/`L1_TOOLS`/`MCP_TOOL_DESCRIPTIONS`**：
  这是引擎内部符号，引擎改名会让该子命令失败（其余子命令不受影响）。
