"""控制面 SQLite 持久化。

控制面只保存租户、会话、运行、工具轨迹、目标和结果元数据。完整结果由
``ResultStore`` 保存到文件，业务销售数据仍然由 MySQL 负责。
"""

import json
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

import aiosqlite

from app.config import get_settings
from app.domain.errors import AppError, ResourceNotFoundError
from app.domain.models import Goal, TenantContext

_SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS tenants (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS users (
    id TEXT NOT NULL,
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, id)
);
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    title TEXT,
    sdk_session_id TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id, user_id) REFERENCES users(tenant_id, id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    question TEXT NOT NULL,
    result_mode TEXT,
    error TEXT,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    run_id TEXT REFERENCES runs(id) ON DELETE SET NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS tool_calls (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    tool_name TEXT NOT NULL,
    tool_use_id TEXT,
    input_json TEXT NOT NULL,
    output_json TEXT,
    status TEXT NOT NULL,
    error TEXT,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS analysis_goals (
    run_id TEXT PRIMARY KEY REFERENCES runs(id) ON DELETE CASCADE,
    tenant_id TEXT NOT NULL,
    goal_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS result_sets (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    file_path TEXT NOT NULL,
    columns_json TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    truncated INTEGER NOT NULL,
    summary TEXT,
    verification_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    file_path TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS memories (
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    content TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, user_id),
    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    tool_name TEXT NOT NULL,
    status TEXT NOT NULL,
    reason TEXT NOT NULL,
    decision TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    decided_at TEXT,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS run_events (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL,
    type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(run_id, seq),
    FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_runs_tenant_conversation ON runs(tenant_id, conversation_id, started_at);
CREATE INDEX IF NOT EXISTS idx_messages_tenant_conversation ON messages(tenant_id, conversation_id, created_at);
CREATE INDEX IF NOT EXISTS idx_events_run_seq ON run_events(run_id, seq);
"""


def _sqlite_path(database_url: str) -> Path:
    match = re.match(r"sqlite\+aiosqlite:///([^?]+)", database_url)
    if not match:
        raise ValueError("control_database_url 必须使用 sqlite+aiosqlite:/// URL")
    path = Path(match.group(1))
    if not path.is_absolute():
        path = Path.cwd() / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


class ControlDatabase:
    def __init__(self, database_url: str | None = None):
        self.path = _sqlite_path(database_url or get_settings().control_database_url)

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[aiosqlite.Connection]:
        connection = await aiosqlite.connect(self.path)
        connection.row_factory = aiosqlite.Row
        await connection.execute("PRAGMA foreign_keys=ON")
        await connection.execute("PRAGMA busy_timeout=5000")
        try:
            yield connection
        finally:
            await connection.close()

    async def initialize(self) -> None:
        async with self.connect() as connection:
            # WAL 允许 SSE 读事件时，后台运行继续写入工具轨迹和结果元数据。
            await connection.execute("PRAGMA journal_mode=WAL")
            await connection.executescript(_SCHEMA)
            # 将旧版本已经生成的 SQL 结果补登记为产物，避免升级后出现两套历史视图。
            cursor = await connection.execute(
                """SELECT rs.id, rs.tenant_id, rs.run_id, rs.file_path,
                          rs.columns_json, rs.row_count, rs.truncated, rs.created_at
                   FROM result_sets rs
                   WHERE NOT EXISTS (SELECT 1 FROM artifacts a WHERE a.id = rs.id)"""
            )
            legacy_results = await cursor.fetchall()
            for result in legacy_results:
                await connection.execute(
                    """INSERT INTO artifacts
                       (id, tenant_id, run_id, kind, file_path, metadata_json, created_at)
                       VALUES (?, ?, ?, 'sql_result', ?, ?, ?)""",
                    (
                        result["id"],
                        result["tenant_id"],
                        result["run_id"],
                        result["file_path"],
                        json.dumps(
                            {
                                "artifact_ref": result["id"],
                                "columns": json.loads(result["columns_json"]),
                                "row_count": result["row_count"],
                                "truncated": bool(result["truncated"]),
                                "legacy_backfill": True,
                            },
                            ensure_ascii=False,
                        ),
                        result["created_at"],
                    ),
                )
            await connection.commit()

    async def ensure_tenant(self, tenant_id: str, user_id: str) -> None:
        async with self.connect() as connection:
            await connection.execute(
                "INSERT INTO tenants(id, name) VALUES (?, ?) ON CONFLICT(id) DO NOTHING",
                (tenant_id, tenant_id),
            )
            await connection.execute(
                "INSERT INTO users(id, tenant_id) VALUES (?, ?) ON CONFLICT(tenant_id, id) DO NOTHING",
                (user_id, tenant_id),
            )
            await connection.commit()

    async def create_conversation(self, context: TenantContext, title: str | None = None) -> None:
        await self.ensure_tenant(context.tenant_id, context.user_id)
        async with self.connect() as connection:
            await connection.execute(
                """INSERT INTO conversations(id, tenant_id, user_id, title)
                   VALUES (?, ?, ?, ?)""",
                (context.conversation_id, context.tenant_id, context.user_id, title),
            )
            await connection.commit()

    async def get_conversation(self, tenant_id: str, conversation_id: str) -> dict[str, Any] | None:
        async with self.connect() as connection:
            cursor = await connection.execute(
                "SELECT * FROM conversations WHERE id=? AND tenant_id=?",
                (conversation_id, tenant_id),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def list_conversations(self, tenant_id: str, user_id: str, limit: int = 100) -> list[dict[str, Any]]:
        bounded_limit = min(max(limit, 1), 200)
        async with self.connect() as connection:
            cursor = await connection.execute(
                """SELECT id, title, sdk_session_id, created_at, updated_at
                   FROM conversations
                   WHERE tenant_id=? AND user_id=?
                   ORDER BY updated_at DESC, created_at DESC LIMIT ?""",
                (tenant_id, user_id, bounded_limit),
            )
            return [dict(row) for row in await cursor.fetchall()]

    async def set_sdk_session(self, context: TenantContext, session_id: str) -> None:
        async with self.connect() as connection:
            await connection.execute(
                "UPDATE conversations SET sdk_session_id=?, updated_at=CURRENT_TIMESTAMP WHERE id=? AND tenant_id=?",
                (session_id, context.conversation_id, context.tenant_id),
            )
            await connection.commit()

    async def create_run(self, context: TenantContext, question: str) -> None:
        async with self.connect() as connection:
            cursor = await connection.execute(
                """SELECT id FROM runs
                   WHERE tenant_id=? AND conversation_id=?
                     AND status IN ('running', 'waiting_review')
                   LIMIT 1""",
                (context.tenant_id, context.conversation_id),
            )
            active_run = await cursor.fetchone()
            if active_run:
                raise AppError("run_conflict", f"会话已有运行中的任务：{active_run[0]}")
            await connection.execute(
                """INSERT INTO runs(id, tenant_id, conversation_id, status, question)
                   VALUES (?, ?, ?, 'running', ?)""",
                (context.run_id, context.tenant_id, context.conversation_id, question),
            )
            await connection.execute(
                """INSERT INTO messages(id, tenant_id, conversation_id, run_id, role, content)
                   VALUES (?, ?, ?, ?, 'user', ?)""",
                (f"msg-{context.run_id}", context.tenant_id, context.conversation_id, context.run_id, question),
            )
            await connection.commit()

    async def get_run(self, tenant_id: str, run_id: str) -> dict[str, Any] | None:
        async with self.connect() as connection:
            cursor = await connection.execute("SELECT * FROM runs WHERE id=? AND tenant_id=?", (run_id, tenant_id))
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def list_tool_calls(self, tenant_id: str, run_id: str) -> list[dict[str, Any]]:
        async with self.connect() as connection:
            cursor = await connection.execute(
                """SELECT * FROM tool_calls
                   WHERE tenant_id=? AND run_id=? ORDER BY started_at, rowid""",
                (tenant_id, run_id),
            )
            rows = await cursor.fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["input"] = json.loads(item.pop("input_json"))
            output_json = item.pop("output_json")
            item["output"] = json.loads(output_json) if output_json else None
            result.append(item)
        return result

    async def list_messages(self, tenant_id: str, user_id: str, conversation_id: str) -> list[dict[str, Any]]:
        async with self.connect() as connection:
            cursor = await connection.execute(
                """SELECT m.id, m.run_id, m.role, m.content, m.created_at
                   FROM messages m JOIN conversations c ON c.id=m.conversation_id
                   WHERE m.tenant_id=? AND c.user_id=? AND m.conversation_id=?
                   ORDER BY m.created_at, m.rowid""",
                (tenant_id, user_id, conversation_id),
            )
            return [dict(row) for row in await cursor.fetchall()]

    async def set_run_status(
        self,
        context: TenantContext,
        status: str,
        *,
        result_mode: str | None = None,
        error: str | None = None,
    ) -> None:
        async with self.connect() as connection:
            await connection.execute(
                """UPDATE runs SET status=?, result_mode=?, error=?,
                   completed_at=CASE WHEN ? IN ('completed', 'failed', 'cancelled')
                       THEN CURRENT_TIMESTAMP ELSE completed_at END
                   WHERE id=? AND tenant_id=?""",
                (status, result_mode, error, status, context.run_id, context.tenant_id),
            )
            await connection.commit()

    async def append_message(self, context: TenantContext, role: str, content: str) -> None:
        async with self.connect() as connection:
            await connection.execute(
                """INSERT INTO messages(id, tenant_id, conversation_id, run_id, role, content)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (f"msg-{uuid4().hex}", context.tenant_id, context.conversation_id, context.run_id, role, content),
            )
            await connection.commit()

    async def append_tool_call(
        self,
        context: TenantContext,
        tool_call_id: str,
        tool_name: str,
        input_data: dict[str, Any],
        output_data: dict[str, Any] | None,
        status: str,
        error: str | None = None,
    ) -> None:
        async with self.connect() as connection:
            await connection.execute(
                """INSERT INTO tool_calls
                   (id, tenant_id, conversation_id, run_id, tool_name, tool_use_id,
                    input_json, output_json, status, error, started_at, completed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP,
                           CASE WHEN ? IN ('completed', 'failed', 'blocked')
                                THEN CURRENT_TIMESTAMP ELSE NULL END)
                   ON CONFLICT(id) DO UPDATE SET
                     input_json=excluded.input_json,
                     output_json=excluded.output_json,
                     status=excluded.status,
                     error=excluded.error,
                     completed_at=CASE WHEN excluded.status IN ('completed', 'failed', 'blocked')
                                      THEN CURRENT_TIMESTAMP ELSE tool_calls.completed_at END""",
                (
                    f"tool-{context.run_id}-{tool_call_id}",
                    context.tenant_id,
                    context.conversation_id,
                    context.run_id,
                    tool_name,
                    tool_call_id,
                    json.dumps(input_data, ensure_ascii=False, default=str),
                    json.dumps(output_data, ensure_ascii=False, default=str) if output_data is not None else None,
                    status,
                    error,
                    status,
                ),
            )
            await connection.commit()

    async def save_goal(self, context: TenantContext, goal: Goal) -> None:
        async with self.connect() as connection:
            await connection.execute(
                """INSERT OR REPLACE INTO analysis_goals(run_id, tenant_id, goal_json)
                   VALUES (?, ?, ?)""",
                (context.run_id, context.tenant_id, json.dumps(goal.as_dict(), ensure_ascii=False)),
            )
            await connection.commit()

    async def get_goal(self, context: TenantContext) -> Goal | None:
        async with self.connect() as connection:
            cursor = await connection.execute(
                "SELECT goal_json FROM analysis_goals WHERE run_id=? AND tenant_id=?",
                (context.run_id, context.tenant_id),
            )
            row = await cursor.fetchone()
        if not row:
            return None
        data = json.loads(row[0])
        return Goal(**data)

    async def save_result_set(
        self,
        context: TenantContext,
        result_id: str,
        file_path: str,
        columns: list[str],
        row_count: int,
        truncated: bool,
        summary: str,
        verification: dict[str, Any],
    ) -> None:
        async with self.connect() as connection:
            await connection.execute(
                """INSERT INTO result_sets
                   (id, tenant_id, conversation_id, run_id, file_path, columns_json,
                    row_count, truncated, summary, verification_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    result_id,
                    context.tenant_id,
                    context.conversation_id,
                    context.run_id,
                    file_path,
                    json.dumps(columns, ensure_ascii=False),
                    row_count,
                    int(truncated),
                    summary,
                    json.dumps(verification, ensure_ascii=False),
                ),
            )
            await connection.commit()

    async def save_artifact(
        self,
        context: TenantContext,
        artifact_id: str,
        kind: str,
        file_path: str,
        metadata: dict[str, Any],
    ) -> None:
        async with self.connect() as connection:
            await connection.execute(
                """INSERT INTO artifacts(id, tenant_id, run_id, kind, file_path, metadata_json)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    artifact_id,
                    context.tenant_id,
                    context.run_id,
                    kind,
                    file_path,
                    json.dumps(metadata, ensure_ascii=False, default=str),
                ),
            )
            await connection.commit()

    async def get_result_set(self, context: TenantContext, result_id: str) -> dict[str, Any]:
        async with self.connect() as connection:
            cursor = await connection.execute(
                "SELECT * FROM result_sets WHERE id=? AND tenant_id=? AND conversation_id=?",
                (result_id, context.tenant_id, context.conversation_id),
            )
            row = await cursor.fetchone()
        if not row:
            raise ResourceNotFoundError("result_set", result_id)
        return dict(row)

    async def get_result_set_by_id(self, tenant_id: str, conversation_id: str, result_id: str) -> dict[str, Any]:
        async with self.connect() as connection:
            cursor = await connection.execute(
                "SELECT * FROM result_sets WHERE id=? AND tenant_id=? AND conversation_id=?",
                (result_id, tenant_id, conversation_id),
            )
            row = await cursor.fetchone()
        if not row:
            raise ResourceNotFoundError("result_set", result_id)
        return dict(row)

    async def append_event(self, context: TenantContext, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        event_id = f"evt-{uuid4().hex}"
        async with self.connect() as connection:
            await connection.execute("BEGIN IMMEDIATE")
            cursor = await connection.execute(
                "SELECT COALESCE(MAX(seq), 0) + 1 FROM run_events WHERE run_id=?",
                (context.run_id,),
            )
            seq = int((await cursor.fetchone())[0])
            await connection.execute(
                """INSERT INTO run_events
                   (id, tenant_id, conversation_id, run_id, seq, type, payload_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    event_id,
                    context.tenant_id,
                    context.conversation_id,
                    context.run_id,
                    seq,
                    event_type,
                    json.dumps(payload, ensure_ascii=False, default=str),
                ),
            )
            await connection.commit()
        return {"event_id": event_id, "seq": seq, "type": event_type, "payload": payload}

    async def list_events(self, tenant_id: str, run_id: str, after_seq: int = 0) -> list[dict[str, Any]]:
        async with self.connect() as connection:
            cursor = await connection.execute(
                """SELECT id, seq, type, payload_json, created_at
                   FROM run_events WHERE run_id=? AND tenant_id=? AND seq>?
                   ORDER BY seq""",
                (run_id, tenant_id, after_seq),
            )
            rows = await cursor.fetchall()
        return [
            {
                "event_id": row[0],
                "seq": row[1],
                "type": row[2],
                "payload": json.loads(row[3]),
                "created_at": row[4],
            }
            for row in rows
        ]

    async def get_memory(self, tenant_id: str, user_id: str) -> str:
        async with self.connect() as connection:
            cursor = await connection.execute(
                "SELECT content FROM memories WHERE tenant_id=? AND user_id=?",
                (tenant_id, user_id),
            )
            row = await cursor.fetchone()
        return str(row[0]) if row else ""

    async def search_history(
        self,
        tenant_id: str,
        user_id: str,
        conversation_id: str,
        query: str,
        scope: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        """在控制面执行租户隔离的轻量历史搜索。

        查询条件使用参数绑定；历史文本不会拼接进 SQL，避免搜索词改变查询语义。
        """
        keyword = f"%{query.strip()}%"
        bounded_limit = min(max(limit, 1), 50)
        rows: list[dict[str, Any]] = []
        async with self.connect() as connection:
            if scope in {"auto", "current", "messages"}:
                conversation_clause = "AND m.conversation_id=?" if scope == "current" else ""
                params: list[Any] = [tenant_id, user_id]
                if conversation_clause:
                    params.append(conversation_id)
                params.extend([keyword, keyword, bounded_limit])
                cursor = await connection.execute(
                    f"""SELECT m.id, m.conversation_id, m.run_id, m.role, m.content, m.created_at
                        FROM messages m JOIN conversations c ON c.id=m.conversation_id
                        WHERE m.tenant_id=? AND c.user_id=? {conversation_clause}
                          AND (m.content LIKE ? OR c.title LIKE ?)
                        ORDER BY m.created_at DESC LIMIT ?""",
                    params,
                )
                rows.extend({"type": "message", **dict(row)} for row in await cursor.fetchall())
            if scope in {"auto", "current", "results"}:
                conversation_clause = "AND r.conversation_id=?" if scope == "current" else ""
                params = [tenant_id, user_id]
                if conversation_clause:
                    params.append(conversation_id)
                params.extend([keyword, keyword, keyword, bounded_limit])
                cursor = await connection.execute(
                    f"""SELECT r.id, r.conversation_id, r.question, r.result_mode, r.status,
                               r.started_at, rs.id AS result_id, rs.summary, rs.row_count
                        FROM runs r JOIN conversations c ON c.id=r.conversation_id
                        LEFT JOIN result_sets rs ON rs.run_id=r.id
                        WHERE r.tenant_id=? AND c.user_id=? {conversation_clause}
                          AND (r.question LIKE ? OR r.result_mode LIKE ? OR rs.summary LIKE ?)
                        ORDER BY r.started_at DESC LIMIT ?""",
                    params,
                )
                rows.extend({"type": "run", **dict(row)} for row in await cursor.fetchall())
        return rows[:bounded_limit]

    async def read_message_context(
        self,
        tenant_id: str,
        user_id: str,
        conversation_id: str,
        message_id: str,
        before: int,
        after: int,
    ) -> list[dict[str, Any]]:
        async with self.connect() as connection:
            cursor = await connection.execute(
                """SELECT m.id, m.role, m.content, m.created_at
                   FROM messages m JOIN conversations c ON c.id=m.conversation_id
                   WHERE m.id=? AND m.tenant_id=? AND c.user_id=? AND m.conversation_id=?""",
                (message_id, tenant_id, user_id, conversation_id),
            )
            anchor = await cursor.fetchone()
            if not anchor:
                raise ResourceNotFoundError("message", message_id)
            cursor = await connection.execute(
                """SELECT id, role, content, created_at FROM messages
                   WHERE tenant_id=? AND conversation_id=?
                   ORDER BY created_at, rowid""",
                (tenant_id, conversation_id),
            )
            messages = [dict(row) for row in await cursor.fetchall()]
        index = next(index for index, message in enumerate(messages) if message["id"] == message_id)
        start = max(0, index - min(max(before, 0), 50))
        end = min(len(messages), index + min(max(after, 0), 50) + 1)
        return messages[start:end]

    async def replace_memory(self, tenant_id: str, user_id: str, content: str) -> None:
        async with self.connect() as connection:
            await connection.execute(
                """INSERT INTO memories(tenant_id, user_id, content)
                   VALUES (?, ?, ?)
                   ON CONFLICT(tenant_id, user_id) DO UPDATE SET
                     content=excluded.content, updated_at=CURRENT_TIMESTAMP""",
                (tenant_id, user_id, content),
            )
            await connection.commit()
