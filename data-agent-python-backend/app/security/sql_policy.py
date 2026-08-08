"""SQL 生成结果的安全策略校验。

在把模型生成的 SELECT 语句真正执行前，用 sqlglot 解析为 AST 并逐项做白/黑名单检查，
防止越权、信息泄露与破坏性操作。所有校验聚合成 checks 列表，便于返回详细失败原因。

校验维度（顺序即检查顺序）：
1. 仅允许单条 SELECT（禁止多语句与写入/管理语句）。
2. 禁止访问数据库系统表（information_schema 等）。
3. 禁止调用身份/版本/会话类函数（USER、VERSION、SLEEP 等）及 @@ 系统变量、INTO OUTFILE。
4. 禁止 SELECT * 宽表导出。
5. 表/字段白名单：仅允许引用已召回 schema 中的表与字段（提供 schema 时）。
6. 关联查询必须带 ON/USING 条件（CROSS JOIN 除外）。
7. 禁止直接返回敏感字段明细（聚合统计除外）。
8. 强制行数上限（row_limit）：超限或缺失 LIMIT 时自动改写为 row_limit。

返回结果带 result_mode 区分拦截类型，retryable 标识是否可重试（如缺 schema 时可重试）。
"""

from dataclasses import dataclass, field
from typing import Any

import sqlglot
from sqlglot import expressions as exp


# 禁止调用的函数：暴露身份/版本/会话信息或可用于拒绝服务（SLEEP/BENCHMARK）
_FORBIDDEN_FUNCTIONS = {
    "CURRENT_USER",
    "CURRENT_VERSION",
    "DATABASE",
    "BENCHMARK",
    "GET_LOCK",
    "LOAD_FILE",
    "SESSION_USER",
    "SYSTEM_USER",
    "USER",
    "VERSION",
    "SLEEP",
}
# 禁止直接访问的数据库系统库
_SYSTEM_DATABASES = {"information_schema", "mysql", "performance_schema", "sys"}


@dataclass(frozen=True)
class SqlPolicyResult:
    """单条 SQL 的策略校验结果。"""

    passed: bool
    sql: str = ""
    result_mode: str | None = None
    reason: str = ""
    retryable: bool = False
    checks: list[dict[str, Any]] = field(default_factory=list)


