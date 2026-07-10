# 数据分析业务规则

本文档描述了 `product_db` 数据库的表结构、关联关系、枚举值和查询注意事项。所有规则以 `schema.sql` 和数据生成代码为准。

## 数据库表清单

当前数据库包含以下 7 张业务表：

| 表名 | 说明 | 主键类型 |
| --- | --- | --- |
| `users` | 用户表 | `INT` |
| `categories` | 商品分类表 | `INT` |
| `products` | 商品表 | `INT` |
| `promotions` | 营销活动表 | `INT` |
| `orders` | 订单表 | `BIGINT` |
| `order_items` | 订单明细表 | `BIGINT` |
| `refunds` | 退款记录表 | `BIGINT` |

**不存在的表：** 当前数据库中不存在 `product_categories`、`order_promotions`、`sales_channels`、`regions` 表。这些表在 `schema.sql` 中被显式删除（`DROP TABLE IF EXISTS`）。如果查询中引用这些表会报错。

## 用户表结构与字段说明

`users` 表存储用户基本信息和画像属性。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `INT` | 用户主键 |
| `username` | `VARCHAR(64)` | 用户名（敏感字段） |
| `email` | `VARCHAR(128)` | 邮箱（敏感字段） |
| `province` | `VARCHAR(32)` | 常住省份 |
| `city` | `VARCHAR(64)` | 常住城市 |
| `membership_level` | `ENUM` | 会员等级 |
| `age_group` | `ENUM` | 年龄段 |
| `created_at` | `DATETIME` | 注册时间 |

`users.province` 和 `users.city` 是用户当前常住地区，用于用户画像分析。订单的收货地区快照保存在 `orders.province` 和 `orders.city` 中，两者在数据生成时取自相同值，但含义不同。

`users.membership_level` 枚举值：`normal`（普通）、`silver`（银卡）、`gold`（金卡）、`platinum`（铂金）。

`users.age_group` 枚举值：`18-24`、`25-34`、`35-44`、`45-54`、`55+`。

`users.created_at` 是用户注册时间，可能早于第一笔订单时间。用户注册时间范围默认为 `start_date - 730 天` 到 `start_date`（即首笔订单前两年内）。

## 商品表结构与字段说明

`products` 表存储商品基本信息。每个商品有且仅有一个分类（通过 `products.category_id` 外键关联 `categories.id`）。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `INT` | 商品主键 |
| `category_id` | `INT` | 所属分类（外键 → `categories.id`） |
| `sku` | `VARCHAR(64)` | 商品编码 |
| `name` | `VARCHAR(128)` | 商品名称 |
| `brand` | `VARCHAR(64)` | 品牌 |
| `price` | `DECIMAL(12,2)` | 当前销售单价 |
| `cost_price` | `DECIMAL(12,2)` | 当前成本单价 |
| `stock` | `INT` | 当前库存 |
| `status` | `ENUM` | 商品状态 |
| `created_at` | `DATETIME` | 上架时间 |

`products.price` 是当前销售单价，`products.cost_price` 是当前成本单价。这两个值可能与下单时的快照价格（`order_items.unit_price`、`order_items.unit_cost`）不同。计算历史销售额和成本时必须使用 `order_items` 中的快照值。

`products.status` 枚举值：`active`（在售）、`inactive`（已下架）。已下架商品的历史订单和订单明细仍然存在，统计历史数据时通常不按商品状态过滤。

`products.created_at` 是商品上架时间，可能早于订单数据起始时间（默认早于 `start_date` 最多 540 天）。

## 商品分类表结构与关联方式

`categories` 表存储商品分类信息。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `INT` | 分类主键 |
| `name` | `VARCHAR(64)` | 分类名称 |

**关联方式：** 商品与分类是一对一关系。每个商品通过 `products.category_id` 直接关联一个分类。当前数据库不存在 `product_categories` 中间表，不支持多对多关联。

**JOIN 路径：**

```sql
products AS p JOIN categories AS c ON c.id = p.category_id
```

**SQL 示例：**

按分类统计商品数量：

```sql
SELECT
    c.name       AS category_name,
    COUNT(p.id)  AS product_count
FROM categories AS c
LEFT JOIN products AS p ON p.category_id = c.id
GROUP BY c.name
ORDER BY product_count DESC;
```

