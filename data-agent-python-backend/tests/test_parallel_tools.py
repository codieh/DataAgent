"""验证 Agent 原生多工具调用会由 LangGraph ToolNode 并发执行。"""

import asyncio
from typing import Annotated, TypedDict

import pytest
from langchain_core.messages import AIMessage, AnyMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from app.domain.errors import InvalidOperationError
from app.workflow.nodes.analysis import _validate_parallel_state_writes


class ParallelToolState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]


@pytest.mark.asyncio
async def test_tool_node_executes_multiple_tool_calls_concurrently() -> None:
    """两个工具互相等待对方启动；只有真正并发执行时图才能正常结束。"""
    both_started = asyncio.Event()
    started: set[str] = set()

    async def wait_for_peer(name: str) -> str:
        started.add(name)
        if len(started) == 2:
            both_started.set()
        await asyncio.wait_for(both_started.wait(), timeout=0.5)
        return name

    @tool
    async def search_schema(query: str) -> str:
        """检索表结构。"""
        return await wait_for_peer("search_schema")

    @tool
    async def retrieve_knowledge(query: str) -> str:
        """检索业务知识。"""
        return await wait_for_peer("retrieve_knowledge")

    builder = StateGraph(ParallelToolState)
    builder.add_node("tools", ToolNode([search_schema, retrieve_knowledge]))
    builder.add_edge(START, "tools")
    builder.add_edge("tools", END)
    graph = builder.compile()

    result = await graph.ainvoke(
        {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "id": "schema_call",
                            "name": "search_schema",
                            "args": {"query": "统计 GMV"},
                        },
                        {
                            "id": "knowledge_call",
                            "name": "retrieve_knowledge",
                            "args": {"query": "统计 GMV"},
                        },
                    ],
                )
            ]
        }
    )

    assert started == {"search_schema", "retrieve_knowledge"}
    assert [message.tool_call_id for message in result["messages"][-2:]] == [
        "schema_call",
        "knowledge_call",
    ]


def test_parallel_tools_reject_conflicting_state_writes() -> None:
    """两个 SQL 提交会争写同一状态，必须在执行前明确失败。"""
    with pytest.raises(InvalidOperationError, match="不允许与其它工具并行"):
        _validate_parallel_state_writes(
            [
                {"id": "sql_1", "name": "execute_sql", "args": {"sql": "SELECT 1"}},
                {"id": "sql_2", "name": "execute_sql", "args": {"sql": "SELECT 2"}},
            ]
        )
