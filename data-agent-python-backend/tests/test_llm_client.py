from types import SimpleNamespace

import pytest

from app.config import Settings
from app.domain.errors import InvalidOperationError
from app.infrastructure.llm.openai import LlmConfigurationError, OpenAiChatClient
from app.workflow.outputs import IntentOutput


class FakeCompletions:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class FakeSdkClient:
    def __init__(self, response):
        self.chat = SimpleNamespace(completions=FakeCompletions(response))
        self.closed = False

    async def close(self):
        self.closed = True


def response(text: str, finish_reason: str = "stop"):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text), finish_reason=finish_reason)]
    )


@pytest.mark.asyncio
async def test_official_sdk_request_and_json_parsing(monkeypatch) -> None:
    monkeypatch.setenv("DATA_AGENT_LLM_API_KEY", "test-key")
    monkeypatch.setenv("DATA_AGENT_LLM_MODEL", "kimi-k2.5")
    monkeypatch.setenv("DATA_AGENT_LLM_TEMPERATURE", "0.2")
    sdk = FakeSdkClient(response('{"classification":"DATA_ANALYSIS"}'))
    client = OpenAiChatClient(Settings(), client=sdk)

    result = await client.complete_json("system", "question", max_tokens=321)

    assert result == {"classification": "DATA_ANALYSIS"}
    assert sdk.chat.completions.calls == [
        {
            "model": "kimi-k2.5",
            "max_tokens": 321,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": "system"},
                {"role": "user", "content": "question"},
            ],
            "extra_body": {"thinking": {"type": "disabled"}},
        }
    ]
    await client.close()
    assert sdk.closed is True


@pytest.mark.asyncio
async def test_structured_output_is_validated(monkeypatch) -> None:
    monkeypatch.setenv("DATA_AGENT_LLM_API_KEY", "test-key")
    sdk = FakeSdkClient(response('{"classification":"DATA_ANALYSIS","execution_path":"simple"}'))
    client = OpenAiChatClient(Settings(), client=sdk)

    result = await client.complete_model(IntentOutput, "system", "question")

    assert result.classification == "DATA_ANALYSIS"
    assert result.execution_path == "simple"


@pytest.mark.asyncio
async def test_missing_key_is_reported_when_request_starts(monkeypatch) -> None:
    monkeypatch.delenv("DATA_AGENT_LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_ANTHROPIC_API_KEY", raising=False)
    client = OpenAiChatClient(Settings())

    with pytest.raises(LlmConfigurationError):
        await client.complete("system", "question")


def test_raw_response_logging_is_enabled_by_local_config(monkeypatch) -> None:
    monkeypatch.delenv("DATA_AGENT_LLM_LOG_RESPONSES", raising=False)

    assert Settings().llm_log_responses is True
    assert Settings().llm_thinking_enabled is False


@pytest.mark.asyncio
async def test_thinking_mode_can_be_enabled_from_config(monkeypatch) -> None:
    monkeypatch.setenv("DATA_AGENT_LLM_API_KEY", "test-key")
    monkeypatch.setenv("DATA_AGENT_LLM_THINKING_ENABLED", "true")
    sdk = FakeSdkClient(response("ok"))
    client = OpenAiChatClient(Settings(), client=sdk)

    await client.complete("system", "question")

    assert sdk.chat.completions.calls[0]["extra_body"] == {"thinking": {"type": "enabled"}}


@pytest.mark.asyncio
async def test_truncated_sdk_response_is_not_accepted(monkeypatch) -> None:
    monkeypatch.setenv("DATA_AGENT_LLM_API_KEY", "test-key")
    client = OpenAiChatClient(Settings(), client=FakeSdkClient(response("partial", "length")))

    with pytest.raises(InvalidOperationError, match="Token"):
        await client.complete("system", "question")


@pytest.mark.asyncio
async def test_raw_response_logging_is_explicitly_configurable(monkeypatch, caplog) -> None:
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
    monkeypatch.setenv("DATA_AGENT_LLM_API_KEY", "test-key")
    monkeypatch.setenv("DATA_AGENT_LLM_LOG_RESPONSES", "true")
    client = OpenAiChatClient(Settings(), client=FakeSdkClient(response("被截断的原始内容", "length")))

    with caplog.at_level("WARNING", logger="app.infrastructure.llm.openai"):
        with pytest.raises(InvalidOperationError, match="Token"):
            await client.complete("system", "question")

    assert "被截断的原始内容" in caplog.text
