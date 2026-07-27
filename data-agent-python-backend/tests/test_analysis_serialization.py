"""测试分析结果相关的序列化与数据规范化逻辑。

覆盖：
- SQL 结果中的日期/时间/Decimal/字节等类型如何被转为可序列化（供结果提示词使用）；
- 构建结果提示词时每个查询结果都被纳入；
- 分析结果中引用的结果集 ID 如何被规范化（剔除无效 ID、单一结果时作为回退来源）；
- 配置项对结果行数 / 预览行数的默认限制。
"""

import json
from datetime import date, datetime, time
from decimal import Decimal
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage

from app.workflow.nodes.analysis import AnalysisNodes, _build_result_payload, _json_default
from app.application.executor import _normalize_result_sources
from app.config import Settings
from app.domain.errors import ContextWindowExceededError


@pytest.mark.asyncio
async def test_agent_publishes_query_result_followup_as_narration(monkeypatch) -> None:
    """已有查询结果时，Agent 文本作为可见过程说明，不冒充最终分析结论。"""

    class FakeLlm:
        on_text_delta = "not-called"

        async def complete_tool_messages(self, _system, _messages, *, tools, on_text_delta=None):
            self.on_text_delta = on_text_delta
            on_text_delta("数据已查询完成，准备总结。")
            return AIMessage(content="数据已查询完成，准备总结。")

    class FakeContextBuilder:
        async def build(self, _state, **_kwargs):
            return SimpleNamespace(
                messages=[{"role": "user", "content": "分析订单趋势"}],
                stats={"updated": False},
                compaction_state={},
            )

    llm = FakeLlm()
    streamed_events = []
    monkeypatch.setattr("app.workflow.nodes.analysis.get_stream_writer", lambda: streamed_events.append)
    monkeypatch.setattr("app.workflow.nodes.analysis._progress", lambda *_args, **_kwargs: None)
    nodes = AnalysisNodes(
        llm=llm,
        database=object(),
        retriever=SimpleNamespace(settings=Settings(retrieval_backend="bm25")),
        agent_context_builder=FakeContextBuilder(),
    )

    result = await nodes.agent_decide({
        "query": "分析订单趋势",
        "contextualized_query": "分析订单趋势",
        "query_results": [{"datasetId": "result_1", "rowCount": 3}],
        "schema": {"tables": [{"name": "orders"}]},
        "observations": [],
        "agent_iterations": 1,
    })

    assert result["agent_decision"]["action"] == "finish"
    assert callable(llm.on_text_delta)
    assert [event["type"] for event in streamed_events] == [
        "agent_message.started",
        "agent_message.delta",
        "agent_message.completed",
    ]
    assert streamed_events[-1]["data"]["kind"] == "narration"


@pytest.mark.asyncio
async def test_agent_reactively_compacts_and_retries_provider_context_error(
    monkeypatch,
) -> None:
    """供应商确认 prompt too long 后，当前决策应强制 Full Compact 并只重试一次。"""

    class FakeLlm:
        def __init__(self):
            self.calls = 0

        async def complete_tool_messages(self, _system, _messages, *, tools, on_text_delta=None):
            self.calls += 1
            if self.calls == 1:
                raise ContextWindowExceededError("prompt too long")
            return AIMessage(content="压缩后继续完成")

    class FakeContextBuilder:
        def __init__(self):
            self.force_flags = []

        async def build(self, _state, **kwargs):
            forced = bool(kwargs.get("force_full_compact"))
            self.force_flags.append(forced)
            return SimpleNamespace(
                messages=[{"role": "user", "content": "压缩后上下文" if forced else "原上下文"}],
                stats={"updated": forced},
                compaction_state={
                    "sequence": 1,
                    "mode": "reactive",
                    "stages": ["reactive_compact"],
                    "beforeTokens": 1000,
                    "afterTokens": 300,
                    "coveredMessageCount": 2,
                } if forced else {},
            )

    llm = FakeLlm()
    builder = FakeContextBuilder()
    streamed_events = []
    monkeypatch.setattr("app.workflow.nodes.analysis.get_stream_writer", lambda: streamed_events.append)
    monkeypatch.setattr("app.workflow.nodes.analysis._progress", lambda *_args, **_kwargs: None)
    nodes = AnalysisNodes(
        llm=llm,
        database=object(),
        retriever=SimpleNamespace(settings=Settings(retrieval_backend="bm25")),
        agent_context_builder=builder,
    )

    result = await nodes.agent_decide({
        "query": "继续分析",
        "contextualized_query": "继续分析",
        "query_results": [],
        "schema": {},
        "observations": [],
        "agent_iterations": 0,
    })

    assert llm.calls == 2
    assert builder.force_flags == [False, True]
    assert result["final_answer"] == "压缩后继续完成"
    assert result["context_compaction"]["mode"] == "reactive"
    assert "context.compaction.retrying" in [event["type"] for event in streamed_events]
    assert "context.compacted" in [event["type"] for event in streamed_events]


