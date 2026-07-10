"""确定性电商演示数据的生成逻辑。

本模块不连接数据库，纯粹根据 ``GenerationConfig`` 生成维度数据（类目/商品/用户/
促销）与订单事实（逐笔订单及其明细、退款）。所有随机性均由固定种子驱动，因此
在相同的 preset 与参数下能复现完全一致的数据。

金额统一使用 ``Decimal`` 并按分（0.01）量化，避免浮点误差；订单/明细/退款通过
``iter_order_bundles`` 以生成器方式惰性产出，便于上层分批写入。
"""

import calendar
import random
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterator

from scripts.demo_data.catalog import (
    BRANDS,
    CATEGORIES,
    CATEGORY_BASE_PRICES,
    CHANNELS,
    PRODUCT_ROOTS,
    REGION_NAMES,
)


# 金额最小单位：分。所有金额均量化到该精度，避免浮点累加误差
MONEY = Decimal("0.01")


@dataclass(frozen=True)
class GenerationConfig:
    """数据生成配置：规模、时间范围与随机种子。

    校验规则保证规模为正、时间范围合法；固定 seed 使生成结果可复现。
    """

    users: int
    products: int
    orders: int
    start_date: date = date(2024, 1, 1)
    end_date: date = date(2025, 12, 31)
    seed: int = 20260706

    def __post_init__(self) -> None:
        if min(self.users, self.products, self.orders) <= 0:
            raise ValueError("users、products 和 orders 必须大于 0")
        if self.end_date < self.start_date:
            raise ValueError("end_date 不能早于 start_date")


@dataclass(frozen=True)
class Dimensions:
    """维度数据集合：类目、商品、用户、促销。"""

    categories: list[dict]
    products: list[dict]
    users: list[dict]
    promotions: list[dict]


@dataclass(frozen=True)
class OrderBundle:
    """单笔订单及其明细与（可选）退款，作为事实数据的最小写入单元。"""

    order: dict
    items: list[dict]
    refund: dict | None


def generate_dimensions(config: GenerationConfig) -> Dimensions:
    """生成全部维度数据（类目/商品/用户/促销）。"""
    rng = random.Random(config.seed)
    categories = [{"id": index, "name": name} for index, name in enumerate(CATEGORIES, start=1)]
    return Dimensions(
        categories=categories,
        products=_generate_products(config, rng),
        users=_generate_users(config, rng),
        promotions=_generate_promotions(config),
    )


def iter_order_bundles(config: GenerationConfig, dimensions: Dimensions) -> Iterator[OrderBundle]:
    """惰性生成逐笔订单事实（订单 + 明细 + 可选退款）。

    设计：使用独立种子（config.seed + 1）使订单流与维度生成解耦但同样可复现；
    用户/商品采用加权抽样，分别模拟会员活跃度与商品长尾热度。
    """
    rng = random.Random(config.seed + 1)
    item_id = 1
    refund_id = 1
    # 会员等级越高，下单权重越大（忠实客户贡献更多订单）
    user_weights = [
        {"normal": 1.0, "silver": 1.8, "gold": 3.2, "platinum": 5.0}[user["membership_level"]]
        for user in dimensions.users
    ]
    # 长尾分布：下标越靠前的商品权重略高，使数据集同时具备爆款与冷门品
    product_weights = [1 + ((len(dimensions.products) - index) % 17) for index in range(len(dimensions.products))]

    for order_id in range(1, config.orders + 1):
        ordered_at = _random_order_datetime(rng, config, dimensions.promotions)
        user = rng.choices(dimensions.users, weights=user_weights, k=1)[0]
        sales_channel = rng.choices(
            [code for code, _name in CHANNELS], weights=[34, 26, 20, 8, 12], k=1
        )[0]
        status = _order_status(rng, ordered_at.date(), config.end_date)
        selected = _weighted_unique_products(rng, dimensions.products, product_weights)
        items = []
        subtotal = Decimal("0.00")
        for product in selected:
            quantity = _quantity_for_price(rng, product["price"])
            line_amount = (product["price"] * quantity).quantize(MONEY)
            subtotal += line_amount
            items.append(
                {
                    "id": item_id,
                    "order_id": order_id,
                    "product_id": product["id"],
                    "quantity": quantity,
                    "unit_price": product["price"],
                    "unit_cost": product["cost_price"],
                    "line_amount": line_amount,
                }
            )
            item_id += 1

        promotion = _active_promotion(rng, ordered_at.date(), subtotal, dimensions.promotions)
        discount = Decimal("0.00")
        if promotion and status != "cancelled":
            # 折扣不超过“比例折扣”与“封顶优惠”二者的较小值
            discount = min(
                subtotal * promotion["discount_rate"], promotion["max_discount"]
            ).quantize(MONEY, rounding=ROUND_HALF_UP)

        order = {
            "id": order_id,
            "user_id": user["id"],
            "promotion_id": promotion["id"] if promotion and status != "cancelled" else None,
            "sales_channel": sales_channel,
            "payment_method": rng.choices(
                ["alipay", "wechat", "bank_card", "cash"], weights=[42, 38, 16, 4], k=1
            )[0],
            "province": user["province"],
            "city": user["city"],
            "subtotal_amount": subtotal.quantize(MONEY),
            "discount_amount": discount,
            "total_amount": (subtotal - discount).quantize(MONEY),
            "status": status,
            "order_date": ordered_at,
        }

        refund = _maybe_refund(rng, refund_id, order, items)
        if refund:
            refund_id += 1
        yield OrderBundle(order=order, items=items, refund=refund)


