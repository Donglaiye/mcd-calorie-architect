# MCP 集成说明

> 说明本项目实际使用的麦当劳 MCP Server、Tool、调用流程与业务价值。

## 1. 使用的 MCP Server

| 项 | 值 |
|---|---|
| 官方仓库 | [M-China/mcd-mcp-server](https://github.com/M-China/mcd-mcp-server) |
| 接入地址 | `https://mcp.mcd.cn` |
| 传输协议 | Streamable HTTP |
| 认证方式 | 请求头 `Authorization: Bearer <MCP_TOKEN>` |
| Token 申请 | [open.mcd.cn/mcp](https://open.mcd.cn/mcp) 手机号登录 → 控制台 → 激活 |
| 限流 | 600 次/分钟（429 需降频；401 需重新申请 Token） |

配置示例（不含真实 Token，仅占位符）：

```json
{
  "mcpServers": {
    "mcd-mcp": {
      "type": "streamablehttp",
      "url": "https://mcp.mcd.cn",
      "headers": {
        "Authorization": "Bearer YOUR_MCP_TOKEN"
      }
    }
  }
}
```

## 2. 实际调用的 Tool

### 核心链路（配餐）

| # | Tool | 输入 | 输出用途 |
|---|---|---|---|
| 1 | `query-nearby-stores` | 用户位置 | 确定售卖门店 |
| 2 | `query-meals` | 门店 ID | 当前可售餐品、分类、餐品编码 |
| 3 | **`list-nutrition-foods`** | — | **餐品营养成分：能量/蛋白质/脂肪/碳水/钠/钙** |
| 4 | `query-meal-detail` | 餐品编码 | 套餐组成、可替换项、套餐独立营养值 |
| 5 | `query-store-coupons` | 门店 ID | 可用券（双目标模式的省钱侧） |
| 6 | `calculate-price` | 商品 + 券 | 实付价复核 |
| 7 | `create-order` | 门店/就餐方式/商品 | 创建订单（**需用户显式确认**） |

### 辅助链路

| Tool | 用途 |
|---|---|
| `available-coupons` / `auto-bind-coupons` | 可领券列表与一键领券 |
| `cancel-order` | 取消订单兜底 |
| `campaign-calendar` | 当月营销活动日历（每日播报） |
| `query-my-account` | 积分账户与临期积分提醒（每日播报） |
| `now-time-info` | 判断早餐/午餐时段 |

## 3. 调用流程

```
用户："600 大卡以内，想吃堡，别超 40 块"
        │
        ├─ ① query-nearby-stores ──────► 门店 ID
        ├─ ② query-meals ──────────────► 可售餐品 + 编码
        ├─ ③ list-nutrition-foods ─────► 营养数据（能量/蛋白/脂肪/碳水/钠）★ 核心
        ├─ ④ query-meal-detail ────────► 套餐独立营养值 + 可替换项
        │
        ├─ ⑤ 本地约束求解 scripts/meal_planner.py
        │      约束：热量上限 / 蛋白下限 / 预算上限 / 必吃品类 / 件数 / 钠上限
        │      输出：Top3 配餐方案
        │
        ├─ ⑥ scripts/burn_calc.py ─────► 运动换算（公里/步数/分钟）
        │
        └─ ⑦ 用户确认 → calculate-price → create-order
```

**关键设计**：MCP 只负责提供**真实数据**，组合优化与运动换算放在本地脚本里完成。
这样做的好处是离线也能验证算法（`--self-test`），且不受 MCP 限流影响。

## 4. 业务价值

1. **启用了一个被闲置的官方能力**：`list-nutrition-foods` 的官方描述中明确提到「搭配指定热量套餐」，
   但公开可见的麦当劳 Skill 普遍只用到点餐/领券/省钱链路，营养数据几乎无人使用。本项目把它作为核心数据源。
2. **把抽象热量翻译成可感知的行为**：用户看不懂「549 kcal」，但看得懂「要跑 7 公里、走 1 万步」。
   这是从数据到决策的最后一公里。
3. **多目标同时优化**：热量、蛋白、价格、钠四类约束可同时成立，覆盖减脂、增肌、控预算、控钠四种人群。
4. **安全边界清晰**：所有涉及资金与权益的动作（`create-order`、`cancel-order`、积分兑换）都在确认之后执行，
   且营养输出始终标注「不构成医疗或营养建议」。

## 5. 降级与容错

| 情况 | 处理 |
|---|---|
| 401 Token 失效 | 提示用户重新申请 Token，**不**退回估算数据 |
| 429 触发限流 | 降低调用频率并重试，仍失败则如实告知 |
| 营养数据缺失 | 明确标注该餐品用的是估算值，并在输出中标出 |
| MCP 完全不可用 | 提示用户可用 `scripts/meal_planner.py --self-test` 验证算法本身 |

## 6. 合规

- 本仓库不包含任何真实 Token，配置示例仅使用 `YOUR_MCP_TOKEN` 占位符
- 遵守麦当劳《使用条款》与《麦当劳 MCP 服务规则》
- 非商业用途，不暗示官方背书
