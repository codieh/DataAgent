# 数据分析指标口径

本文档定义了基于 `product_db` 数据库的各分析指标的业务含义、计算公式和统计条件。所有表名、字段名和枚举值均以 `schema.sql` 为准。

## GMV 与成交总额

**常见说法：** GMV、成交总额、总成交额、总交易额。

**业务定义：** GMV（Gross Merchandise Volume）表示统计周期内所有订单的 `total_amount`（优惠后实付金额）之和，通常包含全部订单，不区分订单状态。

**计算公式：**

```text
GMV = SUM(orders.total_amount)  -- 包含所有订单
```

`orders.total_amount` 是优惠后实付金额，计算方式为 `orders.subtotal_amount - orders.discount_amount`。

**涉及表和字段：**

- `orders.total_amount` —— 优惠后实付金额
- `orders.order_date` —— 下单时间
- `orders.status` —— 订单状态（`completed`、`pending`、`cancelled`）

**统计条件：** GMV 包含所有状态的订单（`completed`、`pending`、`cancelled`）。时间过滤使用 `orders.order_date`。

**默认时间字段：** `orders.order_date`。

**SQL 示例：**

按月份统计 GMV：

```sql
SELECT
    DATE_FORMAT(o.order_date, '%Y-%m') AS order_month,
    SUM(o.total_amount)                AS gmv
FROM orders AS o
GROUP BY DATE_FORMAT(o.order_date, '%Y-%m')
ORDER BY order_month;
```

按状态拆分 GMV：

```sql
SELECT
    o.status,
    COUNT(*)                AS order_count,
    SUM(o.total_amount)     AS gmv
FROM orders AS o
GROUP BY o.status;
```

**容易混淆的概念：** GMV 包含所有订单（含 `cancelled`），而"销售额"通常排除 `cancelled` 订单。在对比两个指标时需注意口径差异。

**待确认事项：**

> 待业务确认：GMV 是否应包含 `pending` 状态的订单。部分业务定义中 GMV 仅统计 `completed` 订单。

## 销售额

**常见说法：** 销售金额、有效销售额、成交金额。

**业务定义：** 销售额表示统计周期内有效订单的 `total_amount` 之和。有效订单排除 `cancelled` 状态，通常包含 `completed` 和 `pending` 状态的订单。

**计算公式：**

```text
销售额 = SUM(orders.total_amount)  WHERE orders.status != 'cancelled'
```

**涉及表和字段：**

- `orders.total_amount` —— 优惠后实付金额
- `orders.status` —— 订单状态
- `orders.order_date` —— 下单时间

**统计条件：** 排除 `orders.status = 'cancelled'` 的订单。时间过滤使用 `orders.order_date`。

**默认时间字段：** `orders.order_date`。

**SQL 示例：**

按商品分类统计销售额（需通过订单明细关联商品）：

```sql
SELECT
    c.name                   AS category_name,
    SUM(oi.line_amount)      AS category_sales
FROM order_items AS oi
JOIN orders AS o ON o.id = oi.order_id
JOIN products AS p ON p.id = oi.product_id
JOIN categories AS c ON c.id = p.category_id
WHERE o.status != 'cancelled'
GROUP BY c.name
ORDER BY category_sales DESC;
```

按商品维度统计时，使用 `order_items.line_amount` 汇总，因为 `orders.total_amount` 是订单级金额，无法按商品正确拆分。

**容易混淆的概念：** 销售额与 GMV 使用相同金额字段 `orders.total_amount`，区别在于是否排除 `cancelled` 订单。按商品维度统计时必须用 `order_items.line_amount`，不能直接使用 `orders.total_amount`。

**待确认事项：**

> 待业务确认：销售额是否应包含 `pending` 状态的订单，还是仅统计 `completed` 订单。

## 实付金额

**常见说法：** 实付金额、实际支付金额、应付金额、到手价。

**业务定义：** 实付金额指单个订单或单用户在扣除优惠后实际支付（或应支付）的金额。在订单表中对应 `orders.total_amount` 字段。

**计算公式：**

```text
单笔订单实付金额 = orders.total_amount
单用户实付金额 = SUM(orders.total_amount) WHERE orders.user_id = 指定用户 AND orders.status != 'cancelled'
```

`orders.total_amount` 的计算关系为 `orders.subtotal_amount - orders.discount_amount`，其中 `subtotal_amount` 是优惠前商品金额，`discount_amount` 是营销活动优惠金额。

**涉及表和字段：**

- `orders.total_amount` —— 优惠后实付金额
- `orders.subtotal_amount` —— 优惠前商品金额
- `orders.discount_amount` —— 优惠金额
- `orders.status` —— 订单状态

**统计条件：** 排除 `orders.status = 'cancelled'` 的订单。

