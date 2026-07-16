"""测试 OpenAI 兼容 LLM 客户端（OpenAiChatClient）的请求构造与响应处理。

覆盖：请求体与 JSON / 结构化输出解析、缺失 API Key 报错、原始响应日志开关、思考模式、
截断响应被拒绝、输入上下文预算校验、上下文压缩（不产生二次摘要）、工具结果过长截断、
原生工具调用返回，以及角色顺序保持。
"""

from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from app.config import Settings
from app.domain.errors import InvalidOperationError
from app.infrastructure.llm.openai import LlmConfigurationError, OpenAiChatClient


# 用于结构化输出校验的示例模型
class ExampleOutput(BaseModel):
    classification: str
    execution_path: str = "simple"


# 记录调用参数并返回固定响应的假 Chat Completions 客户端
class FakeCompletions:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


# 包装 FakeCompletions 的假 SDK 客户端，支持 close 标记
class FakeSdkClient:
    def __init__(self, response):
        self.chat = SimpleNamespace(completions=FakeCompletions(response))
        self.closed = False

    async def close(self):
        self.closed = True


class FakeAsyncStream:
    """模拟 OpenAI SDK 的异步流，确保测试验证的是真实增量消费路径。"""

    def __init__(self, chunks):
        self._chunks = iter(chunks)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._chunks)
        except StopIteration:
            raise StopAsyncIteration
def response(text: str, finish_reason: str = "stop"):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text), finish_reason=finish_reason)]
    )


def tool_response(name: str, arguments: str):
    tool_call = SimpleNamespace(
        id=f"functions.{name}:0",
        function=SimpleNamespace(name=name, arguments=arguments),
    )
    message = SimpleNamespace(content="", tool_calls=[tool_call])
    return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="tool_calls")])


def stream_chunk(text: str = "", finish_reason: str | None = None):
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content=text), finish_reason=finish_reason)]
    )


@pytest.mark.asyncio
async def test_stream_complete_yields_provider_deltas(monkeypatch) -> None:
    """最终文本必须按 SDK 返回的增量产出，而不是等完整响应后人工切字符串。"""
    monkeypatch.setenv("DATA_AGENT_LLM_API_KEY", "test-key")
    sdk = FakeSdkClient(FakeAsyncStream([
        stream_chunk("销售额"),
        stream_chunk("持续增长"),
        stream_chunk(finish_reason="stop"),
    ]))
    client = OpenAiChatClient(Settings(), client=sdk)

    chunks = [chunk async for chunk in client.stream_complete("system", "question")]

    assert chunks == ["销售额", "持续增长"]
    assert sdk.chat.completions.calls[0]["stream"] is True


@pytest.mark.asyncio
async def test_stream_tool_messages_yields_final_text_deltas(monkeypatch) -> None:
    """Agent 直接结束时，用户可见正文应在完整响应结束前逐段交给 SSE 回调。"""
    monkeypatch.setenv("DATA_AGENT_LLM_API_KEY", "test-key")
    sdk = FakeSdkClient(FakeAsyncStream([
        stream_chunk("第一段"),
        stream_chunk("第二段"),
        stream_chunk(finish_reason="stop"),
    ]))
    client = OpenAiChatClient(Settings(), client=sdk)
    deltas: list[str] = []

    message = await client.complete_tool_messages(
        "system",
        [{"role": "user", "content": "question"}],
        tools=[{"name": "search_schema", "description": "search", "parameters": {"type": "object"}}],
        on_text_delta=deltas.append,
    )

    assert deltas == ["第一段", "第二段"]
    assert message.content == "第一段第二段"
    assert message.tool_calls == []


