from pathlib import Path

import pytest

from app.application.events import EventBroker
from app.application.goal_verifier import ResultVerifier
from app.domain.models import TenantContext
from app.infrastructure.datasource.mysql import BusinessDatabase
from app.infrastructure.persistence.database import ControlDatabase
from app.infrastructure.results.store import ResultStore
from app.infrastructure.retrieval.service import KnowledgeSearchService, SchemaSearchService
from app.infrastructure.sdk.hooks import build_hooks
from app.infrastructure.sdk.tools import ToolFactory


@pytest.mark.asyncio
async def test_tool_call_upsert_keeps_one_auditable_record(tmp_path: Path) -> None:
    database = ControlDatabase(f"sqlite+aiosqlite:///{tmp_path / 'control.db'}")
    await database.initialize()
    context = TenantContext("tenant-a", "user-a", "conversation-a", "run-a")
    await database.ensure_tenant(context.tenant_id, context.user_id)
    await database.create_conversation(context)
    await database.create_run(context, "统计订单")

    await database.append_tool_call(context, "call-a", "execute_sql", {"sql": "SELECT 1"}, None, "requested")
    await database.append_tool_call(
        context,
        "call-a",
        "execute_sql",
        {"sql": "SELECT 1"},
        {"status": "passed"},
        "completed",
    )

    async with database.connect() as connection:
        cursor = await connection.execute("SELECT COUNT(*), status, started_at, completed_at FROM tool_calls")
        row = await cursor.fetchone()
    assert row[0] == 1
    assert row[1] == "completed"
    assert row[2] is not None
    assert row[3] is not None
    calls = await database.list_tool_calls(context.tenant_id, context.run_id)
    assert calls[0]["input"] == {"sql": "SELECT 1"}
    assert calls[0]["output"] == {"status": "passed"}


def test_claude_sdk_server_and_options_are_constructible(tmp_path: Path) -> None:
    from claude_agent_sdk import ClaudeAgentOptions

    context = TenantContext("tenant-a", "user-a", "conversation-a", "run-a")
    database = ControlDatabase(f"sqlite+aiosqlite:///{tmp_path / 'control.db'}")
    broker = EventBroker(database)
    server = ToolFactory(
        context,
        database,
        BusinessDatabase("mysql://readonly:password@127.0.0.1:3306/sales"),
        ResultStore(tmp_path / "results"),
        broker,
        SchemaSearchService(),
        KnowledgeSearchService(tmp_path / "knowledge"),
        ResultVerifier(),
    ).build_server()
    options = ClaudeAgentOptions(
        cwd=str(tmp_path),
        tools=["Skill"],
        mcp_servers={"data_agent": server},
        strict_mcp_config=True,
        allowed_tools=["Skill", "mcp__data_agent__*"],
        permission_mode="dontAsk",
        hooks=build_hooks(context, broker, database),
    )
    assert isinstance(server, dict)
    assert options.permission_mode == "dontAsk"
    assert options.allowed_tools == ["Skill", "mcp__data_agent__*"]
    assert ClaudeAgentOptions(thinking={"type": "disabled"}).thinking == {"type": "disabled"}
