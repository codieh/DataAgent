"""演示数据生成命令行入口。

解析参数、组装 ``GenerationConfig``，按四步流程落地：
1) 重建演示 Schema；2) 写入维度；3) 分批写入订单事实；4) 校验完整性。
安全约束：写入数据库必须显式 ``--reset``，且需配置数据库地址，避免误覆盖。
``--dry-run`` 仅生成并预览维度、不连接数据库。

用法示例：
    python -m scripts.demo_data.generate --preset medium --reset \
        --database-url "mysql+pymysql://user:pwd@host/db"
"""

import argparse
import os
from datetime import date
from pathlib import Path

from scripts.demo_data.generator import GenerationConfig, generate_dimensions
from scripts.demo_data.loader import create_database_engine, load_dimensions, load_facts, reset_schema
from scripts.demo_data.presets import PRESETS
from scripts.demo_data.validate import validate_database


# schema.sql 与入口脚本同目录，用于重建演示表结构
SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def parse_args() -> argparse.Namespace:
    """解析命令行参数：规模/时间范围/种子/批大小，以及 reset/dry-run 开关。"""
    parser = argparse.ArgumentParser(description="生成可重复的电商演示数据并写入 MySQL")
    parser.add_argument("--database-url", default=os.getenv("DATA_AGENT_PRODUCT_DATABASE_URL", ""))
    parser.add_argument("--preset", choices=PRESETS, default="medium")
    parser.add_argument("--users", type=int)
    parser.add_argument("--products", type=int)
    parser.add_argument("--orders", type=int)
    parser.add_argument("--start-date", type=date.fromisoformat, default=date(2024, 1, 1))
    parser.add_argument("--end-date", type=date.fromisoformat, default=date(2025, 12, 31))
    parser.add_argument("--seed", type=int, default=20260706)
    parser.add_argument("--batch-size", type=int, default=1_000)
    # 安全开关：必须显式 --reset 才允许写库，避免误覆盖
    parser.add_argument("--reset", action="store_true", help="删除并重建演示表；不传此参数时不会写库")
    parser.add_argument("--dry-run", action="store_true", help="只生成维度并显示计划，不连接数据库")
    return parser.parse_args()


def main() -> None:
    """入口：组装配置并按四步流程生成/写入/校验演示数据。"""
    args = parse_args()
    preset = PRESETS[args.preset]
    config = GenerationConfig(
        # 命令行显式值优先，否则回退到所选 preset 的默认值
        users=args.users or preset.users,
        products=args.products or preset.products,
        orders=args.orders or preset.orders,
        start_date=args.start_date,
        end_date=args.end_date,
        seed=args.seed,
    )
    print(
        f"生成计划: users={config.users}, products={config.products}, orders={config.orders}, "
        f"range={config.start_date}..{config.end_date}, seed={config.seed}"
    )
    dimensions = generate_dimensions(config)
    if args.dry_run:
        # 仅预览维度规模，不连接数据库
        print(
            f"维度预览: categories={len(dimensions.categories)}, "
            f"products={len(dimensions.products)}, promotions={len(dimensions.promotions)}"
        )
        return
    if not args.reset:
        raise SystemExit("为避免误覆盖数据库，写入时必须显式传入 --reset")
    if not args.database_url:
        raise SystemExit("请通过 --database-url 或 DATA_AGENT_PRODUCT_DATABASE_URL 配置 MySQL")

    engine = create_database_engine(args.database_url)
    try:
        print("1/4 重建演示 Schema")
        reset_schema(engine, SCHEMA_PATH)
        print("2/4 写入用户、商品和业务维度")
        load_dimensions(engine, dimensions)
        print("3/4 分批生成并写入订单事实数据")
        load_facts(engine, config, dimensions, batch_size=args.batch_size)
        print("4/4 校验数据完整性")
        report = validate_database(engine, config)
        for name, count in report.counts.items():
            print(f"  {name}: {count}")
        for name, passed in report.checks.items():
            print(f"  {'PASS' if passed else 'FAIL'} {name}")
        if not report.ok:
            raise SystemExit("数据生成完成，但完整性校验未通过")
        print("演示数据生成完成")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