@pytest.mark.asyncio
async def test_official_sdk_request_and_json_parsing(monkeypatch) -> None:
    """验证客户端向官方 SDK 发出的请求参数（model/temperature/messages/思考开关）正确，并能解析 JSON 响应。"""
    monkeypatch.setenv("DATA_AGENT_LLM_API_KEY", "test-key")
    monkeypatch.setenv("DATA_AGENT_LLM_MODEL", "kimi-k2.5")
    monkeypatch.setenv("DATA_AGENT_LLM_TEMPERATURE", "0.2")
    sdk = FakeSdkClient(response('{"classification":"DATA_ANALYSIS"}'))
    client = OpenAiChatClient(Settings(), client=sdk)

    result = await client.complete_json("system", "question")

    assert result == {"classification": "DATA_ANALYSIS"}
    assert sdk.chat.completions.calls == [
        {
            "model": "kimi-k2.5",
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": "system"},
                {"role": "user", "content": "question"},
            ],
            "extra_body": {"thinking": {"type": "disabled"}},
        }
    ]
    # 关闭客户端后底层 SDK 应被标记关闭
    await client.close()
    assert sdk.closed is True


@pytest.mark.asyncio
async def test_structured_output_is_validated(monkeypatch) -> None:
    """验证结构化输出（complete_model）会按 Pydantic 模型校验字段。"""
    monkeypatch.setenv("DATA_AGENT_LLM_API_KEY", "test-key")
    sdk = FakeSdkClient(response('{"classification":"DATA_ANALYSIS","execution_path":"simple"}'))
    client = OpenAiChatClient(Settings(), client=sdk)

    result = await client.complete_model(ExampleOutput, "system", "question")

    assert result.classification == "DATA_ANALYSIS"
    assert result.execution_path == "simple"


@pytest.mark.asyncio
async def test_missing_key_is_reported_when_request_starts(monkeypatch) -> None:
    """验证未配置任何 API Key 时，发起请求会抛出 LlmConfigurationError。"""
    monkeypatch.delenv("DATA_AGENT_LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_ANTHROPIC_API_KEY", raising=False)
    client = OpenAiChatClient(Settings())

    with pytest.raises(LlmConfigurationError):
        await client.complete("system", "question")


def test_raw_response_logging_is_enabled_by_local_config(monkeypatch) -> None:
    """验证本地默认配置下：原始响应日志默认开启，而思考模式默认关闭。"""
    monkeypatch.delenv("DATA_AGENT_LLM_LOG_RESPONSES", raising=False)

    assert Settings().llm_log_responses is True
    assert Settings().llm_thinking_enabled is False


@pytest.mark.asyncio
async def test_thinking_mode_can_be_enabled_from_config(monkeypatch) -> None:
    """验证通过配置开启思考模式后，请求会携带 thinking.enabled 开关。"""
    monkeypatch.setenv("DATA_AGENT_LLM_API_KEY", "test-key")
    monkeypatch.setenv("DATA_AGENT_LLM_THINKING_ENABLED", "true")
    sdk = FakeSdkClient(response("ok"))
    client = OpenAiChatClient(Settings(), client=sdk)

    await client.complete("system", "question")

    assert sdk.chat.completions.calls[0]["extra_body"] == {"thinking": {"type": "enabled"}}


@pytest.mark.asyncio
async def test_truncated_sdk_response_is_not_accepted(monkeypatch) -> None:
    """验证 finish_reason 为 length（token 截断）的响应会被拒绝并抛 InvalidOperationError。"""
    monkeypatch.setenv("DATA_AGENT_LLM_API_KEY", "test-key")
    client = OpenAiChatClient(Settings(), client=FakeSdkClient(response("partial", "length")))

    with pytest.raises(InvalidOperationError, match="Token"):
        await client.complete("system", "question")


@pytest.mark.asyncio
async def test_raw_response_logging_is_explicitly_configurable(monkeypatch, caplog) -> None:
    """验证显式开启原始响应日志后，响应内容会以 BEGIN/END 标记写入日志。"""
    monkeypatch.setenv("DATA_AGENT_LLM_API_KEY", "test-key")
    monkeypatch.setenv("DATA_AGENT_LLM_LOG_RESPONSES", "true")
    client = OpenAiChatClient(Settings(), client=FakeSdkClient(response("完整调试输出")))

    with caplog.at_level("WARNING", logger="app.infrastructure.llm.openai"):
        await client.complete("system", "question")

    assert "LLM_RAW_RESPONSE_BEGIN" in caplog.text
    assert "完整调试输出" in caplog.text
    assert "LLM_RAW_RESPONSE_END" in caplog.text


