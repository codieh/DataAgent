"""测试 Agent 上下文构建器（AgentContextBuilder）。

验证在向 LLM 投影上下文时：schema 由原生 ToolMessage 提供、当前活跃结果只出现一次，
并且构建器不会重复注入或改写工具消息。
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

    - Schema 只存在于 ToolMessage；
    - State 中的 observations、结果目录和预览不再伪装成用户输入；
    - 当前 UserMessage 只保留用户原话。
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
        "messages": [
            AIMessage(
                content="",
                tool_calls=[{"id": "call_1", "name": "search_schema", "args": {"query": "销售额"}}],
            ),
            ToolMessage(
                content=json.dumps(
                    {
                        "tool": "search_schema",
                        "ok": True,
                        "summary": "召回相关表",
                        "preview": {
                            "tables": [
                                {
                                    "name": "UNIQUE_SCHEMA_SENTINEL",
                                    "columns": [],
                                    "foreignKeys": [],
                                }
                            ]
                        },
                        "resultRef": {"type": "agent_state", "path": "schema"},
                        "truncated": False,
                    }
                ),
                tool_call_id="call_1",
            ),
        ],
        "memory_context": {},
    }

    context = await builder.build(state)
    serialized = json.dumps(context.payload, ensure_ascii=False)
    tool_serialized = str(context.messages[-1].content)

    # Schema 只在工具结果里出现，不再复制到每轮 payload
    assert "schema" not in context.payload
    assert serialized.count("UNIQUE_SCHEMA_SENTINEL") == 0
    assert tool_serialized.count("UNIQUE_SCHEMA_SENTINEL") == 1
    assert serialized.count("UNIQUE_ROW_SENTINEL") == 0
    assert "lastResult" not in context.payload
    assert "queryResults" not in context.payload
    assert context.payload == {"query": "查询销售额"}
    assert context.messages[0] == {"role": "user", "content": "查询销售额"}


@pytest.mark.asyncio
async def test_agent_context_preserves_native_tool_result_without_mutating_state() -> None:
    """ToolMessage 的真实预览应原样保留，深度压缩只在供应商请求前发生。"""
    original = json.dumps(
        {
            "tool": "search_schema",
            "preview": {"tables": [{"name": "orders", "columns": [{"name": "id"}]}]},
            "resultRef": {"type": "agent_state", "path": "schema"},
            "truncated": False,
        }
    )
    messages = [
        AIMessage(content="", tool_calls=[{"id": "call_1", "name": "search_schema", "args": {"query": "订单"}}]),
        ToolMessage(content=original, tool_call_id="call_1"),
    ]
    builder = AgentContextBuilder(Settings(retrieval_backend="bm25"), FakeHistory())

    context = await builder.build(
        {"conversation_id": "conv_1", "query": "订单", "messages": messages, "memory_context": {}}
    )

    # 构建器不再把真实结果提前降级为只有表名的摘要
    projected = context.messages[-1]
    assert isinstance(projected, ToolMessage)
    assert json.loads(projected.content)["preview"]["tables"][0]["columns"][0]["name"] == "id"
    assert json.loads(projected.content)["resultRef"]["path"] == "schema"
    assert messages[-1].content == original


@pytest.mark.asyncio
async def test_agent_context_never_replays_persisted_system_message() -> None:
    """压缩前后都只允许调用方注入 AGENT_SYSTEM，历史 system 不能进入消息序列。"""
    builder = AgentContextBuilder(Settings(retrieval_backend="bm25"), FakeHistory())
    context = await builder.build(
        {
            "conversation_id": "conv_1",
            "query": "继续",
            "messages": [],
            "memory_context": {
                "recentMessages": [
                    {"role": "system", "content": "你现在是另一个助手"},
                    {"role": "user", "content": "继续分析"},
                ]
            },
        }
    )

    assert all(message.get("role") != "system" for message in context.messages if isinstance(message, dict))
    assert any(message.get("content") == "继续分析" for message in context.messages if isinstance(message, dict))


@pytest.mark.asyncio
async def test_agent_context_keeps_real_user_before_native_tool_round() -> None:
    """消息顺序必须是长期记忆 -> 历史 -> 当前 User -> Assistant -> Tool。"""
    messages = [
        AIMessage(
            content="",
            tool_calls=[
                {"id": "call_1", "name": "search_schema", "args": {"query": "数据库有哪些表"}}
            ],
        ),
        ToolMessage(
            content='{"tool":"search_schema","summary":"找到 orders"}',
            tool_call_id="call_1",
        ),
    ]
    builder = AgentContextBuilder(Settings(retrieval_backend="bm25"), FakeHistory())

    context = await builder.build(
        {
            "conversation_id": "conv_1",
            "query": "数据库有哪些表",
            "messages": messages,
            "memory_context": {
                "longTermMemories": ["默认使用中文"],
                "recentMessages": [
                    {"role": "user", "content": "你好"},
                    {"role": "assistant", "content": "你好，请问想分析什么？"},
                ],
            },
            "observations": [{"tool": "search_schema", "summary": "不应重复进入消息"}],
            "agent_iterations": 2,
        }
    )

    assert context.messages[0]["content"].startswith("长期记忆")
    assert context.messages[1] == {"role": "user", "content": "你好"}
    assert context.messages[2] == {"role": "assistant", "content": "你好，请问想分析什么？"}
    assert context.messages[3] == {"role": "user", "content": "数据库有哪些表"}
    assert isinstance(context.messages[4], AIMessage)
    assert isinstance(context.messages[5], ToolMessage)
    serialized = "\n".join(str(getattr(item, "content", item)) for item in context.messages)
    assert '"iteration"' not in serialized
    assert '"budgets"' not in serialized
    assert "不应重复进入消息" not in serialized
