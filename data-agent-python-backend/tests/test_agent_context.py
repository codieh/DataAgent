"""测试 Agent 上下文构建器（AgentContextBuilder）。

验证在向 LLM 投影上下文时：schema 与当前活跃结果只出现一次、不重复冗余字段、
以及历史工具消息会被压缩为 schemaRef 引用而不改变原始状态。
"""

import json

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from app.config import Settings
from app.workflow.context_builder import AgentContextBuilder


# 伪造的历史结果存储：提供一条历史查询记录，用于验证“可用结果”来源
class FakeHistory:
    async def recent(self, conversation_id: str, limit: int):
        return [{"datasetId": "old_result", "question": "历史查询", "rowCount": 1}]

    async def inspect(self, conversation_id: str, dataset_id: str, offset: int, limit: int):
        return {
            "datasetId": dataset_id,
            "columns": [{"name": "amount"}],
            "rows": [{"amount": "UNIQUE_ROW_SENTINEL"}],
            "rowCount": 1,
            "returnedRows": 1,
            "hasMore": False,
            "truncated": False,
        }


@pytest.mark.asyncio
async def test_agent_context_contains_schema_and_active_rows_once() -> None:
    """验证构建出的上下文里：schema 与当前结果行各只出现一次，不会重复注入。

    - schema 中的唯一标记（UNIQUE_SCHEMA_SENTINEL）与结果行中的唯一标记（UNIQUE_ROW_SENTINEL）
      在序列化后的上下文里应恰好出现一次；
    - 旧版字段名 lastResult / queryResults 不应保留；
    - 历史结果（old_result）作为 availableResults 提供，而非当前结果。
    """
    builder = AgentContextBuilder(Settings(retrieval_backend="bm25"), FakeHistory())
    state = {
        "conversation_id": "conv_1",
        "query": "查询销售额",
        "schema": {
            "tables": [
                {"name": "UNIQUE_SCHEMA_SENTINEL", "columns": [], "foreignKeys": []}
            ]
        },
        "query_results": [
            {
                "datasetId": "current_result",
                "sql": "SELECT amount FROM orders",
                "columns": [{"name": "amount"}],
                "rowCount": 1,
            }
        ],
        "observations": [
            {
                "tool": "execute_safe_sql",
                "datasetId": "current_result",
                "preview": [{"amount": "UNIQUE_ROW_SENTINEL"}],
            }
        ],
        "messages": [],
        "memory_context": {},
    }

    context = await builder.build(state)
    serialized = json.dumps(context.payload, ensure_ascii=False)

    # schema 与结果行中的哨兵标记都只能出现一次，确认没有重复注入
    assert serialized.count("UNIQUE_SCHEMA_SENTINEL") == 1
    assert serialized.count("UNIQUE_ROW_SENTINEL") == 1
    # 确认旧版冗余字段已被移除
    assert "lastResult" not in context.payload
    assert "queryResults" not in context.payload
    # 历史结果作为“可用结果”提供给模型
    assert context.payload["availableResults"][0]["datasetId"] == "old_result"


@pytest.mark.asyncio
async def test_agent_context_compacts_old_schema_tool_message_without_mutating_state() -> None:
    """验证旧的 search_schema 工具消息会被压缩为 schemaRef 引用（移除冗余 tables 内容）。

    压缩后原始 ToolMessage 内容不应被修改（保持函数无副作用）。
    """
    original = json.dumps(
        {"tool": "search_schema", "tables": [{"name": "orders", "columns": [{"name": "id"}]}]}
    )
    messages = [
        AIMessage(content="", tool_calls=[{"id": "call_1", "name": "search_schema", "args": {"query": "订单"}}]),
        ToolMessage(content=original, tool_call_id="call_1"),
    ]
    builder = AgentContextBuilder(Settings(retrieval_backend="bm25"), FakeHistory())

    context = await builder.build(
        {"conversation_id": "conv_1", "query": "订单", "messages": messages, "memory_context": {}}
    )

    # 投影后的最后一条消息应为压缩后的 ToolMessage
    projected = context.messages[-1]
    assert isinstance(projected, ToolMessage)
    # 压缩后通过 schemaRef 引用状态中的 schema，而非内联 tables
    assert json.loads(projected.content)["schemaRef"] == "state.schema"
    assert "tables" not in json.loads(projected.content)
    # 原始输入消息未被改动，确认构建器无副作用
    assert messages[-1].content == original
