"""面向模型的消息上下文构建器。

模型只看到真实会话语义：长期记忆、历史对话、当前用户原话和原生工具轨迹。
LangGraph State、预算、观察列表与结果目录由程序维护，不伪装成 UserMessage。
"""

from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AnyMessage

from app.config import Settings
from app.context import estimate_tokens
from app.context.manager import AgentContextManager
from app.workflow.state import AnalysisState


@dataclass(frozen=True)
class AgentContext:
    """一次模型调用所需的完整上下文快照。

    属性：
        payload: 仅供后端观测的最小当前请求信息，不直接发送给模型。
        messages: 长期记忆 + 历史对话 + 当前真实用户消息 + 工具轨迹。
        stats: 统计信息，目前包含 ``estimatedTokens``（上下文估算 token 数）与
            ``compactedToolMessages``（被压缩的工具消息条数）。
    """

    payload: dict[str, Any]
    messages: list[Any]
    stats: dict[str, Any]
    compaction_state: dict[str, Any]


class AgentContextBuilder:
    """把持久化的工作流状态投影为面向单一模型调用的有界上下文。

    长期记忆使用明确的 Meta 标签，真实用户输入始终保持原文；工具循环只继续
    LangGraph 中已有的 AIMessage/ToolMessage，不重复添加运行状态。
    """

    def __init__(
        self,
        settings: Settings,
        result_history,
        context_manager: AgentContextManager | None = None,
    ):
        self.settings = settings
        self.result_history = result_history
        self.context_manager = context_manager

    async def build(
        self,
        state: AnalysisState,
        *,
        system: str = "",
        tools: list[dict[str, Any]] | None = None,
        force_full_compact: bool = False,
    ) -> AgentContext:
        user_input = str(state["query"])
        payload = {"query": user_input}
        current_message = {"role": "user", "content": user_input}
        memory_messages = _memory_and_history_messages(state)
        compaction_state = dict(state.get("context_compaction") or {})
        compaction_stats: dict[str, Any] = {
            "beforeTokens": 0,
            "afterTokens": 0,
            "stages": [],
            "toolResultsTrimmed": 0,
            "microCompactedRounds": 0,
            "updated": False,
        }
        if self.context_manager is not None:
            if not system:
                raise ValueError("启用 AgentContextManager 时必须提供固定 System Prompt")
            projection = await self.context_manager.prepare(
                state=state,
                conversation_messages=memory_messages,
                current_message=current_message,
                system=system,
                tools=tools or [],
                force_full_compact=force_full_compact,
            )
            messages = projection.messages
            compaction_state = projection.compaction_state
            compaction_stats = projection.stats
            compacted = int(projection.stats["toolResultsTrimmed"]) + int(
                projection.stats["microCompactedRounds"]
            )
        else:
            # 测试和非 Agent 调用保持原有投影方式。
            messages = [
                *memory_messages,
                current_message,
                *_project_tool_messages(state.get("messages", []))[0],
            ]
            compacted = 0
        return AgentContext(
            payload=payload,
            messages=messages,
            # 估算上下文 token 数，供上层监控；compactedToolMessages 反映压缩力度
            stats={
                "estimatedTokens": (
                    int(compaction_stats["afterTokens"])
                    if self.context_manager is not None
                else sum(
                    estimate_tokens(str(getattr(message, "content", message)))
                    for message in messages
                )
                ),
                "compactedToolMessages": compacted,
                **compaction_stats,
            },
            compaction_state=compaction_state,
        )


def _project_tool_messages(messages: list[AnyMessage]) -> tuple[list[AnyMessage], int]:
    """保留原生工具轨迹；大小控制由发送前的统一压缩器负责。"""
    return list(messages), 0


def _memory_and_history_messages(state: AnalysisState) -> list[dict[str, str]]:
    """投影长期记忆、会话摘要和最近原始对话，均与当前 UserMessage 分离。"""
    context = state.get("memory_context", {})
    messages: list[dict[str, str]] = []
    long_term = [
        str(item).strip()
        for item in context.get("longTermMemories", [])
        if str(item).strip()
    ]
    if long_term:
        messages.append(
            {
                "role": "user",
                "content": (
                    "长期记忆（以下是跨会话保留的用户偏好和约定，仅在与当前任务相关时使用）：\n"
                    + "\n".join(f"- {item}" for item in long_term)
                ),
            }
        )
    summary = str(context.get("summary") or "").strip()
    if summary:
        messages.append(
            {
                "role": "user",
                "content": f"会话摘要：\n{summary}",
            }
        )
    for item in context.get("recentMessages", []):
        role, content = str(item.get("role") or ""), str(item.get("content") or "")
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})
    return messages
