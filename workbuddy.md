# WorkBuddy 联动开发记录

> 本文件记录本项目使用 WorkBuddy 开发的上下文，用于核验 WorkBuddy 专项奖励条件。

## 开发工具

- 客户端：WorkBuddy 桌面端（Windows）
- 协助内容：赛事规则检索与解读、方向选型、Skill 编写、算法实现与自测、文档撰写、仓库结构搭建

## 开发过程

### 1. 赛事调研（WorkBuddy 联网检索完成）

- 定位到官方活动仓库 `M-China/mcd-developer-innovation-challenge`，通读 README 与 activityGuidelines
- 梳理出报名硬性要求：仓库必须包含 `README.md`、`CONTEST_DECLARATION.md`（内容不可改动）、
  `MCP_INTEGRATION.md`、源代码；报名走 Issue；排名依据是 GitHub Star 数
- 定位到官方 MCP Server 仓库 `M-China/mcd-mcp-server`，拿到完整 35 个 Tool 清单

### 2. 方向选型（基于竞品调研的差异化决策）

调研发现开赛首日已有参赛作品切入「凑单省钱 / 一键领券」方向（如麦门精算师），该赛道已经拥挤。

转而查官方 Tool 清单，发现 `list-nutrition-foods`（餐品营养信息列表）的官方描述中明确提到
「需要帮助用户搭配指定热量套餐时使用此工具」——**这是一个官方提供但无人使用的能力**。

因此定方向：**卡路里配餐**，第一约束是热量与蛋白质，价格降为第二约束。
这样既避开拥挤赛道，又用上了官方钦定但闲置的能力。

### 3. 算法实现与验证（WorkBuddy 直接写代码并跑通）

三个 Python 脚本，均带 `--self-test`：

- `scripts/meal_planner.py`：三重约束组合优化，含单品淘汰 / 候选池裁剪 / 累加剪枝三层剪枝，
  以及营养指纹去重（营养完全一样时只留最便宜的，避免为凑件数搭售 0 热量商品）
- `scripts/burn_calc.py`：ACSM 代谢当量公式，把热量换算成跑步/快走/骑车/游泳/跳绳的分钟数、公里数、步数
- `scripts/parse_nutrition.py`：`list-nutrition-foods` 自定义文本格式的解析器，含品类推断与 kJ 兜底换算

开发过程中自测抓出的真实问题：

1. `burn_calc` 自测 1 报「非线性」——实际是断言写在了四舍五入之后的展示值上
   （42.35 显示为 42.4，两倍后 84.7 ≠ 84.8）。修正为对未取整的底层计算做线性断言，
   并额外断言取整展示值与真实值的偏差。
2. 首次端到端跑通后，发现方案 3 比方案 2 多花 ¥9 买一瓶 0 kcal 的零度可乐，
   营养完全相同却更贵。为此新增营养指纹去重，并补了对应的自测 5。
3. 接真实 MCP 数据后，发现品类推断把「冰美式小杯」归成了"其他"——它名字里没有"咖啡"二字。
   补充关键词后加了断言。这类问题只有真数据才能暴露，样例数据永远碰不到。

最终状态：三个脚本共 **14 项断言**全部通过。

### 3.5 真实 MCP 数据跑通（用户拿到 Token 后）

- 直连 `https://mcp.mcd.cn/`（Streamable HTTP，POST JSON-RPC）验证 Token 有效，服务端回 `mcd-mcp v1.0.0`
- `tools/list` 拿到 **35 个工具**
- `list-nutrition-foods` 返回 **160 条**真实餐品营养记录，解析后直接喂进优化器跑通
- 实测得出关键结论：**只约束热量和蛋白时，最优解钠高达 1996 mg**（一天推荐 2000 mg）；
  加 `max_sodium: 1500` 后钠降到 1465 mg、蛋白从 54 g 掉到 46 g。
  **热量与钠是独立维度**——这个结论只有真数据能得出，已写进 README 与实测记录。
- 本次未取价格：营养接口不含价格，需另走门店链路（需用户城市）

### 4. 文档撰写（WorkBuddy 生成）

- `SKILL.md`：四类模式、五步工作流、五条硬性原则（不编造营养数据 / 不替用户决定热量目标 /
  资金动作必须确认 / 输出不是医疗建议 / 钠要一起报）、降级策略
- `MCP_INTEGRATION.md`：7 步调用流程图、实际使用的 Tool 清单、业务价值、降级与容错表
- `README.md`：面向拉 Star 的项目门面，含差异化论证与可直接复现的命令
- `references/tools.md`、`references/nutrition-strategy.md`、`examples/demo.md`

### 5. 合规处理

- `CONTEST_DECLARATION.md` 取自官方仓库原文件，内容未作任何改动
- 全仓库不含真实 Token，配置示例仅保留 `YOUR_MCP_TOKEN` 占位符
- 全仓库不含个人绝对路径、不含他人个人信息

## 待办

- [x] 申请麦当劳 MCP Token 后接入连接器，用真实营养数据跑通一次并补齐实测记录
- [x] 推送至 GitHub 公开仓库
- [x] 在官方活动仓库提交报名 Issue（#159），官方已回复确认报名成功
- [x] 补 `.gitignore`
- [x] 补 `mcp-config.example.json`（脱敏 MCP 配置示例，仅含环境变量占位符）
- [x] 接价格链路（深圳门店实测）后跑一次带价格的完整实测（见 `examples/live-run-2026-10-10.md`）
- [ ] 拉 Star（定榜 2026-10-26 00:00）

## WorkBuddy 专项奖励

本项目全程在 WorkBuddy 桌面端（Windows）中开发，符合 WorkBuddy 专项奖励的参与条件：
本文件即按赛事要求提交的 WorkBuddy 开发上下文记录，涵盖赛事调研、方向选型、算法实现、
真实数据接入、文档撰写与合规处理的完整过程；三次真实自测抓出的 bug、营养指纹去重的由来、
双数据源对齐等关键决策均由此对话上下文沉淀而来。
