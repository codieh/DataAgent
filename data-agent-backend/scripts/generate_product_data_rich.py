import argparse
import calendar
import random
from collections import OrderedDict
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path


RANDOM_SEED = 20260324


CATEGORIES = [
    "电子产品",
    "服装",
    "图书",
    "家居用品",
    "食品",
    "办公用品",
    "运动户外",
    "美妆个护",
    "母婴用品",
    "厨房用品",
]


PRODUCTS = [
    {"name": "智能手机", "price": "3299.00", "stock": 45, "created_at": "2024-06-18 10:00:00", "categories": [1], "weight": 11},
    {"name": "笔记本电脑", "price": "5499.00", "stock": 22, "created_at": "2024-07-02 11:20:00", "categories": [1], "weight": 6},
    {"name": "蓝牙耳机", "price": "399.00", "stock": 68, "created_at": "2024-08-10 09:30:00", "categories": [1], "weight": 12},
    {"name": "平板电脑", "price": "2899.00", "stock": 30, "created_at": "2024-10-08 15:10:00", "categories": [1, 6], "weight": 7},
    {"name": "显示器", "price": "1299.00", "stock": 18, "created_at": "2024-11-12 14:40:00", "categories": [1, 6], "weight": 4},
    {"name": "T恤衫", "price": "99.00", "stock": 260, "created_at": "2024-06-05 12:00:00", "categories": [2], "weight": 9},
    {"name": "牛仔裤", "price": "199.00", "stock": 180, "created_at": "2024-07-16 16:50:00", "categories": [2], "weight": 6},
    {"name": "羽绒服", "price": "499.00", "stock": 70, "created_at": "2024-11-01 13:15:00", "categories": [2], "weight": 5},
    {"name": "运动鞋", "price": "359.00", "stock": 90, "created_at": "2024-09-20 18:00:00", "categories": [2, 7], "weight": 8},
    {"name": "小说", "price": "49.00", "stock": 140, "created_at": "2024-06-25 17:10:00", "categories": [3], "weight": 6},
    {"name": "历史书", "price": "79.00", "stock": 120, "created_at": "2024-08-28 10:35:00", "categories": [3], "weight": 5},
    {"name": "编程书", "price": "129.00", "stock": 85, "created_at": "2024-10-15 11:45:00", "categories": [3, 6], "weight": 6},
    {"name": "儿童绘本", "price": "59.00", "stock": 110, "created_at": "2024-12-06 09:00:00", "categories": [3, 9], "weight": 7},
    {"name": "沙发", "price": "2899.00", "stock": 8, "created_at": "2024-07-09 14:20:00", "categories": [4], "weight": 2},
    {"name": "台灯", "price": "149.00", "stock": 95, "created_at": "2024-06-12 19:00:00", "categories": [4, 6], "weight": 5},
    {"name": "床上四件套", "price": "269.00", "stock": 55, "created_at": "2024-09-05 10:50:00", "categories": [4], "weight": 4},
    {"name": "收纳箱", "price": "69.00", "stock": 160, "created_at": "2024-08-14 15:05:00", "categories": [4], "weight": 6},
    {"name": "牛奶", "price": "18.00", "stock": 75, "created_at": "2024-06-03 08:30:00", "categories": [5], "weight": 13},
    {"name": "巧克力", "price": "29.00", "stock": 88, "created_at": "2024-07-25 09:40:00", "categories": [5], "weight": 10},
    {"name": "咖啡豆", "price": "59.00", "stock": 90, "created_at": "2024-09-12 10:10:00", "categories": [5, 10], "weight": 7},
    {"name": "坚果礼盒", "price": "128.00", "stock": 45, "created_at": "2024-12-20 13:30:00", "categories": [5], "weight": 5},
    {"name": "中性笔", "price": "12.00", "stock": 320, "created_at": "2024-06-09 10:25:00", "categories": [6], "weight": 6},
    {"name": "办公椅", "price": "399.00", "stock": 28, "created_at": "2024-08-02 14:00:00", "categories": [6], "weight": 4},
    {"name": "文件柜", "price": "899.00", "stock": 14, "created_at": "2024-10-19 17:15:00", "categories": [6], "weight": 2},
    {"name": "瑜伽垫", "price": "89.00", "stock": 130, "created_at": "2024-07-18 16:40:00", "categories": [7], "weight": 6},
    {"name": "跑步机", "price": "2499.00", "stock": 6, "created_at": "2024-09-30 12:20:00", "categories": [7], "weight": 2},
    {"name": "登山包", "price": "299.00", "stock": 40, "created_at": "2024-11-03 11:30:00", "categories": [7], "weight": 4},
    {"name": "运动水壶", "price": "39.00", "stock": 150, "created_at": "2024-08-21 10:45:00", "categories": [7, 10], "weight": 8},
    {"name": "洗面奶", "price": "79.00", "stock": 120, "created_at": "2024-06-27 09:15:00", "categories": [8], "weight": 6},
    {"name": "电动牙刷", "price": "259.00", "stock": 85, "created_at": "2024-07-30 15:45:00", "categories": [1, 8], "weight": 11},
    {"name": "面膜", "price": "99.00", "stock": 140, "created_at": "2024-10-05 19:10:00", "categories": [8], "weight": 8},
    {"name": "防晒霜", "price": "129.00", "stock": 95, "created_at": "2025-03-01 13:05:00", "categories": [8], "weight": 9},
    {"name": "婴儿奶粉", "price": "268.00", "stock": 52, "created_at": "2024-07-07 10:00:00", "categories": [9], "weight": 5},
    {"name": "尿不湿", "price": "119.00", "stock": 110, "created_at": "2024-06-30 08:40:00", "categories": [9], "weight": 8},
    {"name": "儿童餐椅", "price": "459.00", "stock": 16, "created_at": "2024-09-18 16:15:00", "categories": [4, 9], "weight": 3},
    {"name": "婴儿推车", "price": "699.00", "stock": 20, "created_at": "2024-11-15 14:50:00", "categories": [9], "weight": 4},
    {"name": "咖啡机", "price": "699.00", "stock": 24, "created_at": "2024-08-08 11:10:00", "categories": [1, 10], "weight": 5},
    {"name": "电饭煲", "price": "329.00", "stock": 42, "created_at": "2024-09-09 09:35:00", "categories": [10], "weight": 5},
    {"name": "不粘锅", "price": "159.00", "stock": 72, "created_at": "2024-07-22 12:45:00", "categories": [10], "weight": 6},
    {"name": "刀具套装", "price": "219.00", "stock": 34, "created_at": "2024-10-27 18:20:00", "categories": [10], "weight": 4},
]


