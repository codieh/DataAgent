"""SDK 消息分派与流式增量的回归测试。

覆盖曾经导致运行失败的缺陷：

1. SDK 消息 dataclass 没有 ``type`` 字段，用 ``getattr(message, "type")`` 判定
   会把所有消息识别成 ``agent.message``，最终回答恒为空。
2. ``StreamEvent`` 只带 ``event``（原始流事件 dict），复用 ``_text_from_message``
   会让每条增量的文本恒为空，等于流式没有内容。
3. ``include_partial_messages=True`` 时 SDK 会把流式中的 partial ``AssistantMessage``
   （``stop_reason=None``）也作为 ``assistant.message`` 发布，前端把它们拼进叙事，
   表现为一堆“生长中”的重复 agent 消息。这类 partial 必须丢弃，只发布完成的消息。
"""

from typing import Any

import pytest
from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    StreamEvent,
    SystemMessage,
    TaskNotificationMessage,
    TaskProgressMessage,
    TaskStartedMessage,
    TaskUpdatedMessage,
    TextBlock,
)

from app.application.events import DELTA_HIGH_WATERMARK, EventBroker
from app.domain.models import TenantContext
from app.infrastructure.sdk.runtime import (
    _classify,
    _is_partial_assistant,
    _session_id_of,
    _stream_deltas,
    _system_event_type,
)


def _stream(event: dict[str, Any]) -> StreamEvent:
    return StreamEvent(uuid="uuid-1", session_id="session-1", event=event)


def _task_started() -> TaskStartedMessage:
    return TaskStartedMessage(
        subtype="task_started",
        data={},
        task_id="t-1",
        description="Analyze request",
        uuid="uuid-1",
        session_id="session-1",
    )


def _task_progress() -> TaskProgressMessage:
    return TaskProgressMessage(
        subtype="task_progress",
        data={},
        task_id="t-1",
        description="Analyzing...",
        usage={"total_tokens": 10, "tool_uses": 0, "duration_ms": 100},
        uuid="uuid-2",
        session_id="session-1",
    )


def _task_notification(status: str) -> TaskNotificationMessage:
    return TaskNotificationMessage(
        subtype="task_notification",
        data={},
        task_id="t-1",
        status=status,  # type: ignore[arg-type]
        output_file="",
        summary="done",
        uuid="uuid-3",
        session_id="session-1",
    )


def _task_updated(status: str) -> TaskUpdatedMessage:
    return TaskUpdatedMessage(
        subtype="task_updated",
        data={},
        task_id="t-1",
        patch={"status": status},
        status=status,  # type: ignore[arg-type]
        uuid="uuid-4",
        session_id="session-1",
    )


def test_classify_uses_types_not_missing_type_attribute() -> None:
    assert not hasattr(AssistantMessage(content=[], model="m"), "type")

    assert _classify(SystemMessage(subtype="init", data={"session_id": "s"})) == ("system", "init")
    assert _classify(AssistantMessage(content=[TextBlock(text="hi")], model="m")) == ("assistant", None)
    assert _classify(
        ResultMessage(
            subtype="success",
            duration_ms=1,
            duration_api_ms=1,
            is_error=False,
            num_turns=1,
            session_id="s",
            result="done",
        )
    ) == ("result", "success")
    assert _classify(_stream({"type": "content_block_delta"})) == ("stream_event", "content_block_delta")


def test_session_id_falls_back_to_system_message_data() -> None:
    assert _session_id_of(SystemMessage(subtype="init", data={"session_id": "s-9"})) == "s-9"
    assert _session_id_of(AssistantMessage(content=[], model="m", session_id="s-1")) == "s-1"
    assert _session_id_of(AssistantMessage(content=[], model="m")) is None


@pytest.mark.parametrize(
    ("delta", "kind", "text"),
    [
        ({"type": "text_delta", "text": "订单"}, "text", "订单"),
        ({"type": "thinking_delta", "thinking": "先看表"}, "thinking", "先看表"),
        ({"type": "input_json_delta", "partial_json": '{"sql":'}, "tool_input", '{"sql":'),
    ],
)
def test_content_block_delta_carries_real_text(delta: dict[str, Any], kind: str, text: str) -> None:
    events = _stream_deltas(_stream({"type": "content_block_delta", "index": 0, "delta": delta}))
    assert len(events) == 1
    event_type, payload = events[0]
    assert event_type == "assistant.message.delta"
    assert payload["kind"] == kind
    assert payload["delta"] == text
    assert payload["index"] == 0
    assert payload["session_id"] == "session-1"


def test_block_and_turn_boundaries_are_emitted() -> None:
    assert _stream_deltas(_stream({"type": "message_start"}))[0][0] == "assistant.turn.start"

    start = _stream_deltas(
        _stream({"type": "content_block_start", "index": 1, "content_block": {"type": "tool_use", "name": "execute_sql", "id": "t1"}})
    )
    assert start[0][0] == "assistant.block.start"
    assert start[0][1]["block_type"] == "tool_use"
    assert start[0][1]["tool_name"] == "execute_sql"

    assert _stream_deltas(_stream({"type": "content_block_stop", "index": 1}))[0][0] == "assistant.block.stop"