def test_sql_result_values_are_serialized_for_result_prompt() -> None:
    """验证 date/datetime/time/Decimal/bytes 等特殊类型能被自定义序列化器转为字符串。"""
    payload = {
        "order_date": date(2026, 7, 1),
        "created_at": datetime(2026, 7, 1, 12, 30, 45),
        "cutoff": time(18, 0),
        "amount": Decimal("1234.50"),
        "raw": b"ok",
    }

    # 通过 _json_default 处理无法被默认 JSON 编码器识别的类型
    encoded = json.loads(json.dumps(payload, default=_json_default))

    assert encoded == {
        "order_date": "2026-07-01",
        "created_at": "2026-07-01T12:30:45",
        "cutoff": "18:00:00",
        "amount": "1234.50",
        "raw": "ok",
    }


def test_result_prompt_contains_every_query_result() -> None:
    """验证 _build_result_payload 会把每个查询结果与对应的明细（行/行数）都纳入提示词。"""
    query_results = [
        {"sql": "SELECT 1 AS first_value", "datasetId": "result_first"},
        {"sql": "SELECT 2 AS second_value", "datasetId": "result_second"},
    ]
    inspected = {
        "result_first": {"columns": [{"name": "first_value"}], "rows": [{"first_value": 1}]},
        "result_second": {
            "columns": [{"name": "second_value"}],
            "rows": [{"second_value": 2}],
            "rowCount": 17,
        },
    }

    payload = _build_result_payload("对比两次查询", query_results, inspected)

    # 两次查询的结果集都应出现在提示词中，且顺序一致
    assert [item["resultSetId"] for item in payload["results"]] == ["result_first", "result_second"]
    assert payload["results"][0]["sql"] == "SELECT 1 AS first_value"
    assert payload["results"][1]["rows"] == [{"second_value": 2}]
    assert payload["results"][1]["rowCount"] == 17


def test_analysis_sources_are_preserved_and_invalid_ids_are_removed() -> None:
    """验证结果集来源被规范化：保留有效的引用 ID，剔除不存在（missing）的 ID。"""
    analysis = {
        "findings": [
            {"id": "f1", "sourceResultSetIds": ["result_first", "missing"]},
            {"id": "f2", "sourceResultSetIds": []},
        ],
        "metrics": [{"id": "m1", "sourceResultSetId": "result_second"}],
        "charts": [{"id": "c1", "resultSetId": "result_first"}],
    }

    _normalize_result_sources(analysis, ["result_first", "result_second"])

    assert analysis["findings"][0]["sourceResultSetIds"] == ["result_first"]
    assert analysis["findings"][1]["sourceResultSetIds"] == []
    assert analysis["metrics"][0]["sourceResultSetId"] == "result_second"
    assert analysis["charts"][0]["resultSetId"] == "result_first"


