import json
import logging
import re
from time import perf_counter
from typing import Any, TypeVar

import openai
from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError

from app.config import Settings
from app.domain.errors import InvalidOperationError
from app.observability.context import current_llm_operation, current_run_id


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

    async def complete(self, system: str, user: str, *, max_tokens: int | None = None) -> str:
        run_id = current_run_id.get()
        operation = current_llm_operation.get()
        token_limit = max_tokens or self.settings.llm_max_tokens
        started = perf_counter()
        logger.info(
            "llm request started: runId=%s operation=%s provider=openai model=%s baseUrl=%s maxTokens=%d inputChars=%d",
            run_id,
            operation,
            self.settings.llm_model,
            self.settings.llm_base_url,
            token_limit,
            len(system) + len(user),
        )
        try:
            response = await self._client().chat.completions.create(
                model=self.settings.llm_model,
                max_tokens=token_limit,
                temperature=self.settings.llm_temperature,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                extra_body={
                    "thinking": {
                        "type": "enabled" if self.settings.llm_thinking_enabled else "disabled",
                    }
                },
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
        if choice.finish_reason == "length":
            raise InvalidOperationError("LLM 输出达到 Token 上限，结果不完整。")
        content = choice.message.content
        if not content:
            raise InvalidOperationError("LLM 返回内容中没有文本结果。")
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
        return content

    async def complete_json(self, system: str, user: str, *, max_tokens: int | None = None) -> dict[str, Any]:
        text = await self.complete(system, user, max_tokens=max_tokens)
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
        *,
        max_tokens: int | None = None,
    ) -> ModelT:
        operation_token = current_llm_operation.set(output_type.__name__)
        try:
            text = await self.complete(system, user, max_tokens=max_tokens)
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
