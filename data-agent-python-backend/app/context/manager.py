"""cc-haha 风格的多阶段活动上下文管理器。

完整消息仍由 LangGraph checkpoint 与 SQLite 轨迹保存；本模块只构造当前模型可见的
活动投影。处理顺序为 Tool Result Budget -> Snip -> Micro -> Context Collapse ->
Auto Compact，压缩成功后调用方可以继续同一次 Run。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage

from app.config import Settings
from app.context.compaction import message_tokens, snip_tool_content, trim_tool_content
from app.context.tokens import estimate_tokens
from app.domain.errors import InvalidOperationError
from app.workflow.ports import LlmClient
from app.workflow.prompts import RUN_CONTEXT_COMPACTION_SYSTEM


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ContextProjection:
    """一次 Agent 调用使用的活动上下文及其持久化压缩状态。"""

    messages: list[Any]
    compaction_state: dict[str, Any]
    stats: dict[str, Any]


class AgentContextManager:
    """按上下文压力逐级缩减活动消息，同时保留完整外部事实。"""

    # 贴近 cc-haha：完整压缩为摘要输出和下一次请求保留绝对空间，而不是用一组
    # 75%/82%/95% 百分比猜测。小窗口测试环境会按窗口自动收窄保留量。
    MAX_SUMMARY_OUTPUT_RESERVE = 20_000
    AUTOCOMPACT_BUFFER_TOKENS = 13_000
    COLLAPSE_COMMIT_RATIO = 0.90
    COLLAPSE_BLOCKING_RATIO = 0.95
    MAX_TOOL_RESULT_TOKENS = 50_000
    MIN_SNIP_RECLAIM_TOKENS = 256
    SNIPPED_TOOL_TOKENS = 96
    SUMMARY_INPUT_HEADROOM_TOKENS = 256
    MAX_SUMMARY_RETRIES = 3

    def __init__(self, settings: Settings, llm: LlmClient):
        self.settings = settings
        self.llm = llm

    async def prepare(
        self,
        *,
        state: dict[str, Any],
        conversation_messages: list[dict[str, str]],
        current_message: dict[str, str],
        system: str,
        tools: list[dict[str, Any]],
        force_full_compact: bool = False,
    ) -> ContextProjection:
        """构造模型活动上下文，并在必要时生成可持久化的压缩边界。"""
        previous = dict(state.get("context_compaction") or {})
        all_workflow = list(state.get("messages") or [])
        covered = min(max(int(previous.get("coveredMessageCount") or 0), 0), len(all_workflow))
        active_workflow = all_workflow[covered:]
        summary_message = _summary_message(previous)
        visible_conversation = (
            [] if previous.get("conversationCompacted") else list(conversation_messages)
        )
        workflow_projection: list[Any] = [
            *([summary_message] if summary_message else []),
            *active_workflow,
        ]
        stages: list[str] = []
        boundary_updated = False
        full_compacted = False
        before_tokens = _request_tokens(
            system, [*visible_conversation, *workflow_projection, current_message], tools
        )

        limits = self._limits()

        # Level 1：工具结果按当前请求的真实剩余空间共享预算；与全局百分比无关。
        workflow_projection, budget_trimmed, budget_reclaimed = (
            self._enforce_tool_result_budget(
                workflow_projection,
                system=system,
                conversation_messages=visible_conversation,
                current_message=current_message,
                tools=tools,
                request_limit=self.settings.max_context_size,
            )
        )
        if budget_trimmed:
            stages.append("tool_result_budget")
        after_budget = _request_tokens(
            system, [*visible_conversation, *workflow_projection, current_message], tools
        )

        # Level 2：只裁剪旧工具轮次。必须确实能回收足量 Token，并且当前请求已
        # 进入压力区；最新工具轮次仍可由 Level 1 的单轮预算约束。
        snipped = 0
        snip_reclaimed = 0
        reclaimable = _reclaimable_tool_tokens(
            workflow_projection,
            target_tokens=self.SNIPPED_TOOL_TOKENS,
        )
        if (
            after_budget >= limits["autoCompactAtTokens"]
            and reclaimable >= self.MIN_SNIP_RECLAIM_TOKENS
        ):
            workflow_projection, snipped, snip_reclaimed = self._snip(
                workflow_projection
            )
            if snipped:
                stages.append("snip")

        # Level 3：Snip 后仍处于 90% Collapse 区间时，按完整 API Round 折叠，
        # 不能留下孤立 ToolMessage。
        after_snip = _request_tokens(
            system, [*visible_conversation, *workflow_projection, current_message], tools
        )
        micro_rounds = 0
        micro_reclaimed = 0
        if after_snip >= limits["collapseCommitAtTokens"]:
            before_micro = after_snip
            workflow_projection, micro_rounds = _micro_compact_rounds(
                workflow_projection
            )
            micro_reclaimed = max(
                0,
                before_micro
                - _request_tokens(
                    system,
                    [*visible_conversation, *workflow_projection, current_message],
                    tools,
                ),
            )
            if micro_rounds:
                stages.append("micro")

        # Level 4：把当前边界之后的完整运行轨迹合并进结构化运行摘要。
        after_micro = _request_tokens(
            system, [*visible_conversation, *workflow_projection, current_message], tools
        )
        compaction_state = previous
        if (
            after_micro >= limits["collapseCommitAtTokens"]
            and active_workflow
        ):
            summary, dropped_rounds = await self._summarize(
                mode="collapse",
                existing_summary=previous.get("summary"),
                messages=_without_context_summary(workflow_projection),
                current_message=current_message,
            )
            compaction_state = self._next_state(
                previous,
                mode="collapse",
                summary=summary,
                covered_message_count=len(all_workflow),
                before_tokens=before_tokens,
                dropped_rounds=dropped_rounds,
                stages=[*stages, "context_collapse"],
            )
            workflow_projection = [_summary_message(compaction_state)]
            stages.append("context_collapse")
            boundary_updated = True

        # Level 5：局部折叠后仍过大时，连会话历史一起生成全量恢复摘要。
        after_collapse = _request_tokens(
            system, [*visible_conversation, *workflow_projection, current_message], tools
        )
        # Context Collapse 开启时遵循 cc-haha 的竞态规避策略：不在绝对
        # autoCompactAt 阈值抢先全量压缩，只有达到 95% blocking 阈值且局部
        # Collapse 后仍放不下，才执行 Full Compact。
        if force_full_compact or after_collapse >= limits["collapseBlockingAtTokens"]:
            full_stage = "reactive_compact" if force_full_compact else "auto_compact"
            summary, dropped_rounds = await self._summarize(
                mode="reactive" if force_full_compact else "auto",
                existing_summary=compaction_state.get("summary"),
                messages=[
                    *visible_conversation,
                    *_without_context_summary(workflow_projection),
                ],
                current_message=current_message,
            )
            compaction_state = self._next_state(
                compaction_state,
                mode="reactive" if force_full_compact else "auto",
                summary=summary,
                covered_message_count=len(all_workflow),
                before_tokens=before_tokens,
                dropped_rounds=dropped_rounds,
                stages=[*stages, full_stage],
            )
            visible_conversation = []
            workflow_projection = [_summary_message(compaction_state)]
            current_message = _compact_current_message(current_message)
            stages.append(full_stage)
            boundary_updated = True
            full_compacted = True

        # 摘要属于 Meta 前缀；真实用户输入只出现一次，工具轨迹严格位于其后。
        summary_projection = [
            message for message in workflow_projection if _is_context_summary(message)
        ]
        active_projection = [
            message for message in workflow_projection if not _is_context_summary(message)
        ]
        final_messages = [
            *summary_projection,
            *([] if full_compacted else visible_conversation),
            current_message,
            *active_projection,
        ]
        after_tokens = _request_tokens(system, final_messages, tools)
        if after_tokens > self.settings.max_context_size:
            raise InvalidOperationError(
                "多阶段上下文压缩后仍无法满足模型输入窗口："
                f"afterTokens={after_tokens}, "
                f"maxContextSize={self.settings.max_context_size}, "
                f"stages={stages or ['none']}。"
            )
        if compaction_state:
            compaction_state = {**compaction_state, "afterTokens": after_tokens}
        logger.info(
            "agent context projected: beforeTokens=%d afterTokens=%d stages=%s "
            "coveredMessages=%d activeMessages=%d autoCompactAt=%d "
            "collapseCommitAt=%d collapseBlockingAt=%d budgetReclaimed=%d "
            "snipReclaimable=%d snipReclaimed=%d microReclaimed=%d",
            before_tokens,
            after_tokens,
            stages or ["none"],
            int(compaction_state.get("coveredMessageCount") or 0),
            len(active_workflow),
            limits["autoCompactAtTokens"],
            limits["collapseCommitAtTokens"],
            limits["collapseBlockingAtTokens"],
            budget_reclaimed,
            reclaimable,
            snip_reclaimed,
            micro_reclaimed,
        )
        return ContextProjection(
            messages=final_messages,
            compaction_state=compaction_state,
            stats={
                "beforeTokens": before_tokens,
                "afterTokens": after_tokens,
                "stages": stages,
                "toolResultsTrimmed": budget_trimmed,
                "microCompactedRounds": micro_rounds,
                "budgetReclaimedTokens": budget_reclaimed,
                "snipReclaimableTokens": reclaimable,
                "snipReclaimedTokens": snip_reclaimed,
                "microReclaimedTokens": micro_reclaimed,
                **limits,
                "updated": boundary_updated,
            },
        )

    def _limits(self) -> dict[str, int]:
        """计算 cc-haha 风格的绝对余量阈值。

        max_context_size 在本项目中表示允许发送的输入窗口。大模型最大输出量目前
        没有可靠的模型元数据，因此用 20K 上限并对小窗口做安全收窄；关键点是所有
        后续判断都使用算出的绝对 Token 阈值，不再各自维护百分比。
        """
        window = self.settings.max_context_size
        summary_reserve = min(
            self.MAX_SUMMARY_OUTPUT_RESERVE,
            max(256, window // 10),
        )
        safety_buffer = min(
            self.AUTOCOMPACT_BUFFER_TOKENS,
            max(256, window // 10),
        )
        effective_window = max(1, window - summary_reserve)
        auto_at = max(1, effective_window - safety_buffer)
        return {
            "summaryOutputReserveTokens": summary_reserve,
            "safetyBufferTokens": safety_buffer,
            "autoCompactAtTokens": auto_at,
            "collapseCommitAtTokens": max(
                1, int(effective_window * self.COLLAPSE_COMMIT_RATIO)
            ),
            "collapseBlockingAtTokens": max(
                1, int(effective_window * self.COLLAPSE_BLOCKING_RATIO)
            ),
        }

    def _enforce_tool_result_budget(
        self,
        messages: list[Any],
        *,
        system: str,
        conversation_messages: list[dict[str, str]],
        current_message: dict[str, str],
        tools: list[dict[str, Any]],
        request_limit: int,
    ) -> tuple[list[Any], int, int]:
        tool_messages = [
            message for message in messages if isinstance(message, ToolMessage)
        ]
        if not tool_messages:
            return messages, 0, 0
        total = sum(
            estimate_tokens(str(message.content or "")) for message in tool_messages
        )
        empty_tools = [
            _copy_tool_message(message, "") if isinstance(message, ToolMessage) else message
            for message in messages
        ]
        fixed_tokens = _request_tokens(
            system,
            [*conversation_messages, *empty_tools, current_message],
            tools=[],
        ) + estimate_tokens(json.dumps(tools, ensure_ascii=False, default=str))
        budget = min(
            self.MAX_TOOL_RESULT_TOKENS,
            max(64, request_limit - fixed_tokens),
        )
        if total <= budget:
            return messages, 0, 0
        per_tool = max(32, budget // len(tool_messages))
        changed = 0
        projected: list[Any] = []
        for message in messages:
            if not isinstance(message, ToolMessage):
                projected.append(message)
                continue
            content = trim_tool_content(str(message.content or ""), per_tool)
            changed += int(content != message.content)
            projected.append(_copy_tool_message(message, content))
        remaining = sum(
            estimate_tokens(str(message.content or ""))
            for message in projected
            if isinstance(message, ToolMessage)
        )
        return projected, changed, max(0, total - remaining)

    def _snip(self, messages: list[Any]) -> tuple[list[Any], int, int]:
        target = self.SNIPPED_TOOL_TOKENS
        latest_round_ids = _latest_tool_round_ids(messages)
        changed = 0
        reclaimed = 0
        projected: list[Any] = []
        for message in messages:
            if (
                not isinstance(message, ToolMessage)
                or message.tool_call_id in latest_round_ids
            ):
                projected.append(message)
                continue
            before = estimate_tokens(str(message.content or ""))
            content = snip_tool_content(str(message.content or ""), target)
            changed += int(content != message.content)
            reclaimed += max(0, before - estimate_tokens(content))
            projected.append(_copy_tool_message(message, content))
        return projected, changed, reclaimed

    async def _summarize(
        self,
        *,
        mode: str,
        existing_summary: Any,
        messages: list[Any],
        current_message: dict[str, str],
    ) -> tuple[str, int]:
        groups = _group_messages_for_summary(messages)
        dropped = 0
        for attempt in range(self.MAX_SUMMARY_RETRIES + 1):
            wire = [
                _message_for_summary(message)
                for group in groups
                for message in group
            ]
            payload = {
                "mode": mode,
                "existingSummary": existing_summary or {},
                "messages": wire,
                "currentRequest": current_message.get("content", ""),
                "droppedOldestRounds": dropped,
                "warning": (
                    f"摘要请求过长，最旧的 {dropped} 个 API Round 未进入本次摘要输入；"
                    "完整轨迹仍在持久化存储中。"
                    if dropped
                    else ""
                ),
            }
            serialized = json.dumps(payload, ensure_ascii=False, default=str)
            summary_input_limit = max(
                1,
                self.settings.max_context_size
                - self._limits()["summaryOutputReserveTokens"]
                - self.SUMMARY_INPUT_HEADROOM_TOKENS,
            )
            if estimate_tokens(serialized) <= summary_input_limit:
                summary = (
                    await self.llm.complete(
                        RUN_CONTEXT_COMPACTION_SYSTEM,
                        serialized,
                    )
                ).strip()
                if not summary:
                    raise InvalidOperationError("运行上下文压缩器返回了空摘要。")
                return summary, dropped
            if attempt >= self.MAX_SUMMARY_RETRIES or len(groups) <= 1:
                raise InvalidOperationError(
                    "上下文压缩请求自身超过摘要输入预算，无法在不丢失全部运行轨迹的情况下继续。"
                )
            # 与 cc-haha 的 PTL retry 一致，按完整 API Round 从头移除。
            remove_count = max(1, len(groups) // 5)
            groups = groups[remove_count:]
            dropped += remove_count
            logger.warning(
                "context summary input trimmed for retry: mode=%s attempt=%d "
                "droppedOldestRounds=%d remainingRounds=%d",
                mode,
                attempt + 1,
                dropped,
                len(groups),
            )
        raise AssertionError("unreachable")

    @staticmethod
    def _next_state(
        previous: dict[str, Any],
        *,
        mode: str,
        summary: str,
        covered_message_count: int,
        before_tokens: int,
        dropped_rounds: int,
        stages: list[str],
    ) -> dict[str, Any]:
        return {
            "mode": mode,
            "sequence": int(previous.get("sequence") or 0) + 1,
            "summary": summary,
            "conversationCompacted": bool(previous.get("conversationCompacted"))
            or mode in {"auto", "reactive"},
            "coveredMessageCount": covered_message_count,
            "beforeTokens": before_tokens,
            "afterTokens": 0,
            "droppedOldestRounds": dropped_rounds,
            "stages": stages,
        }


def _copy_tool_message(message: ToolMessage, content: str) -> ToolMessage:
    return ToolMessage(
        content=content,
        tool_call_id=message.tool_call_id,
        id=message.id,
        name=getattr(message, "name", None),
        status=getattr(message, "status", "success"),
        artifact=getattr(message, "artifact", None),
    )


def _summary_message(state: dict[str, Any]) -> dict[str, Any] | None:
    summary = state.get("summary")
    if not summary:
        return None
    sequence = int(state.get("sequence") or 0)
    summary_text = (
        summary
        if isinstance(summary, str)
        else json.dumps(summary, ensure_ascii=False, default=str)
    )
    return {
        "role": "user",
        "content": (
            f"运行上下文摘要（序号 {sequence}，模式 {state.get('mode', 'collapse')}）：\n"
            f"{summary_text}"
        ),
        # 仅供本地压缩器识别摘要边界；发送给模型时会被消息规范化逻辑移除。
        "_context_summary": True,
    }


def _without_context_summary(messages: list[Any]) -> list[Any]:
    """已有摘要通过 existingSummary 单独传入，避免再次作为消息重复总结。"""
    return [message for message in messages if not _is_context_summary(message)]


def _is_context_summary(message: Any) -> bool:
    return isinstance(message, dict) and message.get("_context_summary") is True


def _request_tokens(
    system: str,
    messages: list[Any],
    tools: list[dict[str, Any]],
) -> int:
    return (
        estimate_tokens(system)
        + sum(message_tokens(_message_for_wire(message)) for message in messages)
        + estimate_tokens(json.dumps(tools, ensure_ascii=False, default=str))
    )


def _message_for_wire(message: Any) -> dict[str, Any]:
    if isinstance(message, dict):
        return dict(message)
    if isinstance(message, AIMessage):
        return {
            "role": "assistant",
            "content": str(message.content or ""),
            "tool_calls": [
                {"id": call["id"], "name": call["name"], "args": call["args"]}
                for call in message.tool_calls
            ],
        }
    if isinstance(message, ToolMessage):
        return {
            "role": "tool",
            "content": str(message.content or ""),
            "tool_call_id": message.tool_call_id,
        }
    raise TypeError(f"不支持的上下文消息类型：{type(message).__name__}")


def _message_for_summary(message: Any) -> dict[str, Any]:
    wire = _message_for_wire(message)
    if wire.get("role") == "tool":
        try:
            content = json.loads(str(wire.get("content") or "{}"))
        except json.JSONDecodeError:
            content = {"summary": str(wire.get("content") or "")}
        wire["content"] = content
    return wire


def _group_messages_for_summary(messages: list[Any]) -> list[list[Any]]:
    """按 API Round 分组，重试裁剪时绝不拆开 AI tool_calls 与结果。"""
    groups: list[list[Any]] = []
    index = 0
    while index < len(messages):
        message = messages[index]
        group = [message]
        index += 1
        if isinstance(message, AIMessage) and message.tool_calls:
            while index < len(messages) and isinstance(messages[index], ToolMessage):
                group.append(messages[index])
                index += 1
        groups.append(group)
    return groups


def _compact_current_message(message: dict[str, str]) -> dict[str, str]:
    """全量压缩后只重新注入当前任务控制信息和外部结果引用。"""
    try:
        payload = json.loads(message.get("content", ""))
    except json.JSONDecodeError:
        return message
    if not isinstance(payload, dict):
        return message
    memory = payload.get("memory") if isinstance(payload.get("memory"), dict) else {}
    payload["memory"] = {
        "summary": "",
        "relatedMessages": [],
        "longTermMemories": memory.get("longTermMemories", []),
    }
    active = payload.get("activeResult")
    if isinstance(active, dict):
        payload["activeResult"] = {
            key: active[key]
            for key in (
                "datasetId",
                "sql",
                "columns",
                "rowCount",
                "returnedRows",
                "hasMore",
                "truncated",
            )
            if key in active
        }
    return {
        "role": "user",
        "content": json.dumps(payload, ensure_ascii=False, default=str),
    }


def _latest_tool_round_ids(messages: list[Any]) -> set[str]:
    """返回最后一个完整工具轮次的 call id，Snip 不裁剪该轮。"""
    latest: set[str] = set()
    for message in messages:
        if isinstance(message, AIMessage) and message.tool_calls:
            latest = {str(call["id"]) for call in message.tool_calls}
    return latest


def _reclaimable_tool_tokens(
    messages: list[Any],
    *,
    target_tokens: int,
) -> int:
    """估算旧工具结果降级为目录后能释放多少 Token。"""
    latest_round_ids = _latest_tool_round_ids(messages)
    reclaimable = 0
    for message in messages:
        if (
            not isinstance(message, ToolMessage)
            or message.tool_call_id in latest_round_ids
        ):
            continue
        content = str(message.content or "")
        compacted = snip_tool_content(content, target_tokens)
        reclaimable += max(
            0,
            estimate_tokens(content) - estimate_tokens(compacted),
        )
    return reclaimable


def _micro_compact_rounds(messages: list[Any]) -> tuple[list[Any], int]:
    """把完整 AI tool_calls + ToolMessage 组替换为一条确定性目录摘要。"""
    projected: list[Any] = []
    compacted = 0
    index = 0
    while index < len(messages):
        message = messages[index]
        if not isinstance(message, AIMessage) or not message.tool_calls:
            projected.append(message)
            index += 1
            continue
        expected = {call["id"] for call in message.tool_calls}
        cursor = index + 1
        results: list[ToolMessage] = []
        while cursor < len(messages) and isinstance(messages[cursor], ToolMessage):
            results.append(messages[cursor])
            cursor += 1
        if expected != {result.tool_call_id for result in results}:
            projected.append(message)
            index += 1
            continue
        summaries = []
        for result in results:
            try:
                value = json.loads(str(result.content or "{}"))
            except json.JSONDecodeError:
                value = {"summary": str(result.content or "")}
            summaries.append(
                {
                    key: value.get(key)
                    for key in (
                        "tool",
                        "ok",
                        "summary",
                        "error",
                        "stats",
                        "resultRef",
                        "nextCursor",
                        "availableActions",
                        "datasetId",
                        "rowCount",
                    )
                    if value.get(key) is not None
                }
            )
        projected.append(
            {
                # 这是 Agent 自己已完成的执行轨迹，不是用户的新指令。
                "role": "assistant",
                "content": (
                    "已完成的工具执行记录：\n"
                    + json.dumps(
                        {
                            "assistantNarration": str(message.content or ""),
                            "calls": [
                                {"id": call["id"], "name": call["name"], "args": call["args"]}
                                for call in message.tool_calls
                            ],
                            "results": summaries,
                        },
                        ensure_ascii=False,
                        default=str,
                    )
                ),
            }
        )
        compacted += 1
        index = cursor
    return projected, compacted