def inspect_select_sql(
    sql: str,
    *,
    row_limit: int,
    schema: dict[str, Any] | None = None,
    sensitive_fields: list[str] | None = None,
) -> SqlPolicyResult:
    """对一条 SQL 语句执行安全策略校验。

    Args:
        sql: 待校验的 SQL 文本（预期为 SELECT）。
        row_limit: 强制行数上限；LIMIT 缺失或超限时将自动改写为该值。
        schema: 可选表结构（召回上下文），提供时启用表/字段白名单校验。
        sensitive_fields: 可选敏感字段名列表，命中且非聚合时拦截。

    Returns:
        SqlPolicyResult：passed 表示通过；未通过时 result_mode/reason 说明拦截类型，
        retryable 指示是否可重试；checks 记录各维度通过情况。
    """
    checks: list[dict[str, Any]] = []
    try:
        statements = sqlglot.parse(sql, read="mysql")
    except sqlglot.errors.ParseError as error:
        # 解析失败通常可重试（如模型偶发生成残缺 SQL）
        return _block("blocked_unsafe_sql", f"SQL 解析失败：{error}", True, checks)
    # 仅允许单条语句且必须是查询（杜绝分号拼接的多语句攻击）
    if len(statements) != 1 or not isinstance(statements[0], exp.Query):
        return _block("blocked_unsafe_sql", "仅允许执行单条 SELECT 查询。", False, checks)
    statement = statements[0]
    # 禁止任何写入/管理类 AST 节点（DELETE/UPDATE/INSERT/CREATE/DROP/ALTER/Command）
    forbidden = (exp.Delete, exp.Update, exp.Insert, exp.Create, exp.Drop, exp.Alter, exp.Command)
    if any(statement.find(node_type) is not None for node_type in forbidden):
        return _block("blocked_unsafe_sql", "查询包含禁止的写入或管理操作。", False, checks)
    checks.append({"name": "select_only", "passed": True})

    # 物理表 = 排除对 CTE（WITH 子句）引用的表，仅检查真实表
    physical_tables = [table for table in statement.find_all(exp.Table) if not _is_cte_reference(statement, table)]
    for table in physical_tables:
        database = (table.db or "").lower()
        if database in _SYSTEM_DATABASES or table.name.lower() in _SYSTEM_DATABASES:
            return _block("blocked_unsafe_sql", "禁止访问数据库系统表。", False, checks)
    checks.append({"name": "system_catalog", "passed": True})

    # 将整条语句大写化，便于做不区分大小写的字符串级禁止项检测
    sql_upper = statement.sql(dialect="mysql").upper()
    # 收集语句中所有函数名（含 sql_name 与 name 两种取法，取并集去空）
    function_names = {
        name
        for function in statement.find_all(exp.Func)
        for name in {function.sql_name().upper(), str(getattr(function, "name", "")).upper()}
        if name
    }
    if (
        function_names & _FORBIDDEN_FUNCTIONS
        or "@@" in sql_upper
        or " INTO OUTFILE " in f" {sql_upper} "
    ):
        return _block(
            "blocked_unsafe_sql",
            "禁止调用数据库身份、版本或会话信息函数。",
            False,
            checks,
        )
    checks.append({"name": "forbidden_functions", "passed": True})

    # 投影列：展开所有 SELECT 的 select 列表
    projections = [projection for select in statement.find_all(exp.Select) for projection in select.selects]
    if any(_is_wildcard_projection(projection) for projection in projections):
        # SELECT * 宽表导出风险高，要求只选必要字段；可重试
        return _block("blocked_wide_export", "禁止使用 SELECT *，请只查询必要字段。", True, checks)
    checks.append({"name": "no_select_star", "passed": True})

    # 表/字段白名单：仅在提供 schema 时启用
    schema_tables = _schema_tables(schema)
    if schema_tables:
        referenced_tables = {table.name.lower() for table in physical_tables}
        unknown_tables = sorted(referenced_tables - set(schema_tables))
        if unknown_tables:
            return _block(
                "blocked_schema_violation",
                f"SQL 使用了未召回或不存在的表：{', '.join(unknown_tables)}。",
                True,
                checks,
            )
        # 别名 -> 真实表名 映射，用于解析带别名的列限定
        alias_to_table = {
            (table.alias_or_name or table.name).lower(): table.name.lower() for table in physical_tables
        }
        # 派生表（子查询）别名，其列不在此 schema 校验范围内
        derived_aliases = {subquery.alias.lower() for subquery in statement.find_all(exp.Subquery) if subquery.alias}
        unknown_columns = _unknown_columns(statement, schema_tables, alias_to_table, derived_aliases)
        if unknown_columns:
            return _block(
                "blocked_schema_violation",
                f"SQL 使用了不存在或未召回的字段：{', '.join(sorted(unknown_columns))}。",
                True,
                checks,
            )
        checks.append({"name": "schema_allowlist", "passed": True})

    # 关联查询必须显式带 ON 或 USING 条件，避免笛卡尔积（CROSS JOIN 除外）
    for join in statement.find_all(exp.Join):
        missing_condition = join.args.get("on") is None and not join.args.get("using")
        if missing_condition and str(join.args.get("kind") or "").upper() != "CROSS":
            return _block("blocked_schema_violation", "关联查询缺少 JOIN 条件。", True, checks)
    checks.append({"name": "join_conditions", "passed": True})

    # 敏感字段检测：命中敏感列且非聚合（COUNT 等）统计时拦截
    sensitive = {item.lower() for item in sensitive_fields or []}
    exposed = set()
    for projection in projections:
        sensitive_columns = {
            column.name.lower()
            for column in projection.find_all(exp.Column)
            if _matches_sensitive(column.name.lower(), sensitive)
        }
        # 允许对敏感字段做 COUNT 聚合，仅禁止返回明细
        if sensitive_columns and projection.find(exp.Count) is None:
            exposed.update(sensitive_columns)
    if exposed:
        return _block(
            "blocked_sensitive_sql",
            f"禁止返回敏感字段明细：{', '.join(sorted(exposed))}。请改为聚合统计。",
            False,
            checks,
        )
    checks.append({"name": "sensitive_fields", "passed": True})

    # 行数上限：LIMIT 缺失或超出 row_limit 时强制改写为 row_limit
    limit = statement.args.get("limit")
    limit_value = _literal_limit(limit)
    if limit_value is None or limit_value > row_limit:
        statement.set("limit", None)
        statement = statement.limit(row_limit)
    checks.append({"name": "row_limit", "passed": True, "maximum": row_limit})
    return SqlPolicyResult(True, statement.sql(dialect="mysql"), checks=checks)