**SQL 示例：**

查看单笔订单的优惠前后金额：

```sql
SELECT
    o.id                 AS order_id,
    o.subtotal_amount,
    o.discount_amount,
    o.total_amount,
    o.status
FROM orders AS o
WHERE o.id = 1;
```

**容易混淆的概念：** 销售额与实付金额使用相同的底层字段 `orders.total_amount`。实付金额侧重单笔订单或单用户的实际支付，销售额侧重总体金额。优惠前金额（`subtotal_amount`）不等于实付金额。

## 订单数

**常见说法：** 订单量、订单笔数、成交单数、有效订单数。

**业务定义：** 订单数表示统计周期内的订单记录数量。有效订单数排除 `cancelled` 状态的订单。

**计算公式：**

```text
订单数 = COUNT(orders.id)
有效订单数 = COUNT(orders.id) WHERE orders.status != 'cancelled'
```

**涉及表和字段：**

- `orders.id` —— 订单主键
- `orders.status` —— 订单状态
- `orders.order_date` —— 下单时间

**统计条件：** 有效订单数排除 `orders.status = 'cancelled'`。时间过滤使用 `orders.order_date`。

**默认时间字段：** `orders.order_date`。

**分组维度：** 可按 `orders.sales_channel`（销售渠道）、`orders.payment_method`（支付方式）、`orders.promotion_id`（营销活动）、`orders.province`（收货省份）等维度分组。用户维度通过 `JOIN users` 获取会员等级和年龄段。

**SQL 示例：**

统计各销售渠道的有效订单数：

```sql
SELECT
    o.sales_channel,
    COUNT(*) AS order_count
FROM orders AS o
WHERE o.status != 'cancelled'
GROUP BY o.sales_channel
ORDER BY order_count DESC;
```

统计特定会员等级用户的订单数：

```sql
SELECT
    u.membership_level,
    COUNT(DISTINCT o.id) AS order_count
FROM orders AS o
JOIN users AS u ON u.id = o.user_id
WHERE o.status != 'cancelled'
GROUP BY u.membership_level;
```

**容易出现的错误：** 当 `orders` 与 `order_items` 进行 JOIN 时，一个订单会产生多行结果。统计订单数必须使用 `COUNT(DISTINCT o.id)` 而非 `COUNT(*)`，否则会将每个订单明细行都计为一个订单。

## 商品销量

**常见说法：** 销量、销售数量、售出件数、成交件数。

**业务定义：** 商品销量表示有效订单明细中商品购买数量的总和。一个订单可包含多个商品，也可以购买同一商品多件。

**计算公式：**

```text
商品销量 = SUM(order_items.quantity) WHERE orders.status != 'cancelled'
```

**涉及表和字段：**

- `order_items.quantity` —— 购买数量
- `order_items.order_id` —— 所属订单
- `orders.id` —— 订单主键
- `orders.status` —— 订单状态

**统计条件：** 排除 `orders.status = 'cancelled'` 的订单。时间过滤使用 `orders.order_date`。

**默认时间字段：** `orders.order_date`。

**注意事项：** 商品销量不是订单数量。一个订单可以包含多个商品，也可以购买同一商品多件。

**SQL 示例：**

统计各商品的销量排名（前 20）：

```sql
SELECT
    oi.product_id,
    p.name              AS product_name,
    SUM(oi.quantity)    AS sales_quantity
FROM order_items AS oi
JOIN orders AS o ON o.id = oi.order_id
JOIN products AS p ON p.id = oi.product_id
WHERE o.status != 'cancelled'
GROUP BY oi.product_id, p.name
ORDER BY sales_quantity DESC
LIMIT 20;
```

**容易出现的错误：** 不能用 `COUNT(order_items.id)` 代替 `SUM(order_items.quantity)`。前者统计明细行数，后者统计实际售出件数。同一商品在同一订单中只出现一行，但 `quantity` 可能大于 1。

## 客单价

**常见说法：** 客单价、用户平均消费、人均消费金额、ARPU。

**业务定义：** 客单价表示平均每个用户的有效消费金额。

**计算公式：**

```text
客单价 = SUM(orders.total_amount) / COUNT(DISTINCT orders.user_id)  WHERE orders.status != 'cancelled'
```

**涉及表和字段：**

- `orders.total_amount` —— 优惠后实付金额
- `orders.user_id` —— 下单用户
- `orders.status` —— 订单状态
- `orders.order_date` —— 下单时间

**统计条件：** 排除 `orders.status = 'cancelled'`。分母为去重用户数。时间过滤使用 `orders.order_date`。

**SQL 示例：**

```sql
SELECT
    SUM(o.total_amount) / COUNT(DISTINCT o.user_id) AS avg_customer_spend
FROM orders AS o
WHERE o.status != 'cancelled';
```

