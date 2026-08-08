"""只读 MySQL 业务数据访问。

驱动调用是阻塞的，因此统一通过 ``asyncio.to_thread`` 放到线程池，避免阻塞
FastAPI 的事件循环。
"""

import asyncio
from typing import Any
from urllib.parse import urlparse

import pymysql

from app.config import get_settings
from app.domain.models import QueryResult


class BusinessDatabase:
    def __init__(self, database_url: str | None = None):
        self.database_url = database_url or get_settings().product_database_url

    def _connect(self, tenant_id: str | None = None):
        settings = get_settings()
        if settings.tenant_database_urls:
            if not tenant_id or tenant_id not in settings.tenant_database_urls:
                raise PermissionError(f"租户未绑定业务数据源：{tenant_id or '<empty>'}")
            database_url = settings.tenant_database_urls[tenant_id]
        else:
            database_url = self.database_url
        if not database_url:
            raise RuntimeError("未配置 DATA_AGENT_PRODUCT_DATABASE_URL 或 DATA_AGENT_TENANT_DATABASE_URLS")
        parsed = urlparse(database_url)
        if parsed.scheme not in {"mysql", "mysql+pymysql"}:
            raise ValueError("product_database_url 必须使用 mysql:// 或 mysql+pymysql://")
        connection = pymysql.connect(
            host=parsed.hostname or "127.0.0.1",
            port=parsed.port or 3306,
            user=parsed.username,
            password=parsed.password,
            database=parsed.path.lstrip("/"),
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            read_timeout=get_settings().sql_timeout_seconds,
            connect_timeout=10,
            autocommit=True,
        )
        with connection.cursor() as cursor:
            # 数据库账号仍必须是只读账号；会话级只读是第二道防线。
            cursor.execute("SET SESSION TRANSACTION READ ONLY")
        return connection

    def _schema_snapshot_sync(self, tenant_id: str | None) -> dict[str, Any]:
        connection = self._connect(tenant_id)
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT table_name AS table_name, table_comment AS table_comment
                       FROM information_schema.tables
                       WHERE table_schema = DATABASE() AND table_type = 'BASE TABLE'
                       ORDER BY table_name"""
                )
                tables = cursor.fetchall()
                for table in tables:
                    # 先保存原始表名，再把返回结构转换为 Agent 使用的字段名。
                    # 不能在 pop("table_name") 后继续读取旧字段，否则会触发 KeyError。
                    table_name = table["table_name"]
                    cursor.execute(
                        """SELECT column_name AS column_name,
                                  data_type AS data_type,
                                  column_type AS column_type,
                                  column_comment AS column_comment,
                                  is_nullable AS is_nullable
                           FROM information_schema.columns
                           WHERE table_schema = DATABASE() AND table_name = %s
                           ORDER BY ordinal_position""",
                        (table_name,),
                    )
                    columns = cursor.fetchall()
                    table["name"] = table.pop("table_name")
                    table["comment"] = table.pop("table_comment") or ""
                    table["columns"] = [
                        {
                            "name": column["column_name"],
                            "data_type": column["data_type"],
                            "column_type": column["column_type"],
                            "comment": column["column_comment"] or "",
                            "nullable": column["is_nullable"] == "YES",
                        }
                        for column in columns
                    ]
                    cursor.execute(
                        """SELECT column_name AS column_name,
                                  referenced_table_name AS referenced_table_name,
                                  referenced_column_name AS referenced_column_name
                           FROM information_schema.key_column_usage
                           WHERE constraint_schema = DATABASE()
                             AND table_name = %s
                             AND referenced_table_name IS NOT NULL
                           ORDER BY ordinal_position""",
                        (table["name"],),
                    )
                    table["foreign_keys"] = [
                        {
                            "column": foreign_key["column_name"],
                            "referred_table": foreign_key["referenced_table_name"],
                            "referred_column": foreign_key["referenced_column_name"],
                        }
                        for foreign_key in cursor.fetchall()
                    ]
            return {"tables": tables}
        finally:
            connection.close()

    async def schema_snapshot(self, tenant_id: str | None = None) -> dict[str, Any]:
        return await asyncio.to_thread(self._schema_snapshot_sync, tenant_id)

    def _execute_sync(self, tenant_id: str | None, sql: str, max_rows: int) -> QueryResult:
        connection = self._connect(tenant_id)
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql)
                columns = [column[0] for column in cursor.description or []]
                rows = cursor.fetchmany(max_rows + 1)
                truncated = len(rows) > max_rows
                rows = rows[:max_rows]
                return QueryResult(
                    columns=columns,
                    rows=[dict(row) for row in rows],
                    row_count=len(rows),
                    truncated=truncated,
                )
        finally:
            connection.close()

    async def execute(self, tenant_id: str | None, sql: str, max_rows: int) -> QueryResult:
        return await asyncio.to_thread(self._execute_sync, tenant_id, sql, max_rows)