**容易出现的错误：** 不要尝试使用 `product_categories` 表关联商品和分类，该表不存在。不要使用 `JOIN product_categories AS pc ON pc.product_id = p.id` 这样的写法。

## 订单与订单明细的关系

`orders` 表存储订单级信息（金额、状态、渠道、支付方式、收货地区）。`order_items` 表存储订单中的每个商品明细（数量、单价、成本、行金额）。

一个订单可以包含 1 到 5 个商品明细（一对多关系）。

### 关联方式

```sql
order_items AS oi JOIN orders AS o ON o.id = oi.order_id
```

`order_items.order_id` 是外键，指向 `orders.id`。

### 订单级字段与明细级字段的区别

以下字段属于 `orders` 表，是订单级数据：

- `orders.total_amount` —— 优惠后实付金额（整单）
- `orders.subtotal_amount` —— 优惠前商品金额（整单）
- `orders.discount_amount` —— 优惠金额（整单）
- `orders.promotion_id` —— 营销活动
- `orders.sales_channel` —— 销售渠道
- `orders.payment_method` —— 支付方式

以下字段属于 `order_items` 表，是明细级数据：

- `order_items.quantity` —— 购买数量
- `order_items.unit_price` —— 下单时销售单价
- `order_items.unit_cost` —— 下单时成本单价
- `order_items.line_amount` —— 明细销售金额（`quantity * unit_price`）

### JOIN 注意事项

`orders` 与 `order_items` 是一对多关系。JOIN 后每个订单的订单级字段会随明细行数重复出现。

如果统计订单级指标（订单数、GMV、销售额），直接使用 `orders` 表，不需要 JOIN `order_items`。

如果统计商品级指标（商品销量、分类销售额），使用 `order_items.line_amount` 和 `order_items.quantity` 汇总。

### 重复计数风险

当 `orders` 与 `order_items` JOIN 后使用 `SUM(o.total_amount)` 统计销售额，同一订单的金额会按明细行数重复累加。

```sql
-- 错误：total_amount 被重复累加
SELECT SUM(o.total_amount) FROM orders o JOIN order_items oi ON oi.order_id = o.id;

-- 正确：订单级统计不 JOIN order_items
SELECT SUM(o.total_amount) FROM orders;

-- 正确：商品级统计使用 line_amount
SELECT SUM(oi.line_amount) FROM order_items oi JOIN orders o ON o.id = oi.order_id;
```

### `orders.subtotal_amount` 与 `SUM(order_items.line_amount)` 的关系

同一订单中，`orders.subtotal_amount` 等于该订单所有明细行的 `order_items.line_amount` 之和。即：

```text
orders.subtotal_amount = SUM(order_items.line_amount) WHERE order_items.order_id = orders.id
```

`orders.total_amount` 等于 `orders.subtotal_amount - orders.discount_amount`。

## 订单表结构与金额字段说明

`orders` 表是核心业务表，包含多个金额字段和状态字段。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `BIGINT` | 订单主键 |
| `user_id` | `INT` | 下单用户（外键 → `users.id`） |
| `promotion_id` | `INT` (NULL) | 主要营销活动（外键 → `promotions.id`，可为 NULL） |
| `sales_channel` | `ENUM` | 销售渠道 |
| `payment_method` | `ENUM` | 支付方式 |
| `province` | `VARCHAR(32)` | 收货省份快照 |
| `city` | `VARCHAR(64)` | 收货城市快照 |
| `subtotal_amount` | `DECIMAL(14,2)` | 优惠前商品金额 |
| `discount_amount` | `DECIMAL(12,2)` | 优惠金额 |
| `total_amount` | `DECIMAL(14,2)` | 优惠后实付金额 |
| `status` | `ENUM` | 订单状态 |
| `order_date` | `DATETIME` | 下单时间 |

### 金额字段关系

```text
orders.subtotal_amount = SUM(order_items.line_amount)  -- 优惠前商品金额
orders.discount_amount = 营销活动优惠金额              -- 优惠金额
orders.total_amount = orders.subtotal_amount - orders.discount_amount  -- 实付金额
```

`orders.discount_amount` 的默认值为 0。当订单未关联营销活动或订单已取消时，优惠金额为 0。

## 订单状态枚举与统计条件

`orders.status` 包含以下枚举值：

