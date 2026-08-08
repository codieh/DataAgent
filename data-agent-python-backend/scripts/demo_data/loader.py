"""把生成的演示数据写入 MySQL。

负责建立引擎、重置（重建）演示表结构、批量写入维度与事实数据。所有写入均放在
事务块中，事实数据按 ``batch_size`` 分批 flush，控制单次提交的内存占用与锁时长。
"""

from pathlib import Path

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.sql.elements import TextClause

from scripts.demo_data.generator import Dimensions, GenerationConfig, iter_order_bundles


# (表名, Dimensions 上的对应属性名) 映射，用于批量写入四类维度表
DIMENSION_TABLES = (
    ("categories", "categories"),
    ("products", "products"),
    ("users", "users"),
    ("promotions", "promotions"),
)


def create_database_engine(database_url: str) -> Engine:
    """创建带连接健康检查的数据库引擎。"""
    return create_engine(database_url, pool_pre_ping=True)


def reset_schema(engine: Engine, schema_path: Path) -> None:
    """按 schema.sql 重建演示表：按分号切分语句，跳过空行与注释（``--`` 开头）。"""
    statements = [statement.strip() for statement in schema_path.read_text(encoding="utf-8").split(";")]
    with engine.begin() as connection:
        for statement in statements:
            # 跳过空语句与 SQL 注释，避免执行无意义的片段
            if statement and not statement.startswith("--"):
                connection.exec_driver_sql(statement)


def load_dimensions(engine: Engine, dimensions: Dimensions) -> None:
    """写入四类维度表（类目/商品/用户/促销）。"""
    with engine.begin() as connection:
        for table, attribute in DIMENSION_TABLES:
            rows = getattr(dimensions, attribute)
            if rows:
                # 以首行推断列名，使用参数化批量插入
                connection.execute(_insert_statement(table, rows[0]), rows)


def load_facts(
    engine: Engine,
    config: GenerationConfig,
    dimensions: Dimensions,
    *,
    batch_size: int = 1_000,
) -> None:
    """惰性消费订单流并分批写入事实表（orders/order_items/refunds）。"""
    batches = {"orders": [], "order_items": [], "refunds": []}
    for bundle in iter_order_bundles(config, dimensions):
        batches["orders"].append(bundle.order)
        batches["order_items"].extend(bundle.items)
        if bundle.refund:
            batches["refunds"].append(bundle.refund)
        # 订单达到批大小即落库，避免一次性堆积过多行
        if len(batches["orders"]) >= batch_size:
            _flush(engine, batches)
    _flush(engine, batches)


def _flush(engine: Engine, batches: dict[str, list[dict]]) -> None:
    """把当前批次写入三张事实表并清空缓冲（空批次直接返回）。"""
    if not batches["orders"]:
        return
    with engine.begin() as connection:
        for table in ("orders", "order_items", "refunds"):
            rows = batches[table]
            if rows:
                connection.execute(_insert_statement(table, rows[0]), rows)
                rows.clear()


def _insert_statement(table: str, sample: dict) -> TextClause:
    """根据样本行构造参数化 INSERT 语句（列名来自样本键，值用命名占位符）。"""
    columns = list(sample)
    column_sql = ", ".join(columns)
    value_sql = ", ".join(f":{column}" for column in columns)
    return text(f"INSERT INTO {table} ({column_sql}) VALUES ({value_sql})")
