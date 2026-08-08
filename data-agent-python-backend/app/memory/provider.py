"""记忆检索提供者（MemoryProvider）。

职责：在 SQLite（事实来源）之外，可选地维护一个 Chroma 向量集合，用于长期记忆的
语义检索；未配置 chroma 时退化为基于字符集合重叠的词汇检索。

设计要点：
- 仅当 memory_backend 与 retrieval_backend 同时为 chroma 时才初始化向量集合。
- sync / delete / search 等 IO 操作通过 asyncio.to_thread 避免阻塞事件循环。
- 综合打分公式：score = 0.7*相似度 + 0.2*时效 + 0.1*重要性，兼顾相关性与新鲜度。
- _lexical_search 作为无向量后端时的兜底召回。
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from app.config import Settings

logger = logging.getLogger(__name__)


class MemoryProvider:
    """为记忆建立检索索引（可选 Chroma 向量），同时以 SQLite 为事实来源。"""

    def __init__(self, settings: Settings):
        """初始化记忆提供者。

        Args:
            settings: 全局配置（决定后端类型与集合参数）。
        """
        self.settings = settings
        self.collection = None
        # 仅当两个后端均为 chroma 时才启用向量检索，否则后续退化为词汇检索
        if settings.memory_backend == "chroma" and settings.retrieval_backend == "chroma":
            self.collection = self._initialize_chroma()

    def _initialize_chroma(self):
        """懒加载并创建 Chroma 持久化集合（embedding 函数与余弦距离）。"""
        import chromadb
        from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

        self.settings.chroma_path.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=str(self.settings.chroma_path))
        embedding = OpenAIEmbeddingFunction(
            api_key=self.settings.embedding_api_key,
            api_base=self.settings.embedding_api_base,
            model_name=self.settings.embedding_model,
        )
        return client.get_or_create_collection(
            name=self.settings.memory_chroma_collection_name,
            embedding_function=embedding,
            metadata={"hnsw:space": "cosine", "embedding:model": self.settings.embedding_model},
        )

    async def sync(self, items: list[Any]) -> None:
        """将记忆项增量同步（upsert）进向量索引。空集合或未启用时直接返回。"""
        if self.collection is None or not items:
            return
        await asyncio.to_thread(self._sync, items)

    async def delete(self, ids: list[str]) -> None:
        """从向量索引中删除指定 id 的记忆项。"""
        if self.collection is not None and ids:
            await asyncio.to_thread(self.collection.delete, ids=ids)

    def _sync(self, items: list[Any]) -> None:
        """真正执行 upsert 的同步逻辑：将内容、会话与重要性等写入元数据。"""
        self.collection.upsert(
            ids=[item.id for item in items],
            documents=[item.content for item in items],
            metadatas=[
                {
                    "conversation_id": item.conversation_id,
                    "kind": item.kind,
                    "source_message_id": item.source_message_id or "",
                    "importance": float(item.importance),
                    "created_at": item.created_at.isoformat(),
                }
                for item in items
            ],
        )

    async def search(
        self, *, query: str, conversation_id: str, items: list[Any], excluded_ids: set[str], top_k: int
    ) -> list[dict[str, Any]]:
        """检索与查询相关的记忆。

        Args:
            query: 查询文本。
            conversation_id: 限定检索的会话范围。
            items: 候选记忆项（通常为同会话全部记忆）。
            excluded_ids: 需排除的 id（如已出现在上下文中的消息）。
            top_k: 期望返回的条数。

        Returns:
            按综合得分降序排列的结果字典列表。
        """
        # 先按 excluded_ids 过滤候选，避免召回已在上下文中的内容
        candidates = [item for item in items if item.id not in excluded_ids]
        if not candidates or top_k <= 0:
            return []
        # 无向量后端时退化为词汇检索
        if self.collection is None:
            return self._lexical_search(query, candidates, top_k)
        await self.sync(candidates)
        return await asyncio.to_thread(self._vector_search, query, conversation_id, candidates, top_k)

    def _vector_search(
        self, query: str, conversation_id: str, candidates: list[Any], top_k: int
    ) -> list[dict[str, Any]]:
        """在向量集合中按会话与类型过滤后，做相似度检索并综合打分。"""
        by_id = {item.id: item for item in candidates}
        # 仅检索候选中实际存在的类型，避免空 kind 过滤
        kinds = sorted({item.kind for item in candidates})
        # 多取 top_k*3 以提升召回，再在统一打分后截断
        result = self.collection.query(
            query_texts=[query],
            n_results=min(len(candidates), max(top_k * 3, top_k)),
            where={
                "$and": [
                    {"conversation_id": conversation_id},
                    {"kind": {"$in": kinds}},
                ]
            },
            include=["distances"],
        )
        now = datetime.now(timezone.utc)
        ranked = []
        for memory_id, distance in zip(result.get("ids", [[]])[0], result.get("distances", [[]])[0], strict=False):
            item = by_id.get(memory_id)
            if item is None:
                continue
            # Chroma 返回 cosine 距离（0~2），这里转成 0~1 的相似度
            similarity = max(0.0, 1.0 - float(distance))
            # 低于阈值视为不相关，直接丢弃
            if similarity < self.settings.memory_retrieval_min_score:
                continue
            # 时效衰减：越新的记忆时效分越接近 1，以 30 天为半衰期尺度
            age_days = max(0.0, (now - _aware(item.created_at)).total_seconds() / 86400)
            recency = 1.0 / (1.0 + age_days / 30.0)
            # 综合打分：相似度为主，时效与重要性为辅
            score = 0.7 * similarity + 0.2 * recency + 0.1 * float(item.importance)
            ranked.append(_result(item, score))
        return sorted(ranked, key=lambda value: value["score"], reverse=True)[:top_k]

    @staticmethod
    def _lexical_search(query: str, candidates: list[Any], top_k: int) -> list[dict[str, Any]]:
        """无向量后端时的兜底召回：基于字符集合重叠的词汇匹配。"""
        query_terms = set(query.lower())
        ranked = []
        for item in candidates:
            overlap = len(query_terms & set(item.content.lower()))
            if overlap:
                # 得分归一化为重叠字符数占查询字符数的比例
                ranked.append(_result(item, overlap / max(1, len(query_terms))))
        return sorted(ranked, key=lambda value: value["score"], reverse=True)[:top_k]


def _result(item: Any, score: float) -> dict[str, Any]:
    """将记忆项与得分封装为统一的检索结果字典。"""
    return {
        "id": item.id,
        "kind": item.kind,
        "content": item.content,
        "role": (item.metadata_json or {}).get("role", ""),
        "score": round(score, 4),
        "createdAt": item.created_at.isoformat(),
    }


def _aware(value: datetime) -> datetime:
    """为无时区信息的 datetime 补上 UTC 时区，便于与时区感知时间做差值。"""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