| 枚举值 | 含义 | 计入销售额 | 计入销量 | 说明 |
| --- | --- | --- | --- | --- |
| `completed` | 已完成 | 是 | 是 | 订单已完成交付 |
| `pending` | 待处理 | 待确认 | 待确认 | 仅出现在距数据结束日期 14 天内的订单 |
| `cancelled` | 已取消 | 否 | 否 | 不计入有效销售，优惠金额恒为 0 |

**默认规则：** 统计销售额、订单数、商品销量等指标时，排除 `status = 'cancelled'` 的订单。

**待确认事项：**

> 待业务确认：`pending` 状态的订单是否应计入销售额和销量统计。`pending` 仅出现在最近 14 天的订单中，可能表示尚未确认收货。

## 商品状态枚举

`products.status` 包含以下枚举值：

| 枚举值 | 含义 |
| --- | --- |
| `active` | 在售 |
| `inactive` | 已下架 |

统计历史销售数据时，通常不需要按商品状态过滤。`inactive` 商品的历史订单和订单明细仍然存在。如需查看当前在售商品的表现，可增加 `WHERE p.status = 'active'`。

## 退款状态枚举与统计条件

`refunds.status` 包含以下枚举值：

| 枚举值 | 含义 | 计入退款金额 |
| --- | --- | --- |
| `approved` | 已批准 | 是 |
| `processing` | 处理中 | 否 |
| `rejected` | 已拒绝 | 否 |

统计退款金额时仅统计 `status = 'approved'` 的记录。`processing` 和 `rejected` 的退款不应计入退款总额。

退款仅针对 `completed` 状态的订单生成。`pending` 和 `cancelled` 状态的订单不会产生退款记录。

## 当前商品价格与下单快照价格的区别

`products.price` 是商品的当前销售单价，`products.cost_price` 是商品的当前成本单价。这两个值反映的是商品的最新定价。

`order_items.unit_price` 是下单时的销售单价快照，`order_items.unit_cost` 是下单时的成本单价快照。这两个值在订单创建时从商品表复制，不会随商品价格变动而改变。

`order_items.line_amount` 等于 `order_items.quantity * order_items.unit_price`，是明细行的销售金额。

**对分析的影响：**

计算历史订单的销售额时，应使用 `order_items.unit_price` 或 `order_items.line_amount`，而非 `products.price`。

计算历史订单的成本时，应使用 `order_items.unit_cost`，而非 `products.cost_price`。

`products.price` 和 `products.cost_price` 适用于查看当前定价和分析库存价值。

```sql
-- 正确：使用快照价格计算历史销售额
SELECT SUM(oi.line_amount) AS historical_sales
FROM order_items AS oi
JOIN orders AS o ON o.id = oi.order_id
WHERE o.status != 'cancelled';

-- 错误：使用当前价格计算历史销售额
SELECT SUM(oi.quantity * p.price) AS wrong_historical_sales
FROM order_items AS oi
JOIN orders AS o ON o.id = oi.order_id
JOIN products AS p ON p.id = oi.product_id
WHERE o.status != 'cancelled';
-- products.price 是当前价格，与下单时可能不同
```

## 用户常住地区与订单收货地区的区别

`users.province` 和 `users.city` 是用户的当前常住地区，存储在 `users` 表中。

`orders.province` 和 `orders.city` 是订单的收货地区快照，存储在 `orders` 表中。下单时从用户常住地区复制，后续不会随用户地址变更而改变。

在数据生成逻辑中，`orders.province` 和 `orders.city` 直接取自下单时的 `users.province` 和 `users.city`，因此两者通常一致。但在真实业务场景中，用户可能修改常住地址或指定不同的收货地址，两者可能不同。

**适用场景：**

- 分析"商品卖到了哪些地区"，使用 `orders.province`（收货地区）
- 分析"用户来自哪些地区"，使用 `users.province`（常住地区）
- 对比用户常住地与收货地的差异（在真实业务中有意义）

## 销售渠道枚举值与含义

`orders.sales_channel` 表示订单的销售渠道。

| 枚举值 | 中文含义 |
| --- | --- |
| `app` | 移动应用 |
| `web` | 官方网站 |
| `mini_program` | 微信小程序 |
| `store` | 线下门店 |
| `marketplace` | 第三方平台 |

数据生成时的渠道分布权重约为：app 34%、web 26%、mini_program 20%、store 8%、marketplace 12%。

