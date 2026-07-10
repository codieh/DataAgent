"""对话摘要器（ConversationSummarizer）。

职责：在上下文 token 预算接近上限（memory_context_token_budget * 阈值）时，将
较早且完整的对话消息压缩为持久化摘要，从而「腾出」预算容纳最新对话。

设计要点：
- 压力指标 = 现有摘要 token + 尚未摘要消息的 token 之和。
- 达到 compact_at 阈值才触发；保留最近一段（preserve_ratio）作为原文对话。
- 仅归档「旧且完整」的消息，最近若干条始终以原文保留以保证连贯性。
- 副作用：通过 repository.save_conversation_summary 更新摘要与游标，并写审计日志。
"""

import json
import logging
from typing import Any

from app.config import Settings
from app.infrastructure.persistence.repository import Repository
from app.context import estimate_tokens, truncate_to_tokens
from app.workflow.outputs import ConversationSummaryOutput
from app.workflow.ports import LlmClient
from app.workflow.prompts import CONVERSATION_SUMMARY_SYSTEM

logger = logging.getLogger(__name__)


class ConversationSummarizer:
    """当会话上下文预算吃紧时，持久化压缩历史对话为摘要。"""

    def __init__(self, settings: Settings, llm: LlmClient):
        """初始化摘要器。

        Args:
            settings: 全局配置（预算、压缩阈值、保留比例等）。
            llm: LLM 客户端，用于生成压缩摘要。
        """
        self.settings = settings
        self.llm = llm

    async def maybe_summarize(
        self,
        *,
        repository: Repository,
        conversation: Any,
        messages: list[Any],
        current_message_id: str | None,
    ) -> dict[str, Any]:
        """在压力达到阈值时压缩历史消息。

        Args:
            repository: 持久化仓储，读取摘要状态并保存新摘要。
            conversation: 当前会话（含 id、summary）。
            messages: 会话全部消息。
            current_message_id: 正在处理的消息 id，从待压缩集合中排除。

        Returns:
            统计字典：updated / archivedCount / archivedTokens，以及诊断用的
            pressureTokens（当前压力）与 compactAtTokens（触发阈值）。
        """
        # 排除当前正在处理的消息，避免把「正在回复的内容」也计入可压缩历史
        eligible = [message for message in messages if message.id != current_message_id]
        if not eligible:
            return {"updated": False, "archivedCount": 0, "archivedTokens": 0}
        state = await repository.get_summary_state(conversation.id)
        # 仅考虑游标之后的未摘要消息
        unsummarized = _after_cursor(eligible, state)
        summary_tokens = estimate_tokens(conversation.summary or "") if conversation.summary else 0
        # 压力 = 现有摘要 token + 未摘要消息 token
        pressure_tokens = summary_tokens + sum(estimate_tokens(message.content) for message in unsummarized)
        # 触发阈值 = 总预算 * 压缩阈值
        compact_at = int(
            self.settings.memory_context_token_budget * self.settings.context_compact_threshold
        )
        base_stats = {
            "updated": False,
            "archivedCount": 0,
            "archivedTokens": 0,
            "pressureTokens": pressure_tokens,
            "compactAtTokens": compact_at,
        }
        # 压力未达阈值时不压缩，直接返回
        if pressure_tokens < compact_at:
            return base_stats

        # 压力达阈值后：保留最近一段作为原文对话，仅将更早的完整消息合并进 SQLite 摘要
        preserve_budget = max(
            1,
            int(
                self.settings.memory_context_token_budget
                * self.settings.context_compact_preserve_ratio
            ),
        )
        # 最近若干条消息（在保留预算内）始终以原文保留
        recent_ids = self._recent_message_ids(unsummarized, preserve_budget)
        # 其余较早消息进入待归档集合
        archive = [message for message in unsummarized if message.id not in recent_ids]
        archived_tokens = sum(estimate_tokens(message.content) for message in archive)
        if not archive:
            return base_stats
        payload = {
            "existingSummary": conversation.summary or "",
            "archivedMessages": [
                {"role": message.role, "content": message.content, "createdAt": message.created_at.isoformat()}
                for message in archive
            ],
        }
        # 调用 LLM 生成新的合并摘要
        result = await self.llm.complete_model(
            ConversationSummaryOutput,
            CONVERSATION_SUMMARY_SYSTEM,
            json.dumps(payload, ensure_ascii=False),
        )
        summary = truncate_to_tokens(result.summary.strip(), self.settings.memory_summary_token_budget)
        # LLM 未产出有效摘要时，仍记录归档量，但不更新摘要游标
        if not summary:
            return {**base_stats, "archivedCount": len(archive), "archivedTokens": archived_tokens}
        # 累计已摘要消息数，并以最后一条归档消息作为新游标
        total = (state.summarized_message_count if state else 0) + len(archive)
        await repository.save_conversation_summary(
            conversation=conversation,
            summary=summary,
            last_message_id=archive[-1].id,
            summarized_message_count=total,
        )
        logger.info(
            "conversation summary updated: conversationId=%s archivedMessages=%d archivedTokens=%d total=%d",
            conversation.id,
            len(archive),
            archived_tokens,
            total,
        )
        return {
            **base_stats,
            "updated": True,
            "archivedCount": len(archive),
            "archivedTokens": archived_tokens,
        }

    @staticmethod
    def _recent_message_ids(messages: list[Any], budget: int) -> set[str]:
        """从最新消息向前贪心选取，累计 token 不超过 budget，返回其 id 集合。"""
        selected = set()
        used = 0
        for message in reversed(messages):
            cost = estimate_tokens(message.content)
            # 已选若干后若加入会超预算则停止（保证至少保留当前消息）
            if selected and used + cost > budget:
                break
            selected.add(message.id)
            used += cost
        return selected


def _after_cursor(messages: list[Any], state: Any | None) -> list[Any]:
    """返回摘要游标之后的消息，避免再次处理已被摘要覆盖的内容。"""
    if state is None or not state.last_message_id:
        return messages
    cursor_index = next(
        (index for index, message in enumerate(messages) if message.id == state.last_message_id),
        None,
    )
    return messages if cursor_index is None else messages[cursor_index + 1 :]
