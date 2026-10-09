---
name: mcd-calorie-architect
description: 麦门卡路里精算师。基于麦当劳官方 MCP 的真实营养数据，在热量上限、蛋白质下限和预算上限三重约束下算出最优配餐组合，并把热量翻译成要跑几公里。当用户问吃麦当劳怎么不胖、怎么控卡、多少大卡、要跑几公里、健身怎么点麦当劳、减脂增肌怎么吃时使用。
version: 1.0.0
---

# 🍟 麦门卡路里精算师（McDonald's Calorie Architect）

把「我想吃麦当劳」和「我在控卡/健身」这两件冲突的事，一次性算清楚。

和常见"省钱凑单"类 Skill 的区别是：**本 Skill 的第一约束是热量和蛋白质，价格是第二约束**，
并且用的是麦当劳官方 MCP 的真实营养数据，不是估算、不是编的。

## 核心能力

| 模式 | 触发示例 | 做什么 |
|---|---|---|
| 🧮 卡路里配餐 | "午餐 600 大卡怎么吃" "今天练腿，蛋白要 40g" | 拉真实营养数据 → 约束求解 → 输出 Top3 方案（热量/蛋白/脂肪/碳水/钠/价格全列出） |
| 🔥 运动换算 | "这顿要跑几公里" "吃完得走多少步" | 把热量翻译成跑步/快走/骑车/游泳/跳绳的分钟数、公里数、步数 |
| 💰 双目标 | "600 大卡以内，最好别超过 35 块" | 同时约束热量和预算 |
| 🛒 确认下单 | "就按方案 2 下单" | 复核实付价 → 展示明细 → 用户确认后才创建订单 |
| ☀️ 每日轻食播报 | "麦麦轻食早报"（可挂定时任务） | 今日活动 + 低卡推荐 + 积分提醒 |

## 工作流

### 第一步 收集约束（缺什么问什么，不要替用户拍板）

必须问清的：`max_calories`（热量上限）
能推断就推断，推断不了就问：`min_protein`、`max_price`、`max_sodium`、`must_categories`（必吃品类）、`max_items`（最多几件）

如果用户没给热量上限，但有目标（如"减脂中"），按下面的默认值给，并**明确告诉用户这是默认值**：
减脂午餐 600 / 增肌午餐 800 / 随便吃吃 900。

### 第二步 拉真实数据（不要凭印象估热量）

1. `query-nearby-stores` 定位门店
2. `query-meals` 拿当前可售餐品与编码
3. `list-nutrition-foods` 拿营养数据（能量/蛋白质/脂肪/碳水/钠）
4. 套餐用 `query-meal-detail` 单独拆开取营养，**不要用单点相加代替**
5. 需要控制花费时，再取 `query-store-coupons` + `calculate-price`

`list-nutrition-foods` 返回的是自定义文本格式（形如 `[160]{字段...}:` 加数据行），
用解析器转成标准 JSON：

```bash
python scripts/parse_nutrition.py --input mcp_response.json --output items.json
```

然后把 `items.json` 的 items 连同约束整理成 `examples/sample_input.json` 的形状，喂给优化器：

```bash
python scripts/meal_planner.py --mode cut < input.json
```

参数说明见 `scripts/meal_planner.py --list-modes`。

### 第三步 输出方案

按优化器输出原样呈现，包含：每件的热量/蛋白/价格、合计的五大营养素与总价、热量余额。
**不要**为了好看去四舍五入到"整百大卡"——用户是靠这个数字控卡的。

### 第四步 运动换算（用户问"要跑多久"时）

```bash
python scripts/burn_calc.py 549 --weight 68
```

体重默认 65kg，用户给过体重就用用户的。

### 第五步 下单（必须经过确认）

1. 用 `calculate-price` 复核实付价，把明细摆给用户
2. 用户明确说"下单/就这个"之后才调 `create-order`
3. **任何涉及支付、积分消耗的动作，未经确认一律不动**

## 硬性原则

1. **不编造营养数据**。MCP 拿不到就明说"当前拿不到实时数据，以下是估算"，绝不把估算伪装成实时数据。
2. **不替用户决定热量目标**。用户说"我想减肥"，可以建议，但要把建议值显式标出来让用户确认。
3. **钱和权益的动作必须确认**。下单、取消、积分兑换、抽奖，全部需要显式指令。
4. **输出不是医疗建议**。涉及疾病、孕期、未成年、进食障碍等，建议咨询医生或营养师。
5. **钠要一起报**。控卡人群常常也要控钠，默认输出钠，别只报热量。

## 降级策略

MCP 不可用（401 Token 失效 / 429 限流 / 网络问题）时：
- 明确告知用户原因（401 要重新申请 Token，429 要降低频率）
- 不要静默切换到编造的数据
- 可以提示用户：离线状态下可先用 `scripts/meal_planner.py --self-test` 验证算法本身是可用的

## 算法验证

两个脚本都有内置自测，改动后必须跑：

```bash
python scripts/meal_planner.py --self-test
python scripts/burn_calc.py --self-test
python scripts/parse_nutrition.py --self-test
```

共 14 项断言，覆盖约束遵守性、无解返回空、模式排序、脏数据容错、营养指纹去重、
运动换算线性与边界、MCP 格式解析与 kJ 兜底换算、品类推断。

## 目录

```
├── SKILL.md                     本文件
├── scripts/
│   ├── meal_planner.py          配餐组合优化器（带剪枝 + 营养指纹去重 + 自测）
│   ├── burn_calc.py             运动消耗换算器（ACSM MET 公式 + 自测）
│   └── parse_nutrition.py       MCP 营养数据解析器（自定义格式 → 标准 JSON + 自测）
├── references/
│   ├── tools.md                 麦当劳 MCP 工具速查与实测要点
│   └── nutrition-strategy.md    配餐策略与免责边界
└── examples/
    ├── sample_input.json        可直接跑的输入样例
    ├── demo.md                  完整对话示例
    └── live-run-2026-10-10.md   真实 MCP 数据跑通记录（160 条餐品）
```