**容易混淆的概念：** 客单价的分母是去重用户数（`COUNT(DISTINCT user_id)`），平均订单金额的分母是订单数（`COUNT(id)`）。同一用户在统计周期内可能有多笔订单，因此客单价通常高于平均订单金额。

## 平均订单金额

**常见说法：** 平均订单金额、单均金额、AOV（Average Order Value）。

**业务定义：** 平均订单金额表示有效订单的平均实付金额。

**计算公式：**

```text
平均订单金额 = SUM(orders.total_amount) / COUNT(orders.id)  WHERE orders.status != 'cancelled'
```

**涉及表和字段：**

- `orders.total_amount` —— 优惠后实付金额
- `orders.status` —— 订单状态
- `orders.order_date` —— 下单时间

**统计条件：** 排除 `orders.status = 'cancelled'` 的订单。时间过滤使用 `orders.order_date`。

**SQL 示例：**

```sql
SELECT
    SUM(o.total_amount) / COUNT(*) AS avg_order_amount
FROM orders AS o
WHERE o.status != 'cancelled';
```

**容易混淆的概念：** 平均订单金额的分母是订单数，客单价的分母是去重用户数。两者分子相同（均为有效订单的 `total_amount` 之和），但客单价 ≥ 平均订单金额。

**容易出现的错误：** 不能用 `AVG(products.price)` 代替。`products.price` 是当前售价，不是实际成交价，且每个订单包含的商品数量不同。

## 订单平均件数

**常见说法：** 平均购买件数、单均件数。

**业务定义：** 订单平均件数表示每笔有效订单平均购买的商品数量。

**计算公式：**

```text
订单平均件数 = SUM(order_items.quantity) / COUNT(DISTINCT orders.id)  WHERE orders.status != 'cancelled'
```

**涉及表和字段：**

- `order_items.quantity` —— 购买数量
- `orders.id` —— 订单主键
- `orders.status` —— 订单状态

**统计条件：** 排除 `orders.status = 'cancelled'`。

**SQL 示例：**

```sql
SELECT
    SUM(oi.quantity) / COUNT(DISTINCT o.id) AS avg_items_per_order
FROM order_items AS oi
JOIN orders AS o ON o.id = oi.order_id
WHERE o.status != 'cancelled';
```

**容易出现的错误：** 不能用 `COUNT(oi.id) / COUNT(DISTINCT o.id)` 代替。`COUNT(oi.id)` 统计明细行数（每行是一个商品），而 `SUM(oi.quantity)` 统计实际售出件数（一行中 `quantity` 可能大于 1）。

## 优惠金额

**常见说法：** 折扣金额、促销优惠、减免金额。

**业务定义：** 优惠金额表示统计周期内有效订单中营销活动优惠的总金额，对应 `orders.discount_amount` 字段。

**计算公式：**

```text
优惠金额 = SUM(orders.discount_amount) WHERE orders.status != 'cancelled'
```

`orders.discount_amount` 的计算方式为：当订单处于活动期间且满足最低订单金额时，`discount_amount = MIN(subtotal_amount * discount_rate, max_discount)`。已取消订单的 `discount_amount` 始终为 0。

**涉及表和字段：**

- `orders.discount_amount` —— 优惠金额
- `orders.promotion_id` —— 营销活动 ID（可为 NULL）
- `orders.status` —— 订单状态

**统计条件：** 排除 `orders.status = 'cancelled'` 的订单（取消订单的优惠金额恒为 0）。

**SQL 示例：**

按月份统计优惠金额：

```sql
SELECT
    DATE_FORMAT(o.order_date, '%Y-%m') AS order_month,
    SUM(o.discount_amount)             AS total_discount
FROM orders AS o
WHERE o.status != 'cancelled'
GROUP BY DATE_FORMAT(o.order_date, '%Y-%m')
ORDER BY order_month;
```

按是否使用营销活动统计平均优惠：

```sql
SELECT
    CASE WHEN o.promotion_id IS NOT NULL THEN '有活动' ELSE '无活动' END AS has_promotion,
    COUNT(*)                  AS order_count,
    AVG(o.discount_amount)    AS avg_discount
FROM orders AS o
WHERE o.status != 'cancelled'
GROUP BY has_promotion;
```

**注意事项：** `orders.promotion_id` 为 NULL 表示该订单未关联营销活动。可能原因包括：订单已取消、无适用活动、或活动未触发。`discount_amount` 是订单级字段，无法直接拆分到单个商品。

## 退款金额

**常见说法：** 退款额、退款总额、已退款金额。

**业务定义：** 退款金额表示统计周期内已批准退款的总金额。只统计 `refunds.status = 'approved'` 的记录，排除 `processing`（处理中）和 `rejected`（已拒绝）的退款。

