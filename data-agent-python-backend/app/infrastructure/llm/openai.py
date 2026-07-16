"""OpenAI 兼容的异步 LLM 客户端。

封装官方 ``openai`` SDK，向上提供文本补全、结构化（Pydantic）输出、带工具
调用的对话等能力。所有请求最终都汇聚到 ``_request``，因此模型输入/输出、
Token 用量、错误与耗时等可观测信息都从这里统一输出到日志。
"""

import json
import logging
import re
from collections.abc import AsyncIterator
from time import perf_counter
from typing import Any, Callable, TypeVar

import openai
from openai import AsyncOpenAI
from langchain_core.messages import AIMessage
from pydantic import BaseModel, ValidationError

from app.config import Settings
from app.context import estimate_tokens
from app.context.compaction import (
    message_tokens,
    trim_tool_results,
)
from app.domain.errors import InvalidOperationError
from app.observability.context import current_llm_operation, current_run_id
from app.observability.logging_setup import truncate_text


class LlmConfigurationError(InvalidOperationError):
    pass


ModelT = TypeVar("ModelT", bound=BaseModel)
logger = logging.getLogger(__name__)


class OpenAiChatClient:
    """OpenAI-compatible provider backed by the official async SDK."""

    def __init__(self, settings: Settings, client: AsyncOpenAI | None = None):
        self.settings = settings
        self._sdk_client = client

    def _client(self) -> AsyncOpenAI:
        if not self.settings.llm_api_key.strip():
            raise LlmConfigurationError("未配置 DATA_AGENT_LLM_API_KEY，无法执行真实 LLM 工作流。")
        if self._sdk_client is None:
            self._sdk_client = AsyncOpenAI(
                api_key=self.settings.llm_api_key,
                base_url=self.settings.llm_base_url,
                timeout=self.settings.llm_timeout_seconds,
                max_retries=self.settings.llm_max_retries,
            )
        return self._sdk_client

    async def complete(self, system: str, user: str) -> str:
        return await self.complete_messages(system, [{"role": "user", "content": user}])

    async def complete_messages(
        self, system: str, messages: list[dict[str, str]]
    ) -> str:
        choice, _response = await self._request(system, messages)
        content = choice.message.content
        if not content:
            raise InvalidOperationError("LLM 返回内容中没有文本结果。")
        return content

    async def stream_complete(self, system: str, user: str) -> AsyncIterator[str]:
        """流式生成纯文本；仅在收到服务端增量后向调用方产出，不伪造逐字效果。"""
        run_id = current_run_id.get()
        operation = "final_answer_stream"
        messages = [{"role": "user", "content": user}]
        input_tokens_estimate = _estimate_request_tokens(system, messages, "")
        if input_tokens_estimate > self.settings.max_context_size:
            raise InvalidOperationError(
                f"LLM 上下文约 {input_tokens_estimate} Token，超过输入预算 {self.settings.max_context_size} Token。"
            )
        request = {
            "model": self.settings.llm_model,
            "temperature": self.settings.llm_temperature,
            "messages": [{"role": "system", "content": system}, *messages],
            "extra_body": {
                "thinking": {"type": "enabled" if self.settings.llm_thinking_enabled else "disabled"}
            },
            "stream": True,
        }
        started = perf_counter()
        logger.info(
            "llm stream started: runId=%s operation=%s model=%s estimatedInputTokens=%d",
            run_id,
            operation,
            self.settings.llm_model,
            input_tokens_estimate,
        )
        chunks: list[str] = []
        finish_reason = None
        try:
            stream = await self._client().chat.completions.create(**request)
            async for chunk in stream:
                for choice in getattr(chunk, "choices", None) or []:
                    finish_reason = choice.finish_reason or finish_reason
                    content = getattr(choice.delta, "content", None)
                    if content:
                        chunks.append(content)
                        yield content
        except openai.AuthenticationError as error:
            logger.exception("llm stream authentication failed: runId=%s operation=%s", run_id, operation)
            raise InvalidOperationError("LLM 认证失败（401）：请检查 API Key 与 Base URL。") from error
        except openai.APIError as error:
            logger.exception("llm stream failed: runId=%s operation=%s", run_id, operation)
            raise InvalidOperationError(f"LLM 流式请求失败：{error.__class__.__name__}") from error
        text = "".join(chunks)
        if not text:
            raise InvalidOperationError("LLM 流式响应中没有文本结果。")
        if finish_reason == "length":
            raise InvalidOperationError("LLM 输出达到 Token 上限，结果不完整。")
        logger.info(
            "llm stream completed: runId=%s operation=%s model=%s finishReason=%s outputChars=%d durationMs=%d",
            run_id,
            operation,
            self.settings.llm_model,
            finish_reason,
            len(text),
            int((perf_counter() - started) * 1000),
        )

    async def complete_tool_messages(
        self,
        system: str,
        messages: list[Any],
        *,
        tools: list[dict[str, Any]],
        on_text_delta: Callable[[str], None] | None = None,
    ) -> AIMessage:
        if on_text_delta is not None:
            return await self._stream_tool_messages(system, messages, tools, on_text_delta)
        choice, _response = await self._request(
            system,
            messages,
            tools=tools,
        )
        tool_calls = []
        for call in getattr(choice.message, "tool_calls", None) or []:
            try:
                arguments = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError as error:
                raise InvalidOperationError(
                    f"工具 {call.function.name} 的参数不是有效 JSON：{error.msg}"
                ) from error
            if not isinstance(arguments, dict):
                raise InvalidOperationError(f"工具 {call.function.name} 的参数必须是 JSON 对象。")
            tool_calls.append(
                {
                    "id": call.id,
                    "name": call.function.name,
                    "args": arguments,
                    "type": "tool_call",
                }
            )
        return AIMessage(content=choice.message.content or "", tool_calls=tool_calls)

    async def _stream_tool_messages(
        self,
        system: str,
        messages: list[Any],
        tools: list[dict[str, Any]],
        on_text_delta: Callable[[str], None],
    ) -> AIMessage:
        """流式消费 Agent 响应，同时组装可能被拆成多段的原生 Tool Call。"""
        run_id = current_run_id.get()
        normalized_messages = trim_tool_results(
            _normalize_messages(messages, allow_tool_messages=True),
            self.settings.context_tool_result_max_tokens,
        )
        openai_tools = _openai_tools(tools)
        tool_schema_text = json.dumps(openai_tools, ensure_ascii=False)
        input_tokens_estimate = _estimate_request_tokens(system, normalized_messages, tool_schema_text)
        if input_tokens_estimate > self.settings.max_context_size:
            raise InvalidOperationError(
                f"LLM 上下文约 {input_tokens_estimate} Token，超过输入预算 {self.settings.max_context_size} Token。"
            )
        request = {
            "model": self.settings.llm_model,
            "temperature": self.settings.llm_temperature,
            "messages": [{"role": "system", "content": system}, *normalized_messages],
            "extra_body": {
                "thinking": {"type": "enabled" if self.settings.llm_thinking_enabled else "disabled"}
            },
            "tools": openai_tools,
            "tool_choice": "auto",
            "parallel_tool_calls": False,
            "stream": True,
        }
        started = perf_counter()
        logger.info(
            "llm agent stream started: runId=%s model=%s estimatedInputTokens=%d",
            run_id,
            self.settings.llm_model,
            input_tokens_estimate,
        )
        content_parts: list[str] = []
        calls: dict[int, dict[str, str]] = {}
        finish_reason = None
        try:
            stream = await self._client().chat.completions.create(**request)
            async for chunk in stream:
                for choice in getattr(chunk, "choices", None) or []:
                    finish_reason = choice.finish_reason or finish_reason
                    delta = choice.delta
                    content = getattr(delta, "content", None)
                    if content:
                        content_parts.append(content)
                        on_text_delta(content)
                    for call in getattr(delta, "tool_calls", None) or []:
                        item = calls.setdefault(call.index, {"id": "", "name": "", "arguments": ""})
                        if call.id:
                            item["id"] += call.id
                        function = getattr(call, "function", None)
                        if function is not None:
                            item["name"] += getattr(function, "name", None) or ""
                            item["arguments"] += getattr(function, "arguments", None) or ""
        except openai.AuthenticationError as error:
            logger.exception("llm agent stream authentication failed: runId=%s", run_id)
            raise InvalidOperationError("LLM 认证失败（401）：请检查 API Key 与 Base URL。") from error
        except openai.APIError as error:
            logger.exception("llm agent stream failed: runId=%s", run_id)
            raise InvalidOperationError(f"LLM 流式请求失败：{error.__class__.__name__}") from error

        content = "".join(content_parts)
        if calls and content:
            raise InvalidOperationError("LLM 同时返回了工具调用和用户可见文本，违反 Agent 输出协议。")
        if finish_reason == "length":
            raise InvalidOperationError("LLM 输出达到 Token 上限，结果不完整。")
        tool_calls = []
        for index in sorted(calls):
            call = calls[index]
            try:
                arguments = json.loads(call["arguments"] or "{}")
            except json.JSONDecodeError as error:
                raise InvalidOperationError(f"工具 {call['name']} 的参数不是有效 JSON：{error.msg}") from error
            if not call["id"] or not call["name"] or not isinstance(arguments, dict):
                raise InvalidOperationError("LLM 返回了不完整的工具调用。")
            tool_calls.append({
                "id": call["id"],
                "name": call["name"],
                "args": arguments,
                "type": "tool_call",
            })
        if not content and not tool_calls:
            raise InvalidOperationError("LLM 流式响应既没有文本也没有工具调用。")
        logger.info(
            "llm agent stream completed: runId=%s model=%s finishReason=%s outputChars=%d toolCalls=%d durationMs=%d",
            run_id,
            self.settings.llm_model,
            finish_reason,
            len(content),
            len(tool_calls),
            int((perf_counter() - started) * 1000),
        )
        return AIMessage(content=content, tool_calls=tool_calls)

    async def _request(
        self,
        system: str,
        messages: list[Any],
        *,
        tools: list[dict[str, Any]] | None = None,
    ):
        run_id = current_run_id.get()
        operation = current_llm_operation.get()
        normalized_messages = _normalize_messages(messages, allow_tool_messages=tools is not None)
        # Tool responses can be much larger than normal dialogue. Trim them before
        # measuring the request so one query result cannot consume the whole window.
        normalized_messages = trim_tool_results(
            normalized_messages, self.settings.context_tool_result_max_tokens
        )
        openai_tools = _openai_tools(tools) if tools is not None else None
        tool_schema_text = json.dumps(openai_tools, ensure_ascii=False) if openai_tools is not None else ""
        input_budget = self.settings.max_context_size
        input_tokens_estimate = _estimate_request_tokens(
            system, normalized_messages, tool_schema_text
        )
        if input_tokens_estimate > input_budget:
            raise InvalidOperationError(
                f"LLM 上下文约 {input_tokens_estimate} Token，超过输入预算 {input_budget} Token。"
            )
        started = perf_counter()
        logger.info(
            "llm request started: runId=%s operation=%s provider=openai model=%s baseUrl=%s "
            "inputChars=%d estimatedInputTokens=%d maxContextSize=%d",
            run_id,
            operation,
            self.settings.llm_model,
            self.settings.llm_base_url,
            len(system) + sum(len(message["content"]) for message in normalized_messages) + len(tool_schema_text),
            input_tokens_estimate,
            self.settings.max_context_size,
        )
        # 记录模型“实际看到的输入”：系统提示 + 历史/工具消息。截断后写入，
        # 便于排查模型为何给出某个回答，同时避免巨型工具结果刷屏日志。
        if self.settings.llm_log_io:
            logger.info(
                "llm input BEGIN runId=%s operation=%s model=%s\n[system]\n%s\n[messages]\n%s\n[tools]\n%s\nllm input END",
                run_id,
                operation,
                self.settings.llm_model,
                truncate_text(system, self.settings.llm_log_input_chars),
                truncate_text(_format_messages(normalized_messages), self.settings.llm_log_input_chars),
                truncate_text(_format_tools(openai_tools), self.settings.llm_log_input_chars),
            )
        try:
            request: dict[str, Any] = {
                "model": self.settings.llm_model,
                "temperature": self.settings.llm_temperature,
                "messages": [{"role": "system", "content": system}, *normalized_messages],
                "extra_body": {
                    "thinking": {
                        "type": "enabled" if self.settings.llm_thinking_enabled else "disabled",
                    }
                },
            }
            if tools is not None:
                request.update(
                    {
                        "tools": openai_tools,
                        "tool_choice": "auto",
                        "parallel_tool_calls": False,
                    }
                )
            response = await self._client().chat.completions.create(
                **request,
            )
        except openai.AuthenticationError as error:
            logger.error(
                "llm authentication failed: runId=%s operation=%s model=%s baseUrl=%s status=401 requestId=%s "
                "providerMessage=%s durationMs=%d",
                run_id,
                operation,
                self.settings.llm_model,
                self.settings.llm_base_url,
                getattr(error, "request_id", None) or "-",
                _provider_error_message(error),
                int((perf_counter() - started) * 1000),
            )
            raise InvalidOperationError(
                "LLM 认证失败（401）：请检查 API Key 是否属于当前 Moonshot 开放平台，以及 Base URL 是否匹配。"
            ) from error
        except openai.APIStatusError as error:
            logger.error(
                "llm api failed: runId=%s operation=%s model=%s status=%s requestId=%s providerMessage=%s "
                "durationMs=%d",
                run_id,
                operation,
                self.settings.llm_model,
                error.status_code,
                getattr(error, "request_id", None) or "-",
                _provider_error_message(error),
                int((perf_counter() - started) * 1000),
            )
            raise InvalidOperationError(f"LLM 请求失败：HTTP {error.status_code}") from error
        except openai.APIError as error:
            status = getattr(error, "status_code", None)
            detail = f"HTTP {status}" if status else error.__class__.__name__
            logger.exception(
                "llm request error: runId=%s operation=%s model=%s detail=%s durationMs=%d",
                run_id,
                operation,
                self.settings.llm_model,
                detail,
                int((perf_counter() - started) * 1000),
            )
            raise InvalidOperationError(f"LLM 请求失败：{detail}") from error
        choice = response.choices[0] if response.choices else None
        if choice is None:
            raise InvalidOperationError("LLM 返回结果中没有候选内容。")
        if self.settings.llm_log_responses:
            logger.warning(
                "LLM_RAW_RESPONSE_BEGIN runId=%s operation=%s model=%s\n%s\n"
                "LLM_RAW_RESPONSE_END runId=%s operation=%s",
                run_id,
                operation,
                self.settings.llm_model,
                _serialize_response(response),
                run_id,
                operation,
            )
        # 记录模型“实际返回的输出”：文本内容与工具调用（名称 + 参数）。
        # 这是观察 Agent 决策（调用了哪个工具、传了什么参数）的核心日志。
        if self.settings.llm_log_io:
            message = choice.message
            tool_calls = getattr(message, "tool_calls", None) or []
            logger.info(
                "llm output BEGIN runId=%s operation=%s model=%s finishReason=%s\n[content]\n%s\n[tool_calls]\n%s\nllm output END",
                run_id,
                operation,
                self.settings.llm_model,
                choice.finish_reason,
                truncate_text(message.content or "", self.settings.llm_log_output_chars),
                truncate_text(_format_tool_calls(tool_calls), self.settings.llm_log_output_chars),
            )
        if choice.finish_reason == "length":
            raise InvalidOperationError("LLM 输出达到 Token 上限，结果不完整。")
        usage = getattr(response, "usage", None)
        logger.info(
            "llm request completed: runId=%s operation=%s model=%s requestId=%s finishReason=%s "
            "promptTokens=%s completionTokens=%s totalTokens=%s durationMs=%d",
            run_id,
            operation,
            self.settings.llm_model,
            getattr(response, "_request_id", None) or "-",
            choice.finish_reason,
            getattr(usage, "prompt_tokens", None),
            getattr(usage, "completion_tokens", None),
            getattr(usage, "total_tokens", None),
            int((perf_counter() - started) * 1000),
        )
        return choice, response

    async def complete_json(self, system: str, user: str) -> dict[str, Any]:
        text = await self.complete(system, user)
        candidate = _extract_json(text)
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError as error:
            raise InvalidOperationError(f"LLM 未返回有效 JSON：{error.msg}") from error
        if not isinstance(value, dict):
            raise InvalidOperationError("LLM JSON 结果必须是对象。")
        return value

    async def complete_model(
        self,
        output_type: type[ModelT],
        system: str,
        user: str,
    ) -> ModelT:
        return await self.complete_messages_model(
            output_type,
            system,
            [{"role": "user", "content": user}],
        )

    async def complete_messages_model(
        self,
        output_type: type[ModelT],
        system: str,
        messages: list[dict[str, str]],
    ) -> ModelT:
        operation_token = current_llm_operation.set(output_type.__name__)
        try:
            text = await self.complete_messages(system, messages)
            try:
                return output_type.model_validate_json(_extract_json(text))
            except ValidationError as error:
                fields = ", ".join(".".join(map(str, item["loc"])) for item in error.errors()[:3])
                logger.error(
                    "llm structured output invalid: runId=%s operation=%s fields=%s outputChars=%d",
                    current_run_id.get(),
                    output_type.__name__,
                    fields,
                    len(text),
                )
                raise InvalidOperationError(f"LLM 结构化结果校验失败：{fields}") from error
        finally:
            current_llm_operation.reset(operation_token)

    async def close(self) -> None:
        if self._sdk_client is not None:
            await self._sdk_client.close()
            self._sdk_client = None


