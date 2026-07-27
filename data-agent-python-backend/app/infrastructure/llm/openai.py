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
from app.domain.errors import ContextWindowExceededError, InvalidOperationError
from app.observability.context import (
    current_conversation_id,
    current_llm_operation,
    current_run_id,
)
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
        conversation_id = current_conversation_id.get()
        operation = "final_answer_stream"
        messages, input_tokens_estimate = self._prepare_request_context(
            system,
            [{"role": "user", "content": user}],
            "",
            run_id=run_id,
            operation=operation,
        )
        request = {
            "model": self.settings.llm_model,
            "temperature": self.settings.llm_temperature,
            "messages": _canonical_request_messages(system, messages),
            "extra_body": {
                "thinking": {"type": "enabled" if self.settings.llm_thinking_enabled else "disabled"}
            },
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        _add_prompt_cache_key(request, conversation_id)
        started = perf_counter()
        logger.info(
            "llm stream started: runId=%s conversationId=%s operation=%s model=%s baseUrl=%s "
            "messageCount=%d temperature=%s thinkingEnabled=%s promptCacheKey=%s estimatedInputTokens=%d",
            run_id,
            conversation_id,
            operation,
            self.settings.llm_model,
            self.settings.llm_base_url,
            len(request["messages"]),
            self.settings.llm_temperature,
            self.settings.llm_thinking_enabled,
            request.get("prompt_cache_key", "-"),
            input_tokens_estimate,
        )
        self._log_input(run_id, conversation_id, operation, system, messages, None)
        chunks: list[str] = []
        finish_reason = None
        response_id = "-"
        response_model = self.settings.llm_model
        usage = None
        chunk_count = 0
        first_token_ms = None
        try:
            stream = await self._client().chat.completions.create(**request)
            async for chunk in stream:
                chunk_count += 1
                response_id = getattr(chunk, "id", None) or response_id
                response_model = getattr(chunk, "model", None) or response_model
                usage = getattr(chunk, "usage", None) or usage
                for choice in getattr(chunk, "choices", None) or []:
                    finish_reason = choice.finish_reason or finish_reason
                    content = getattr(choice.delta, "content", None)
                    if content:
                        if first_token_ms is None:
                            first_token_ms = int((perf_counter() - started) * 1000)
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
        self._log_stream_response(
            run_id=run_id,
            conversation_id=conversation_id,
            operation=operation,
            response_id=response_id,
            response_model=response_model,
            finish_reason=finish_reason,
            content=text,
            tool_calls=[],
            usage=usage,
            chunk_count=chunk_count,
            first_token_ms=first_token_ms,
            duration_ms=int((perf_counter() - started) * 1000),
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
        conversation_id = current_conversation_id.get()
        operation = current_llm_operation.get()
        normalized_messages = _normalize_messages(messages, allow_tool_messages=True)
        openai_tools = _openai_tools(tools)
        tool_schema_text = json.dumps(openai_tools, ensure_ascii=False)
        normalized_messages, input_tokens_estimate = self._prepare_request_context(
            system,
            normalized_messages,
            tool_schema_text,
            run_id=run_id,
            operation=operation,
        )
        request = {
            "model": self.settings.llm_model,
            "temperature": self.settings.llm_temperature,
            "messages": _canonical_request_messages(system, normalized_messages),
            "extra_body": {
                "thinking": {"type": "enabled" if self.settings.llm_thinking_enabled else "disabled"}
            },
            "tools": openai_tools,
            "tool_choice": "auto",
            "parallel_tool_calls": True,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        _add_prompt_cache_key(request, conversation_id)
        started = perf_counter()
        logger.info(
            "llm agent stream started: runId=%s conversationId=%s operation=%s model=%s baseUrl=%s "
            "messageCount=%d toolCount=%d temperature=%s thinkingEnabled=%s promptCacheKey=%s "
            "estimatedInputTokens=%d",
            run_id,
            conversation_id,
            operation,
            self.settings.llm_model,
            self.settings.llm_base_url,
            len(request["messages"]),
            len(openai_tools),
            self.settings.llm_temperature,
            self.settings.llm_thinking_enabled,
            request.get("prompt_cache_key", "-"),
            input_tokens_estimate,
        )
        self._log_input(run_id, conversation_id, operation, system, normalized_messages, openai_tools)
        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        calls: dict[int, dict[str, str]] = {}
        finish_reason = None
        response_id = "-"
        response_model = self.settings.llm_model
        usage = None
        chunk_count = 0
        first_token_ms = None
        try:
            stream = await self._client().chat.completions.create(**request)
            async for chunk in stream:
                chunk_count += 1
                response_id = getattr(chunk, "id", None) or response_id
                response_model = getattr(chunk, "model", None) or response_model
                usage = getattr(chunk, "usage", None) or usage
                for choice in getattr(chunk, "choices", None) or []:
                    finish_reason = choice.finish_reason or finish_reason
                    delta = choice.delta
                    reasoning = getattr(delta, "reasoning_content", None)
                    if reasoning:
                        reasoning_parts.append(reasoning)
                    content = getattr(delta, "content", None)
                    if content:
                        if first_token_ms is None:
                            first_token_ms = int((perf_counter() - started) * 1000)
                        content_parts.append(content)
                        on_text_delta(content)
                    for call in getattr(delta, "tool_calls", None) or []:
                        if first_token_ms is None:
                            first_token_ms = int((perf_counter() - started) * 1000)
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
        except openai.APIStatusError as error:
            if _is_context_window_error(error):
                logger.warning(
                    "llm agent stream context window exceeded: runId=%s operation=%s "
                    "status=%s providerMessage=%s",
                    run_id,
                    operation,
                    error.status_code,
                    _provider_error_message(error),
                )
                raise ContextWindowExceededError(
                    "LLM 供应商拒绝了过长上下文，需要执行响应式压缩。"
                ) from error
            logger.exception("llm agent stream failed: runId=%s", run_id)
            raise InvalidOperationError(
                f"LLM 流式请求失败：HTTP {error.status_code}"
            ) from error
        except openai.APIError as error:
            logger.exception("llm agent stream failed: runId=%s", run_id)
            raise InvalidOperationError(f"LLM 流式请求失败：{error.__class__.__name__}") from error

        content = "".join(content_parts)
        # OpenAI 兼容模型允许同一条 assistant 消息同时携带可见说明与 Tool Call。
        # content 由上层作为过程消息展示，tool_calls 仍交给 LangGraph 执行；两者不能互斥。
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
        self._log_stream_response(
            run_id=run_id,
            conversation_id=conversation_id,
            operation=operation,
            response_id=response_id,
            response_model=response_model,
            finish_reason=finish_reason,
            content=content,
            reasoning="".join(reasoning_parts),
            tool_calls=tool_calls,
            usage=usage,
            chunk_count=chunk_count,
            first_token_ms=first_token_ms,
            duration_ms=int((perf_counter() - started) * 1000),
        )
        return AIMessage(content=content, tool_calls=tool_calls)

    def _log_input(
        self,
        run_id: str,
        conversation_id: str,
        operation: str,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
    ) -> None:
        """记录模型实际收到的输入；所有内容均受配置的字符上限约束。"""
        if not self.settings.llm_log_io:
            return
        logger.info(
            "llm input BEGIN runId=%s conversationId=%s operation=%s model=%s\n"
            "[system]\n%s\n[messages]\n%s\n[tools]\n%s\nllm input END",
            run_id,
            conversation_id,
            operation,
            self.settings.llm_model,
            truncate_text(system, self.settings.llm_log_input_chars),
            truncate_text(_format_messages(messages), self.settings.llm_log_input_chars),
            truncate_text(_format_tools(tools), self.settings.llm_log_input_chars),
        )

    def _log_stream_response(
        self,
        *,
        run_id: str,
        conversation_id: str,
        operation: str,
        response_id: str,
        response_model: str,
        finish_reason: str | None,
        content: str,
        tool_calls: list[dict[str, Any]],
        usage: Any,
        chunk_count: int,
        first_token_ms: int | None,
        duration_ms: int,
        reasoning: str = "",
    ) -> None:
        """把流式分片汇总为一条可追踪响应日志，并保留服务端 usage。"""
        usage_details = _usage_details(usage)
        if self.settings.llm_log_responses:
            raw = {
                "id": response_id,
                "model": response_model,
                "finish_reason": finish_reason,
                "content": content,
                "reasoning_content": reasoning or None,
                "tool_calls": tool_calls,
                "usage": usage_details["raw"],
                "chunk_count": chunk_count,
            }
            logger.warning(
                "LLM_STREAM_RESPONSE_BEGIN runId=%s conversationId=%s operation=%s\n%s\n"
                "LLM_STREAM_RESPONSE_END runId=%s operation=%s",
                run_id,
                conversation_id,
                operation,
                truncate_text(
                    json.dumps(raw, ensure_ascii=False, indent=2),
                    self.settings.llm_log_output_chars,
                ),
                run_id,
                operation,
            )
        if self.settings.llm_log_io:
            logger.info(
                "llm output BEGIN runId=%s conversationId=%s operation=%s model=%s finishReason=%s\n"
                "[content]\n%s\n[reasoning_content]\n%s\n[tool_calls]\n%s\nllm output END",
                run_id,
                conversation_id,
                operation,
                response_model,
                finish_reason,
                truncate_text(content, self.settings.llm_log_output_chars),
                truncate_text(reasoning, self.settings.llm_log_output_chars) if reasoning else "(无)",
                truncate_text(
                    json.dumps(tool_calls, ensure_ascii=False, indent=2) if tool_calls else "(无工具调用)",
                    self.settings.llm_log_output_chars,
                ),
            )
        logger.info(
            "llm stream completed: runId=%s conversationId=%s operation=%s model=%s responseId=%s "
            "finishReason=%s chunks=%d firstTokenMs=%s outputChars=%d toolCalls=%d "
            "promptTokens=%s completionTokens=%s totalTokens=%s cachedTokens=%s cacheStatus=%s "
            "cacheHitRate=%s usage=%s durationMs=%d",
            run_id,
            conversation_id,
            operation,
            response_model,
            response_id,
            finish_reason,
            chunk_count,
            first_token_ms,
            len(content),
            len(tool_calls),
            usage_details["prompt_tokens"],
            usage_details["completion_tokens"],
            usage_details["total_tokens"],
            usage_details["cached_tokens"],
            usage_details["cache_status"],
            usage_details["cache_hit_rate"],
            json.dumps(usage_details["raw"], ensure_ascii=False, separators=(",", ":")),
            duration_ms,
        )

    async def _request(
        self,
        system: str,
        messages: list[Any],
        *,
        tools: list[dict[str, Any]] | None = None,
    ):
        run_id = current_run_id.get()
        conversation_id = current_conversation_id.get()
        operation = current_llm_operation.get()
        normalized_messages = _normalize_messages(messages, allow_tool_messages=tools is not None)
        openai_tools = _openai_tools(tools) if tools is not None else None
        tool_schema_text = json.dumps(openai_tools, ensure_ascii=False) if openai_tools is not None else ""
        normalized_messages, input_tokens_estimate = self._prepare_request_context(
            system,
            normalized_messages,
            tool_schema_text,
            run_id=run_id,
            operation=operation,
        )
        started = perf_counter()
        logger.info(
            "llm request started: runId=%s conversationId=%s operation=%s provider=openai model=%s "
            "baseUrl=%s messageCount=%d toolCount=%d temperature=%s thinkingEnabled=%s "
            "promptCacheKey=%s inputChars=%d estimatedInputTokens=%d maxContextSize=%d",
            run_id,
            conversation_id,
            operation,
            self.settings.llm_model,
            self.settings.llm_base_url,
            len(normalized_messages) + 1,
            len(openai_tools or []),
            self.settings.llm_temperature,
            self.settings.llm_thinking_enabled,
            _prompt_cache_key(conversation_id) or "-",
            len(system) + sum(len(message["content"]) for message in normalized_messages) + len(tool_schema_text),
            input_tokens_estimate,
            self.settings.max_context_size,
        )
        # 记录模型“实际看到的输入”：系统提示 + 历史/工具消息。截断后写入，
        # 便于排查模型为何给出某个回答，同时避免巨型工具结果刷屏日志。
        self._log_input(run_id, conversation_id, operation, system, normalized_messages, openai_tools)
        try:
            request: dict[str, Any] = {
                "model": self.settings.llm_model,
                "temperature": self.settings.llm_temperature,
                "messages": _canonical_request_messages(system, normalized_messages),
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
                        "parallel_tool_calls": True,
                    }
                )
            _add_prompt_cache_key(request, conversation_id)
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
            if _is_context_window_error(error):
                raise ContextWindowExceededError(
                    "LLM 供应商拒绝了过长上下文，需要执行响应式压缩。"
                ) from error
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
                truncate_text(_serialize_response(response), self.settings.llm_log_output_chars),
                run_id,
                operation,
            )
        # 记录模型“实际返回的输出”：文本内容与工具调用（名称 + 参数）。
        # 这是观察 Agent 决策（调用了哪个工具、传了什么参数）的核心日志。
        if self.settings.llm_log_io:
            message = choice.message
            tool_calls = getattr(message, "tool_calls", None) or []
            logger.info(
                "llm output BEGIN runId=%s conversationId=%s operation=%s model=%s finishReason=%s\n"
                "[content]\n%s\n[tool_calls]\n%s\nllm output END",
                run_id,
                conversation_id,
                operation,
                self.settings.llm_model,
                choice.finish_reason,
                truncate_text(message.content or "", self.settings.llm_log_output_chars),
                truncate_text(_format_tool_calls(tool_calls), self.settings.llm_log_output_chars),
            )
        if choice.finish_reason == "length":
            raise InvalidOperationError("LLM 输出达到 Token 上限，结果不完整。")
        usage = getattr(response, "usage", None)
        usage_details = _usage_details(usage)
        logger.info(
            "llm request completed: runId=%s conversationId=%s operation=%s model=%s requestId=%s "
            "responseId=%s finishReason=%s promptTokens=%s completionTokens=%s totalTokens=%s "
            "cachedTokens=%s cacheStatus=%s cacheHitRate=%s usage=%s durationMs=%d",
            run_id,
            conversation_id,
            operation,
            self.settings.llm_model,
            getattr(response, "_request_id", None) or "-",
            getattr(response, "id", None) or "-",
            choice.finish_reason,
            usage_details["prompt_tokens"],
            usage_details["completion_tokens"],
            usage_details["total_tokens"],
            usage_details["cached_tokens"],
            usage_details["cache_status"],
            usage_details["cache_hit_rate"],
            json.dumps(usage_details["raw"], ensure_ascii=False, separators=(",", ":")),
            int((perf_counter() - started) * 1000),
        )
        return choice, response

    def _prepare_request_context(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tool_schema_text: str,
        *,
        run_id: str,
        operation: str,
    ) -> tuple[list[dict[str, Any]], int]:
        """供应商边界只做最终预算校验，不再维护第二套百分比压缩策略。

        Agent 请求已经由 AgentContextManager 完成多阶段投影；这里仅处理绕过
        AgentContextManager 的直接 LLM 调用，以及估算误差导致的最后工具预算收缩。
        """
        prepared = list(messages)
        before_tokens = _estimate_request_tokens(system, prepared, tool_schema_text)
        after_tokens = before_tokens
        compacted_tool_messages = 0
        if after_tokens > self.settings.max_context_size:
            # 固定提示词和普通消息先占用总预算，剩余额度由本次所有工具结果平均共享。
            # 这是根据当前请求动态计算的，不再维护单条工具结果固定上限。
            tool_count = sum(1 for message in prepared if message.get("role") == "tool")
            if tool_count:
                without_tool_content = [
                    {**message, "content": ""} if message.get("role") == "tool" else message
                    for message in prepared
                ]
                fixed_tokens = _estimate_request_tokens(
                    system,
                    without_tool_content,
                    tool_schema_text,
                )
                available_tokens = max(1, self.settings.max_context_size - fixed_tokens)
                # 结构化截断会附加 truncated/notice 等元数据，为每条结果预留封装开销。
                envelope_reserve = 64 * tool_count
                per_tool_tokens = max(
                    1,
                    (available_tokens - envelope_reserve) // tool_count,
                )
                original = prepared
                prepared = trim_tool_results(prepared, per_tool_tokens)
                compacted_tool_messages = sum(
                    1
                    for before, after in zip(original, prepared, strict=True)
                    if before.get("role") == "tool"
                    and before.get("content") != after.get("content")
                )
                after_tokens = _estimate_request_tokens(system, prepared, tool_schema_text)
        logger.info(
            "llm context checked: runId=%s operation=%s beforeTokens=%d afterTokens=%d "
            "maxContextSize=%d finalGuardTriggered=%s compactedToolMessages=%d",
            run_id,
            operation,
            before_tokens,
            after_tokens,
            self.settings.max_context_size,
            before_tokens > self.settings.max_context_size,
            compacted_tool_messages,
        )
        if after_tokens > self.settings.max_context_size:
            raise InvalidOperationError(
                f"LLM 上下文压缩后仍约 {after_tokens} Token，超过输入预算 "
                f"{self.settings.max_context_size} Token。"
            )
        return prepared, after_tokens

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


def _canonical_request_messages(
    system: str, messages: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """构造唯一 System Prompt 前缀，禁止历史或摘要注入第二条 system 消息。"""
    if not system.strip():
        raise InvalidOperationError("LLM System Prompt 不能为空。")
    nested_system_count = sum(1 for message in messages if message.get("role") == "system")
    if nested_system_count:
        raise InvalidOperationError(
            "LLM 历史上下文中出现额外 system 消息；Agent 身份只能由当前 System Prompt 定义。"
        )
    return [{"role": "system", "content": system}, *messages]


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


def _is_context_window_error(error: openai.APIStatusError) -> bool:
    """仅识别供应商明确报告的输入窗口超限，避免把普通 400 错误误判为可重试。"""
    body = getattr(error, "body", None)
    candidates = [_provider_error_message(error), str(error)]
    if isinstance(body, dict):
        nested = body.get("error")
        if isinstance(nested, dict):
            candidates.extend(
                str(nested.get(key) or "")
                for key in ("code", "type", "message")
            )
        candidates.extend(str(body.get(key) or "") for key in ("code", "type", "message"))
    text = " ".join(candidates).lower()
    markers = (
        "context_length_exceeded",
        "context window",
        "maximum context length",
        "prompt is too long",
        "prompt too long",
        "input tokens exceed",
        "上下文长度",
        "上下文过长",
    )
    return any(marker in text for marker in markers)


def _serialize_response(response: Any) -> str:
    model_dump_json = getattr(response, "model_dump_json", None)
    if callable(model_dump_json):
        return model_dump_json(indent=2)
    return repr(response)


def _prompt_cache_key(conversation_id: str) -> str | None:
    """仅使用真实会话 ID 作为缓存键，避免把缺省占位符发送给供应商。"""
    value = conversation_id.strip()
    return value if value and value != "-" else None


def _add_prompt_cache_key(request: dict[str, Any], conversation_id: str) -> None:
    """为同一会话提供稳定缓存键；Kimi 会据此优化重复上下文的缓存命中。"""
    cache_key = _prompt_cache_key(conversation_id)
    if cache_key:
        request["prompt_cache_key"] = cache_key


def _usage_details(usage: Any) -> dict[str, Any]:
    """兼容 OpenAI 标准字段和供应商扩展字段，提取 Token/缓存诊断信息。"""
    raw = _to_log_dict(usage)
    prompt_tokens = _first_int(raw, ("prompt_tokens",), ("input_tokens",))
    completion_tokens = _first_int(raw, ("completion_tokens",), ("output_tokens",))
    total_tokens = _first_int(raw, ("total_tokens",))
    # Kimi 将 cached_tokens 放在 usage 顶层；OpenAI 可能放在输入详情中。
    cached_tokens = _first_int(
        raw,
        ("cached_tokens",),
        ("prompt_tokens_details", "cached_tokens"),
        ("input_tokens_details", "cached_tokens"),
        ("cache_read_input_tokens",),
    )
    cache_status = "unknown" if cached_tokens is None else ("hit" if cached_tokens > 0 else "miss")
    cache_hit_rate = "unknown"
    if cached_tokens is not None and prompt_tokens:
        cache_hit_rate = f"{cached_tokens / prompt_tokens:.2%}"
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "cached_tokens": cached_tokens,
        "cache_status": cache_status,
        "cache_hit_rate": cache_hit_rate,
        "raw": raw,
    }


def _to_log_dict(value: Any) -> dict[str, Any]:
    """把 SDK 的 Pydantic 模型或测试替身转为可 JSON 序列化字典。"""
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(exclude_none=True)
        return dumped if isinstance(dumped, dict) else {"value": dumped}
    try:
        return {
            key: item
            for key, item in vars(value).items()
            if not key.startswith("_") and item is not None
        }
    except TypeError:
        return {"value": str(value)}


def _first_int(source: dict[str, Any], *paths: tuple[str, ...]) -> int | None:
    for path in paths:
        value: Any = source
        for key in path:
            if not isinstance(value, dict) or key not in value:
                break
            value = value[key]
        else:
            if isinstance(value, bool):
                continue
            if isinstance(value, (int, float)):
                return int(value)
    return None


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
