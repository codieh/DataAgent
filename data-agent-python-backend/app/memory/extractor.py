"""长期记忆抽取器（LongTermMemoryExtractor）。

职责：在每轮对话后，借助 LLM 从用户与助手消息中识别值得长期保留的事实（upsert）
或应删除的记忆（delete），并以确定性策略落库，最后同步到检索索引。

设计要点：
- 抽取开关受 settings.memory_extraction_enabled 控制，关闭时直接返回空统计。
- 仅保留近 memory_extraction_max_existing 条已有记忆作为去重 / 更新的上下文。
- 确定性校验：key 归一化、去重、最低置信度过滤、空内容丢弃，避免脏数据入库。
- 副作用：通过 provider 同步（sync）新增/更新项、删除（delete）失效项，并写审计日志。
"""

import json
import logging
from typing import Any

from app.config import Settings
from app.infrastructure.persistence.repository import Repository
from app.memory.provider import MemoryProvider
from app.workflow.outputs import MemoryExtractionOutput
from app.workflow.ports import LlmClient
from app.workflow.prompts import MEMORY_EXTRACTION_SYSTEM

logger = logging.getLogger(__name__)


class LongTermMemoryExtractor:
    """借助 LLM 抽取记忆候选，并施加确定性存储策略后落库。"""

    def __init__(self, settings: Settings, llm: LlmClient, provider: MemoryProvider):
        """初始化抽取器。

        Args:
            settings: 全局配置（抽取开关、最大已有条数、最小置信度等）。
            llm: LLM 客户端，用于生成记忆操作。
            provider: 记忆检索提供者，用于将变更同步到检索索引。
        """
        self.settings = settings
        self.llm = llm
        self.provider = provider

    async def extract_and_store(
        self,
        *,
        repository: Repository,
        conversation: Any,
        source_message_id: str,
        user_message: str,
        assistant_message: str,
    ) -> dict[str, int]:
        """抽取并存储本轮对话衍生的长期记忆。

        Args:
            repository: 持久化仓储，读取已有记忆并执行 upsert/delete。
            conversation: 当前会话（提供 id、datasource_id）。
            source_message_id: 触发本次抽取的消息 id（用于溯源）。
            user_message: 用户消息文本。
            assistant_message: 助手回复文本。

        Returns:
            统计字典：proposed（候选数）、upserted、deleted、rejected（被拒数）。
        """
        # 抽取功能关闭时直接短路，避免无谓的 LLM 调用
        if not self.settings.memory_extraction_enabled:
            return {"proposed": 0, "upserted": 0, "deleted": 0, "rejected": 0}
        # 仅取最近若干条非对话消息类记忆，作为去重 / 更新的上下文窗口
        existing = [
            item
            for item in await repository.list_memory_items(conversation.id)
            if item.kind != "conversation_message"
        ][-self.settings.memory_extraction_max_existing :]
        payload = {
            "userMessage": user_message,
            "assistantMessage": assistant_message,
            "existingMemories": [
                {
                    "key": (item.metadata_json or {}).get("memoryKey", ""),
                    "kind": item.kind,
                    "content": item.content,
                }
                for item in existing
            ],
        }
        # 交由 LLM 产出结构化的记忆操作列表（upsert / delete）
        result = await self.llm.complete_model(
            MemoryExtractionOutput,
            MEMORY_EXTRACTION_SYSTEM,
            json.dumps(payload, ensure_ascii=False),
        )
        stats = {"proposed": len(result.operations), "upserted": 0, "deleted": 0, "rejected": 0}
        changed = []
        deleted_ids = []
        seen_keys = set()
        for operation in result.operations:
            # 归一化 key（小写、截断）与 content（截断），统一存储形态
            key = operation.key.strip().lower()[:100]
            content = operation.content.strip()[:1000]
            # 确定性拒绝：空 key、重复 key、置信度不足、upsert 但内容为空
            if (
                not key
                or key in seen_keys
                or operation.confidence < self.settings.memory_extraction_min_confidence
                or (operation.action == "upsert" and not content)
            ):
                stats["rejected"] += 1
                continue
            seen_keys.add(key)
            # 由仓储执行实际的长期记忆 upsert/delete，返回变更项与删除项 id
            item, deleted_id = await repository.apply_long_term_memory(
                conversation_id=conversation.id,
                datasource_id=conversation.datasource_id,
                source_message_id=source_message_id,
                action=operation.action,
                key=key,
                kind=operation.kind,
                content=content,
                confidence=min(1.0, max(0.0, operation.confidence)),
            )
            if item is not None:
                changed.append(item)
                stats["upserted"] += 1
            if deleted_id is not None:
                deleted_ids.append(deleted_id)
                stats["deleted"] += 1
        # 将变更同步到检索索引（新增/更新与删除分别处理）
        await self.provider.sync(changed)
        await self.provider.delete(deleted_ids)
        logger.info(
            "long-term memory updated: conversationId=%s proposed=%d upserted=%d deleted=%d rejected=%d",
            conversation.id,
            stats["proposed"],
            stats["upserted"],
            stats["deleted"],
            stats["rejected"],
        )
        return stats
