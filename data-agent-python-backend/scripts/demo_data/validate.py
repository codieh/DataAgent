"""演示数据完整性校验。

提供两类校验：
- ``validate_sample``：在内存中对“生成结果”做一致性校验（金额关系、外键、时间范围、非负）；
- ``validate_database``：在写入 MySQL 后做端到端校验（行数符合预期、金额闭合、无孤儿明细、
  时间范围合法）。

两者都产出 ``ValidationReport``（``ok`` 汇总所有检查项），供 generate.py 决定退出状态。
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from sqlalchemy import Engine, text

from scripts.demo_data.generator import Dimensions, GenerationConfig, OrderBundle


@dataclass(frozen=True)
class ValidationReport:
    """校验结果：整体是否通过（ok）、各表行数（counts）、各项检查结论（checks）。"""

    ok: bool
    counts: dict[str, int]
    checks: dict[str, bool]


def validate_sample(
    config: GenerationConfig,
    dimensions: Dimensions,
    bundles: Iterable[OrderBundle],
) -> ValidationReport:
    """对生成的内存数据做一致性校验（不落库）。

    检查项：订单金额 = 明细行金额之和 - 折扣；外键（user/product/promotion）有效；
    订单日期落在目标区间；总金额非负。
    """
    materialized = list(bundles)
    user_ids = {row["id"] for row in dimensions.users}
    product_ids = {row["id"] for row in dimensions.products}
    promotion_ids = {row["id"] for row in dimensions.promotions}
    items = [item for bundle in materialized for item in bundle.items]
    refunds = [bundle.refund for bundle in materialized if bundle.refund]

    # 金额闭合：total_amount 必须等于各明细 line_amount 之和减去折扣
    amount_match = all(
        bundle.order["total_amount"]
        == sum(item["line_amount"] for item in bundle.items)
        - bundle.order["discount_amount"]
        for bundle in materialized
    )
    # 外键完整性：用户/商品/促销引用均存在（promotion 可为空）
    foreign_keys = all(
        bundle.order["user_id"] in user_ids
        and all(item["product_id"] in product_ids for item in bundle.items)
        and (
            bundle.order["promotion_id"] is None
            or bundle.order["promotion_id"] in promotion_ids
        )
        for bundle in materialized
    )
    checks = {
        "order_amounts_match": amount_match,
        "foreign_keys_valid": foreign_keys,
        "date_range_valid": all(
            config.start_date <= bundle.order["order_date"].date() <= config.end_date
            for bundle in materialized
        ),
        "non_negative_amounts": all(
            bundle.order["total_amount"] >= Decimal("0.00") for bundle in materialized
        ),
    }
    counts = {
        "users": len(dimensions.users),
        "products": len(dimensions.products),
        "orders": len(materialized),
        "order_items": len(items),
        "refunds": len(refunds),
    }
    return ValidationReport(ok=all(checks.values()), counts=counts, checks=checks)


def validate_database(engine: Engine, expected: GenerationConfig) -> ValidationReport:
    """对写入后的数据库做端到端校验。

    除行数符合预期外，重点用 SQL 校验金额闭合（允许 0.01 浮点误差）、无孤儿明细
    （明细引用的订单/商品必须存在）、订单日期在目标区间。
    """
    tables = [
        "users",
        "products",
        "orders",
        "order_items",
        "refunds",
    ]
    with engine.connect() as connection:
        # 各表实际行数
        counts = {
            table: int(connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one())
            for table in tables
        }
        # 金额闭合：订单 total 应等于其明细小计减去折扣（误差阈值 0.01）
        mismatch_count = int(
            connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM orders o
                    JOIN (
                        SELECT order_id, SUM(quantity * unit_price) AS subtotal
                        FROM order_items GROUP BY order_id
                    ) i ON i.order_id = o.id
                    WHERE ABS(o.total_amount - (i.subtotal - o.discount_amount)) > 0.01
                    """
                )
            ).scalar_one()
        )
        # 孤儿明细：明细引用的订单或商品缺失
        orphan_items = int(
            connection.execute(
                text(
                    """
                    SELECT COUNT(*) FROM order_items i
                    LEFT JOIN orders o ON o.id = i.order_id
                    LEFT JOIN products p ON p.id = i.product_id
                    WHERE o.id IS NULL OR p.id IS NULL
                    """
                )
            ).scalar_one()
        )
        # 时间越界：订单日期落在预期区间之外
        date_violations = int(
            connection.execute(
                text("SELECT COUNT(*) FROM orders WHERE DATE(order_date) < :start OR DATE(order_date) > :end"),
                {"start": expected.start_date, "end": expected.end_date},
            ).scalar_one()
        )
    checks = {
        "expected_users": counts["users"] == expected.users,
        "expected_products": counts["products"] == expected.products,
        "expected_orders": counts["orders"] == expected.orders,
        "order_amounts_match": mismatch_count == 0,
        "foreign_keys_valid": orphan_items == 0,
        "date_range_valid": date_violations == 0,
    }
    return ValidationReport(ok=all(checks.values()), counts=counts, checks=checks)