def _extract_json(text: str) -> str:
    stripped = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced.group(1)
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        return stripped[start : end + 1]
    return stripped


def _estimate_request_tokens(
    system: str, messages: list[dict[str, Any]], tool_schema_text: str
) -> int:
    # The budget covers everything sent over the wire, not only visible message text.
    return (
        estimate_tokens(system)
        + sum(message_tokens(message) for message in messages)
        + (estimate_tokens(tool_schema_text) if tool_schema_text else 0)
    )


def _normalize_messages(messages: list[Any], *, allow_tool_messages: bool = False) -> list[dict[str, Any]]:
    normalized = []
    for message in messages:
        normalized_message = _normalize_message(message, allow_tool_messages)
        if normalized_message is not None:
            normalized.append(normalized_message)
    if not normalized or (not allow_tool_messages and normalized[-1]["role"] != "user"):
        raise InvalidOperationError("LLM 会话必须以当前用户消息结束。")
    return normalized


def _normalize_message(message: Any, allow_tool_messages: bool) -> dict[str, Any] | None:
    if isinstance(message, dict):
        role = str(message.get("role") or "")
        content = str(message.get("content") or "")
        if role not in {"system", "user", "assistant"}:
            raise InvalidOperationError(f"不支持的会话消息角色：{role or 'empty'}")
        return {"role": role, "content": content} if content else None
    if not allow_tool_messages:
        raise InvalidOperationError("普通 LLM 调用不支持工具消息。")
    message_type = getattr(message, "type", "")
    if message_type == "ai":
        tool_calls = [
            {
                "id": call["id"],
                "type": "function",
                "function": {"name": call["name"], "arguments": json.dumps(call["args"], ensure_ascii=False)},
            }
            for call in getattr(message, "tool_calls", [])
        ]
        return {"role": "assistant", "content": str(message.content or ""), "tool_calls": tool_calls}
    if message_type == "tool":
        return {
            "role": "tool",
            "content": str(message.content or ""),
            "tool_call_id": message.tool_call_id,
        }
    raise InvalidOperationError(f"不支持的工具会话消息类型：{message_type or 'empty'}")


