import pytest

from app.infrastructure.datasource.sql import SqlPolicyError, validate_select_sql


def test_adds_limit_to_select() -> None:
    sql = validate_select_sql("SELECT id FROM orders", 200)
    assert "LIMIT 200" in sql.upper()


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM orders",
        "UPDATE orders SET status = 'cancelled'",
        "DROP TABLE orders",
        "SELECT 1; SELECT 2",
    ],
)
def test_rejects_unsafe_sql(sql: str) -> None:
    with pytest.raises(SqlPolicyError):
        validate_select_sql(sql, 200)
