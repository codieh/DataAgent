# 增强版 `product_db` 测试数据设计

## 目标

- 支持 `data-agent-backend` 的 NL2SQL 流水线评测与演示
- 保持现有 6 张表结构不变
- 提升数据规模、时间跨度和业务分布
- 确保 `orders.total_amount` 与 `order_items` 汇总金额严格一致

## 数据规模

- 用户：80
- 分类：10
- 商品：40
- 订单：500
- 订单明细：约 1500
- 时间范围：`2025-01-01` ~ `2025-06-30`

## 分类清单

1. 电子产品
2. 服装
3. 图书
4. 家居用品
5. 食品
6. 办公用品
7. 运动户外
8. 美妆个护
9. 母婴用品
10. 厨房用品

## 商品清单

| 分类 | 商品 |
| --- | --- |
| 电子产品 | 智能手机、笔记本电脑、蓝牙耳机、平板电脑、显示器 |
| 服装 | T恤衫、牛仔裤、羽绒服、运动鞋 |
| 图书 | 小说、历史书、编程书、儿童绘本 |
| 家居用品 | 沙发、台灯、床上四件套、收纳箱 |
| 食品 | 牛奶、巧克力、咖啡豆、坚果礼盒 |
| 办公用品 | 中性笔、办公椅、文件柜 |
| 运动户外 | 瑜伽垫、跑步机、登山包、运动水壶 |
| 美妆个护 | 洗面奶、电动牙刷、面膜、防晒霜 |
| 母婴用品 | 婴儿奶粉、尿不湿、儿童餐椅、婴儿推车 |
| 厨房用品 | 咖啡机、电饭煲、不粘锅、刀具套装 |

## 多分类商品

以下商品会出现在两个分类中，用于覆盖多对多场景：

- 平板电脑：电子产品 + 办公用品
- 显示器：电子产品 + 办公用品
- 运动鞋：服装 + 运动户外
- 编程书：图书 + 办公用品
- 儿童绘本：图书 + 母婴用品
- 台灯：家居用品 + 办公用品
- 咖啡豆：食品 + 厨房用品
- 运动水壶：运动户外 + 厨房用品
- 电动牙刷：电子产品 + 美妆个护
- 儿童餐椅：家居用品 + 母婴用品
- 咖啡机：电子产品 + 厨房用品

## 订单生成规则

### 用户分层

- 高活跃用户：16 人，权重高
- 普通用户：40 人，权重中
- 低活跃用户：24 人，权重低

### 月度分布

- 2025-01：50 单
- 2025-02：60 单
- 2025-03：75 单
- 2025-04：85 单
- 2025-05：105 单
- 2025-06：125 单

整体体现“越临近 6 月订单越多”的趋势。

### 状态分布

- `completed`：350
- `pending`：100
- `cancelled`：50

### 明细分布

- 每单 1~5 个商品
- 商品选择按热度权重抽样
- 高价商品通常购买 1 件
- 低价快消品可购买 2~5 件

## 业务特征

- 爆款商品：智能手机、蓝牙耳机、牛奶、巧克力、电动牙刷
- 滞销商品：沙发、文件柜、跑步机、儿童餐椅、显示器
- 低库存商品：沙发、跑步机、文件柜、儿童餐椅
- 夏季偏热商品：防晒霜、运动水壶在 6 月更容易出现在订单里（通过权重和订单增长体现）

## 生成方式

使用脚本：

`D:\GitHub\DataAgent\data-agent-backend\scripts\generate_product_data_rich.py`

生成命令：

`python D:\GitHub\DataAgent\data-agent-backend\scripts\generate_product_data_rich.py`

输出文件：

`D:\GitHub\DataAgent\data-agent-backend\src\main\resources\sql\product_data_rich.sql`

## 使用建议

1. 先执行原始建表脚本，保持 6 张表结构不变
2. 再执行 `product_data_rich.sql`
3. 执行后优先验证：
   - `SELECT COUNT(*) FROM users;`
   - `SELECT COUNT(*) FROM products;`
   - `SELECT COUNT(*) FROM orders;`
   - `SELECT COUNT(*) FROM order_items;`
4. 额外验证金额一致性：

```sql
SELECT
    o.id,
    o.total_amount,
    SUM(oi.quantity * oi.unit_price) AS detail_amount
FROM orders o
JOIN order_items oi ON oi.order_id = o.id
GROUP BY o.id, o.total_amount
HAVING o.total_amount <> SUM(oi.quantity * oi.unit_price);
```

理论上该查询应返回 0 行。
