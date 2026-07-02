import asyncio
from typing import Any

import sqlglot
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlglot import expressions as exp

from app.config import Settings
from app.domain.errors import InvalidOperationError


class SqlPolicyError(InvalidOperationError):
    pass


class BusinessDatabase:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._engine: Engine | None = None

    @property
    def engine(self) -> Engine:
        if self._engine is None:
            self._engine = create_engine(
                self.settings.product_database_url,
                pool_pre_ping=True,
                pool_size=5,
                max_overflow=5,
                connect_args={"connect_timeout": self.settings.sql_timeout_seconds},
            )
        return self._engine

    async def schema_snapshot(self) -> dict[str, Any]:
        return await asyncio.to_thread(self._schema_snapshot_sync)

    def _schema_snapshot_sync(self) -> dict[str, Any]:
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

    async def execute_select(self, sql: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        safe_sql = validate_select_sql(sql, self.settings.sql_row_limit)
        return await asyncio.wait_for(
            asyncio.to_thread(self._execute_sync, safe_sql),
            timeout=self.settings.sql_timeout_seconds,
        )

    def _execute_sync(self, sql: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        with self.engine.connect() as connection:
            result = connection.execute(text(sql))
            rows = [dict(row._mapping) for row in result.fetchmany(self.settings.sql_row_limit)]
            columns = [
                {"name": key, "label": key, "dataType": _infer_type(rows, key)}
                for key in result.keys()
            ]
            return columns, rows

    async def close(self) -> None:
        if self._engine is not None:
            await asyncio.to_thread(self._engine.dispose)
            self._engine = None


def validate_select_sql(sql: str, row_limit: int) -> str:
    try:
        statements = sqlglot.parse(sql, read="mysql")
    except sqlglot.errors.ParseError as error:
        raise SqlPolicyError(f"SQL 解析失败：{error}") from error
    if len(statements) != 1 or not isinstance(statements[0], exp.Query):
        raise SqlPolicyError("仅允许执行单条 SELECT 查询。")
    statement = statements[0]
    forbidden = (exp.Delete, exp.Update, exp.Insert, exp.Create, exp.Drop, exp.Alter, exp.Command)
    if any(statement.find(node_type) is not None for node_type in forbidden):
        raise SqlPolicyError("查询包含禁止的写入或管理操作。")
    if statement.args.get("limit") is None:
        statement = statement.limit(row_limit)
    return statement.sql(dialect="mysql")


def _infer_type(rows: list[dict[str, Any]], key: str) -> str:
    value = next((row.get(key) for row in rows if row.get(key) is not None), None)
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    return "string"

