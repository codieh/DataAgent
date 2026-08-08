"""测试演示数据（demo data）的生成器、预设与校验脚本。

覆盖：预设的三种规模（小/中/大型）、生成的确定性与金额一致性、是否为业务实体补充了
扩展维度（会员等级、省份、销售渠道、促销、退款等）、样本校验能否通过，以及建表
SQL 的表与字段是否满足原始 + 扩展设计要求。
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

from scripts.demo_data.generator import GenerationConfig, generate_dimensions, iter_order_bundles
from scripts.demo_data.presets import PRESETS
from scripts.demo_data.validate import validate_sample


def test_presets_offer_development_demo_and_stress_scales() -> None:
    """验证预设提供开发、演示、压测三档订单规模（5k / 50k / 300k）。"""
    assert PRESETS["small"].orders == 5_000
    assert PRESETS["medium"].orders == 50_000
    assert PRESETS["large"].orders == 300_000


def test_generation_is_deterministic_and_preserves_order_amount() -> None:
    """验证相同配置 + 随机种子下生成结果可复现，且订单总金额等于明细小计减折扣、且不为负。"""
    config = GenerationConfig(
        users=30,
        products=40,
        orders=10,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31),
        seed=42,
    )
    first_dimensions = generate_dimensions(config)
    second_dimensions = generate_dimensions(config)
    first = list(iter_order_bundles(config, first_dimensions))
    second = list(iter_order_bundles(config, second_dimensions))

    # 相同配置两次生成结果完全一致（确定性）
    assert first == second
    for bundle in first:
        # 订单金额应等于各明细数量×单价之和减去折扣
        item_total = sum(item["quantity"] * item["unit_price"] for item in bundle.items)
        assert bundle.order["total_amount"] == item_total - bundle.order["discount_amount"]
        # 金额不应为负
        assert bundle.order["total_amount"] >= Decimal("0.00")


def test_generated_data_contains_extended_business_dimensions() -> None:
    """验证生成数据覆盖了扩展业务维度：会员等级、省份、销售渠道、促销与退款。"""
    config = GenerationConfig(users=100, products=60, orders=300, seed=7)
    dimensions = generate_dimensions(config)
    bundles = list(iter_order_bundles(config, dimensions))

    assert {user["membership_level"] for user in dimensions.users} >= {"normal", "silver", "gold"}
    assert {user["province"] for user in dimensions.users} >= {"上海", "广东", "北京"}
    assert {bundle.order["sales_channel"] for bundle in bundles} >= {"app", "web", "mini_program"}
    assert dimensions.promotions
    assert any(bundle.order["promotion_id"] for bundle in bundles)
    assert any(bundle.refund for bundle in bundles)


def test_sample_validation_detects_consistent_dataset() -> None:
    """验证样本校验能识别金额一致、外键有效的数据集，并统计订单/订单项数量。"""
    config = GenerationConfig(users=80, products=50, orders=500, seed=20260706)
    dimensions = generate_dimensions(config)
    bundles = list(iter_order_bundles(config, dimensions))

    report = validate_sample(config, dimensions, bundles)

    assert report.ok is True
    assert report.counts["orders"] == 500
    assert report.counts["order_items"] > 500
    assert report.checks["order_amounts_match"] is True
    assert report.checks["foreign_keys_valid"] is True


def test_schema_defines_original_and_extended_tables() -> None:
    """验证建表 SQL 包含原始 + 扩展表，且不再包含已废弃的旧表（regions 等）。"""
    schema = (
        Path(__file__).parents[1] / "scripts" / "demo_data" / "schema.sql"
    ).read_text(encoding="utf-8")

    for table in (
        "users",
        "categories",
        "products",
        "orders",
        "order_items",
        "promotions",
        "refunds",
    ):
        assert f"CREATE TABLE {table}" in schema

    for removed_table in ("regions", "sales_channels", "product_categories", "order_promotions"):
        assert f"CREATE TABLE {removed_table}" not in schema


def test_schema_keeps_analysis_dimensions_on_business_entities() -> None:
    """验证业务实体表保留了分析所需的维度字段（省份、会员等级、销售渠道、促销、小计、成本等）。"""
    schema = (
        Path(__file__).parents[1] / "scripts" / "demo_data" / "schema.sql"
    ).read_text(encoding="utf-8")

    assert "province VARCHAR" in schema
    assert "membership_level ENUM" in schema
    assert "category_id INT NOT NULL" in schema
    assert "sales_channel ENUM" in schema
    assert "promotion_id INT NULL" in schema
    assert "subtotal_amount DECIMAL" in schema
    assert "unit_cost DECIMAL" in schema
