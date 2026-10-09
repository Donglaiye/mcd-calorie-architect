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

两个 Python 脚本，均带 `--self-test`：

- `scripts/meal_planner.py`：三重约束组合优化，含单品淘汰 / 候选池裁剪 / 累加剪枝三层剪枝，
  以及营养指纹去重（营养完全一样时只留最便宜的，避免为凑件数搭售 0 热量商品）
- `scripts/burn_calc.py`：ACSM 代谢当量公式，把热量换算成跑步/快走/骑车/游泳/跳绳的分钟数、公里数、步数

开发过程中自测抓出的真实问题：

1. `burn_calc` 自测 1 报「非线性」——实际是断言写在了四舍五入之后的展示值上
   （42.35 显示为 42.4，两倍后 84.7 ≠ 84.8）。修正为对未取整的底层计算做线性断言，
   并额外断言取整展示值与真实值的偏差。
2. 首次端到端跑通后，发现方案 3 比方案 2 多花 ¥9 买一瓶 0 kcal 的零度可乐，
   营养完全相同却更贵。为此新增营养指纹去重，并补了对应的自测 5。

最终状态：`meal_planner.py` 5 项自测、`burn_calc.py` 5 项自测，共 10 项断言全部通过。

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

- [ ] 申请麦当劳 MCP Token 后接入连接器，用真实营养数据跑通一次并补齐实测记录
- [ ] 推送至 GitHub 公开仓库
- [ ] 在官方活动仓库提交报名 Issue
