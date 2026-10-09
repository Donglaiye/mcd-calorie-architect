# 麦当劳 MCP 工具速查

> 来源：麦当劳中国官方 MCP Server 使用指南（M-China/mcd-mcp-server）
> 接入地址 `https://mcp.mcd.cn`，Streamable HTTP，请求头 `Authorization: Bearer <TOKEN>`
> 限流：600 次/分钟；401 = Token 无效，429 = 触发限流

## 本 Skill 实际用到的工具

| Tool | 用途 | 在本 Skill 中的位置 |
|---|---|---|
| `list-nutrition-foods` | 获取餐品营养成分（能量/蛋白质/脂肪/碳水/钠/钙），官方说明中明确用于「帮助用户搭配指定热量套餐」 | **核心数据源**，配餐优化器的输入 |
| `query-nearby-stores` | 查询附近可用门店 | 确定售卖门店 |
| `query-meals` | 查询门店当前可售餐品（分类、编码、标签） | 拿餐品编码与实时菜单 |
| `query-meal-detail` | 查询餐品详情与套餐组成、可替换项 | 拆分套餐、做替换（换小薯、换无糖） |
| `query-store-coupons` | 当前门店可用优惠券 | 计算实付价 |
| `available-coupons` / `auto-bind-coupons` | 可领券列表 / 一键领券 | 双目标模式的省钱侧 |
| `calculate-price` | 按商品与券计算金额、配送费、优惠、应付总价 | 下单前复核真实到手价 |
| `create-order` | 创建订单，返回订单详情与支付链接 | 用户确认后下单 |
| `cancel-order` | 取消订单 | 反悔兜底 |
| `campaign-calendar` | 当月营销活动日历 | 每日播报的活动部分 |
| `query-my-account` | 积分账户（可用/累计/冻结/即将过期） | 每日播报的积分提醒 |
| `now-time-info` | 当前时间 | 判断是否早餐/午餐时段 |

## 其余官方工具（未直接使用，供扩展）

`delivery-query-addresses`、`delivery-create-address`、`delivery-query-stores`、
`query-meal-assistance`、`order-list`、`query-order`、`query-my-coupons`、
`mall-points-products`、`mall-product-detail`、`mall-create-order`、`mall-order-list`、
`mall-order-detail`、`query-lottery-info`、`draw-lottery`、`query-my-prizes`、
`query-party-city`、`query-party-store`、`query-partystore-date`、`query-partystore-session`、
`party-order-create`

## 实测要点（2026-10-10 真实调用验证）

0. **`list-nutrition-foods` 是零参数的**，直接 `tools/call` 即可，实测返回 **160 条**餐品营养记录，
   字段为 `productName / nutritionDescription / energyKj / energyKcal / protein / fat / carbohydrate / sodium / calcium`，
   以 `[160]{...}:` 表头 + 数据行的自定义文本格式返回（需要解析，见 `scripts/parse_nutrition.py`）。
   ⚠️ **该接口不返回价格**，价格要走 `query-nearby-stores` → `query-meals` 另一条链路。
1. **营养数据以 `list-nutrition-foods` 为准**，不要凭印象估算热量——不同门店、不同批次配方会变。
   **接口也不返回分类字段**，品类需按餐品名推断（注意「冰美式小杯」不含"咖啡"二字这类坑）。
2. **套餐要先 `query-meal-detail` 拆开**：套餐的营养值通常不等于单点之和，且可替换项会改变结果。
3. **热量和价格要分开取**：营养来自 `list-nutrition-foods`，价格与优惠来自 `query-meals` + `calculate-price`，两者靠餐品编码对齐。
4. **钠必须一起看**：真实数据实测——只约束热量和蛋白时，最优解钠高达 1996 mg（一天推荐 2000 mg）；
   加上 `max_sodium: 1500` 后钠降到 1465 mg，代价是蛋白从 54 g 掉到 46 g。
   **热量与钠是独立维度，只看热量的"健康配餐"不成立。**
5. **先算后买**：任何下单动作前必须过一遍 `calculate-price`，且必须得到用户显式确认。
6. **拿不到实时数据时降级**：若 MCP 不可用，明确告知用户当前用的是估算值，不要伪装成实时数据。
