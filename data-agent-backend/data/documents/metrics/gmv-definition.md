# GMV 定义

GMV 指平台成交总额。

在 product_db 中，GMV 默认按 `SUM(order_items.quantity * order_items.unit_price)` 汇总，仅统计 `orders.status = 'completed'` 的订单。

**注意**：不使用 `orders.total_amount` 作为 GMV 口径，因为 order_items 才是明细来源。

## 订单状态处理

| 状态 | 是否计入 GMV | 说明 |
|------|------------|------|
| completed | 是 | 默认统计口径 |
| pending | 否 | 待处理订单，除非用户明确要求 |
| cancelled | 否 | 已取消订单，永远不计入 |

## 分类统计注意事项

products 与 categories 是多对多关系，通过 `product_categories` 关联表连接。

按分类统计 GMV 时，JOIN 路径为：`order_items → products → product_categories → categories`。

一个商品可能属于多个分类（如平板电脑同时属于"电子产品"和"办公用品"），统计时需注意去重或明确口径。

## 价格字段说明

- `products.price`：商品当前单价（可能已调整）
- `order_items.unit_price`：下单时的快照单价

计算 GMV 应使用 `order_items.unit_price`，以反映实际成交价格。
