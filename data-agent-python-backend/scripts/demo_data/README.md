# Demo Data Generator

用于一次性创建 DataAgent 的 MySQL 演示数据库。它是离线 CLI，不属于后端服务，也不会在应用启动时自动运行。

## 数据模型

演示库采用 7 张业务表。地区、渠道和会员等级直接保存在它们所属的业务实体上，避免为了几个固定枚举增加无意义的关联表：

```text
users ── orders ── order_items ── products ── categories
            │              │
            │              └── refunds（可关联具体明细）
            ├── promotions
            └── refunds
```

- `users` 保存省份、城市、会员等级和年龄段。
- `orders` 保存销售渠道、支付方式、收货地区快照及优惠前后金额。
- `products` 直接关联一个主营分类，并保存品牌、成本、售价和库存。
- `promotions` 保存活动周期和优惠规则，订单可关联一个主要活动。
- `refunds` 独立保存退款生命周期，并可定位整单或具体订单明细。

生成数据包含稳定且可复现的业务规律：

- 618、双十一和春节活动期间订单增长
- 周末及晚间订单更集中
- 高等级会员购买频率更高
- App、Web、小程序、门店和第三方平台具有不同订单占比
- 第三方平台与高金额订单退款率略高
- 商品价格、成本、销量和库存存在可分析差异

这些规律用于展示趋势分析、用户分层、渠道对比、活动评估、退款分析和多表关联能力，不代表真实经营数据。

## 使用方法

在 `data-agent-python-backend` 目录执行：

```bash
uv run python -m scripts.demo_data.generate --preset medium --dry-run
```

确认计划后写入 MySQL：

```bash
uv run python -m scripts.demo_data.generate \
  --database-url "mysql+pymysql://root:password@127.0.0.1:3306/product_db" \
  --preset medium \
  --reset
```

也可以复用后端环境变量：

```bash
export DATA_AGENT_PRODUCT_DATABASE_URL="mysql+pymysql://root:password@127.0.0.1:3306/product_db"
uv run python -m scripts.demo_data.generate --preset medium --reset
```

> `--reset` 会删除并重建上述演示表。为避免误操作，不传 `--reset` 时脚本不会写入数据库。

## 规模预设

| Preset | 用户 | 商品 | 订单 | 适用场景 |
| --- | ---: | ---: | ---: | --- |
| `small` | 500 | 80 | 5,000 | 日常开发与快速重置 |
| `medium` | 5,000 | 200 | 50,000 | 默认演示和复杂分析 |
| `large` | 20,000 | 500 | 300,000 | 查询性能和大结果集测试 |

参数可以单独覆盖：

```bash
uv run python -m scripts.demo_data.generate \
  --preset small \
  --users 1000 \
  --products 120 \
  --orders 20000 \
  --start-date 2024-01-01 \
  --end-date 2025-12-31 \
  --seed 20260706 \
  --reset
```

相同参数和 `seed` 会生成相同数据。事实表按批写入，不会先在内存中构造全部订单；可使用 `--batch-size` 调整每批订单数量。

## 自动校验

写入完成后脚本自动检查：

- 用户、商品和订单数量是否符合配置
- 订单金额是否等于明细金额减去优惠金额
- 订单明细是否存在孤立外键
- 订单时间是否位于指定范围

任一检查失败时命令以非零状态退出。