def _generate_products(config: GenerationConfig, rng: random.Random) -> list[dict]:
    """生成商品维度：按类目轮转分配类目，并在基准价上浮动定价、推算成本。"""
    products = []
    created_start = config.start_date - timedelta(days=540)
    date_span = max(1, (config.start_date - created_start).days)
    for product_id in range(1, config.products + 1):
        category_id = ((product_id - 1) % len(CATEGORIES)) + 1
        base = Decimal(str(CATEGORY_BASE_PRICES[category_id - 1]))
        # 在基准价 0.55~1.85 倍区间内浮动定价
        price = (base * Decimal(str(rng.uniform(0.55, 1.85)))).quantize(MONEY)
        # 成本约为售价的 0.52~0.78 倍
        cost_price = (price * Decimal(str(rng.uniform(0.52, 0.78)))).quantize(MONEY)
        brand = BRANDS[(product_id - 1) % len(BRANDS)]
        # 款型随“每类目内的序号”轮转，保证命名多样
        root = PRODUCT_ROOTS[((product_id - 1) // len(CATEGORIES)) % len(PRODUCT_ROOTS)]
        products.append(
            {
                "id": product_id,
                "category_id": category_id,
                "sku": f"SKU-{category_id:02d}-{product_id:05d}",
                "name": f"{brand}{CATEGORIES[category_id - 1]}{root}{product_id:03d}",
                "brand": brand,
                "price": price,
                "cost_price": cost_price,
                "stock": rng.randint(0, 500),
                "status": rng.choices(["active", "inactive"], weights=[96, 4], k=1)[0],
                "created_at": datetime.combine(
                    created_start + timedelta(days=rng.randint(0, date_span)), time(rng.randint(8, 20))
                ),
            }
        )
    return products


def _generate_users(config: GenerationConfig, rng: random.Random) -> list[dict]:
    """生成用户维度：随机分配地区、会员等级与年龄组，并给出注册时间。"""
    users = []
    registration_start = config.start_date - timedelta(days=730)
    span = max(1, (config.start_date - registration_start).days)
    levels = ["normal", "silver", "gold", "platinum"]
    age_groups = ["18-24", "25-34", "35-44", "45-54", "55+"]
    locations = [{"province": province, "city": city} for province, city in REGION_NAMES]
    location_weights = [18, 14, 11, 12, 11, 10, 4, 8, 7, 5]
    for user_id in range(1, config.users + 1):
        location = rng.choices(locations, weights=location_weights, k=1)[0]
        users.append(
            {
                "id": user_id,
                "username": f"user{user_id:06d}",
                "email": f"user{user_id:06d}@example.com",
                "province": location["province"],
                "city": location["city"],
                "membership_level": rng.choices(levels, weights=[62, 23, 11, 4], k=1)[0],
                "age_group": rng.choices(age_groups, weights=[16, 35, 27, 15, 7], k=1)[0],
                "created_at": datetime.combine(
                    registration_start + timedelta(days=rng.randint(0, span)),
                    time(rng.randint(8, 22), rng.randint(0, 59)),
                ),
            }
        )
    return users


def _generate_promotions(config: GenerationConfig) -> list[dict]:
    """生成年度促销维度：覆盖范围内每年生成春节/618/双十一三档百分比折扣。"""
    promotions = []
    promotion_id = 1
    for year in range(config.start_date.year, config.end_date.year + 1):
        # (名称, 类型, 开始, 结束, 折扣率, 封顶优惠, 起用门槛)
        definitions = [
            ("春节焕新", "percentage", date(year, 1, 15), date(year, 2, min(15, calendar.monthrange(year, 2)[1])), "0.08", "300", "200"),
            ("618 年中大促", "percentage", date(year, 6, 1), date(year, 6, 20), "0.12", "800", "300"),
            ("双十一", "percentage", date(year, 11, 1), date(year, 11, 12), "0.15", "1200", "500"),
        ]
        for name, promotion_type, start, end, rate, maximum, minimum in definitions:
            # 只保留与目标时间范围有交集的促销
            if end < config.start_date or start > config.end_date:
                continue
            promotions.append(
                {
                    "id": promotion_id,
                    "name": f"{year} {name}",
                    "promotion_type": promotion_type,
                    "start_date": max(start, config.start_date),
                    "end_date": min(end, config.end_date),
                    "discount_rate": Decimal(rate),
                    "max_discount": Decimal(maximum),
                    "min_order_amount": Decimal(minimum),
                }
            )
            promotion_id += 1
    return promotions


def _random_order_datetime(rng: random.Random, config: GenerationConfig, promotions: list[dict]) -> datetime:
    """随机生成下单时间：约 28% 概率落在某促销期内，否则落在整体区间（并偶尔推到周末）。"""
    if promotions and rng.random() < 0.28:
        promotion = rng.choice(promotions)
        day = promotion["start_date"] + timedelta(
            days=rng.randint(0, (promotion["end_date"] - promotion["start_date"]).days)
        )
    else:
        day = config.start_date + timedelta(
            days=rng.randint(0, max(0, (config.end_date - config.start_date).days))
        )
        # 工作日有 22% 概率顺延到最近的周末，模拟周末消费高峰
        if day.weekday() < 5 and rng.random() < 0.22:
            weekend = day + timedelta(days=5 - day.weekday())
            if weekend <= config.end_date:
                day = weekend
    # 下单时段偏向晚间（18-23 点权重更高）
    hour = rng.choices(range(8, 24), weights=[1, 2, 3, 3, 2, 2, 3, 4, 4, 4, 5, 6, 7, 6, 4, 2], k=1)[0]
    return datetime.combine(day, time(hour, rng.randint(0, 59), rng.randint(0, 59)))


def _order_status(rng: random.Random, ordered_on: date, end_date: date) -> str:
    """决定订单状态：临近结束日期的订单更可能是未完成态（pending/cancelled）。"""
    if (end_date - ordered_on).days <= 14:
        return rng.choices(["completed", "pending", "cancelled"], weights=[67, 25, 8], k=1)[0]
    return rng.choices(["completed", "cancelled"], weights=[92, 8], k=1)[0]


def _weighted_unique_products(rng: random.Random, products: list[dict], weights: list[int]) -> list[dict]:
    """按长尾权重抽取不重复的商品组合（1~5 件）。"""
    count = min(len(products), rng.choices([1, 2, 3, 4, 5], weights=[22, 36, 25, 12, 5], k=1)[0])
    pool = list(zip(products, weights, strict=True))
    selected = []
    for _ in range(count):
        choice = rng.choices(pool, weights=[item[1] for item in pool], k=1)[0]
        selected.append(choice[0])
        pool.remove(choice)
    return selected


def _quantity_for_price(rng: random.Random, price: Decimal) -> int:
    """根据单价决定购买数量：越便宜买得越多。"""
    if price < Decimal("100"):
        return rng.choices([1, 2, 3, 4, 5], weights=[25, 32, 23, 13, 7], k=1)[0]
    if price < Decimal("1000"):
        return rng.choices([1, 2, 3], weights=[62, 29, 9], k=1)[0]
    return rng.choices([1, 2], weights=[92, 8], k=1)[0]


def _active_promotion(
    rng: random.Random, ordered_on: date, subtotal: Decimal, promotions: list[dict]
) -> dict | None:
    """返回下单当日可用且满足起用门槛的促销（约 82% 概率命中，否则不享优惠）。"""
    active = [
        item
        for item in promotions
        if item["start_date"] <= ordered_on <= item["end_date"]
        and subtotal >= item["min_order_amount"]
    ]
    return rng.choice(active) if active and rng.random() < 0.82 else None


def _maybe_refund(
    rng: random.Random, refund_id: int, order: dict, items: list[dict]
) -> dict | None:
    """按概率生成退款：第三方平台、高额订单退款率更高；整单退款或单品退款二选一。"""
    if order["status"] != "completed":
        return None
    rate = 0.055 + (0.035 if order["sales_channel"] == "marketplace" else 0)
    rate += 0.02 if order["total_amount"] > Decimal("2000") else 0
    if rng.random() >= rate:
        return None
    item = rng.choice(items)
    full_order = rng.random() < 0.28
    amount = order["total_amount"] if full_order else min(item["line_amount"], order["total_amount"])
    return {
        "id": refund_id,
        "order_id": order["id"],
        "order_item_id": None if full_order else item["id"],
        "refund_amount": amount.quantize(MONEY),
        "reason": rng.choice(["质量问题", "尺寸不合适", "物流延迟", "用户取消", "重复下单"]),
        "status": rng.choices(["approved", "processing", "rejected"], weights=[78, 14, 8], k=1)[0],
        "created_at": order["order_date"] + timedelta(days=rng.randint(1, 20)),
    }
