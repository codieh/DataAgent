"""确定性 SQL 安全校验。"""

from dataclasses import dataclass, field
from typing import Any

import sqlglot
from sqlglot import expressions as exp


@dataclass(frozen=True, slots=True)
class PolicyResult:
    passed: bool
    sql: str
    code: str | None = None
    reason: str | None = None
    retryable: bool = False
    checks: list[dict[str, Any]] = field(default_factory=list)


_FORBIDDEN_FUNCTIONS = {"USER", "CURRENT_USER", "SESSION_USER", "SYSTEM_USER", "VERSION", "DATABASE", "SLEEP", "BENCHMARK"}
_SYSTEM_DATABASES = {"information_schema", "mysql", "performance_schema", "sys"}


def inspect_select_sql(
    sql: str,
    *,
    row_limit: int,
    schema: dict[str, Any] | None = None,
    sensitive_fields: list[str] | None = None,
) -> PolicyResult:
    checks: list[dict[str, Any]] = []
    try:
        statements = sqlglot.parse(sql, read="mysql")
    except sqlglot.errors.ParseError as error:
        return _blocked("blocked_unsafe_sql", f"SQL 解析失败：{error}", True, checks)
    if len(statements) != 1 or not isinstance(statements[0], exp.Query):
        return _blocked("blocked_unsafe_sql", "仅允许执行单条 SELECT 查询。", False, checks)
    statement = statements[0]
    forbidden_nodes = (exp.Delete, exp.Update, exp.Insert, exp.Create, exp.Drop, exp.Alter, exp.Command)
    if any(statement.find(node_type) is not None for node_type in forbidden_nodes):
        return _blocked("blocked_unsafe_sql", "查询包含禁止的写入或管理操作。", False, checks)
    checks.append({"name": "select_only", "passed": True})

    physical_tables = list(statement.find_all(exp.Table))
    if any((table.db or "").lower() in _SYSTEM_DATABASES or table.name.lower() in _SYSTEM_DATABASES for table in physical_tables):
        return _blocked("blocked_unsafe_sql", "禁止访问数据库系统表。", False, checks)
    checks.append({"name": "system_catalog", "passed": True})

    function_names = {
        name
        for function in statement.find_all(exp.Func)
        for name in {function.sql_name().upper(), str(getattr(function, "name", "")).upper()}
        if name
    }
    rendered = statement.sql(dialect="mysql").upper()
    if function_names & _FORBIDDEN_FUNCTIONS or "@@" in rendered or "INTO OUTFILE" in rendered:
        return _blocked("blocked_unsafe_sql", "禁止调用身份、版本、会话或文件导出相关函数。", False, checks)
    checks.append({"name": "forbidden_functions", "passed": True})

    projections = [projection for select in statement.find_all(exp.Select) for projection in select.selects]
    if any(
        isinstance(projection, exp.Star)
        or (isinstance(projection, exp.Column) and isinstance(projection.this, exp.Star))
        for projection in projections
    ):
        return _blocked("blocked_wide_export", "禁止使用 SELECT *，请只查询必要字段。", True, checks)
    checks.append({"name": "no_select_star", "passed": True})

    allowed_tables = {str(table.get("name", "")).lower() for table in (schema or {}).get("tables", [])}
    if allowed_tables:
        referenced = {table.name.lower() for table in physical_tables}
        unknown = sorted(referenced - allowed_tables)
        if unknown:
            return _blocked("blocked_schema_violation", f"SQL 使用了未召回的表：{', '.join(unknown)}。", True, checks)
    checks.append({"name": "schema_allowlist", "passed": True})

    for join in statement.find_all(exp.Join):
        if join.args.get("on") is None and not join.args.get("using") and str(join.args.get("kind") or "").upper() != "CROSS":
            return _blocked("blocked_schema_violation", "关联查询缺少 JOIN 条件。", True, checks)
    checks.append({"name": "join_conditions", "passed": True})

    sensitive = {field.lower() for field in (sensitive_fields or [])}
    referenced_columns = {column.name.lower() for column in statement.find_all(exp.Column)}
    if sensitive & referenced_columns:
        return _blocked("blocked_sensitive_sql", "查询包含受保护的敏感字段。", False, checks)
    checks.append({"name": "sensitive_fields", "passed": True})

    limit = statement.args.get("limit")
    if limit is None or not isinstance(limit.expression, exp.Literal) or int(limit.expression.this) > row_limit:
        statement = statement.limit(row_limit)
    checks.append({"name": "row_limit", "passed": True, "row_limit": row_limit})
    return PolicyResult(True, statement.sql(dialect="mysql"), checks=checks)


def _blocked(code: str, reason: str, retryable: bool, checks: list[dict[str, Any]]) -> PolicyResult:
    checks.append({"name": code, "passed": False, "reason": reason})
    return PolicyResult(False, "", code, reason, retryable, checks)