**计算公式：**

```text
退款金额 = SUM(refunds.refund_amount) WHERE refunds.status = 'approved'
```

退款记录存储在独立的 `refunds` 表中，不在 `orders` 表中体现。退款不修改原订单的 `total_amount` 或 `status`。

**涉及表和字段：**

- `refunds.refund_amount` —— 退款金额
- `refunds.status` —— 退款状态（`approved`、`processing`、`rejected`）
- `refunds.created_at` —— 退款申请时间
- `refunds.order_id` —— 原订单 ID

**统计条件：** 仅统计 `refunds.status = 'approved'`。时间过滤使用 `refunds.created_at`（退款申请时间），而非 `orders.order_date`。

**SQL 示例：**

```sql
SELECT
    SUM(r.refund_amount) AS total_refund
FROM refunds AS r
WHERE r.status = 'approved';
```

按退款原因统计退款金额：

```sql
SELECT
    r.reason,
    COUNT(*)              AS refund_count,
    SUM(r.refund_amount)  AS total_refund
FROM refunds AS r
WHERE r.status = 'approved'
GROUP BY r.reason
ORDER BY total_refund DESC;
```

**注意事项：** 退款金额存储在 `refunds.refund_amount` 中，不能从 `orders.total_amount` 推算。一个订单最多有一条退款记录（整单退款或部分退款）。部分退款的 `refund_amount` 取自 `order_items.line_amount`（明细行金额），未扣除订单级优惠的分摊比例。

## 净销售额

**常见说法：** 净收入、净销售额、扣除退款后销售额。

**业务定义：** 净销售额表示有效订单的销售额减去已批准退款金额后的净值。

**计算公式：**

```text
净销售额 = SUM(orders.total_amount) WHERE orders.status != 'cancelled'
         - SUM(refunds.refund_amount) WHERE refunds.status = 'approved'
```

**涉及表和字段：**

- `orders.total_amount` —— 优惠后实付金额
- `orders.status` —— 订单状态
- `refunds.refund_amount` —— 退款金额
- `refunds.status` —— 退款状态

**SQL 示例：**

按商品分类统计净销售额：

```sql
SELECT
    c.name                   AS category_name,
    SUM(oi.line_amount)      AS gross_sales,
    COALESCE(SUM(approved_refunds.refund_total), 0) AS refund_total,
    SUM(oi.line_amount) - COALESCE(SUM(approved_refunds.refund_total), 0) AS net_sales
FROM order_items AS oi
JOIN orders AS o ON o.id = oi.order_id
JOIN products AS p ON p.id = oi.product_id
JOIN categories AS c ON c.id = p.category_id
LEFT JOIN (
    SELECT r.order_id, SUM(r.refund_amount) AS refund_total
    FROM refunds AS r
    WHERE r.status = 'approved'
    GROUP BY r.order_id
) AS approved_refunds ON approved_refunds.order_id = o.id
WHERE o.status != 'cancelled'
GROUP BY c.name
ORDER BY net_sales DESC;
```

**容易出现的错误：** 不能直接用 `orders.total_amount - refunds.refund_amount` 计算。退款金额在 `refunds` 表中独立记录，且一个订单最多只有一条退款记录。通过子查询先聚合退款金额可以避免 JOIN 导致的重复计算。

## 商品成本

**常见说法：** 销售成本、已售商品成本、COGS（Cost of Goods Sold）。

**业务定义：** 商品成本表示有效订单中已售商品的总成本。使用 `order_items.unit_cost`（下单时的成本快照），不使用 `products.cost_price`（当前成本）。

**计算公式：**

```text
商品成本 = SUM(order_items.quantity * order_items.unit_cost) WHERE orders.status != 'cancelled'
```

**涉及表和字段：**

- `order_items.unit_cost` —— 下单时成本单价（快照）
- `order_items.quantity` —— 购买数量
- `orders.status` —— 订单状态

**统计条件：** 排除 `orders.status = 'cancelled'` 的订单。

**SQL 示例：**

按品牌统计商品成本：

```sql
SELECT
    p.brand,
    SUM(oi.quantity * oi.unit_cost) AS total_cost
FROM order_items AS oi
JOIN orders AS o ON o.id = oi.order_id
JOIN products AS p ON p.id = oi.product_id
WHERE o.status != 'cancelled'
GROUP BY p.brand
ORDER BY total_cost DESC;
```

**容易出现的错误：** 不能使用 `products.cost_price` 计算历史订单的成本。`products.cost_price` 是当前成本，可能与下单时的 `order_items.unit_cost` 不同。分析历史数据时必须使用 `order_items.unit_cost`。

## 毛利润

**常见说法：** 毛利、毛利润、Gross Profit。