**分析用途：** 渠道维度可用于对比不同渠道的订单量、销售额、客单价和退款率差异。

```sql
SELECT
    o.sales_channel,
    COUNT(*)                    AS order_count,
    SUM(o.total_amount)         AS sales_amount,
    AVG(o.total_amount)         AS avg_order_amount
FROM orders AS o
WHERE o.status != 'cancelled'
GROUP BY o.sales_channel;
```

## 支付方式枚举值与含义

`orders.payment_method` 表示订单的支付方式。

| 枚举值 | 中文含义 |
| --- | --- |
| `alipay` | 支付宝 |
| `wechat` | 微信支付 |
| `bank_card` | 银行卡 |
| `cash` | 现金 |

数据生成时的支付方式分布权重约为：alipay 42%、wechat 38%、bank_card 16%、cash 4%。

## 营销活动表结构与订单关联

`promotions` 表存储营销活动的定义信息。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `INT` | 活动主键 |
| `name` | `VARCHAR(96)` | 活动名称 |
| `promotion_type` | `ENUM` | 优惠类型 |
| `start_date` | `DATE` | 开始日期 |
| `end_date` | `DATE` | 结束日期 |
| `discount_rate` | `DECIMAL(5,4)` | 折扣比例 |
| `max_discount` | `DECIMAL(12,2)` | 单笔最高优惠金额 |
| `min_order_amount` | `DECIMAL(12,2)` | 最低订单金额门槛 |

### 优惠类型枚举

| 枚举值 | 含义 |
| --- | --- |
| `percentage` | 按比例折扣（discount_rate 表示折扣比例，如 0.12 表示打 88 折） |
| `fixed` | 固定金额优惠 |

### 关联方式

`orders.promotion_id` 是外键，指向 `promotions.id`。每个订单最多关联一个营销活动（一对多关系，从订单侧看是多对一）。当前数据库不存在 `order_promotions` 中间表。

`orders.promotion_id` 可为 NULL，表示订单未使用任何营销活动。已取消订单的 `promotion_id` 恒为 NULL，且 `discount_amount` 恒为 0。

### 活动触发条件

一个订单关联营销活动需同时满足以下条件：订单日期在活动周期内（`promotions.start_date <= order_date <= promotions.end_date`）、订单优惠前金额达到最低门槛（`orders.subtotal_amount >= promotions.min_order_amount`）。

实际优惠金额的计算方式为：

```text
discount_amount = MIN(orders.subtotal_amount * promotions.discount_rate, promotions.max_discount)
```

### 活动效果分析 SQL 示例

对比活动期间与非活动期间的销售额：

```sql
SELECT
    CASE WHEN o.promotion_id IS NOT NULL THEN '活动期间' ELSE '非活动期间' END AS period_type,
    COUNT(DISTINCT o.id)   AS order_count,
    SUM(o.total_amount)    AS sales_amount,
    AVG(o.total_amount)    AS avg_order_amount
FROM orders AS o
WHERE o.status != 'cancelled'
GROUP BY period_type;
```

按活动统计订单数和优惠金额：

```sql
SELECT
    p.name                   AS promotion_name,
    p.start_date,
    p.end_date,
    COUNT(DISTINCT o.id)     AS order_count,
    SUM(o.discount_amount)   AS total_discount,
    SUM(o.total_amount)      AS sales_amount
FROM orders AS o
JOIN promotions AS p ON p.id = o.promotion_id
WHERE o.status != 'cancelled'
GROUP BY p.name, p.start_date, p.end_date
ORDER BY p.start_date;
```

## 退款表结构与订单关联

`refunds` 表存储退款记录，独立于订单表。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `BIGINT` | 退款主键 |
| `order_id` | `BIGINT` | 原订单 ID（外键 → `orders.id`） |
| `order_item_id` | `BIGINT` (NULL) | 部分退款对应的订单明细（外键 → `order_items.id`，整单退款时为 NULL） |
| `refund_amount` | `DECIMAL(14,2)` | 退款金额 |
| `reason` | `VARCHAR(128)` | 退款原因 |
| `status` | `ENUM` | 退款状态 |
| `created_at` | `DATETIME` | 退款申请时间 |

### 关联方式

```sql
refunds AS r JOIN orders AS o ON o.id = r.order_id
```

`refunds.order_id` 是外键，指向 `orders.id`。一个订单最多有一条退款记录。