def test_noise_events_are_dropped() -> None:
    assert _stream_deltas(_stream({"type": "content_block_delta", "delta": {"type": "signature_delta"}})) == []
    assert _stream_deltas(_stream({"type": "content_block_delta", "delta": {"type": "text_delta", "text": ""}})) == []
    assert _stream_deltas(_stream({"type": "message_stop"})) == []
    assert _stream_deltas(object()) == []


def test_is_partial_assistant_detects_streaming_partials() -> None:
    # partial 的 stop_reason 默认为 None
    partial = AssistantMessage(content=[TextBlock(text="订")], model="m")
    complete = AssistantMessage(content=[TextBlock(text="订单")], model="m", stop_reason="end_turn")
    assert _is_partial_assistant(partial) is True
    assert _is_partial_assistant(complete) is False
    # 非 AssistantMessage 不算 partial
    assert _is_partial_assistant(SystemMessage(subtype="init", data={})) is False


def test_system_event_type_maps_and_suppresses_task_noise() -> None:
    assert _system_event_type("init", SystemMessage(subtype="init", data={})) == "agent.initialized"
    assert _system_event_type("task_progress", _task_progress()) is None
    assert _system_event_type("thinking_tokens", SystemMessage(subtype="thinking_tokens", data={})) is None
    assert _system_event_type("status", SystemMessage(subtype="status", data={})) is None
    assert _system_event_type("task_started", _task_started()) == "agent.task.started"
    assert _system_event_type("task_notification", _task_notification("completed")) == "agent.task.completed"
    assert _system_event_type("task_notification", _task_notification("failed")) == "agent.task.failed"
    assert _system_event_type("task_notification", _task_notification("stopped")) == "agent.task.stopped"
    assert _system_event_type("task_updated", _task_updated("completed")) == "agent.task.completed"
    assert _system_event_type("task_updated", _task_updated("failed")) == "agent.task.failed"
    assert _system_event_type("task_updated", _task_updated("killed")) == "agent.task.failed"
    assert _system_event_type("task_updated", _task_updated("running")) is None
    assert _system_event_type("mirror_error", SystemMessage(subtype="mirror_error", data={})) == "agent.system"
    assert _system_event_type("unknown", SystemMessage(subtype="unknown", data={})) == "agent.system"


@pytest.mark.asyncio
async def test_handle_message_suppresses_task_progress_but_emits_task_started() -> None:
    """task_progress 等高频系统消息不发布；任务开始/完成/失败才进入时间线。"""
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.infrastructure.sdk.runtime import SDKRuntime

    db = MagicMock()
    db.append_event = AsyncMock(return_value={"type": "agent.task.started", "seq": 1, "event_id": "e1", "payload": {}})
    broker = EventBroker(database=db)
    context = TenantContext("tenant-a", "user-a", "conversation-a", "run-a")
    with patch("app.infrastructure.sdk.runtime.get_settings", return_value=MagicMock()):
        runtime = SDKRuntime(control=MagicMock(), business=MagicMock(), results=MagicMock(), events=broker)

    async with broker.subscribe(context.run_id) as queue:
        await runtime._handle_message(context, _task_progress(), "system", "task_progress")
        assert queue.empty()

        await runtime._handle_message(context, _task_started(), "system", "task_started")
        event = queue.get_nowait()
        assert event["type"] == "agent.task.started"


@pytest.mark.asyncio
async def test_handle_message_skips_partial_but_keeps_complete_assistant() -> None:
    """partial 不发布任何事件；完成的 assistant 消息才发布为 assistant.message 快照。"""
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.infrastructure.sdk.runtime import SDKRuntime

    # publish 需要数据库附录事件；用假的 AsyncMock 提供最小可用的 append_event。
    db = MagicMock()
    db.append_event = AsyncMock(return_value={"type": "assistant.message", "seq": 1, "event_id": "e1", "payload": {}})
    broker = EventBroker(database=db)
    context = TenantContext("tenant-a", "user-a", "conversation-a", "run-a")
    with patch("app.infrastructure.sdk.runtime.get_settings", return_value=MagicMock()):
        runtime = SDKRuntime(control=MagicMock(), business=MagicMock(), results=MagicMock(), events=broker)

    async with broker.subscribe(context.run_id) as queue:
        # 流式中的 partial（stop_reason=None）不应发布任何事件
        await runtime._handle_message(context, AssistantMessage(content=[TextBlock(text="订")], model="m"), "assistant", None)
        assert queue.empty()

        # 完成的 assistant 消息（stop_reason 非空）应发布为 assistant.message 快照
        await runtime._handle_message(
            context,
            AssistantMessage(content=[TextBlock(text="订单结果")], model="m", stop_reason="end_turn"),
            "assistant",
            None,
        )
        assert not queue.empty()
        event = queue.get_nowait()
        assert event["type"] == "assistant.message"


@pytest.mark.asyncio
async def test_deltas_are_dropped_before_they_can_starve_durable_events() -> None:
    broker = EventBroker(database=None)  # type: ignore[arg-type]
    context = TenantContext("tenant-a", "user-a", "conversation-a", "run-a")

    async with broker.subscribe(context.run_id) as queue:
        for _ in range(DELTA_HIGH_WATERMARK + 50):
            broker.publish_delta(context, "assistant.message.delta", {"kind": "text", "delta": "x"})
        # 增量在高水位处停止入队，绝不会打满队列而触发整条流重连。
        assert queue.qsize() == DELTA_HIGH_WATERMARK
        assert queue.get_nowait()["ephemeral"] is True