**业务定义：** 毛利润表示有效订单的销售收入减去商品成本后的差额。

**计算公式：**

```text
毛利润 = SUM(order_items.line_amount) - SUM(order_items.quantity * order_items.unit_cost)
       WHERE orders.status != 'cancelled'
```

其中 `order_items.line_amount` 是明细销售金额（等于 `quantity * unit_price`），`order_items.unit_cost` 是下单时成本快照。

**涉及表和字段：**

- `order_items.line_amount` —— 明细销售金额（`quantity * unit_price`）
- `order_items.unit_cost` —— 下单时成本单价
- `order_items.quantity` —— 购买数量
- `orders.status` —— 订单状态

**统计条件：** 排除 `orders.status = 'cancelled'`。

**SQL 示例：**

按商品分类统计毛利润：

```sql
SELECT
    c.name                                                       AS category_name,
    SUM(oi.line_amount)                                          AS revenue,
    SUM(oi.quantity * oi.unit_cost)                              AS cost,
    SUM(oi.line_amount) - SUM(oi.quantity * oi.unit_cost)       AS gross_profit
FROM order_items AS oi
JOIN orders AS o ON o.id = oi.order_id
JOIN products AS p ON p.id = oi.product_id
JOIN categories AS c ON c.id = p.category_id
WHERE o.status != 'cancelled'
GROUP BY c.name
ORDER BY gross_profit DESC;
```

**注意事项：** 此公式中收入使用 `order_items.line_amount`（优惠前金额），未扣除订单级优惠分摊。如需考虑优惠，应使用 `orders.total_amount` 按明细比例分摊，但当前数据库未提供明细级优惠字段。

**待确认事项：**

> 待业务确认：毛利润计算是否应扣除订单级优惠（`orders.discount_amount`）的分摊金额。当前 `order_items` 表没有明细级优惠字段，无法直接按商品维度分摊优惠。

## 毛利率

**常见说法：** 毛利率、Gross Margin、毛利率百分比。

**业务定义：** 毛利率表示毛利润占销售收入的比例。

**计算公式：**

```text
毛利率 = 毛利润 / 销售收入

其中：
  毛利润 = SUM(order_items.line_amount) - SUM(order_items.quantity * order_items.unit_cost)
  销售收入 = SUM(order_items.line_amount)
  过滤条件均为 orders.status != 'cancelled'
```

**涉及表和字段：** 与"毛利润"指标相同。

**SQL 示例：**

按品牌统计毛利率：

```sql
SELECT
    p.brand,
    SUM(oi.line_amount) AS revenue,
    SUM(oi.quantity * oi.unit_cost) AS cost,
    ROUND(
        (SUM(oi.line_amount) - SUM(oi.quantity * oi.unit_cost))
        / NULLIF(SUM(oi.line_amount), 0) * 100, 2
    ) AS gross_margin_pct
FROM order_items AS oi
JOIN orders AS o ON o.id = oi.order_id
JOIN products AS p ON p.id = oi.product_id
WHERE o.status != 'cancelled'
GROUP BY p.brand
ORDER BY gross_margin_pct DESC;
```

**容易出现的错误：** 分母可能为 0。使用 `NULLIF(SUM(oi.line_amount), 0)` 避免除零错误。

## 退款率

**常见说法：** 退款率、退款比例、退款订单占比。

**业务定义：** 退款率表示发生退款的订单数占有效订单数的比例。仅统计 `refunds.status = 'approved'` 的退款记录。

**计算公式：**

```text
退款率 = COUNT(DISTINCT refunds.order_id WHERE refunds.status = 'approved')
       / COUNT(DISTINCT orders.id WHERE orders.status = 'completed')
```

退款仅针对 `completed` 状态的订单生成（数据生成逻辑中，只有 `completed` 订单才会产生退款记录）。因此分母使用 `completed` 订单数。

**涉及表和字段：**

- `refunds.order_id` —— 退款关联的订单
- `refunds.status` —— 退款状态
- `orders.id` —— 订单主键
- `orders.status` —— 订单状态

**SQL 示例：**

按月统计退款率：

```sql
SELECT
    DATE_FORMAT(o.order_date, '%Y-%m') AS order_month,
    COUNT(DISTINCT o.id)               AS completed_orders,
    COUNT(DISTINCT r.order_id)         AS refund_orders,
    ROUND(COUNT(DISTINCT r.order_id) / COUNT(DISTINCT o.id) * 100, 2) AS refund_rate_pct
FROM orders AS o
LEFT JOIN refunds AS r ON r.order_id = o.id AND r.status = 'approved'
WHERE o.status = 'completed'
GROUP BY DATE_FORMAT(o.order_date, '%Y-%m')
ORDER BY order_month;
```