`refunds.order_item_id` 可为 NULL。为 NULL 时表示整单退款，`refund_amount` 等于 `orders.total_amount`。非 NULL 时表示部分退款，关联到具体的 `order_items` 行，`refund_amount` 取自该行的 `order_items.line_amount`。

### 退款产生条件

退款仅针对 `orders.status = 'completed'` 的订单。`pending` 和 `cancelled` 状态的订单不会产生退款记录。

退款申请时间 `refunds.created_at` 晚于订单下单时间 `orders.order_date`（生成逻辑中为下单后 1 到 20 天）。

### 退款不修改原订单

退款记录不会修改 `orders` 表中的任何字段。原订单的 `total_amount`、`status` 和其他字段保持不变。计算净销售额时需要单独查询 `refunds` 表并从销售额中减去已批准的退款金额。

### 退款分析 SQL 示例

按退款状态统计退款数量和金额：

```sql
SELECT
    r.status,
    COUNT(*)              AS refund_count,
    SUM(r.refund_amount)  AS total_refund_amount
FROM refunds AS r
GROUP BY r.status;
```

按退款类型（整单 vs 部分）统计：

```sql
SELECT
    CASE WHEN r.order_item_id IS NULL THEN '整单退款' ELSE '部分退款' END AS refund_type,
    COUNT(*)              AS refund_count,
    SUM(r.refund_amount)  AS total_refund_amount
FROM refunds AS r
WHERE r.status = 'approved'
GROUP BY refund_type;
```

## 订单与退款关联后的重复计数风险

`orders` 与 `refunds` 是一对一或一对零关系（每个订单最多一条退款记录）。LEFT JOIN 不会导致订单金额重复累计。

但需要注意：当同时 JOIN `order_items` 和 `refunds` 时，如果订单有多条明细，退款信息会随明细行重复出现。

```sql
-- 错误：同时 JOIN order_items 和 refunds，退款金额按明细行重复
SELECT SUM(r.refund_amount) AS wrong_refund
FROM orders AS o
JOIN order_items AS oi ON oi.order_id = o.id
LEFT JOIN refunds AS r ON r.order_id = o.id;
```

**正确做法：** 先按订单聚合退款金额，再与其他表关联。

```sql
-- 正确：使用子查询先聚合退款
SELECT
    o.id AS order_id,
    o.total_amount,
    COALESCE(ref.refund_total, 0) AS refund_total
FROM orders AS o
LEFT JOIN (
    SELECT order_id, SUM(refund_amount) AS refund_total
    FROM refunds
    WHERE status = 'approved'
    GROUP BY order_id
) AS ref ON ref.order_id = o.id
WHERE o.status = 'completed';
```

## 时间字段的区别与使用场景

数据库中有多个时间字段，适用于不同的分析场景：

| 表 | 字段 | 说明 | 适用场景 |
| --- | --- | --- | --- |
| `orders` | `order_date` | 下单时间 | 销售趋势、订单统计的默认时间字段 |
| `users` | `created_at` | 用户注册时间 | 新增用户统计、用户增长分析 |
| `products` | `created_at` | 商品上架时间 | 新品分析、商品生命周期分析 |
| `refunds` | `created_at` | 退款申请时间 | 退款趋势分析 |
| `promotions` | `start_date` / `end_date` | 活动起止日期 | 活动期间筛选 |

**默认规则：** 统计销售额、订单数、商品销量等指标时，时间过滤使用 `orders.order_date`。统计退款时使用 `refunds.created_at`。

`orders.order_date` 是 `DATETIME` 类型（精确到秒），`promotions.start_date` 和 `promotions.end_date` 是 `DATE` 类型。

**退款分析的时间归属：** 退款申请时间晚于原订单下单时间。按 `orders.order_date` 分组会将退款归入下单月，按 `refunds.created_at` 分组会将退款归入退款月。两种口径适用于不同分析目的。

## 默认查询规则

以下规则在生成 SQL 查询时应默认遵守：

**时间过滤：** 使用 `orders.order_date` 作为默认时间字段。退款分析使用 `refunds.created_at`。

**订单状态过滤：** 统计销售额、订单数、商品销量等正向指标时，排除 `orders.status = 'cancelled'`。即使用 `WHERE o.status != 'cancelled'`。

