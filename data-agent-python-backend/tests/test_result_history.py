"""测试结果历史（result history）的持久化与检索。

覆盖：结果集的全文检索按会话隔离、查询历史详情工具在结果缺失时返回不可重试错误，
以及会话消息的全文检索与可读会话读取。
"""

import pytest

from app.domain.errors import ResourceNotFoundError
from app.infrastructure.persistence.database import initialize_database, session_factory
from app.infrastructure.persistence.repository import Repository
from app.workflow.tools import AnalysisToolRegistry
from app.analysis.datasets import AnalysisDatasetStore
from app.config import get_settings


@pytest.mark.asyncio
async def test_result_history_fts_is_scoped_to_conversation() -> None:
    """验证结果历史 FTS 检索结果被限定在所属会话内，不会跨会话返回其他会话的结果。"""
    await initialize_database()
    async with session_factory() as session:
        repository = Repository(session)
        first = await repository.create_conversation(title="A", agent_id="agent", datasource_id="sales")
        second = await repository.create_conversation(title="B", agent_id="agent", datasource_id="sales")
        first_run = await repository.create_run(
            conversation=first, question="统计华东地区销售额", human_review_enabled=False, idempotency_key=None
        )
        second_run = await repository.create_run(
            conversation=second, question="统计华东地区销售额", human_review_enabled=False, idempotency_key=None
        )
        first_result = await repository.add_result_set(
            run_id=first_run.id, columns=[{"name": "sales_amount"}], rows=[{"sales_amount": 10}]
        )
        second_result = await repository.add_result_set(
            run_id=second_run.id, columns=[{"name": "sales_amount"}], rows=[{"sales_amount": 99}]
        )
        await repository.add_query(run_id=first_run.id, sql="SELECT sales_amount FROM orders", status="success", result_set_id=first_result.id)
        await repository.add_query(run_id=second_run.id, sql="SELECT sales_amount FROM orders", status="success", result_set_id=second_result.id)
        await repository.index_result_history(first.id, first_run.id, first_result.id, first_run.question, "SELECT sales_amount FROM orders", ["sales_amount"])
        await repository.index_result_history(second.id, second_run.id, second_result.id, second_run.question, "SELECT sales_amount FROM orders", ["sales_amount"])

        # 在会话 first 内检索“华东 销售额”，应只返回该会话自身的结果，而非会话 second 的
        matches = await repository.search_result_history_fts(first.id, "华东 销售额", 5)

        assert [item["datasetId"] for item in matches] == [first_result.id]


@pytest.mark.asyncio
async def test_inspect_history_tool_returns_recoverable_error_for_missing_result() -> None:
    """验证当要查看的结果集不存在时，inspect_query_result 工具返回 ok=False 且不可重试（retryable=False）。"""
    class MissingHistory:
        async def inspect(self, conversation_id, dataset_id, offset, limit):
            raise ResourceNotFoundError("result_set", dataset_id)

    registry = AnalysisToolRegistry(object(), object(), result_history=MissingHistory())
    tool = next(item for item in registry.tools if item.name == "inspect_query_result")

    command = await tool.ainvoke(
        {
            "name": "inspect_query_result",
            "type": "tool_call",
            "id": "call_1",
            "args": {
                "dataset_id": "missing",
                "offset": 0,
                "limit": 20,
                "state": {"conversation_id": "conv_1", "observations": []},
            },
        }
    )

    # 缺失结果应标记为失败且不可重试（属数据不存在，重试无意义）
    assert command.update["observations"][-1]["ok"] is False
    assert command.update["observations"][-1]["retryable"] is False


@pytest.mark.asyncio
async def test_conversation_history_fts_searches_messages_and_returns_readable_conversation() -> None:
    """验证会话消息 FTS 检索命中并返回片段（snippet），且可读会话接口返回完整 user/assistant 消息列表。"""
    await initialize_database()
    async with session_factory() as session:
        repository = Repository(session)
        conversation = await repository.create_conversation(
            title="退款率分析", agent_id="agent", datasource_id="sales"
        )
        await repository.add_message(
            conversation_id=conversation.id,
            run_id=None,
            role="user",
            content="分析退款成功金额占销售额的比例",
        )
        await repository.add_message(
            conversation_id=conversation.id,
            run_id=None,
            role="assistant",
            content="退款率按退款成功金额除以已完成订单销售额计算。",
        )

        matches = await repository.search_conversation_history("退款成功金额占销售额", 5)
        detail = await repository.read_conversation_history(conversation.id, 10)

    current = next(item for item in matches if item["conversationId"] == conversation.id)
    assert "退款成功" in current["snippet"]
    assert [item["role"] for item in detail["messages"]] == ["user", "assistant"]


@pytest.mark.asyncio
async def test_dataset_cleanup_removes_unreferenced_csv_files(tmp_path) -> None:
    """启动清理应删除没有 result_sets 记录引用的遗留 CSV。"""
    settings = get_settings().model_copy(update={"analysis_dataset_dir": tmp_path})
    store = AnalysisDatasetStore(settings)
    referenced = tmp_path / "result_referenced.csv"
    orphan = tmp_path / "result_orphan.csv"
    referenced.write_text("value\n1\n", encoding="utf-8")
    orphan.write_text("value\n2\n", encoding="utf-8")

    await initialize_database()
    async with session_factory() as session:
        repository = Repository(session)
        conversation = await repository.create_conversation(title="清理测试", agent_id="agent", datasource_id="sales")
        run = await repository.create_run(
            conversation=conversation,
            question="清理孤儿文件",
            human_review_enabled=False,
            idempotency_key=None,
        )
        await repository.add_result_set(
            run_id=run.id,
            columns=[{"name": "value"}],
            rows=[{"value": 1}],
            storage_type="csv",
            file_path=str(referenced),
        )

    removed = await store.cleanup_orphans()

    assert removed == 1
    assert referenced.exists()
    assert not orphan.exists()