**注意事项：** 退款记录与原订单可能不在同一月份（退款申请时间 `refunds.created_at` 晚于下单时间 `orders.order_date`）。上述 SQL 按原订单的下单月份统计，可能将退款归入下单月而非退款月。

**待确认事项：**

> 待业务确认：退款率统计应按原订单下单时间还是退款申请时间分组。

**容易出现的错误：** 退款率是订单数比例，不是金额比例。不能用 `SUM(refunds.refund_amount) / SUM(orders.total_amount)` 计算退款率。

## 用户消费金额

**常见说法：** 用户消费、用户累计消费、用户总消费金额、LTV。

**业务定义：** 用户消费金额表示指定用户在统计周期内所有有效订单的 `total_amount` 之和。

**计算公式：**

```text
用户消费金额 = SUM(orders.total_amount) WHERE orders.user_id = 指定用户 AND orders.status != 'cancelled'
```

**涉及表和字段：**

- `orders.total_amount` —— 优惠后实付金额
- `orders.user_id` —— 下单用户
- `orders.status` —— 订单状态
- `users.id` —— 用户主键

**统计条件：** 排除 `orders.status = 'cancelled'`。时间过滤使用 `orders.order_date`。

**SQL 示例：**

查询消费金额最高的前 10 位用户：

```sql
SELECT
    u.id             AS user_id,
    u.username,
    u.membership_level,
    SUM(o.total_amount) AS total_spend
FROM users AS u
JOIN orders AS o ON o.user_id = u.id
WHERE o.status != 'cancelled'
GROUP BY u.id, u.username, u.membership_level
ORDER BY total_spend DESC
LIMIT 10;
```

**注意事项：** `users.email` 和 `users.username` 属于敏感字段，在面向外部的查询结果中应避免展示或进行脱敏处理。

## 用户购买次数

**常见说法：** 购买次数、下单次数、复购次数。

**业务定义：** 用户购买次数表示指定用户在统计周期内的有效订单数。

**计算公式：**

```text
用户购买次数 = COUNT(orders.id) WHERE orders.user_id = 指定用户 AND orders.status != 'cancelled'
```

**涉及表和字段：**

- `orders.id` —— 订单主键
- `orders.user_id` —— 下单用户
- `orders.status` —— 订单状态
- `users.id` —— 用户主键

**统计条件：** 排除 `orders.status = 'cancelled'`。时间过滤使用 `orders.order_date`。

**SQL 示例：**

统计各会员等级的平均购买次数：

```sql
SELECT
    u.membership_level,
    COUNT(*)                                     AS total_orders,
    COUNT(DISTINCT u.id)                         AS user_count,
    COUNT(*) / COUNT(DISTINCT u.id)              AS avg_orders_per_user
FROM users AS u
JOIN orders AS o ON o.user_id = u.id
WHERE o.status != 'cancelled'
GROUP BY u.membership_level
ORDER BY avg_orders_per_user DESC;
```

**分组维度：** 可按 `users.membership_level`（会员等级）、`users.province`（常住省份）、`users.age_group`（年龄段）分组。

## 商品维度统计方法

**业务定义：** 商品维度统计以商品（`products`）为分组依据，通过 `order_items` 关联 `orders` 获取销量、销售额等指标。

**涉及表和关联路径：** `orders` → `order_items` → `products`。

**统计条件：** 排除 `orders.status = 'cancelled'`。

**SQL 示例：**

```sql
SELECT
    p.id                   AS product_id,
    p.name                 AS product_name,
    p.brand,
    SUM(oi.quantity)       AS sales_quantity,
    SUM(oi.line_amount)    AS sales_amount,
    COUNT(DISTINCT o.id)   AS order_count
FROM order_items AS oi
JOIN orders AS o ON o.id = oi.order_id
JOIN products AS p ON p.id = oi.product_id
WHERE o.status != 'cancelled'
GROUP BY p.id, p.name, p.brand;
```

**注意事项：** `products.status` 包含 `active` 和 `inactive` 两种状态。`inactive` 商品表示已下架但历史订单仍然存在，统计历史销量时通常不需要按商品状态过滤。如需查看当前在售商品表现，可增加 `WHERE p.status = 'active'`。

## 商品分类维度统计方法

**业务定义：** 分类维度统计以商品分类（`categories`）为分组依据。每个商品有且仅有一个分类（`products.category_id` 是外键，一对一关系），不存在多对多关联表。

**涉及表和关联路径：** `orders` → `order_items` → `products` → `categories`。

**SQL 示例：**

```sql
SELECT
    c.name                 AS category_name,
    SUM(oi.line_amount)    AS sales_amount,
    SUM(oi.quantity)       AS sales_quantity,
    COUNT(DISTINCT o.id)   AS order_count
FROM order_items AS oi
JOIN orders AS o ON o.id = oi.order_id
JOIN products AS p ON p.id = oi.product_id
JOIN categories AS c ON c.id = p.category_id
WHERE o.status != 'cancelled'
GROUP BY c.name
ORDER BY sales_amount DESC;
```

