"""把项目 LLM 端口适配为 LangChain 标准 ChatModel。"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Sequence
from contextvars import ContextVar
from typing import Any

from langchain_core.callbacks import AsyncCallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import ConfigDict, PrivateAttr

from app.workflow.ports import LlmClient


# Middleware 在一次模型调用前写入流式事件处理器，ChatModel 只负责转发 Token。
agent_text_delta_handler: ContextVar[Callable[[str], None] | None] = ContextVar(
    "agent_text_delta_handler",
    default=None,
)


class LangChainChatModelAdapter(BaseChatModel):
    """复用现有 Kimi/OpenAI 客户端，同时满足 ``create_agent`` 的模型协议。

    供应商特有的 thinking、prompt cache、错误映射和原始日志仍由
    ``OpenAiChatClient`` 负责；工具绑定、Agent 循环和消息协议交给 LangChain。
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    _client: LlmClient = PrivateAttr()
    _bound_tools: list[dict[str, Any]] = PrivateAttr(default_factory=list)

    def __init__(
        self,
        client: LlmClient,
        *,
        bound_tools: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__()
        self._client = client
        self._bound_tools = list(bound_tools or [])

    @property
    def _llm_type(self) -> str:
        return "data-agent-openai-compatible"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {"adapter": self._llm_type}

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable[..., Any] | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> LangChainChatModelAdapter:
        """绑定工具，但不重复实现 LangChain 的工具执行逻辑。"""
        del tool_choice, kwargs
        specifications = [_to_client_tool_specification(tool) for tool in tools]
        return LangChainChatModelAdapter(self._client, bound_tools=specifications)

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del stop, kwargs
        system, conversation = _split_system_message(messages)
        external_delta_handler = agent_text_delta_handler.get()

        async def publish_token(delta: str) -> None:
            if run_manager is not None:
                await run_manager.on_llm_new_token(delta)

        def on_text_delta(delta: str) -> None:
            if external_delta_handler is not None:
                external_delta_handler(delta)
            # OpenAiChatClient 的回调是同步接口；LangChain callback 由事件循环调度。
            if run_manager is not None:
                import asyncio

                asyncio.create_task(publish_token(delta))

        response = await self._client.complete_tool_messages(
            system,
            _to_port_messages(conversation),
            tools=self._bound_tools,
            on_text_delta=on_text_delta,
        )
        return ChatResult(generations=[ChatGeneration(message=response)])

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        raise NotImplementedError("DataAgent ChatModel 仅支持异步调用")

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        """Agent 当前由底层客户端流式消费；这里保留标准接口并返回完整消息块。"""
        result = await self._agenerate(messages, stop, run_manager, **kwargs)
        message = result.generations[0].message
        yield ChatGenerationChunk(
            message=AIMessageChunk(
                content=message.content,
                tool_calls=message.tool_calls,
            )
        )


def _split_system_message(messages: list[BaseMessage]) -> tuple[str, list[BaseMessage]]:
    """提取固定系统提示词，避免把 SystemMessage 重复放入普通消息列表。"""
    systems: list[str] = []
    conversation: list[BaseMessage] = []
    for message in messages:
        if isinstance(message, SystemMessage):
            systems.append(str(message.content))
        else:
            conversation.append(message)
    return "\n\n".join(systems), conversation


def _to_port_messages(messages: list[BaseMessage]) -> list[Any]:
    """兼容既有 LLM 端口：用户消息用字典，原生工具轨迹保留消息对象。

    ToolMessage 必须保留 ``tool_call_id`` 等结构，不能为了兼容普通聊天消息而
    展平成只有 role/content 的字典，否则模型看不到已经执行过哪些工具。
    """
    converted: list[Any] = []
    for message in messages:
        if isinstance(message, HumanMessage):
            converted.append({"role": "user", "content": message.content})
        else:
            converted.append(message)
    return converted


def _to_client_tool_specification(
    tool: dict[str, Any] | type | Callable[..., Any] | BaseTool,
) -> dict[str, Any]:
    """把 LangChain 工具转换成现有 LLM 端口使用的扁平函数描述。"""
    converted = convert_to_openai_tool(tool)
    function = converted.get("function")
    if not isinstance(function, dict):
        raise TypeError(f"不支持的工具定义：{converted}")
    return {
        "name": str(function["name"]),
        "description": str(function.get("description") or ""),
        "parameters": function.get("parameters") or {"type": "object", "properties": {}},
    }
