# PrintOps · 印刷订单 Skill

> 把客户一句「我想印 500 份三折页」，变成一张**每个字段都有出处、并经人工确认**的订单交接单。

本仓库是一个可直接安装的 agent skill（ZCode / 兼容 SKILL.md 约定的宿主均可加载）。
你用大白话说需求，它负责：参数补齐 → 术语对齐 → 三档工艺方案 → 参考费用量级 →
PDF 印前线索 → 生成人工确认后的交接单草稿。

- **本地运行**：不发起任何外部网络请求，订单数据只落在你指定的工作目录。
- **零依赖**：纯 Python 标准库（3.9+），不需要 `pip install`。
- **字段可溯源**：每个字段记录来源（规则识别 / 用户确认）、置信度与时间。
- **人工确认闸门**：交接单与询价草稿只是草稿；工具不替你联系供应商、不承诺报价。

## 安装

```bash
git clone https://github.com/11122313211/print-order-skill.git
cd print-order-skill
./install.sh                 # 安装到 ~/.agents/skills/ 与 ${CODEX_HOME:-~/.codex}/skills/
```

或手动把 `printops/` 目录整个复制到宿主的技能目录（如 `~/.agents/skills/printops-1.3.0/`）。
发布前可自检：`python3 validate-skills.py printops`。

## 用起来是什么样

装好后直接对 AI 助手说需求即可，例如：

> 做 500 份 A4 宣传册，32页骑马钉，157g哑粉纸，双面四色，下周内

技能会识别品类、数量、尺寸、纸张、颜色、装订与交期，缺什么就追问什么（一次最多问
两三个），并确认低置信度的推断（比如"是用作品牌宣传吗？"）。参数齐了给出三档方案：

| 方案 | 印刷方式 | 材料 | 表面工艺 | 参考费用* | 适用 |
| --- | --- | --- | --- | --- | --- |
| 经济 | 合版 | 157g 哑粉纸 | 无特殊工艺 | ¥1139.73-1676.08 | 控预算 |
| 平衡（综合推荐） | 合版 | 200g 铜版纸 | 哑膜 | ¥1330.95-1957.28 | 大多数场景 |
| 质感 | 专版 | 300g 铜版纸 | 烫金/击凸 | ¥2125.74-3126.09 | 品牌/高端 |

\* 示例参数估算，不构成报价，以供应商回复为准。

改单也是一句话："数量改成 1200""不要覆膜"——改的是同一张订单，已确认的参数不会丢。
多产品需求（"500张名片和200个纸杯"）会拆成独立订单分别推进。

## 命令一览

技能内部由 `printops/scripts/printops_cli.py` 驱动（模型负责对话与呈现，以下命令
由它在对话中调用；你也可以手动运行）：

```bash
python printops/scripts/printops_cli.py ingest --text "<用户原话>"   # 主入口：理解并合并进订单
python printops/scripts/printops_cli.py status                      # 当前订单 + 校验 + 待追问
python printops/scripts/printops_cli.py recommend                   # 三档工艺方案
python printops/scripts/printops_cli.py price                       # 参考费用区间
python printops/scripts/printops_cli.py capability                  # 平台能力逐字段匹配
python printops/scripts/printops_cli.py quote                       # 询价草稿（不发送）
python printops/scripts/printops_cli.py handoff --out 交接单.md     # 交接单草稿（需人工确认）
python printops/scripts/printops_cli.py preflight 文件.pdf          # PDF 印前线索扫描
python printops/scripts/printops_cli.py terms "哑粉纸和铜版纸的区别" # 术语解释
python printops/scripts/printops_cli.py catalog --product 名片      # 品类档案与追问口径
python printops/scripts/printops_cli.py reset                       # 删除订单文件重新开始
```

订单状态默认写在当前工作目录的 `printops-order.json`；不要把真实客户订单存进技能目录。

## 我们刻意不做的事

- **不做平面设计、不做印前文件制作与修复**（PDF 预检只给线索，不给结论）。
- **不接真实供应商**：不下单、不发询价、不承诺交期与产能；一切对外动作由人完成。
- **不给确定报价**：费用来自版本化示例参数表（当前 `2026.11.01`），只是量级参考。
- **不猜**：立体造型件（纸模型、异形摆件）明确超出 18 类品类范围，会如实说明并给出
  打样件、数码快印等替代路线，而不是硬塞进最近的品类。

## 引擎与溯源

`printops/scripts/` 内置 PrintOps 引擎的 12 个模块快照（规则感知、订单契约、工具集、
品类知识、平台适配，以及 v1.3.0 起拆分出的词表、单位换算、测量语义、估价引擎、
费率契约、连接器契约），费率卡数据在 `rate_cards/`，基线指纹见
[`printops/scripts/SOURCE_INFO.txt`](printops/scripts/SOURCE_INFO.txt)：

- 上游：[11122313211/PrintOps](https://github.com/11122313211/PrintOps) v1.3.0（commit `7226a25`，2026-11-01 同步）
- 知识版本 `2026.09.05`、价格参数表 `2026.11.01`（均随工具输出返回，可追溯）
- 上游升级后更新快照、刷新指纹并回归测试 `printops_cli.py`

## 支持的品类（18 类）

宣传册 · 画册 · 单页 · 折页 · 名片 · 邀请函 · PVC 卡 · 吊牌 · 联单 · 信封封套 · 标签 ·
包装盒 · 手提袋 · 纸杯 · 海报 · 喷画 · PVC 展板 · 数码快印

## License

[MIT](LICENSE)。引擎核心模块来自 [PrintOps](https://github.com/11122313211/PrintOps)（MIT）；
品类口径参考盛大印刷公开产品导航（[sd2000.com](https://www.sd2000.com/)）等公开信息整理，
仅用于参数对齐，不代表任何供应商的实时价格、产能或交期。