@pytest.mark.asyncio
async def test_truncated_response_is_logged_before_rejection(monkeypatch, caplog) -> None:
    """验证被截断的响应在拒绝前也会原样记录到日志，便于排查。"""
    monkeypatch.setenv("DATA_AGENT_LLM_API_KEY", "test-key")
    monkeypatch.setenv("DATA_AGENT_LLM_LOG_RESPONSES", "true")
    client = OpenAiChatClient(Settings(), client=FakeSdkClient(response("被截断的原始内容", "length")))

    with caplog.at_level("WARNING", logger="app.infrastructure.llm.openai"):
        with pytest.raises(InvalidOperationError, match="Token"):
            await client.complete("system", "question")

    assert "被截断的原始内容" in caplog.text


@pytest.mark.asyncio
async def test_total_context_limit_is_enforced_before_provider_call(monkeypatch) -> None:
    """验证输入超过上下文预算时，在调用供应商前就抛错，且不发出任何请求。"""
    monkeypatch.setenv("DATA_AGENT_LLM_API_KEY", "test-key")
    sdk = FakeSdkClient(response("unused"))
    settings = Settings()
    settings.max_context_size = 100
    client = OpenAiChatClient(settings, client=sdk)

    with pytest.raises(InvalidOperationError, match="超过输入预算"):
        await client.complete("系统", "很长的上下文" * 30)

    # 超预算时不应向供应商发起任何调用
    assert sdk.chat.completions.calls == []


@pytest.mark.asyncio
async def test_llm_client_does_not_create_a_second_temporary_summary(monkeypatch) -> None:
    """验证上下文很长时只做一次压缩/摘要，不产生第二次临时摘要；旧消息被保留、最新消息仍在末尾。"""
    monkeypatch.setenv("DATA_AGENT_LLM_API_KEY", "test-key")
    sdk = FakeSdkClient(response("最终回答"))
    settings = Settings(
        max_context_size=240,
        context_compact_threshold=0.45,
        context_compact_preserve_ratio=0.3,
        memory_context_token_budget=40,
        memory_recent_token_budget=30,
        context_schema_token_budget=30,
        context_knowledge_token_budget=20,
    )
    client = OpenAiChatClient(settings, client=sdk)

    result = await client.complete_messages(
        "system",
        [
            {"role": "user", "content": "旧问题" * 15},
            {"role": "assistant", "content": "旧回答" * 15},
            {"role": "user", "content": "请继续分析最新情况"},
        ],
    )

    # 只触发一次 LLM 调用（一次压缩，无二次临时摘要）
    assert result == "最终回答"
    assert len(sdk.chat.completions.calls) == 1
    final_messages = sdk.chat.completions.calls[0]["messages"]
    # 压缩后旧问题仍保留在上下文前部
    assert final_messages[1]["content"].startswith("旧问题")
    # 最新用户消息保持在末尾
    assert final_messages[-1] == {"role": "user", "content": "请继续分析最新情况"}


