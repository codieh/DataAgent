"""会话上下文构建器（ContextBuilder）。

职责：在每次请求中，将「持久化的原始消息 + 已压缩的对话摘要 + 可选的长期记忆」
组装成一份受 token 预算约束的模型上下文，避免无限累积历史导致上下文溢出。

设计要点：
- 摘要优先：先尝试全量压缩游标之后的历史（若注入 summarizer），未触发压缩时
  才把尚未摘要的消息作为原始上下文。
- 预算分配：只使用 max_context_size 总预算，先扣除摘要占用，剩余给尚未摘要的消息。
- 已摘要消息不重复纳入原始消息（由 unsummarized_messages 过滤），避免信息重复。
- 当前正在处理的消息（current_message_id）从上下文消息列表中排除，防止自指。
"""

import re
from typing import Any

from app.config import Settings
from app.context import estimate_tokens, truncate_to_tokens
from app.infrastructure.persistence.repository import Repository
from app.memory.provider import MemoryProvider


class ContextBuilder:
    """基于持久化消息与已召回记忆，构建受预算约束的模型上下文。"""

    def __init__(self, settings: Settings, provider: MemoryProvider, summarizer: Any | None = None):
        """初始化上下文构建器。

        Args:
            settings: 全局配置（预算、token 估算相关）。
            provider: 记忆检索提供者（当前上下文构建未直接用于检索，保留以便扩展）。
            summarizer: 可选的历史摘要器；为 None 时跳过摘要压缩步骤。
        """
        self.settings = settings
        self.provider = provider
        self.summarizer = summarizer

    async def build(
        self, *, repository: Repository, conversation: Any, current_message_id: str | None, query: str
    ) -> dict[str, Any]:
        """构建本次请求使用的模型上下文。

        Args:
            repository: 持久化仓储，用于读取消息与摘要状态。
            conversation: 当前会话对象（含 id、summary 等）。
            current_message_id: 正在处理的消息 id；从上下文列表中排除，避免自指。
            query: 用户查询（此处暂未用于检索，预留接口）。

        Returns:
            包含 summary / recentMessages / longTermMemories / stats 等键的上下文字典。
            其中 stats 汇报消息计数、token 估算与各预算上限，便于上游做可观测性统计。
        """
        messages = await repository.list_messages(conversation.id)
        # System 消息是会话级核心记忆，不属于可摘要的对话历史。将其单独投影到
        # memory 区，避免成为第二条 System Prompt 覆盖 Agent 身份。
        core_memories = [
            _plain_memory_text(message.content)
            for message in messages
            if str(getattr(message, "role", "")) == "system" and message.content
        ]
        dialogue_messages = [
            message
            for message in messages
            if str(getattr(message, "role", "")) in {"user", "assistant"}
        ]
        # 排除正在处理的当前消息，避免其被当作历史上下文再次输入
        context_messages = [
            message for message in dialogue_messages if message.id != current_message_id
        ]
        summary_stats = {"updated": False, "archivedCount": 0, "archivedTokens": 0}
        if self.summarizer is not None:
            # 在预算吃紧时压缩历史对话，返回摘要更新统计
            summary_stats = await self.summarizer.maybe_summarize(
                repository=repository,
                conversation=conversation,
                messages=dialogue_messages,
                current_message_id=current_message_id,
            )
        summary_state = await repository.get_summary_state(conversation.id)
        # 仅保留未被摘要覆盖的后续消息，避免与摘要内容重复
        active_messages = unsummarized_messages(context_messages, summary_state)
        summary = truncate_to_tokens(
            conversation.summary or "",
            max(1, int(self.settings.max_context_size * self.settings.context_compact_preserve_ratio)),
        )
        summary_tokens = estimate_tokens(summary) if summary else 0
        # 总预算中先扣除摘要占用，剩余额度给尚未触发下一次压缩的原始消息。
        recent_budget = max(0, self.settings.max_context_size - summary_tokens)
        recent, _, recent_tokens = self._recent(active_messages, recent_budget)
        used_tokens = summary_tokens + recent_tokens
        return {
            "summary": summary,
            "recentMessages": recent,
            "relatedMessages": [],
            "longTermMemories": core_memories,
            "stats": {
                "messageCount": len(dialogue_messages),
                "recentCount": len(recent),
                "retrievedMessageCount": 0,
                "longTermMemoryCount": len(core_memories),
                "retrievedCount": 0,
                "estimatedTokens": used_tokens,
                "summaryUpdated": summary_stats["updated"],
                "summarizedMessages": summary_stats["archivedCount"],
                "retentionDeleted": 0,
                "budgets": {
                    "totalContext": self.settings.max_context_size,
                },
            },
        }

    def _recent(self, items: list[Any], budget: int | None = None) -> tuple[list[dict[str, Any]], set[str], int]:
        """从尾部（最新）向前贪心选取消息，直到超出 token 预算。

        Args:
            items: 候选消息列表（按时间顺序排列）。
            budget: 可选 token 预算；缺省时使用 max_context_size。

        Returns:
            (选中的消息字典列表, 选中消息 id 集合, 已用 token 数)。
            字典含 id / role / content / createdAt，供模型上下文直接使用。
        """
        selected = []
        used = 0
        budget = self.settings.max_context_size if budget is None else max(0, budget)
        # 从最新消息向前遍历，优先保留近期对话
        for item in reversed(items):
            cost = estimate_tokens(item.content)
            # 已选若干后若加入会超预算，则停止（保证至少能容纳当前消息）
            if selected and used + cost > budget:
                break
            # 首条即超预算时跳过该消息，继续向前寻找更小的消息
            if not selected and cost > budget:
                continue
            selected.append(
                {
                    "id": item.id,
                    "role": getattr(item, "role", None) or (getattr(item, "metadata_json", None) or {}).get("role", ""),
                    "content": item.content,
                    "createdAt": item.created_at.isoformat(),
                }
            )
            used += cost
        # 还原为时间正序，符合对话自然顺序
        selected.reverse()
        return selected, {item["id"] for item in selected}, used


def _fit_budget(items: list[dict[str, Any]], budget: int) -> list[dict[str, Any]]:
    """按 token 预算从前向后贪心裁剪消息列表（超预算者丢弃）。"""
    selected = []
    used = 0
    for item in items:
        cost = estimate_tokens(item["content"])
        if used + cost > budget:
            continue
        selected.append(item)
        used += cost
    return selected


def unsummarized_messages(messages: list[Any], summary_state: Any | None) -> list[Any]:
    """排除已被持久化对话摘要所覆盖的原始消息。

    通过摘要游标 summary_state.last_message_id 定位截止点，仅返回其后的消息，
    从而避免摘要内容与近期原始消息重复占用上下文。
    """
    if summary_state is None or not summary_state.last_message_id:
        return messages
    cursor_index = next(
        (index for index, message in enumerate(messages) if message.id == summary_state.last_message_id),
        None,
    )
    return messages if cursor_index is None else messages[cursor_index + 1 :]


def _plain_memory_text(content: str) -> str:
    """兼容旧数据：移除历史版本保存的单层 XML 包装，不改动记忆正文。"""
    text = str(content).strip()
    text = re.sub(r"^<[^>]+>\s*", "", text, count=1)
    text = re.sub(r"\s*</[^>]+>$", "", text, count=1)
    return text.strip()