MONTHLY_ORDER_COUNTS = OrderedDict([
    ((2025, 1), 50),
    ((2025, 2), 60),
    ((2025, 3), 75),
    ((2025, 4), 85),
    ((2025, 5), 105),
    ((2025, 6), 125),
])


STATUS_POOL = ["completed"] * 350 + ["pending"] * 100 + ["cancelled"] * 50


def sql_escape(value):
    return value.replace("\\", "\\\\").replace("'", "''")


def pick_weighted_unique(rng, population, weights, count):
    pool = list(population)
    pool_weights = list(weights)
    result = []
    for _ in range(min(count, len(pool))):
        total = sum(pool_weights)
        threshold = rng.uniform(0, total)
        upto = 0
        for index, weight in enumerate(pool_weights):
            upto += weight
            if upto >= threshold:
                result.append(pool.pop(index))
                pool_weights.pop(index)
                break
    return result


def random_datetime_in_month(rng, year, month):
    last_day = calendar.monthrange(year, month)[1]
    days = list(range(1, last_day + 1))
    weights = []
    for day in days:
        weekday = datetime(year, month, day).weekday()
        weights.append(2.2 if weekday >= 5 else 1.0)
    day = rng.choices(days, weights=weights, k=1)[0]
    hour = rng.choices([9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21], weights=[2, 4, 4, 3, 3, 4, 4, 4, 5, 5, 4, 3, 2], k=1)[0]
    minute = rng.randint(0, 59)
    second = rng.randint(0, 59)
    return datetime(year, month, day, hour, minute, second)


def quantity_for_price(rng, price):
    if price < Decimal("30"):
        return rng.choices([1, 2, 3, 4, 5], weights=[1, 2, 4, 3, 2], k=1)[0]
    if price < Decimal("100"):
        return rng.choices([1, 2, 3, 4], weights=[2, 4, 3, 1], k=1)[0]
    if price < Decimal("500"):
        return rng.choices([1, 2, 3], weights=[4, 3, 1], k=1)[0]
    if price < Decimal("1500"):
        return rng.choices([1, 2], weights=[5, 1], k=1)[0]
    return 1


def build_users(rng):
    users = []
    start = datetime(2024, 1, 1, 8, 0, 0)
    end = datetime(2025, 6, 30, 20, 0, 0)
    total_seconds = int((end - start).total_seconds())
    for user_id in range(1, 81):
        created_at = start + timedelta(seconds=rng.randint(0, total_seconds))
        users.append({
            "id": user_id,
            "username": "user{0:03d}".format(user_id),
            "email": "user{0:03d}@example.com".format(user_id),
            "created_at": created_at.strftime("%Y-%m-%d %H:%M:%S"),
        })
    return users


