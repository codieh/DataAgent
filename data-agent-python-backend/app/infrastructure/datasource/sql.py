"""业务数据库访问适配器（只读、安全、受限）。

封装对公司「产品数据库」的访问，所有查询都被强制为只读 SELECT，并叠加多层
安全与稳定性约束：

- SQL 安全策略校验：委托 ``app.security.inspect_select_sql`` 校验语句是否合法、
  是否为只读、是否包含危险子句（如写操作、多语句等）。不通过则抛出
  ``SqlPolicyError``。
- 只读会话：若配置 ``sql_enforce_read_only_session``，则在连接建立后执行
  ``SET SESSION TRANSACTION READ ONLY``，从数据库层面杜绝写操作。
- 语句超时：通过 ``MAX_EXECUTION_TIME``（MySQL）与连接级 ``read_timeout``/
  ``write_timeout`` 双重限制单条语句耗时，避免慢查询拖垮连接池。
- 行数上限：``execute_select`` 强制 ``row_limit``，防止结果集过大耗尽内存。
- 凭据预警：当检测到使用 ``root`` 账号直连业务库时打印告警，提示应使用
  专用只读账号。

模块中的同步阻塞操作（建连、执行 SQL、取结构）均通过 ``asyncio.to_thread``
放到线程池执行，以保持对外接口为异步、不阻塞事件循环。
"""

import asyncio
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine import make_url

from app.config import Settings
from app.domain.errors import InvalidOperationError
from app.security import inspect_select_sql

logger = logging.getLogger(__name__)


class SqlPolicyError(InvalidOperationError):
    """SQL 安全策略校验未通过时抛出的错误。

    继承自领域层的 ``InvalidOperationError``，用于表示「该 SQL 因违反只读/
    安全策略而被拒绝执行」。``reason`` 字段（来自 ``inspect_select_sql`` 的
    返回）会说明具体的拒绝原因。
    """

    pass