**退款状态过滤：** 统计退款金额时，仅统计 `refunds.status = 'approved'`。

**成本字段选择：** 计算历史订单成本时使用 `order_items.unit_cost`，不使用 `products.cost_price`。

**价格字段选择：** 计算历史订单销售额时使用 `order_items.unit_price` 或 `order_items.line_amount`，不使用 `products.price`。

**订单级 vs 明细级统计：** 订单级指标（订单数、GMV）直接使用 `orders` 表。商品级指标（销量、分类销售额）使用 `order_items` 表。

**去重：** 当 JOIN 产生一对多结果时，使用 `COUNT(DISTINCT ...)` 统计唯一记录数。

## 容易造成重复统计的关联关系

### orders 与 order_items（一对多）

`orders` 与 `order_items` 是一对多关系。JOIN 后 `orders` 表中的 `total_amount`、`subtotal_amount`、`discount_amount` 等字段会随明细行数重复出现。统计订单级金额指标时不要 JOIN `order_items`。

### orders 与 refunds（一对一或一对零）

`orders` 与 `refunds` 是一对一或一对零关系。单独 JOIN 不会导致重复。但与 `order_items` 同时 JOIN 时需注意基数变化。

### products 与 categories（多对一）

`products` 与 `categories` 是多对一关系。多个商品属于同一分类，JOIN 后按分类分组不会产生重复计数。

### 需要特别注意的场景

当查询同时涉及 `orders`、`order_items` 和 `refunds` 三张表时，建议分步聚合：先用子查询分别聚合 `order_items` 和 `refunds` 的数据，再与 `orders` 关联。

```sql
SELECT
    o.id AS order_id,
    o.total_amount,
    items.item_count,
    items.line_total,
    COALESCE(ref.refund_total, 0) AS refund_total
FROM orders AS o
LEFT JOIN (
    SELECT order_id, COUNT(*) AS item_count, SUM(line_amount) AS line_total
    FROM order_items GROUP BY order_id
) AS items ON items.order_id = o.id
LEFT JOIN (
    SELECT order_id, SUM(refund_amount) AS refund_total
    FROM refunds WHERE status = 'approved' GROUP BY order_id
) AS ref ON ref.order_id = o.id
WHERE o.status != 'cancelled';
```

## 敏感字段及使用限制

以下字段包含用户个人信息，在面向外部的查询结果中应避免展示或进行脱敏处理：

| 表 | 字段 | 说明 | 限制 |
| --- | --- | --- | --- |
| `users` | `email` | 用户邮箱 | 不应出现在查询结果中 |
| `users` | `username` | 用户名 | 不应出现在查询结果中，或进行脱敏 |

`users.id` 作为关联键可以在查询中使用，但不建议将用户 ID 直接展示给最终用户。

`orders.province`、`orders.city`、`users.province`、`users.city` 是地区信息，不属于敏感字段，可以在查询结果中正常展示。

## 常见错误查询与正确写法

### 错误一：JOIN order_items 后统计订单金额

```sql
-- 错误：total_amount 被重复累加
SELECT SUM(o.total_amount) AS sales
FROM orders AS o
JOIN order_items AS oi ON oi.order_id = o.id
WHERE o.status != 'cancelled';
```

正确写法：

```sql
-- 订单级统计，不 JOIN order_items
SELECT SUM(o.total_amount) AS sales
FROM orders AS o
WHERE o.status != 'cancelled';
```

### 错误二：使用当前价格计算历史销售

```sql
-- 错误：products.price 是当前价格
SELECT SUM(oi.quantity * p.price) AS sales
FROM order_items AS oi
JOIN products AS p ON p.id = oi.product_id;
```

正确写法：

```sql
-- 使用下单时的快照价格
SELECT SUM(oi.line_amount) AS sales
FROM order_items AS oi
JOIN orders AS o ON o.id = oi.order_id
WHERE o.status != 'cancelled';
```

### 错误三：使用当前成本计算历史成本

```sql
-- 错误：products.cost_price 是当前成本
SELECT SUM(oi.quantity * p.cost_price) AS cost
FROM order_items AS oi
JOIN products AS p ON p.id = oi.product_id;
```

正确写法：

```sql
-- 使用下单时的快照成本
SELECT SUM(oi.quantity * oi.unit_cost) AS cost
FROM order_items AS oi
JOIN orders AS o ON o.id = oi.order_id
WHERE o.status != 'cancelled';
```