**容易出现的错误：** 当前数据库不存在 `product_categories` 表。商品与分类是一对一关系（`products.category_id`），不需要通过中间表关联。

## 品牌维度统计方法

**业务定义：** 品牌维度统计以 `products.brand` 字段为分组依据。品牌信息存储在商品表中，需要通过 `order_items` 关联 `products` 获取。

**涉及表和关联路径：** `orders` → `order_items` → `products`（使用 `products.brand` 字段）。

**SQL 示例：**

```sql
SELECT
    p.brand,
    SUM(oi.line_amount)    AS sales_amount,
    SUM(oi.quantity)       AS sales_quantity
FROM order_items AS oi
JOIN orders AS o ON o.id = oi.order_id
JOIN products AS p ON p.id = oi.product_id
WHERE o.status != 'cancelled'
GROUP BY p.brand
ORDER BY sales_amount DESC;
```

## 地区维度统计方法

**业务定义：** 地区维度统计有两种地区数据源：`orders.province` / `orders.city`（收货地区快照，下单时取自用户常住地区）和 `users.province` / `users.city`（用户当前常住地区）。两者在本数据库中通常一致（数据生成逻辑中订单收货地区直接复制用户常住地区）。

**按收货地区统计（推荐，反映实际收货分布）：**

```sql
SELECT
    o.province,
    COUNT(DISTINCT o.id)   AS order_count,
    SUM(o.total_amount)    AS sales_amount
FROM orders AS o
WHERE o.status != 'cancelled'
GROUP BY o.province
ORDER BY sales_amount DESC;
```

**按用户常住地区统计（反映用户归属）：**

```sql
SELECT
    u.province,
    COUNT(DISTINCT o.id)   AS order_count,
    SUM(o.total_amount)    AS sales_amount
FROM orders AS o
JOIN users AS u ON u.id = o.user_id
WHERE o.status != 'cancelled'
GROUP BY u.province
ORDER BY sales_amount DESC;
```

**注意事项：** `orders.province` 和 `orders.city` 是收货地区快照字段，下单时从用户常住地区复制。`users.province` 和 `users.city` 是用户当前常住地区。两种维度适用于不同分析场景：收货地区适合物流和区域销售分析，用户常住地区适合用户画像分析。

## 销售渠道维度统计方法

**业务定义：** 销售渠道维度以 `orders.sales_channel` 为分组依据。

**渠道枚举值：**

- `app` —— 移动应用
- `web` —— 官方网站
- `mini_program` —— 微信小程序
- `store` —— 线下门店
- `marketplace` —— 第三方平台

**SQL 示例：**

```sql
SELECT
    o.sales_channel,
    COUNT(*)                    AS order_count,
    SUM(o.total_amount)         AS sales_amount,
    SUM(o.total_amount) / COUNT(*) AS avg_order_amount
FROM orders AS o
WHERE o.status != 'cancelled'
GROUP BY o.sales_channel
ORDER BY sales_amount DESC;
```

## 营销活动维度统计方法

**业务定义：** 营销活动维度通过 `orders.promotion_id` 关联 `promotions` 表进行统计。`orders.promotion_id` 可为 NULL，表示该订单未关联营销活动。

**涉及表和关联路径：** `orders.promotion_id` → `promotions.id`。每个订单最多关联一个营销活动（无 `order_promotions` 中间表）。

**SQL 示例：**

```sql
SELECT
    COALESCE(p.name, '无活动')  AS promotion_name,
    COUNT(DISTINCT o.id)        AS order_count,
    SUM(o.total_amount)         AS sales_amount,
    AVG(o.discount_amount)      AS avg_discount
FROM orders AS o
LEFT JOIN promotions AS p ON p.id = o.promotion_id
WHERE o.status != 'cancelled'
GROUP BY o.promotion_id, p.name
ORDER BY sales_amount DESC;
```

**注意事项：** `orders.promotion_id` 为 NULL 可能因为：订单未使用活动优惠、订单已取消（取消订单的 `promotion_id` 恒为 NULL）、或无适用活动。使用 `LEFT JOIN` 可以保留未关联活动的订单。

活动效果对比可结合 `promotions.start_date` 和 `promotions.end_date` 筛选活动期间订单，与非活动期间的同类指标进行比较。

## 用户会员等级维度统计方法

**业务定义：** 会员等级维度通过 `users.membership_level` 字段进行分组统计。

**会员等级枚举值：**

- `normal` —— 普通会员
- `silver` —— 银卡会员
- `gold` —— 金卡会员
- `platinum` —— 铂金会员