def _schema_tables(schema: dict[str, Any] | None) -> dict[str, set[str]]:
    """把 schema 规整为 {表名小写: {字段名小写集合}} 映射；无 schema 时返回空。"""
    if not schema:
        return {}
    return {
        str(table.get("name", "")).lower(): {
            str(column.get("name", "")).lower() for column in table.get("columns", [])
        }
        for table in schema.get("tables", [])
        if table.get("name")
    }


def _unknown_columns(
    statement: exp.Query,
    schema_tables: dict[str, set[str]],
    alias_to_table: dict[str, str],
    derived_aliases: set[str],
) -> set[str]:
    """找出语句中引用了但不在 schema 白名单内的字段（带限定则按表校验）。"""
    unknown = set()
    # 所有表字段的并集，用于无限定列名的快速判定
    all_columns = set().union(*schema_tables.values()) if schema_tables else set()
    # 投影中的别名（如 SELECT x AS y 中的 y），不视为未知列
    select_aliases = {projection.alias.lower() for projection in statement.selects if projection.alias}
    for column in statement.find_all(exp.Column):
        name = column.name.lower()
        qualifier = (column.table or "").lower()
        # 通配符与 SELECT 别名跳过敏感/白名单校验
        if name == "*" or name in select_aliases:
            continue
        if qualifier:
            # 限定为派生表别名时，其列不在当前白名单范围内，跳过
            if qualifier in derived_aliases:
                continue
            table_name = alias_to_table.get(qualifier, qualifier)
            # 带表限定：仅当该表存在且字段不在该表内时记为未知
            if table_name in schema_tables and name not in schema_tables[table_name]:
                unknown.add(f"{qualifier}.{name}")
        elif name not in all_columns:
            # 无限定列名：只要不在任何表的字段集合中即视为未知
            unknown.add(name)
    return unknown


def _is_wildcard_projection(projection: exp.Expression) -> bool:
    """判断某投影是否为 SELECT *（兼容 `alias.*` 与别名包裹两种形式）。"""
    target = projection.this if isinstance(projection, exp.Alias) else projection
    if isinstance(target, exp.Star):
        return True
    return isinstance(target, exp.Column) and target.name == "*"


def _is_cte_reference(statement: exp.Query, table: exp.Table) -> bool:
    """判断 table 是否指向 WITH 子句定义的 CTE（而非真实物理表）。"""
    cte_names = {cte.alias_or_name.lower() for cte in statement.find_all(exp.CTE)}
    return table.name.lower() in cte_names and not table.db


def _literal_limit(limit: exp.Expression | None) -> int | None:
    """提取 LIMIT 后的整数字面量；非字面量或缺失返回 None。"""
    if limit is None:
        return None
    expression = limit.args.get("expression")
    if isinstance(expression, exp.Literal) and expression.is_int:
        return int(expression.this)
    return None


def _matches_sensitive(name: str, sensitive: set[str]) -> bool:
    """字段名是否命中敏感词：精确相等或包含敏感关键词（子串匹配）。"""
    return any(keyword == name or keyword in name for keyword in sensitive)


def _block(
    mode: str,
    reason: str,
    retryable: bool,
    checks: list[dict[str, Any]],
) -> SqlPolicyResult:
    """构造一条未通过的 SqlPolicyResult（保留已执行过的 checks 便于诊断）。"""
    return SqlPolicyResult(False, result_mode=mode, reason=reason, retryable=retryable, checks=checks)