@pytest.mark.asyncio
async def test_large_tool_result_is_trimmed_before_context_compaction(monkeypatch) -> None:
    """验证超长的工具结果在进入上下文前被截断，并标注“已截断”提示。"""
    monkeypatch.setenv("DATA_AGENT_LLM_API_KEY", "test-key")
    sdk = FakeSdkClient(response("ok"))
    settings = Settings(context_tool_result_max_tokens=8)
    client = OpenAiChatClient(settings, client=sdk)
    tools = [{"name": "search", "description": "search", "parameters": {"type": "object"}}]
    assistant = SimpleNamespace(
        type="ai",
        content="",
        tool_calls=[{"id": "call-1", "name": "search", "args": {"query": "orders"}}],
    )
    tool = SimpleNamespace(type="tool", content="查询结果" * 30, tool_call_id="call-1")

    await client.complete_tool_messages(
        "system",
        [{"role": "user", "content": "查询订单"}, assistant, tool],
        tools=tools,
    )

    # 发送给模型的是被截断后的 tool 消息
    sent_tool = sdk.chat.completions.calls[0]["messages"][-1]
    assert sent_tool["role"] == "tool"
    # 内容中标注了截断
    assert "工具结果过长，已截断" in sent_tool["content"]
    assert len(sent_tool["content"]) < len(tool.content)


@pytest.mark.asyncio
async def test_tool_schemas_are_logged_as_llm_input(monkeypatch, caplog) -> None:
    """验证工具列表作为 OpenAI 顶层 tools 参数发送时，也会出现在 LLM input 日志中。"""
    monkeypatch.setenv("DATA_AGENT_LLM_API_KEY", "test-key")
    monkeypatch.setenv("DATA_AGENT_LLM_LOG_IO", "true")
    monkeypatch.setenv("DATA_AGENT_LLM_LOG_RESPONSES", "false")
    sdk = FakeSdkClient(tool_response("search_schema", '{"query":"订单趋势"}'))
    client = OpenAiChatClient(Settings(), client=sdk)
    tools = [
        {
            "name": "search_schema",
            "description": "检索相关数据表",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        }
    ]

    with caplog.at_level("INFO", logger="app.infrastructure.llm.openai"):
        await client.complete_tool_messages(
            "system",
            [{"role": "user", "content": "分析订单趋势"}],
            tools=tools,
        )

    assert "[tools]" in caplog.text
    assert '"type": "function"' in caplog.text
    assert '"name": "search_schema"' in caplog.text
    assert '"query"' in caplog.text


@pytest.mark.asyncio
async def test_complete_messages_preserves_conversation_roles(monkeypatch) -> None:
    """验证 complete_messages 会原样保持 user/assistant 的角色交替顺序。"""
    monkeypatch.setenv("DATA_AGENT_LLM_API_KEY", "test-key")
    sdk = FakeSdkClient(response("继续分析华东地区。"))
    client = OpenAiChatClient(Settings(), client=sdk)

    await client.complete_messages(
        "system",
        [
            {"role": "user", "content": "分析全部地区"},
            {"role": "assistant", "content": "华东地区销量最高"},
            {"role": "user", "content": "那上个月呢？"},
        ],
    )

    assert [message["role"] for message in sdk.chat.completions.calls[0]["messages"]] == [
        "system",
        "user",
        "assistant",
        "user",
    ]


@pytest.mark.asyncio
async def test_native_tool_call_is_returned_as_ai_message(monkeypatch) -> None:
    """验证原生工具调用模式：返回 AIMessage 形式的 tool_calls，且请求使用 tool_choice=auto 且禁用并行调用。"""
    monkeypatch.setenv("DATA_AGENT_LLM_API_KEY", "test-key")
    sdk = FakeSdkClient(tool_response("search_schema", '{"query":"订单趋势"}'))
    client = OpenAiChatClient(Settings(), client=sdk)
    tools = [
        {
            "name": "search_schema",
            "description": "检索相关数据表",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        }
    ]

    message = await client.complete_tool_messages(
        "system",
        [{"role": "user", "content": "分析订单趋势"}],
        tools=tools,
    )

    assert message.tool_calls == [
        {"id": "functions.search_schema:0", "name": "search_schema", "args": {"query": "订单趋势"}, "type": "tool_call"}
    ]
    request = sdk.chat.completions.calls[0]
    assert request["tool_choice"] == "auto"
    assert request["parallel_tool_calls"] is False
    assert request["tools"][0]["function"] == tools[0]
