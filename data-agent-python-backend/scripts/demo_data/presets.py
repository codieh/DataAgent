"""演示数据规模预设。

提供 small / medium / large 三档规模，供命令行 ``--preset`` 选择；
未显式指定 users/products/orders 时作为默认值使用。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class DataPreset:
    """单一规模预设：用户数、商品数、订单数。"""

    users: int
    products: int
    orders: int


PRESETS = {
    "small": DataPreset(users=500, products=80, orders=5_000),
    "medium": DataPreset(users=5_000, products=200, orders=50_000),
    "large": DataPreset(users=20_000, products=500, orders=300_000),
}