class BusinessDatabase:
    """业务数据库访问入口（只读）。

    负责按需创建并缓存 SQLAlchemy 引擎，并提供「取结构快照」与「执行安全
    SELECT」两类能力。引擎采用懒加载（首次访问 ``engine`` 属性时才创建），
    并通过连接池复用连接。
    """
    def __init__(self, settings: Settings):
        self.settings = settings
        # 引擎懒加载：首次访问 ``engine`` 属性时才真正创建。
        self._engine: Engine | None = None

    @property
    def engine(self) -> Engine:
        """返回（必要时创建）底层 SQLAlchemy 引擎。

        创建时配置连接池与两个连接级事件：
        - ``sql_enforce_read_only_session`` 为真时挂载只读会话钩子。
        - 始终挂载语句超时钩子（基于配置超时换算为毫秒）。
        此外会检测是否使用 ``root`` 账号直连，若是则打告警。
        """
        if self._engine is None:
            self._engine = create_engine(
                self.settings.product_database_url,
                pool_pre_ping=True,  # 取连接前做一次探活，剔除已断开的连接
                pool_size=5,
                max_overflow=5,
                connect_args=mysql_connect_args(self.settings.sql_timeout_seconds),
            )
            if self.settings.sql_enforce_read_only_session:
                event.listen(self._engine, "connect", _set_read_only_session)
            event.listen(
                self._engine,
                "connect",
                lambda connection, record: _set_statement_timeout(
                    connection, record, mysql_statement_timeout_ms(self.settings.sql_timeout_seconds)
                ),
            )
            if (make_url(self.settings.product_database_url).username or "").lower() == "root":
                logger.warning(
                    "product database uses root credentials; configure a dedicated SELECT-only account for production"
                )
        return self._engine

    async def schema_snapshot(self) -> dict[str, Any]:
        """异步获取业务库结构快照（表、字段、外键）。

        委托同步实现 ``_schema_snapshot_sync`` 在线程池中执行，避免阻塞事件循环。
        返回形如 ``{"tables": [{name, columns, foreignKeys}, ...]}`` 的结构。
        """
        return await asyncio.to_thread(self._schema_snapshot_sync)

    def _schema_snapshot_sync(self) -> dict[str, Any]:
        """同步实现：遍历所有表，抽取字段元信息与外键关系。"""
        inspector = inspect(self.engine)
        tables = []
        for table_name in inspector.get_table_names():
            columns = [
                {
                    "name": column["name"],
                    "dataType": str(column["type"]),
                    "nullable": bool(column.get("nullable", True)),
                    "comment": column.get("comment") or "",
                }
                for column in inspector.get_columns(table_name)
            ]
            foreign_keys = [
                {
                    "columns": foreign_key.get("constrained_columns") or [],
                    "referredTable": foreign_key.get("referred_table"),
                    "referredColumns": foreign_key.get("referred_columns") or [],
                }
                for foreign_key in inspector.get_foreign_keys(table_name)
            ]
            tables.append({"name": table_name, "columns": columns, "foreignKeys": foreign_keys})
        return {"tables": tables}

    async def execute_select(
        self, sql: str, *, row_limit: int | None = None
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """执行一条只读 SELECT 查询，返回 ``(columns, rows)``。

        流程：先用 ``validate_select_sql`` 做安全策略校验并归一化（含行数上限），
        再在线程池中执行；并用 ``asyncio.wait_for`` 在「配置超时 + 2 秒」的
        整体预算内收口，防止异常情况下永久挂起。
        """
        effective_limit = row_limit or self.settings.sql_row_limit
        safe_sql = validate_select_sql(sql, effective_limit)
        return await asyncio.wait_for(
            asyncio.to_thread(self._execute_sync, safe_sql, effective_limit),
            timeout=self.settings.sql_timeout_seconds + 2,
        )

    def _execute_sync(self, sql: str, row_limit: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """同步执行 SQL，最多取 ``row_limit`` 行，并推断列类型。"""
        with self.engine.connect() as connection:
            result = connection.execute(text(sql))
            # 只取前 row_limit 行，避免大结果集一次性载入内存
            rows = [dict(row._mapping) for row in result.fetchmany(row_limit)]
            columns = [
                {"name": key, "label": key, "dataType": _infer_type(rows, key)}
                for key in result.keys()
            ]
            return columns, rows

    async def close(self) -> None:
        """释放引擎与连接池，并清空缓存以便下次重新创建。"""
        if self._engine is not None:
            await asyncio.to_thread(self._engine.dispose)
            self._engine = None


def validate_select_sql(sql: str, row_limit: int) -> str:
    """对 SQL 做安全策略校验，返回归一化后的安全 SQL。

    委托 ``app.security.inspect_select_sql`` 完成校验；若不通过则抛出
    ``SqlPolicyError``，其 ``reason`` 描述具体拒绝原因。``row_limit`` 会回传给
    策略校验器用于约束返回行数。
    """
    result = inspect_select_sql(sql, row_limit=row_limit)
    if not result.passed:
        raise SqlPolicyError(result.reason)
    return result.sql


def _infer_type(rows: list[dict[str, Any]], key: str) -> str:
    """根据已有行数据推断某列的逻辑类型，供前端展示使用。

    取该列第一个非空值判断其 Python 类型，映射为 ``boolean/integer/number/
    datetime/date/string`` 之一；无数据时回退为 ``string``。
    """
    value = next((row.get(key) for row in rows if row.get(key) is not None), None)
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, (float, Decimal)):
        return "number"
    if isinstance(value, datetime):
        return "datetime"
    if isinstance(value, date):
        return "date"
    return "string"


def _set_read_only_session(dbapi_connection, _connection_record) -> None:
    """连接建立钩子：将该连接所在会话置为只读事务，从数据库层禁用写操作。"""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("SET SESSION TRANSACTION READ ONLY")
    finally:
        cursor.close()


def mysql_connect_args(timeout_seconds: int) -> dict[str, int]:
    """构造 MySQL 驱动连接参数，设置连接/读写超时（秒）。

    ``read_timeout``/``write_timeout`` 比 ``connect_timeout`` 多留 1 秒余量，
    避免网络抖动被误判为连接失败；所有值下限取 1 防止非法 0 值。
    """
    driver_timeout = max(1, timeout_seconds + 1)
    return {
        "connect_timeout": max(1, timeout_seconds),
        "read_timeout": driver_timeout,
        "write_timeout": driver_timeout,
    }


def mysql_statement_timeout_ms(timeout_seconds: int) -> int:
    """将秒级语句超时换算为毫秒，供 MySQL ``MAX_EXECUTION_TIME`` 使用。"""
    return max(1, timeout_seconds) * 1000


def _set_statement_timeout(dbapi_connection, _connection_record, timeout_ms: int) -> None:
    """连接建立钩子：为该连接设置单条语句的最大执行时间（毫秒）。"""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute(f"SET SESSION MAX_EXECUTION_TIME = {int(timeout_ms)}")
    finally:
        cursor.close()