def _provider_error_message(error: openai.APIStatusError) -> str:
    body = getattr(error, "body", None)
    if isinstance(body, dict):
        nested = body.get("error")
        if isinstance(nested, dict):
            return str(nested.get("message") or nested.get("type") or "unknown")[:300]
        return str(body.get("message") or body.get("detail") or "unknown")[:300]
    return str(error)[:300]


def _serialize_response(response: Any) -> str:
    model_dump_json = getattr(response, "model_dump_json", None)
    if callable(model_dump_json):
        return model_dump_json(indent=2)
    return repr(response)


def _openai_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Wrap internal tool specs into the exact OpenAI tool schema sent on wire."""
    return [{"type": "function", "function": item} for item in tools]


def _format_messages(messages: list[dict[str, Any]]) -> str:
    """把发送给模型的消息列表格式化为易读的「[角色] 内容」多行文本。"""
    parts: list[str] = []
    for message in messages:
        role = str(message.get("role") or "?")
        content = str(message.get("content") or "")
        parts.append(f"[{role}] {content}")
    return "\n".join(parts) if parts else "(空)"


def _format_tools(tools: list[dict[str, Any]] | None) -> str:
    """把发送给模型的工具 schema 格式化为 JSON，方便核对工具名和参数定义。"""
    if not tools:
        return "(无工具)"
    return json.dumps(tools, ensure_ascii=False, indent=2)


def _format_tool_calls(tool_calls: list[Any]) -> str:
    """把模型返回的工具调用格式化为「- 名称(参数JSON)」多行文本。"""
    if not tool_calls:
        return "(无工具调用)"
    parts: list[str] = []
    for call in tool_calls:
        function = getattr(call, "function", None)
        name = getattr(function, "name", "?") if function is not None else "?"
        arguments = getattr(function, "arguments", "") if function is not None else ""
        parts.append(f"- {name}({arguments})")
    return "\n".join(parts)