### 错误四：COUNT(*) 代替 COUNT(DISTINCT)

```sql
-- 错误：JOIN 后 COUNT(*) 统计的是明细行数
SELECT COUNT(*) AS order_count
FROM orders AS o
JOIN order_items AS oi ON oi.order_id = o.id
WHERE o.status != 'cancelled';
```

正确写法：

```sql
-- 使用 COUNT(DISTINCT) 统计订单数
SELECT COUNT(DISTINCT o.id) AS order_count
FROM orders AS o
JOIN order_items AS oi ON oi.order_id = o.id
WHERE o.status != 'cancelled';
```

或直接在 orders 表上统计：

```sql
SELECT COUNT(*) AS order_count
FROM orders
WHERE status != 'cancelled';
```

### 错误五：引用不存在的表

```sql
-- 错误：product_categories 表不存在
SELECT * FROM products p
JOIN product_categories pc ON pc.product_id = p.id
JOIN categories c ON c.id = pc.category_id;
```

正确写法：

```sql
-- 商品与分类通过 products.category_id 直接关联
SELECT p.name, c.name AS category_name
FROM products AS p
JOIN categories AS c ON c.id = p.category_id;
```

### 错误六：包含 cancelled 订单统计销售额

```sql
-- 错误：未排除 cancelled 订单
SELECT SUM(total_amount) AS sales FROM orders;
```

正确写法：

```sql
SELECT SUM(total_amount) AS sales FROM orders WHERE status != 'cancelled';
```

### 错误七：退款统计未过滤状态

```sql
-- 错误：包含了 processing 和 rejected 的退款
SELECT SUM(refund_amount) AS refund_total FROM refunds;
```

正确写法：

```sql
SELECT SUM(refund_amount) AS refund_total FROM refunds WHERE status = 'approved';
```

### 错误八：使用 COUNT(order_items.id) 统计销量

```sql
-- 错误：统计的是明细行数，不是实际售出件数
SELECT COUNT(oi.id) AS sales FROM order_items oi;
```

正确写法：

```sql
SELECT SUM(oi.quantity) AS sales
FROM order_items AS oi
JOIN orders AS o ON o.id = oi.order_id
WHERE o.status != 'cancelled';
```

## 完整 JOIN 路径参考

以下是所有合法的表关联路径：

```text
users.id ← orders.user_id                          -- 用户 → 订单
orders.id ← order_items.order_id                   -- 订单 → 订单明细
products.id ← order_items.product_id               -- 商品 → 订单明细
categories.id ← products.category_id               -- 分类 → 商品
promotions.id ← orders.promotion_id (可 NULL)      -- 营销活动 → 订单
orders.id ← refunds.order_id                       -- 订单 → 退款
order_items.id ← refunds.order_item_id (可 NULL)   -- 订单明细 → 退款（部分退款）
```

典型的多表查询 JOIN 链：

```sql
-- 完整的商品销售分析关联链
FROM order_items AS oi
JOIN orders AS o ON o.id = oi.order_id
JOIN products AS p ON p.id = oi.product_id
JOIN categories AS c ON c.id = p.category_id
JOIN users AS u ON u.id = o.user_id
```

## 数据覆盖的日期范围

默认数据生成配置的日期范围为 2024-01-01 至 2025-12-31（由 `GenerationConfig` 的 `start_date` 和 `end_date` 参数控制）。可通过命令行参数自定义。

各时间字段的实际覆盖范围：

- `orders.order_date`：在 `start_date` 到 `end_date` 之间
- `users.created_at`：在 `start_date - 730 天` 到 `start_date` 之间（即首笔订单前两年内）
- `products.created_at`：在 `start_date - 540 天` 到 `start_date` 之间（即首笔订单前约一年半内）
- `refunds.created_at`：在原订单 `order_date` 后 1 到 20 天内
- `promotions.start_date` / `end_date`：在数据范围内按年度生成（春节、618、双十一）

查询时应根据实际数据确定日期范围，可使用以下 SQL 检查：

```sql
SELECT
    MIN(order_date) AS earliest_order,
    MAX(order_date) AS latest_order
FROM orders;
```

```sql
SELECT
    MIN(u.created_at) AS earliest_registration,
    MAX(u.created_at) AS latest_registration
FROM users AS u;
```
