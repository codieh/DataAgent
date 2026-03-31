# GMV 定义

GMV 指平台成交总额。

在当前 product_db 示例库中，GMV 默认按 `order_items.quantity * order_items.unit_price` 汇总，不直接使用 `orders.total_amount` 作为唯一口径。

## 取消订单处理

状态为 `cancelled` 的订单默认不计入 GMV。

状态为 `pending` 的订单是否计入，默认取决于具体分析场景；如果问题没有特别说明，优先统计 `completed` 订单。

## 分类统计注意事项

当按分类统计 GMV 时，需要注意 `products` 与 `categories` 是多对多关系，必须通过 `product_categories` 关联。

如果一个商品属于多个分类，统计口径需要明确；在当前演示场景中，默认按商品所属分类进行关联统计。
