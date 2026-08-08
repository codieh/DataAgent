from app.security.sql_policy import inspect_select_sql


def test_select_sql_gets_a_limit():
    result = inspect_select_sql("SELECT id FROM orders", row_limit=50, schema={"tables": [{"name": "orders"}]})

    assert result.passed is True
    assert "LIMIT 50" in result.sql.upper()


def test_write_statement_is_blocked():
    result = inspect_select_sql("DELETE FROM orders", row_limit=50)

    assert result.passed is False
    assert result.code == "blocked_unsafe_sql"


def test_unknown_table_is_blocked():
    result = inspect_select_sql(
        "SELECT id FROM secrets",
        row_limit=50,
        schema={"tables": [{"name": "orders"}]},
    )

    assert result.passed is False
    assert result.code == "blocked_schema_violation"


def test_qualified_select_star_is_blocked():
    result = inspect_select_sql("SELECT o.* FROM orders o", row_limit=50)

    assert result.passed is False
    assert result.code == "blocked_wide_export"