def test_single_result_is_used_as_source_fallback() -> None:
    """验证当分析对象引用为空时，仅有的单一结果集会作为 findings/metrics/charts 的来源回退。"""
    analysis = {
        "findings": [{"sourceResultSetIds": []}],
        "metrics": [{"sourceResultSetId": ""}],
        "charts": [{"resultSetId": ""}],
    }

    _normalize_result_sources(analysis, ["only_result"])

    assert analysis["findings"][0]["sourceResultSetIds"] == ["only_result"]
    assert analysis["metrics"][0]["sourceResultSetId"] == "only_result"
    assert analysis["charts"][0]["resultSetId"] == "only_result"


def test_default_limits_keep_full_results_but_only_persist_small_preview() -> None:
    """验证默认配置下保留完整结果（5 万行），但只持久化少量预览行（50 行）。"""
    settings = Settings()

    # 完整结果行上限
    assert settings.sql_row_limit == 50_000
    # 数据集保留的最大行数
    assert settings.analysis_dataset_max_rows == 50_000
    # 仅持久化给前端的小预览行数
    assert settings.analysis_dataset_preview_rows == 50
    assert settings.analysis_dataset_max_rows == 50_000
    assert settings.analysis_dataset_preview_rows == 50


@pytest.mark.asyncio
async def test_execute_sql_returns_final_result_and_uses_unified_row_limit(monkeypatch) -> None:
    """execute_sql 应在一次工具调用内完成校验和执行，并返回最终结果。"""

    class FakeDatabase:
        settings = SimpleNamespace(sql_row_limit=123)
        execute_count = 0

        async def execute_select(self, sql: str, *, row_limit: int | None = None):
            self.execute_count += 1
            self.last_row_limit = row_limit
            return ([{"name": "id", "dataType": "integer"}], [{"id": 1}])

    class FakeStore:
        async def create(self, *, run_id, columns, rows):
            return {
                "id": "result_test",
                "columns": columns,
                "previewRows": rows,
                "rowCount": len(rows),
                "filePath": "/tmp/result_test.csv",
            }

    database = FakeDatabase()
    sql_events = []
    monkeypatch.setattr("app.workflow.tools._progress", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "app.workflow.tools._sql_event",
        lambda event_type, data: sql_events.append((event_type, data)),
    )
    nodes = AnalysisNodes(
        llm=object(),
        database=database,
        retriever=SimpleNamespace(settings=Settings(retrieval_backend="bm25")),
        dataset_store=FakeStore(),
    )
    state = {
        "run_id": "run_test",
        "schema": {"tables": [{"name": "orders", "columns": [{"name": "id"}]}]},
        "query_results": [],
        "analysis_datasets": [],
        "observations": [],
    }
    execute_sql = next(
        tool for tool in nodes.tool_registry.tools if tool.name == "execute_sql"
    )
    command = await execute_sql.coroutine(
        sql="SELECT id FROM orders",
        state=state,
        tool_call_id="call_sql_test",
    )
    update = command.update
    tool_result = json.loads(update["messages"][0].content)

    assert "LIMIT 123" in update["sql"].upper()
    assert database.last_row_limit == 123
    assert update["query_results"][0]["rowCount"] == 1
    assert tool_result["tool"] == "execute_sql"
    assert [event_type for event_type, _data in sql_events] == [
        "sql.validated",
        "sql.executing",
        "sql.executed",
    ]
    assert tool_result["ok"] is True
    assert tool_result["summary"] == "查询成功，返回 1 行"
    assert "候选 SQL 已提交" not in update["messages"][0].content

    repeated = await execute_sql.coroutine(
        sql="SELECT id FROM orders",
        state={**state, **update},
        tool_call_id="call_sql_repeated",
    )
    repeated_result = json.loads(repeated.update["messages"][0].content)
    assert database.execute_count == 1
    assert repeated_result["stats"]["reused"] is True
    assert repeated_result["resultRef"]["datasetId"] == "result_test"
