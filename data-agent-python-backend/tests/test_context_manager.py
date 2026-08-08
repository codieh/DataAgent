"""测试 cc-haha 风格的多阶段活动上下文压缩。"""

import json

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from app.config import Settings
from app.context.manager import AgentContextManager, _micro_compact_rounds
class FakeLlm:
    def __init__(self):
        self.calls: list[dict] = []

    async def complete(self, system, user):
        payload = json.loads(user)
        self.calls.append(payload)
        return (
            "当前目标：\n分析订单\n\n"
            "用户约束与纠正：\n只看已完成订单\n\n"
            "已确认的数据上下文：\norders\n\n"
            "已完成的工作：\n已查询订单\n\n"
            "结果引用：\nresult_1，可通过 inspect_query_result 读取\n\n"
            "错误与处理：\n无\n\n"
            "当前进度与待办：\n尚未生成最终结论"
        )


def _tool_round(call_id: str, marker: str) -> list:
    return [
        AIMessage(
            content="正在查询",
            tool_calls=[
                {
                    "id": call_id,
                    "name": "execute_sql",
                    "args": {"sql": "SELECT * FROM orders"},
                }
            ],
        ),
        ToolMessage(
            content=json.dumps(
                {
                    "tool": "execute_sql",
                    "ok": True,
                    "summary": "查询成功",
                    "preview": {"rows": [{"value": marker * 300}]},
                    "resultRef": {"type": "query_result", "datasetId": "result_1"},
                    "stats": {"rowCount": 1000},
                },
                ensure_ascii=False,
            ),
            tool_call_id=call_id,
        ),
    ]


def test_large_window_uses_cc_haha_absolute_reserves() -> None:
    manager = AgentContextManager(
        Settings(retrieval_backend="bm25", max_context_size=200_000),
        FakeLlm(),
    )

    limits = manager._limits()

    assert limits["summaryOutputReserveTokens"] == 20_000
    assert limits["safetyBufferTokens"] == 13_000
    assert limits["autoCompactAtTokens"] == 167_000
    assert limits["collapseCommitAtTokens"] == 162_000
    assert limits["collapseBlockingAtTokens"] == 171_000


@pytest.mark.asyncio
async def test_tool_budget_does_not_protect_latest_complete_result() -> None:
    settings = Settings(retrieval_backend="bm25", max_context_size=2_000)
    manager = AgentContextManager(settings, FakeLlm())
    workflow_messages = [
        *_tool_round("call_1", "旧" * 20),
        *_tool_round("call_2", "新" * 20),
    ]

    projection = await manager.prepare(
        state={"messages": workflow_messages},
        conversation_messages=[],
        current_message={"role": "user", "content": "继续"},
        system="system",
        tools=[],
    )

    tool_messages = [
        message for message in projection.messages if isinstance(message, ToolMessage)
    ]
    assert len(tool_messages) == 2
    assert all(json.loads(message.content)["truncated"] is True for message in tool_messages)
    assert projection.stats["budgetReclaimedTokens"] > 0


@pytest.mark.asyncio
async def test_micro_compact_replaces_complete_tool_round_without_orphans() -> None:
    workflow_messages = [
        *_tool_round("call_1", "数据" * 8),
        *_tool_round("call_2", "最新" * 8),
    ]
    projection, compacted_rounds = _micro_compact_rounds(workflow_messages)
    wire = [message for message in projection if isinstance(message, dict)]
    round_summaries = [
        message for message in wire if message.get("content", "").startswith("已完成的工具执行记录：")
    ]
    assert len(round_summaries) == 2
    assert all(message["role"] == "assistant" for message in round_summaries)
    assert compacted_rounds == 2
    assert not any(isinstance(message, (AIMessage, ToolMessage)) for message in projection)


@pytest.mark.asyncio
async def test_context_collapse_persists_boundary_and_keeps_new_suffix() -> None:
    settings = Settings(retrieval_backend="bm25", max_context_size=3_000)
    llm = FakeLlm()
    manager = AgentContextManager(settings, llm)
    manager.COLLAPSE_COMMIT_RATIO = 0.01
    manager.COLLAPSE_BLOCKING_RATIO = 2.0
    first_messages = _tool_round("call_1", "历史数据")

    first = await manager.prepare(
        state={"messages": first_messages},
        conversation_messages=[
                {"role": "user", "content": "很长的历史问题" * 30},
        ],
        current_message={"role": "user", "content": "继续"},
        system="system",
        tools=[],
    )

    assert first.compaction_state["coveredMessageCount"] == len(first_messages)
    assert first.compaction_state["sequence"] == 1
    assert first.compaction_state["summary"]
    assert llm.calls

    new_round = _tool_round("call_2", "新增数据")
    second = await manager.prepare(
        state={
            "messages": [*first_messages, *new_round],
            "context_compaction": first.compaction_state,
        },
        conversation_messages=[],
        current_message={"role": "user", "content": "继续"},
        system="system",
        tools=[],
    )

    serialized = "\n".join(
        message.get("content", "") if isinstance(message, dict) else str(message.content)
        for message in second.messages
    )
    assert "运行上下文摘要" in serialized
    assert "call_1" not in serialized
    # 第二次摘要输入必须包含边界之后的新工具轮次，随后游标继续向前推进。
    assert "call_2" in json.dumps(llm.calls[-1]["messages"], ensure_ascii=False)
    assert second.compaction_state["coveredMessageCount"] == len(first_messages) + len(new_round)
    assert second.compaction_state["sequence"] == 2


@pytest.mark.asyncio
async def test_auto_compact_rebuilds_context_without_identity_or_old_conversation() -> None:
    settings = Settings(retrieval_backend="bm25", max_context_size=3_000)
    llm = FakeLlm()
    manager = AgentContextManager(settings, llm)
    manager.COLLAPSE_COMMIT_RATIO = 2.0
    manager.COLLAPSE_BLOCKING_RATIO = 0.01

    projection = await manager.prepare(
        state={"messages": _tool_round("call_1", "历史数据")},
        conversation_messages=[
            {"role": "user", "content": "OLD_CONVERSATION_SENTINEL"},
            {"role": "assistant", "content": "旧回答"},
        ],
        current_message={
            "role": "user",
            "content": json.dumps(
                {
                    "query": "继续分析",
                    "memory": {
                        "summary": "OLD_MEMORY_SENTINEL",
                        "relatedMessages": ["旧细节"],
                        "longTermMemories": ["默认中文"],
                    },
                    "activeResult": {
                        "datasetId": "result_1",
                        "rowCount": 1000,
                        "rows": [{"value": "LARGE_PREVIEW_SENTINEL"}],
                    },
                },
                ensure_ascii=False,
            ),
        },
        system="IMMUTABLE_SYSTEM_SENTINEL",
        tools=[],
    )

    serialized = "\n".join(
        message.get("content", "") if isinstance(message, dict) else str(message.content)
        for message in projection.messages
    )
    assert projection.compaction_state["mode"] == "auto"
    assert "OLD_CONVERSATION_SENTINEL" not in serialized
    assert "OLD_MEMORY_SENTINEL" not in serialized
    assert "LARGE_PREVIEW_SENTINEL" not in serialized
    assert "默认中文" in serialized
    # System Prompt 由请求层重新注入，不能被压缩为普通历史消息。
    assert "IMMUTABLE_SYSTEM_SENTINEL" not in serialized
