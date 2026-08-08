"""DataAgent 的 Agent Middleware。

框架负责 ReAct 循环；本模块只保留项目特有的上下文投影、调用护栏、
可观测事件和最终结果构建。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import (
    ExtendedModelResponse,
    ModelRequest,
    ModelResponse,
    ToolCallRequest,
)
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langgraph.config import get_stream_writer
from langgraph.types import Command

from app.config import get_settings
from app.domain.errors import ContextWindowExceededError
from app.observability.logging_setup import truncate_text
from app.workflow.chat_model import agent_text_delta_handler
from app.workflow.nodes.analysis import (
    AnalysisNodes,
    _budget_exhausted_message,
    _normalize_tool_calls,
    _validate_parallel_state_writes,
)
from app.workflow.prompts import AGENT_SYSTEM
from app.workflow.state import AnalysisState


logger = logging.getLogger(__name__)


class DataAgentMiddleware(AgentMiddleware[AnalysisState, None]):
    """把项目领域逻辑挂到 LangChain Agent 的标准生命周期上。"""

    state_schema = AnalysisState

    def __init__(self, nodes: AnalysisNodes) -> None:
        self.nodes = nodes

    async def abefore_agent(self, state: AnalysisState, runtime: Any) -> dict[str, Any] | None:
        del runtime
        guard = await self.nodes.input_guard(state)
        if guard.get("result_mode") != "blocked_prompt_injection":
            return guard
        # 被输入守卫拦截时不调用模型，但仍生成统一的前端分析结构。
        blocked_state = {**state, **guard}
        return {**guard, **(await self.nodes.result(blocked_state))}

    async def aafter_agent(self, state: AnalysisState, runtime: Any) -> dict[str, Any] | None:
        del runtime
        final_state = dict(state)
        if not final_state.get("final_answer"):
            for message in reversed(final_state.get("messages", [])):
                if isinstance(message, AIMessage) and not message.tool_calls:
                    final_state["final_answer"] = str(message.content or "")
                    break
        if not final_state.get("result_mode") and not final_state.get("query_results"):
            final_state["result_mode"] = "conversation"
        return {
            "final_answer": final_state.get("final_answer", ""),
            "result_mode": final_state.get("result_mode"),
            **(await self.nodes.result(final_state)),
        }

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Any,
    ) -> ModelResponse | ExtendedModelResponse:
        state: AnalysisState = request.state
        iteration = int(state.get("agent_iterations", 0))
        writer = get_stream_writer()
        writer(
            {
                "type": "stage.started",
                "stage": "agent_decide",
                "message": "正在确定下一步分析动作",
            }
        )

        if state.get("result_mode") == "blocked_prompt_injection":
            # AgentMiddleware.before_agent 只能更新状态，不能跳转图节点。这里在模型
            # 边界确定性短路，既不调用供应商，也不让被拦截输入进入任何工具。
            text = str(state.get("error") or "请求包含不安全指令，已停止处理。")
            message = AIMessage(content=text)
            return ExtendedModelResponse(
                model_response=ModelResponse(result=[message]),
                command=Command(
                    update={
                        "messages": [message],
                        "final_answer": text,
                        "result_mode": "blocked_prompt_injection",
                        "agent_decision": {
                            "action": "finish",
                            "actions": [],
                            "reasonSummary": "输入安全检查未通过",
                            "arguments": {},
                        },
                    }
                ),
            )

        if self.nodes.agent_context_builder is None:
            raise RuntimeError("AgentContextBuilder 未配置")
        tool_specifications = self.nodes.tool_registry.specifications()
        context = await self.nodes.agent_context_builder.build(
            state,
            system=AGENT_SYSTEM,
            tools=tool_specifications,
        )
        message_id = f"agent-message-{iteration + 1}"
        streamed_parts: list[str] = []

        def on_text_delta(delta: str) -> None:
            if not streamed_parts:
                writer(
                    {
                        "type": "agent_message.started",
                        "stage": "agent_decide",
                        "data": {"messageId": message_id, "iteration": iteration + 1},
                    }
                )
            streamed_parts.append(delta)
            writer(
                {
                    "type": "agent_message.delta",
                    "stage": "agent_decide",
                    "data": {"messageId": message_id, "delta": delta},
                }
            )

        token = agent_text_delta_handler.set(on_text_delta)
        try:
            try:
                response = await handler(
                    request.override(
                        messages=context.messages,
                        system_message=SystemMessage(content=AGENT_SYSTEM),
                    )
                )
            except ContextWindowExceededError:
                # 响应式压缩暂时保持原语义，后续可独立拆为通用重试中间件。
                writer(
                    {
                        "type": "context.compaction.retrying",
                        "stage": "agent_decide",
                        "data": {
                            "iteration": iteration + 1,
                            "reason": "provider_context_window_exceeded",
                        },
                    }
                )
                context = await self.nodes.agent_context_builder.build(
                    {**state, "context_compaction": context.compaction_state},
                    system=AGENT_SYSTEM,
                    tools=tool_specifications,
                    force_full_compact=True,
                )
                response = await handler(
                    request.override(
                        messages=context.messages,
                        system_message=SystemMessage(content=AGENT_SYSTEM),
                    )
                )
        finally:
            agent_text_delta_handler.reset(token)

        message = _last_ai_message(response)
        original_tool_calls = list(message.tool_calls)
        tool_calls = _normalize_tool_calls(
            original_tool_calls,
            state=state,
            schema_search_limit=self.nodes.retriever.settings.agent_max_schema_searches,
            sql_execution_limit=self.nodes.retriever.settings.agent_max_sql_executions,
        )
        _validate_parallel_state_writes(tool_calls)
        if tool_calls != original_tool_calls:
            message = AIMessage(content=message.content, tool_calls=tool_calls)
            response = ModelResponse(result=[*response.result[:-1], message])

        if streamed_parts:
            kind = "narration" if original_tool_calls or state.get("query_results") else "final"
            writer(
                {
                    "type": "agent_message.completed",
                    "stage": "agent_decide",
                    "data": {
                        "messageId": message_id,
                        "iteration": iteration + 1,
                        "kind": kind,
                        "text": "".join(streamed_parts),
                        "toolNames": [call["name"] for call in original_tool_calls],
                    },
                }
            )

        action = tool_calls[0]["name"] if tool_calls else "finish"
        if not tool_calls and original_tool_calls:
            message = AIMessage(
                content=_budget_exhausted_message(original_tool_calls, state, self.nodes.retriever)
            )
            response = ModelResponse(result=[*response.result[:-1], message])
        updates: dict[str, Any] = {
            # create_agent 会先写入模型消息；这里携带同 ID 消息，让执行器在同一个
            # update 中同时看到工具调用和决策元数据。add_messages 会按 ID 替换，
            # 不会在 Graph State 中产生重复消息。
            "messages": [message],
            "agent_decision": {
                "action": action,
                "actions": [
                    {"action": call["name"], "arguments": call["args"]}
                    for call in tool_calls
                ],
                "reasonSummary": str(message.content or ""),
                "arguments": tool_calls[0]["args"] if tool_calls else {},
            },
            "agent_iterations": iteration + 1,
        }
        if context.stats.get("updated"):
            updates["context_compaction"] = context.compaction_state
            writer(
                {
                    "type": "context.compacted",
                    "stage": "agent_decide",
                    "data": {
                        "sequence": context.compaction_state.get("sequence"),
                        "mode": context.compaction_state.get("mode"),
                        "stages": context.compaction_state.get("stages", []),
                        "beforeTokens": context.compaction_state.get("beforeTokens"),
                        "afterTokens": context.compaction_state.get("afterTokens"),
                        "coveredMessageCount": context.compaction_state.get("coveredMessageCount"),
                    },
                }
            )
        if action == "finish":
            updates["final_answer"] = str(message.content or "") or "分析已结束，但模型没有返回可展示的结论。"
            if not state.get("query_results"):
                updates["result_mode"] = state.get("result_mode") or "conversation"
                writer(
                    {
                        "type": "final_answer.completed",
                        "stage": "agent_decide",
                        "data": {"text": updates["final_answer"]},
                    }
                )
        return ExtendedModelResponse(
            model_response=response,
            command=Command(update=updates),
        )

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Any,
    ) -> ToolMessage | Command:
        """使用框架工具切面记录调用，不再继承并覆盖 ``ToolNode``。"""
        settings = get_settings()
        call = request.tool_call
        logger.info(
            "tool call started: name=%s args=%s",
            call.get("name"),
            truncate_text(
                json.dumps(call.get("args") or {}, ensure_ascii=False),
                settings.tool_log_content_chars,
            ),
        )
        result = await handler(request)
        for message in _tool_messages(result):
            logger.info(
                "tool call completed: name=%s toolCallId=%s content=%s",
                call.get("name"),
                message.tool_call_id,
                truncate_text(str(message.content or ""), settings.tool_log_content_chars),
            )
        return result


def _last_ai_message(response: ModelResponse) -> AIMessage:
    for message in reversed(response.result):
        if isinstance(message, AIMessage):
            return message
    raise RuntimeError("Agent 模型响应中缺少 AIMessage")


def _tool_messages(result: ToolMessage | Command) -> list[ToolMessage]:
    if isinstance(result, ToolMessage):
        return [result]
    update = getattr(result, "update", None) or {}
    return [message for message in update.get("messages", []) if isinstance(message, ToolMessage)]
