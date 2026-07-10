"""LLM 客户端端口（抽象接口）。

本模块定义工作流对 LLM 的最小依赖契约 ``LlmClient``（typing.Protocol），
使工作流节点与具体 LLM 实现（如 OpenAI）解耦，便于替换与测试。
方法分为两类：自由文本/JSON 输出（complete*）与结构化模型输出（*model）以及
带原生工具调用的 ``complete_tool_messages``。
"""

from typing import Any, Protocol, TypeVar

from pydantic import BaseModel
from langchain_core.messages import AIMessage


# 结构化输出模型类型参数，限定为 Pydantic BaseModel 子类
ModelT = TypeVar("ModelT", bound=BaseModel)


class LlmClient(Protocol):
    """工作流使用的 LLM 客户端协议。

    约定：
    - ``system`` 为系统提示词，``user``/``messages`` 为用户侧输入；
    - ``*_model`` 方法会把输出解析为 ``output_type`` 指定的 Pydantic 模型；
    - ``complete_tool_messages`` 支持原生工具调用，返回携带 tool_calls 的 AIMessage。
    """

    async def complete(self, system: str, user: str) -> str: ...

    async def complete_messages(
        self, system: str, messages: list[dict[str, str]]
    ) -> str: ...

    async def complete_json(
        self, system: str, user: str
    ) -> dict[str, Any]: ...

    async def complete_model(
        self, output_type: type[ModelT], system: str, user: str
    ) -> ModelT: ...

    async def complete_messages_model(
        self,
        output_type: type[ModelT],
        system: str,
        messages: list[dict[str, str]],
    ) -> ModelT: ...

    async def complete_tool_messages(
        self,
        system: str,
        messages: list[Any],
        *,
        tools: list[dict[str, Any]],
    ) -> AIMessage: ...