**SQL 示例：**

```sql
SELECT
    u.membership_level,
    COUNT(DISTINCT u.id)                         AS user_count,
    COUNT(DISTINCT o.id)                         AS order_count,
    SUM(o.total_amount)                          AS sales_amount,
    SUM(o.total_amount) / COUNT(DISTINCT u.id)   AS avg_spend_per_user
FROM users AS u
JOIN orders AS o ON o.user_id = u.id
WHERE o.status != 'cancelled'
GROUP BY u.membership_level
ORDER BY sales_amount DESC;
```

## 用户年龄段维度统计方法

**业务定义：** 年龄段维度通过 `users.age_group` 字段进行分组统计。

**年龄段枚举值：** `18-24`、`25-34`、`35-44`、`45-54`、`55+`。

**SQL 示例：**

```sql
SELECT
    u.age_group,
    SUM(o.total_amount)   AS sales_amount,
    COUNT(DISTINCT o.id)  AS order_count
FROM users AS u
JOIN orders AS o ON o.user_id = u.id
WHERE o.status != 'cancelled'
GROUP BY u.age_group
ORDER BY sales_amount DESC;
```

## 支付方式维度统计方法

**业务定义：** 支付方式维度以 `orders.payment_method` 为分组依据。

**支付方式枚举值：**

- `alipay` —— 支付宝
- `wechat` —— 微信支付
- `bank_card` —— 银行卡
- `cash` —— 现金

**SQL 示例：**

```sql
SELECT
    o.payment_method,
    COUNT(*)             AS order_count,
    SUM(o.total_amount)  AS sales_amount
FROM orders AS o
WHERE o.status != 'cancelled'
GROUP BY o.payment_method
ORDER BY sales_amount DESC;
```

## 重复计数风险提示

`orders` 与 `order_items` 是一对多关系。当两者 JOIN 后，每笔订单的 `orders.total_amount`、`orders.discount_amount` 等订单级字段会随每个明细行重复出现。

如果按商品维度统计时使用 `SUM(o.total_amount)`，同一订单金额会被重复累加（每个 `order_items` 行都会带入一次订单金额）。

**正确做法：**

按订单维度统计时（订单数、GMV、销售额等），直接使用 `orders` 表字段，不需要 JOIN `order_items`。

按商品维度统计时（商品销量、分类销售额等），使用 `order_items.line_amount` 汇总。

如果必须同时 JOIN 两张表且需要订单级字段，可以先用子查询聚合 `order_items`，再与 `orders` 关联。

**典型错误示例：**

```sql
-- 错误：统计销售额时重复计算
SELECT SUM(o.total_amount) AS wrong_sales
FROM orders AS o
JOIN order_items AS oi ON oi.order_id = o.id
WHERE o.status != 'cancelled';
-- 每个订单有多个明细行时，total_amount 会被重复累加
```

**正确写法：**

```sql
-- 正确：订单级统计不需要 JOIN order_items
SELECT SUM(o.total_amount) AS correct_sales
FROM orders AS o
WHERE o.status != 'cancelled';
```

```sql
-- 正确：商品维度统计使用 order_items.line_amount
SELECT SUM(oi.line_amount) AS correct_product_sales
FROM order_items AS oi
JOIN orders AS o ON o.id = oi.order_id
WHERE o.status != 'cancelled';
```

## 常用同义词与指标对照

| 用户说法 | 对应指标 | 计算依据 |
| --- | --- | --- |
| GMV、成交总额 | GMV | `SUM(orders.total_amount)` 所有订单 |
| 销售额、有效销售额 | 销售额 | `SUM(orders.total_amount)` 排除 cancelled |
| 实付金额、到手价 | 实付金额 | `orders.total_amount` 单笔 |
| 订单数、订单量 | 订单数 | `COUNT(orders.id)` |
| 销量、售出件数 | 商品销量 | `SUM(order_items.quantity)` |
| 客单价、ARPU | 客单价 | `SUM(total_amount) / COUNT(DISTINCT user_id)` |
| 单均金额、AOV | 平均订单金额 | `SUM(total_amount) / COUNT(orders.id)` |
| 折扣、减免 | 优惠金额 | `SUM(orders.discount_amount)` |
| 退款额 | 退款金额 | `SUM(refunds.refund_amount)` 限 approved |
| 净销售额、净收入 | 净销售额 | 销售额 - 已批准退款金额 |
| 成本、COGS | 商品成本 | `SUM(quantity * unit_cost)` |
| 毛利 | 毛利润 | `SUM(line_amount) - SUM(quantity * unit_cost)` |
| 毛利率 | 毛利率 | 毛利润 / 销售收入 |
| 退款率 | 退款率 | 退款订单数 / 完成订单数 |
