"""测试 SQL 安全策略与约束。

覆盖：自动补 LIMIT、拒绝非 SELECT（DELETE/UPDATE/DROP/多语句）、收紧过大 LIMIT、
确定性 SQL 策略分类（宽表导出/敏感字段/越权表/不安全 SQL 等）、敏感字段聚合的放行，
以及 MySQL 连接/语句超时的推导。
"""

import pytest

from app.infrastructure.datasource.sql import (
    SqlPolicyError,
    mysql_connect_args,
    mysql_statement_timeout_ms,
    validate_select_sql,
)
from app.security import inspect_select_sql


# 用于策略校验的示例 schema：orders / users 两张表，email 视为敏感字段
SCHEMA = {
    "tables": [
        {
            "name": "orders",
            "columns": [
                {"name": "id"},
                {"name": "user_id"},
                {"name": "total_amount"},
                {"name": "status"},
            ],
        },
        {
            "name": "users",
            "columns": [{"name": "id"}, {"name": "email"}, {"name": "name"}],
        },
    ]
}


def test_adds_limit_to_select() -> None:
    """验证无 LIMIT 的 SELECT 会被自动追加行数限制（LIMIT 200）。"""
    sql = validate_select_sql("SELECT id FROM orders", 200)
    assert "LIMIT 200" in sql.upper()


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM orders",  # 写操作
        "UPDATE orders SET status = 'cancelled'",  # 写操作
        "DROP TABLE orders",  # DDL
        "SELECT 1; SELECT 2",  # 多语句
    ],
)
def test_rejects_unsafe_sql(sql: str) -> None:
    # 任何非只读 SELECT 都应被拒绝
    with pytest.raises(SqlPolicyError):
        validate_select_sql(sql, 200)


def test_caps_existing_limit() -> None:
    """验证已有的超限 LIMIT 会被收紧到策略上限（200），且仍判定通过。"""
    result = inspect_select_sql("SELECT id FROM orders LIMIT 100000", row_limit=200, schema=SCHEMA)

    assert result.passed is True
    assert "LIMIT 200" in result.sql.upper()


@pytest.mark.parametrize(
    ("sql", "mode"),
    [
        ("SELECT * FROM orders", "blocked_wide_export"),  # 宽表全列导出
        ("SELECT password FROM users", "blocked_schema_violation"),  # 越权字段
        ("SELECT id FROM secret_orders", "blocked_schema_violation"),  # 越权表
        ("SELECT email FROM users LIMIT 10", "blocked_sensitive_sql"),  # 敏感字段明文
        ("SELECT VERSION()", "blocked_unsafe_sql"),  # 不安全函数
        ("SELECT SLEEP(10)", "blocked_unsafe_sql"),  # 危险函数
        ("SELECT orders.id FROM orders JOIN users", "blocked_schema_violation"),  # 越权 JOIN
        ("SELECT id FROM (SELECT * FROM orders) AS scoped", "blocked_wide_export"),  # 子查询绕宽表
        ("SELECT GROUP_CONCAT(email) FROM users", "blocked_sensitive_sql"),  # 敏感字段聚合并行
    ],
)
def test_enforces_deterministic_sql_policy(sql: str, mode: str) -> None:
    """验证各类违规 SQL 被确定性地拦截，并返回预期的拦截模式（result_mode）。"""
    result = inspect_select_sql(sql, row_limit=200, schema=SCHEMA, sensitive_fields=["email"])

    assert result.passed is False
    assert result.result_mode == mode


def test_allows_sensitive_field_aggregation() -> None:
    """验证敏感字段的聚合统计（如 COUNT(email)）被放行，而非明文列出。"""
    result = inspect_select_sql(
        "SELECT COUNT(email) AS user_count FROM users",
        row_limit=200,
        schema=SCHEMA,
        sensitive_fields=["email"],
    )

    assert result.passed is True


def test_mysql_driver_and_server_timeouts_are_derived_from_sql_timeout() -> None:
    # 连接超时等于 SQL 超时，读写超时略留余量（+1 秒）
    assert mysql_connect_args(10) == {"connect_timeout": 10, "read_timeout": 11, "write_timeout": 11}
    # 语句超时以毫秒为单位
    assert mysql_statement_timeout_ms(10) == 10_000