def build_orders_and_items(rng):
    product_rows = []
    for index, product in enumerate(PRODUCTS, start=1):
        product_rows.append({
            "id": index,
            "name": product["name"],
            "price": Decimal(product["price"]),
            "weight": product["weight"],
        })

    user_weights = []
    for user_id in range(1, 81):
        if user_id <= 16:
            user_weights.append(8)
        elif user_id <= 56:
            user_weights.append(3)
        else:
            user_weights.append(1)

    statuses = list(STATUS_POOL)
    rng.shuffle(statuses)

    orders = []
    order_items = []
    order_id = 1
    order_item_id = 1

    for (year, month), month_count in MONTHLY_ORDER_COUNTS.items():
        for _ in range(month_count):
            user_id = rng.choices(range(1, 81), weights=user_weights, k=1)[0]
            order_date = random_datetime_in_month(rng, year, month)
            status = statuses[order_id - 1]
            item_count = rng.choices([1, 2, 3, 4, 5], weights=[2, 4, 5, 3, 1], k=1)[0]
            selected_products = pick_weighted_unique(
                rng,
                product_rows,
                [product["weight"] for product in product_rows],
                item_count,
            )

            amount = Decimal("0.00")
            for product in selected_products:
                quantity = quantity_for_price(rng, product["price"])
                line_amount = product["price"] * quantity
                amount += line_amount
                order_items.append({
                    "id": order_item_id,
                    "order_id": order_id,
                    "product_id": product["id"],
                    "quantity": quantity,
                    "unit_price": product["price"],
                })
                order_item_id += 1

            orders.append({
                "id": order_id,
                "user_id": user_id,
                "order_date": order_date.strftime("%Y-%m-%d %H:%M:%S"),
                "total_amount": amount.quantize(Decimal("0.01")),
                "status": status,
            })
            order_id += 1

    return orders, order_items


def format_insert(table, columns, rows):
    lines = ["INSERT INTO {0} ({1}) VALUES".format(table, ", ".join(columns))]
    values = []
    for row in rows:
        formatted = []
        for value in row:
            if value is None:
                formatted.append("NULL")
            elif isinstance(value, int):
                formatted.append(str(value))
            elif isinstance(value, Decimal):
                formatted.append(str(value.quantize(Decimal("0.01"))))
            else:
                formatted.append("'" + sql_escape(str(value)) + "'")
        values.append("({0})".format(", ".join(formatted)))
    lines.append(",\n".join(values) + ";")
    return "\n".join(lines)


def build_sql():
    rng = random.Random(RANDOM_SEED)
    users = build_users(rng)
    orders, order_items = build_orders_and_items(rng)

    statements = [
        "-- 增强版 product_db 测试数据",
        "-- 生成规则：80 用户 / 10 分类 / 40 商品 / 500 订单 / 明细金额严格回填订单金额",
        "SET FOREIGN_KEY_CHECKS = 0;",
        "TRUNCATE TABLE product_categories;",
        "TRUNCATE TABLE order_items;",
        "TRUNCATE TABLE orders;",
        "TRUNCATE TABLE products;",
        "TRUNCATE TABLE categories;",
        "TRUNCATE TABLE users;",
        "SET FOREIGN_KEY_CHECKS = 1;",
        "",
        format_insert(
            "users",
            ["id", "username", "email", "created_at"],
            [(user["id"], user["username"], user["email"], user["created_at"]) for user in users],
        ),
        "",
        format_insert(
            "categories",
            ["id", "name"],
            [(index, name) for index, name in enumerate(CATEGORIES, start=1)],
        ),
        "",
        format_insert(
            "products",
            ["id", "name", "price", "stock", "created_at"],
            [
                (index, product["name"], Decimal(product["price"]), product["stock"], product["created_at"])
                for index, product in enumerate(PRODUCTS, start=1)
            ],
        ),
        "",
        format_insert(
            "product_categories",
            ["product_id", "category_id"],
            [
                (index, category_id)
                for index, product in enumerate(PRODUCTS, start=1)
                for category_id in product["categories"]
            ],
        ),
        "",
        format_insert(
            "orders",
            ["id", "user_id", "total_amount", "status", "order_date"],
            [
                (order["id"], order["user_id"], order["total_amount"], order["status"], order["order_date"])
                for order in orders
            ],
        ),
        "",
        format_insert(
            "order_items",
            ["id", "order_id", "product_id", "quantity", "unit_price"],
            [
                (
                    item["id"],
                    item["order_id"],
                    item["product_id"],
                    item["quantity"],
                    item["unit_price"],
                )
                for item in order_items
            ],
        ),
        "",
        "-- 数据校验示例：",
        "-- SELECT COUNT(*) FROM orders;",
        "-- SELECT COUNT(*) FROM order_items;",
        "-- SELECT SUM(total_amount) FROM orders;",
    ]
    return "\n".join(statements) + "\n"


def main():
    parser = argparse.ArgumentParser(description="生成增强版 product_db 测试数据 SQL")
    parser.add_argument(
        "--output",
        default=str(Path(__file__).resolve().parents[1] / "src" / "main" / "resources" / "sql" / "product_data_rich.sql"),
        help="输出 SQL 文件路径",
    )
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(build_sql(), encoding="utf-8")
    print("已生成:", output_path)


if __name__ == "__main__":
    main()
